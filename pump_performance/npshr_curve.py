"""Supplied NPSHR points in SI flow/head; bounded piecewise-linear interpolation."""
from dataclasses import dataclass
from bisect import bisect_left
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pipe_geometry import positive
from .pump_curve import curve_flow_to_si
from .system_curve import head_to_metres

OUT_OF_RANGE = 'Operating flow is outside the supplied NPSHR-curve range; NPSHR is not extrapolated.'


@dataclass(frozen=True)
class NPSHRPoint:
    flow_m3_s: float
    npshr_m: float


@dataclass(frozen=True)
class NPSHRCurve:
    points: tuple[NPSHRPoint, ...]


@dataclass(frozen=True)
class NPSHRInterpolationResult:
    flow_m3_s: float
    npshr_m: float
    exact_point: bool


@dataclass(frozen=True)
class NPSHRExtremaResult:
    minimum_m: float
    minimum_flows_m3_s: tuple[float, ...]
    maximum_m: float
    maximum_flows_m3_s: tuple[float, ...]


def create_npshr_curve(points, flow_unit, head_unit, flow_factors):
    if len(points) < 3:
        raise ValueError('Enter at least 3 unique vendor NPSHR-curve points.')
    converted = []
    for index, pair in enumerate(points, 1):
        if not isinstance(pair, (tuple, list)) or len(pair) != 2:
            raise ValueError(f'Point {index} must contain flow and vendor NPSHR.')
        try:
            q = curve_flow_to_si(pair[0],flow_unit,flow_factors)
            positive(pair[1],'Vendor NPSHR')
            r = positive(head_to_metres(pair[1],head_unit,'Vendor NPSHR'),'Converted Vendor NPSHR')
        except ValueError as exc:
            raise ValueError(f'Point {index}: {exc}') from None
        converted.append(NPSHRPoint(q,r))
    converted.sort(key=lambda p:p.flow_m3_s)
    if any(a.flow_m3_s == b.flow_m3_s for a,b in zip(converted,converted[1:])):
        raise ValueError('Each vendor NPSHR-curve flow value must be unique.')
    return NPSHRCurve(tuple(converted))


def interpolate_npshr(curve, operating_flow_si):
    q = nonnegative(operating_flow_si,'Operating flow')
    flows = [p.flow_m3_s for p in curve.points]
    # Same roundoff convention as Phases 3M/3N: eight ULPs, no absolute
    # flow tolerance that could admit physically meaningful extrapolation.
    def same(a,b):
        return abs(a-b) <= 8 * max(math.ulp(a),math.ulp(b))
    if (q < flows[0] and not same(q,flows[0])) or (q > flows[-1] and not same(q,flows[-1])):
        raise ValueError(OUT_OF_RANGE)
    index = bisect_left(flows,q)
    for candidate in (index,index-1):
        if 0 <= candidate < len(flows) and same(q,flows[candidate]):
            return NPSHRInterpolationResult(q,curve.points[candidate].npshr_m,True)
    lower,upper = curve.points[index-1:index+1]
    weight = (q-lower.flow_m3_s)/(upper.flow_m3_s-lower.flow_m3_s)
    # Convex form avoids cancellation to zero for a sharply descending curve.
    r = (1-weight)*lower.npshr_m + weight*upper.npshr_m
    return NPSHRInterpolationResult(q,positive(r,'Interpolated Vendor NPSHR'),False)


def find_npshr_extrema(curve):
    # Every distinct supplied flow at the represented minimum/maximum is
    # returned once; no interpolated extrema or operating limits are inferred.
    minimum = min(p.npshr_m for p in curve.points)
    maximum = max(p.npshr_m for p in curve.points)
    return NPSHRExtremaResult(minimum,tuple(p.flow_m3_s for p in curve.points if p.npshr_m == minimum),
                             maximum,tuple(p.flow_m3_s for p in curve.points if p.npshr_m == maximum))
