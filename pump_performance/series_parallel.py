"""Phase 3L: exactly two supplied piecewise-linear pump curves, bounded domains."""
from dataclasses import dataclass
import math

from .pump_curve import PumpCurve, create_pump_curve, interpolate_pump_head
from .operating_point import head_tolerance


@dataclass(frozen=True)
class CombinedPumps:
    configuration: str
    pump_mode: str
    pump_1: PumpCurve
    pump_2: PumpCurve
    combined: PumpCurve
    common_basis: str
    overlap_minimum: float
    overlap_maximum: float


def _si_curve(curve):
    # Revalidate via Phase 3E and keep an SI view to avoid unit round trips.
    return create_pump_curve([(p.flow_m3_s,p.head_m) for p in curve.points],
                             'm³/s','m',{'m³/s':1.0})


def _close_coordinate(a,b):
    return abs(a-b) <= 8 * max(math.ulp(a),math.ulp(b))


def _grid(values,minimum,maximum):
    if not minimum < maximum:
        raise ValueError('Valid overlap must have positive width; a single contact point is not a combined curve.')
    points=[minimum]
    for value in sorted(set(values)):
        if minimum < value < maximum and not _close_coordinate(value,points[-1]) and not _close_coordinate(value,maximum):
            points.append(value)
    points.append(maximum)
    if len(points)==2:
        # A common domain may lie wholly inside one segment of each pump.
        # The deterministic interpolated midpoint preserves that exact line and
        # supplies the three points required by the unchanged Phase 3G API.
        mid=minimum+(maximum-minimum)/2
        if not minimum < mid < maximum:
            raise ValueError('Overlap spacing exceeds the supported numeric range.')
        points.insert(1,mid)
    return points


def _head(curve,q):
    return interpolate_pump_head(curve,q).head_m


def _strictly_decreasing(curve):
    if any(a.head_m <= b.head_m for a,b in zip(curve.points,curve.points[1:])):
        raise ValueError('Parallel combination requires strictly decreasing head with increasing flow for unique head-to-flow inversion. Flat or non-monotonic curves are ambiguous; review vendor data. No branch is selected.')


def _flow_at_head(curve,head):
    # Local inverse of each strictly decreasing linear segment. This is the
    # parallel-specific inverse, not a second forward pump interpolation engine.
    for point in curve.points:
        if head==point.head_m:return point.flow_m3_s
    for a,b in zip(curve.points,curve.points[1:]):
        if b.head_m < head < a.head_m:
            weight=(a.head_m-head)/(a.head_m-b.head_m)
            q=a.flow_m3_s+weight*(b.flow_m3_s-a.flow_m3_s)
            if not a.flow_m3_s <= q <= b.flow_m3_s:
                raise ValueError('Inverse pump flow is outside its supplied segment.')
            checked=_head(curve,q)
            if abs(checked-head)>head_tolerance(checked,head):
                raise ValueError('Inverse pump interpolation exceeds the supported numeric range.')
            return q
    raise ValueError('Common head is outside the supplied pump range. Extrapolation is not performed.')


def _combined_curve(points):
    return create_pump_curve(points,'m³/s','m',{'m³/s':1.0})


def combine_series_curves(pump_curve_1,pump_curve_2):
    a,b=_si_curve(pump_curve_1),_si_curve(pump_curve_2)
    lower=max(a.points[0].flow_m3_s,b.points[0].flow_m3_s)
    upper=min(a.points[-1].flow_m3_s,b.points[-1].flow_m3_s)
    if lower>=upper:
        raise ValueError('No positive-width overlapping flow domain exists for series operation. Supply curves with a Valid Overlap Range; no extrapolation is performed.')
    grid=_grid([p.flow_m3_s for p in a.points+b.points],lower,upper)
    points=[(q,_head(a,q)+_head(b,q)) for q in grid]
    return CombinedPumps('Series','Different',a,b,_combined_curve(points),'flow_m3_s',lower,upper)


def combine_parallel_curves(pump_curve_1,pump_curve_2):
    a,b=_si_curve(pump_curve_1),_si_curve(pump_curve_2)
    _strictly_decreasing(a);_strictly_decreasing(b)
    lower=max(a.points[-1].head_m,b.points[-1].head_m)
    upper=min(a.points[0].head_m,b.points[0].head_m)
    if lower>=upper:
        raise ValueError('No positive-width overlapping head domain exists for parallel operation. Supply curves with a Valid Overlap Range; no extrapolation is performed.')
    grid=_grid([p.head_m for p in a.points+b.points],lower,upper)
    points=[(_flow_at_head(a,h)+_flow_at_head(b,h),h) for h in reversed(grid)]
    return CombinedPumps('Parallel','Different',a,b,_combined_curve(points),'head_m',lower,upper)


def combine_identical_series(pump_curve):
    a=_si_curve(pump_curve)
    combined=_combined_curve([(p.flow_m3_s,2*p.head_m) for p in a.points])
    return CombinedPumps('Series','Identical',a,a,combined,'flow_m3_s',a.points[0].flow_m3_s,a.points[-1].flow_m3_s)


def combine_identical_parallel(pump_curve):
    a=_si_curve(pump_curve)
    _strictly_decreasing(a)
    combined=_combined_curve([(2*p.flow_m3_s,p.head_m) for p in a.points])
    return CombinedPumps('Parallel','Identical',a,a,combined,'head_m',a.points[-1].head_m,a.points[0].head_m)
