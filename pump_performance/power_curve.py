"""Supplied shaft-power interpolation and numerical driver comparison, SI internally."""
from dataclasses import dataclass, replace
from bisect import bisect_left
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pump_head import finite_signed
from .pump_curve import curve_flow_to_si
from .pump_efficiency import power_to_watts
from .duty_point_check import calculate_driver_margin as _existing_driver_margin
from .hydraulic_power import hydraulic_power
from .shaft_power import shaft_power
from .efficiency_curve import interpolate_efficiency

OUT_OF_RANGE = 'Operating flow is outside the supplied vendor power-curve range; shaft power is not extrapolated.'


@dataclass(frozen=True)
class PowerPoint:
    flow_m3_s: float
    shaft_power_w: float


@dataclass(frozen=True)
class PowerCurve:
    points: tuple[PowerPoint, ...]


@dataclass(frozen=True)
class PowerInterpolationResult:
    flow_m3_s: float
    shaft_power_w: float
    exact_point: bool


@dataclass(frozen=True)
class MaximumPowerResult:
    shaft_power_w: float
    flows_m3_s: tuple[float, ...]


@dataclass(frozen=True)
class PowerComparisonResult:
    vendor_power_w: float
    calculated_power_w: float
    difference_w: float
    percent_difference: float | None
    efficiency_percent: float
    hydraulic_power_w: float


def create_power_curve(points, flow_unit, power_unit, flow_factors):
    if len(points) < 3:
        raise ValueError('Enter at least 3 unique vendor power-curve points.')
    converted = []
    for index, pair in enumerate(points, 1):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f'Point {index} must contain flow and shaft/brake power.')
        try:
            q = curve_flow_to_si(pair[0], flow_unit, flow_factors)
            p = power_to_watts(pair[1], power_unit, 'Vendor shaft/brake power', allow_zero=True)
        except ValueError as exc:
            raise ValueError(f'Point {index}: {exc}') from None
        converted.append(PowerPoint(q, p))
    converted.sort(key=lambda p: p.flow_m3_s)
    if any(a.flow_m3_s == b.flow_m3_s for a,b in zip(converted, converted[1:])):
        raise ValueError('Each vendor power-curve flow value must be unique.')
    return PowerCurve(tuple(converted))


def interpolate_power(curve, operating_flow_si):
    q = nonnegative(operating_flow_si, 'Operating flow')
    flows = [p.flow_m3_s for p in curve.points]
    # Match Phase 3M's endpoint convention: eight ULPs, no fixed absolute
    # tolerance that could admit physically meaningful extrapolation.
    def same(a,b):
        return abs(a-b) <= 8 * max(math.ulp(a), math.ulp(b))
    if (q < flows[0] and not same(q, flows[0])) or (q > flows[-1] and not same(q, flows[-1])):
        raise ValueError(OUT_OF_RANGE)
    index = bisect_left(flows, q)
    for candidate in (index, index-1):
        if 0 <= candidate < len(flows) and same(q, flows[candidate]):
            return PowerInterpolationResult(q, curve.points[candidate].shaft_power_w, True)
    lower, upper = curve.points[index-1:index+1]
    weight = (q-lower.flow_m3_s)/(upper.flow_m3_s-lower.flow_m3_s)
    power = lower.shaft_power_w + weight*(upper.shaft_power_w-lower.shaft_power_w)
    if not math.isfinite(power) or power < 0:
        raise ValueError('Interpolated shaft power exceeds the supported numeric range.')
    return PowerInterpolationResult(q, power, False)


def find_maximum_supplied_power(curve):
    maximum = max(p.shaft_power_w for p in curve.points)
    return MaximumPowerResult(maximum, tuple(p.flow_m3_s for p in curve.points if p.shaft_power_w == maximum))


def calculate_driver_margin(shaft_power_w, driver_rating_w):
    result = _existing_driver_margin(shaft_power_w, driver_rating_w)
    # Reporting tolerance only, not an engineering allowance. Raw margins
    # retain full precision; criteria below always use the actual percentage.
    equal = math.isclose(result.driver_rating_w, result.shaft_power_w, rel_tol=1e-12, abs_tol=1e-9)
    relationship = 'equals' if equal else ('is above' if result.driver_rating_w > result.shaft_power_w else 'is below')
    return replace(result, relationship_status=f'Entered driver rating {relationship} interpolated shaft power.')


def compare_driver_margin(actual_margin_percent, required_margin_percent):
    required = nonnegative(required_margin_percent, 'User/Vendor/Project Required Driver Power Margin %')
    if actual_margin_percent is None:
        return 'N/A — shaft power is zero'
    actual = finite_signed(actual_margin_percent, 'Actual driver power margin (%)')
    return 'Meets entered driver power margin' if actual >= required else 'Does not meet entered driver power margin'


def compare_calculated_power(*, vendor_power_w, flow_si, density, density_unit,
                             head_m, density_factors, flow_factors,
                             efficiency_percent=None, efficiency_curve=None):
    if (efficiency_percent is None) == (efficiency_curve is None):
        raise ValueError('Supply either explicit pump efficiency or a vendor efficiency curve.')
    vendor = nonnegative(vendor_power_w, 'Vendor interpolated shaft power')
    q = curve_flow_to_si(flow_si, 'm³/s', flow_factors)
    eta = (interpolate_efficiency(efficiency_curve,q).efficiency_percent
           if efficiency_curve is not None else efficiency_percent)
    hydraulic = hydraulic_power(density=density,density_unit=density_unit,flow=q,flow_unit='m³/s',
                                head_m=head_m,density_factors=density_factors,flow_factors=flow_factors)
    shaft = shaft_power(hydraulic.watts,'W',eta)
    difference = shaft.shaft_watts-vendor
    percent = None if vendor == 0 else difference/vendor*100
    if not math.isfinite(difference) or (percent is not None and not math.isfinite(percent)):
        raise ValueError('Calculated power comparison exceeds the supported numeric range.')
    return PowerComparisonResult(vendor,shaft.shaft_watts,difference,percent,shaft.efficiency_percent,hydraulic.watts)
