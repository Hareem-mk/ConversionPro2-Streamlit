"""Vendor efficiency points in SI flow and percent; no curve fitting/extrapolation."""
from dataclasses import dataclass
from bisect import bisect_left
import math
from .pump_curve import curve_flow_to_si
from .shaft_power import pump_efficiency
from piping_hydraulics.pipe_capacity import nonnegative

OUT_OF_RANGE = 'Operating flow is outside the supplied efficiency-curve range; efficiency is not extrapolated.'


@dataclass(frozen=True)
class EfficiencyPoint:
    flow_m3_s: float
    efficiency_percent: float


@dataclass(frozen=True)
class EfficiencyCurve:
    points: tuple[EfficiencyPoint, ...]


@dataclass(frozen=True)
class EfficiencyInterpolationResult:
    flow_m3_s: float
    efficiency_percent: float
    exact_point: bool


@dataclass(frozen=True)
class PeakEfficiencyResult:
    efficiency_percent: float
    flows_m3_s: tuple[float, ...]


def create_efficiency_curve(points, flow_unit, flow_factors):
    if len(points) < 3:
        raise ValueError('Enter at least 3 unique vendor efficiency-curve points.')
    converted = []
    for index, pair in enumerate(points, 1):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f'Point {index} must contain flow and efficiency (%).')
        try:
            q = curve_flow_to_si(pair[0], flow_unit, flow_factors)
            percent, _ = pump_efficiency(pair[1])
        except ValueError as exc:
            raise ValueError(f'Point {index}: {exc}') from None
        converted.append(EfficiencyPoint(q, percent))
    converted.sort(key=lambda p: p.flow_m3_s)
    if any(a.flow_m3_s == b.flow_m3_s for a,b in zip(converted, converted[1:])):
        raise ValueError('Each efficiency-curve flow value must be unique.')
    return EfficiencyCurve(tuple(converted))


def interpolate_efficiency(curve, operating_flow_si):
    q = nonnegative(operating_flow_si, 'Operating flow')
    flows = [p.flow_m3_s for p in curve.points]
    # Eight ULPs of the compared values absorb conversion roundoff only; no
    # fixed absolute tolerance that could admit meaningful extrapolation.
    def same(a,b):
        return abs(a-b) <= 8 * max(math.ulp(a), math.ulp(b))
    if (q < flows[0] and not same(q, flows[0])) or (q > flows[-1] and not same(q, flows[-1])):
        raise ValueError(OUT_OF_RANGE)
    index = bisect_left(flows, q)
    for candidate in (index, index-1):
        if 0 <= candidate < len(flows) and same(q, flows[candidate]):
            p = curve.points[candidate]
            return EfficiencyInterpolationResult(q, p.efficiency_percent, True)
    lower, upper = curve.points[index-1:index+1]
    weight = (q-lower.flow_m3_s)/(upper.flow_m3_s-lower.flow_m3_s)
    percent = lower.efficiency_percent + weight*(upper.efficiency_percent-lower.efficiency_percent)
    pump_efficiency(percent)
    return EfficiencyInterpolationResult(q, percent, False)


def find_peak_supplied_efficiency(curve):
    maximum = max(p.efficiency_percent for p in curve.points)
    return PeakEfficiencyResult(maximum, tuple(p.flow_m3_s for p in curve.points if p.efficiency_percent == maximum))
