"""Descriptive supplied Q–H characteristics; no inferred vendor limits."""
from dataclasses import dataclass,replace
from bisect import bisect_left
import math
from piping_hydraulics.pipe_capacity import nonnegative
from .pump_curve import interpolate_pump_head,CurvePoint,OUT_OF_RANGE

# Numerical head-change tolerance only, not an engineering flatness criterion.
HEAD_ABS_TOL_M=1e-9
HEAD_REL_TOL=1e-12
NO_SHUTOFF='No supplied Q = 0 point; shutoff head is not inferred.'


@dataclass(frozen=True)
class SegmentSlope:
    index: int
    lower: CurvePoint
    upper: CurvePoint
    slope_si: float
    classification: str


@dataclass(frozen=True)
class PumpCurveCharacteristics:
    minimum_flow_m3_s: float
    maximum_flow_m3_s: float
    minimum_head_m: float
    maximum_head_m: float
    shutoff_head_m: float | None
    maximum_flow_point: CurvePoint
    segments: tuple[SegmentSlope, ...]
    flat_segment_count: int
    rising_segment_count: int
    monotonicity_status: str


@dataclass(frozen=True)
class CurveSlopeResult:
    operating_flow_m3_s: float
    evaluated_flow_m3_s: float
    operating_head_m: float
    local_segments: tuple[SegmentSlope, ...]
    exact_point: bool


@dataclass(frozen=True)
class ShutoffRiseResult:
    rise_m: float
    percent_of_operating_head: float | None
    percent_of_shutoff_head: float | None


def segment_slopes(curve):
    segments=[]
    for index,(lower,upper) in enumerate(zip(curve.points,curve.points[1:]),1):
        delta=upper.head_m-lower.head_m
        slope=delta/(upper.flow_m3_s-lower.flow_m3_s)
        if not math.isfinite(slope) or (delta != 0 and slope == 0):
            raise ValueError('Pump-curve slope exceeds the supported numeric range.')
        flat=math.isclose(upper.head_m,lower.head_m,rel_tol=HEAD_REL_TOL,abs_tol=HEAD_ABS_TOL_M)
        classification='Flat' if flat else ('Rising' if delta > 0 else 'Falling')
        segments.append(SegmentSlope(index,lower,upper,slope,classification))
    return tuple(segments)


def analyze_curve_characteristics(curve):
    segments=segment_slopes(curve)
    flat=sum(s.classification=='Flat' for s in segments)
    rising=sum(s.classification=='Rising' for s in segments)
    if rising:status='Supplied head curve is not monotonically decreasing.'
    elif flat==len(segments):status='Supplied head curve is flat within numerical tolerance.'
    elif flat:status='Supplied head curve is non-increasing with flat segment(s).'
    else:status='Supplied head curve is monotonically decreasing.'
    return PumpCurveCharacteristics(curve.points[0].flow_m3_s,curve.points[-1].flow_m3_s,
        min(p.head_m for p in curve.points),max(p.head_m for p in curve.points),
        curve.shutoff_head_m,curve.points[-1],segments,flat,rising,status)


def local_curve_slope(curve,operating_flow_si):
    q=nonnegative(operating_flow_si,'Operating flow')
    selected=q
    # Eight-ULP matching absorbs flow conversion roundoff, consistent with
    # recent curve adapters. It never infers Q=0 or alters stored curve data.
    for point in curve.points:
        if abs(q-point.flow_m3_s) <= 8*max(math.ulp(q),math.ulp(point.flow_m3_s)):
            selected=point.flow_m3_s
            break
    if selected < curve.points[0].flow_m3_s or selected > curve.points[-1].flow_m3_s:
        raise ValueError(OUT_OF_RANGE)
    # Phase 3E owns head interpolation. Its stored points are already SI;
    # SI metadata avoids converting an SI request a second time.
    si_curve=replace(curve,flow_unit='m³/s',flow_factor=1.0)
    head=interpolate_pump_head(si_curve,selected)
    slopes=segment_slopes(curve)
    index=bisect_left([p.flow_m3_s for p in curve.points],selected)
    exact=curve.points[index].flow_m3_s==selected
    if exact:
        indices=([index-1] if index>0 else [])+([index] if index<len(slopes) else [])
        local=tuple(slopes[i] for i in indices)
    else:local=(slopes[index-1],)
    return CurveSlopeResult(q,selected,head.head_m,local,exact)


def calculate_shutoff_head_rise(shutoff_head_m,operating_head_m):
    shutoff=nonnegative(shutoff_head_m,'Supplied shutoff head')
    operating=nonnegative(operating_head_m,'Operating head')
    rise=shutoff-operating
    pct_op=None if operating==0 else rise/operating*100
    pct_shutoff=None if shutoff==0 else rise/shutoff*100
    if any(v is not None and not math.isfinite(v) for v in (rise,pct_op,pct_shutoff)):
        raise ValueError('Shutoff head-rise result exceeds the supported numeric range.')
    return ShutoffRiseResult(rise,pct_op,pct_shutoff)


def display_slope(slope_si,flow_unit,head_unit,flow_factors):
    from .pump_curve import HEAD_FACTORS
    if flow_unit not in flow_factors or head_unit not in HEAD_FACTORS:
        raise ValueError('Select supported slope flow/head display units.')
    slope=slope_si*flow_factors[flow_unit]/HEAD_FACTORS[head_unit]
    if not math.isfinite(slope) or (slope_si != 0 and slope == 0):
        raise ValueError('Displayed slope exceeds the supported numeric range.')
    return slope


def compare_minimum_flow(operating_flow_si,minimum_flow_si):
    q=nonnegative(operating_flow_si,'Operating flow')
    minimum=nonnegative(minimum_flow_si,'Vendor/Project Minimum Flow')
    if math.isclose(q,minimum,rel_tol=1e-12,abs_tol=0):return 'Equals entered minimum flow'
    return 'Above entered minimum flow' if q>minimum else 'Below entered minimum flow'
