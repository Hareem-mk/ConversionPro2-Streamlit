"""Phase 3E: supplied Q–H data and in-range piecewise-linear interpolation."""
from dataclasses import dataclass
from bisect import bisect_left
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.units import flow_to_si

FT_PER_M = 3.280839895013123
HEAD_FACTORS = {'m': 1.0, 'ft': 1 / FT_PER_M}
OUT_OF_RANGE = 'Requested flow is outside the supplied pump-curve range. Extrapolation is not performed.'
RISING_HEAD_WARNING = ('Pump head normally decreases as flow increases for a conventional '
                       'centrifugal-pump Q–H curve. Review the entered/vendor data.')


@dataclass(frozen=True)
class CurvePoint:
    flow_m3_s: float
    head_m: float


@dataclass(frozen=True)
class PumpCurve:
    points: tuple[CurvePoint, ...]
    flow_unit: str
    head_unit: str
    flow_factor: float
    head_factor: float

    @property
    def has_rising_head(self):
        return any(b.head_m > a.head_m for a, b in zip(self.points, self.points[1:]))

    @property
    def shutoff_head_m(self):
        return self.points[0].head_m if self.points[0].flow_m3_s == 0 else None

    def display_points(self):
        return tuple((p.flow_m3_s / self.flow_factor, p.head_m / self.head_factor) for p in self.points)


@dataclass(frozen=True)
class InterpolatedHead:
    flow_m3_s: float
    head_m: float
    lower: CurvePoint
    upper: CurvePoint
    exact_point: bool


def curve_flow_to_si(value, unit, flow_factors):
    """Reuse the positive-flow adapter; allow a validated supplied zero-flow point."""
    q = nonnegative(value, 'Flow rate')
    if q == 0:
        if unit not in flow_factors:
            raise ValueError('Select a supported volumetric flow unit.')
        positive(flow_factors[unit], 'Flow conversion factor')
        return 0.0
    return flow_to_si(q, unit, flow_factors)


def create_pump_curve(points, flow_unit, head_unit, flow_factors):
    if flow_unit not in flow_factors:
        raise ValueError('Select a supported volumetric flow unit.')
    flow_factor = positive(flow_factors[flow_unit], 'Flow conversion factor')
    if head_unit not in HEAD_FACTORS:
        raise ValueError('Select a supported head unit: m or ft.')
    head_factor = HEAD_FACTORS[head_unit]
    if len(points) < 3:
        raise ValueError('Enter at least 3 valid unique Q–H points for a pump curve.')
    converted = []
    for index, pair in enumerate(points, 1):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f'Point {index} must contain both flow and head.')
        try:
            q = curve_flow_to_si(pair[0], flow_unit, flow_factors)
            head = nonnegative(pair[1], 'Pump head')
            h = head * head_factor
            if not math.isfinite(h) or (head > 0 and h == 0):
                raise ValueError('Converted head exceeds the supported numeric range.')
        except ValueError as exc:
            raise ValueError(f'Point {index}: {exc}') from None
        converted.append(CurvePoint(q, h))
    converted.sort(key=lambda point: point.flow_m3_s)
    if any(a.flow_m3_s == b.flow_m3_s for a, b in zip(converted, converted[1:])):
        raise ValueError('Each pump-curve flow value must be unique.')
    return PumpCurve(tuple(converted), flow_unit, head_unit, flow_factor, head_factor)


def interpolate_pump_head(curve, requested_flow):
    q = curve_flow_to_si(requested_flow, curve.flow_unit, {curve.flow_unit: curve.flow_factor})
    if q < curve.points[0].flow_m3_s or q > curve.points[-1].flow_m3_s:
        raise ValueError(OUT_OF_RANGE)
    index = bisect_left([p.flow_m3_s for p in curve.points], q)
    if curve.points[index].flow_m3_s == q:
        point = curve.points[index]
        # Return the stored supplied head directly; no interpolation drift.
        return InterpolatedHead(q, point.head_m, point, point, True)
    lower, upper = curve.points[index - 1], curve.points[index]
    weight = (q - lower.flow_m3_s) / (upper.flow_m3_s - lower.flow_m3_s)
    head = lower.head_m + (upper.head_m - lower.head_m) * weight
    if not math.isfinite(head) or head < 0:
        raise ValueError('Interpolated head exceeds the supported numeric range.')
    return InterpolatedHead(q, head, lower, upper, False)
