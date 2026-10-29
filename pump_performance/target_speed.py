"""Bounded inverse affinity search; shared interpolation and forward verification."""
from dataclasses import dataclass
import math
from piping_hydraulics.pipe_geometry import positive
from .pump_curve import PumpCurve, interpolate_pump_head
from .affinity_laws import calculate_speed_affinity
from .variable_speed import scale_head_curve_by_speed
from .operating_point import (find_operating_points, head_tolerance,
    FLOW_ABS_TOL_M3_S, FLOW_REL_TOL)

NO_SOLUTION = 'No valid required-speed solution exists within the supplied affinity-scaled pump-curve domain.'

@dataclass(frozen=True)
class TargetSpeedSolution:
    required_speed_rpm: float
    ratio: float
    speed_change_percent: float
    scaled_curve: PumpCurve
    verification: object
    verified_flow_m3_s: float
    verified_head_m: float
    flow_residual_m3_s: float
    head_residual_m: float

@dataclass(frozen=True)
class SpeedRatioInterval:
    minimum_ratio: float
    maximum_ratio: float  # math.inf denotes a mathematically unbounded interval

@dataclass(frozen=True)
class TargetSpeedResult:
    reference_speed_rpm: float
    target_flow_m3_s: float
    target_system_head_m: float
    base: object
    solutions: tuple[TargetSpeedSolution, ...]
    coincident_ratio_intervals: tuple[SpeedRatioInterval, ...]


def _si_view(curve):
    return PumpCurve(curve.points,'m³/s','m',1.0,1.0)


def _head_at_ratio(curve, target, ratio):
    q=target/ratio
    lo,hi=curve.points[0].flow_m3_s,curve.points[-1].flow_m3_s
    # Only reconcile roundoff from target / (target / endpoint), never a
    # material out-of-domain trial or physical extrapolation.
    if q<lo and lo-q<=8*max(math.ulp(q),math.ulp(lo)):q=lo
    if q>hi and q-hi<=8*max(math.ulp(q),math.ulp(hi)):q=hi
    head=interpolate_pump_head(curve,q).head_m
    return calculate_speed_affinity(0,head,0,1,ratio).estimated_head_m


def verify_target_speed_solution(curve,reference_speed,system,target,ratio):
    speed=positive(reference_speed*ratio,'Required speed')
    scaling=scale_head_curve_by_speed(curve,reference_speed,speed)
    roots=find_operating_points(scaling.scaled_curve,system)
    required=system.at_flow(target).total_head_m
    residual=_head_at_ratio(_si_view(curve),target,scaling.ratio)-required
    flow_tol=FLOW_ABS_TOL_M3_S+FLOW_REL_TOL*max(target,scaling.scaled_curve.points[-1].flow_m3_s)
    matches=[p for p in roots.points if abs(p.flow_m3_s-target)<=flow_tol]
    if matches:
        p=min(matches,key=lambda p:abs(p.flow_m3_s-target));q,h=p.flow_m3_s,p.head_m
    elif any(i.minimum_flow_m3_s-flow_tol<=target<=i.maximum_flow_m3_s+flow_tol for i in roots.coincident_intervals):
        q=target;h=system.at_flow(target).total_head_m
    else:raise ValueError('Required-speed solution failed Phase 3G target-flow verification; residual is material.')
    if abs(residual)>head_tolerance(required+residual,required):
        raise ValueError('Required-speed solution head residual exceeds Phase 3G tolerance.')
    return TargetSpeedSolution(speed,scaling.ratio,scaling.speed_change_percent,scaling.scaled_curve,
        roots,q,h,q-target,residual)


def solve_speed_for_target_flow(reference_pump_curve,reference_speed_rpm,system_curve,target_flow_si):
    """Search every reference segment's admissible ratio interval.

    Within a linear supplied segment f(R)=aR²+b*Qtarget*R-Htarget.
    Coefficients identify stationary partitions only; every trial head is
    evaluated with Phase 3E interpolation and Phase 3I scaling. Sign-changing
    monotone partitions use deterministic bisection. Contacts use the same
    eight-ULP discovery convention as Phase 3G. No fitted curve is introduced.
    """
    target=positive(target_flow_si,'Target Operating Flow')
    speed=positive(reference_speed_rpm,'Reference Pump Speed')
    calculate_speed_affinity(0,0,0,speed,speed)
    curve=_si_view(reference_pump_curve)
    base=find_operating_points(curve,system_curve)
    required=system_curve.at_flow(target).total_head_m
    candidates=[];intervals=[]
    def value(r):
        h=_head_at_ratio(curve,target,r)
        return h-required, abs(h-required)<=8*math.ulp(max(h,required))
    def bisect(left,right,fl):
        for _ in range(2200):
            mid=left+(right-left)/2
            if mid==left or mid==right:return min((left,right),key=lambda r:abs(value(r)[0]))
            fm,_=value(mid)
            if fm==0:return mid
            if (fm<0)==(fl<0):left=mid;fl=fm
            else:right=mid
        raise ValueError('Required-speed root search did not converge.')
    for low,high in zip(curve.points,curve.points[1:]):
        if high.flow_m3_s<=0:continue
        left=positive(target/high.flow_m3_s,'Admissible speed ratio')
        right=target/low.flow_m3_s if low.flow_m3_s>0 else math.inf
        if low.flow_m3_s>0 and not math.isfinite(right):
            raise ValueError('Admissible speed-ratio domain exceeds the supported numeric range.')
        if low.head_m==high.head_m==required==0:
            intervals.append(SpeedRatioInterval(left,right));continue
        slope=(high.head_m-low.head_m)/(high.flow_m3_s-low.flow_m3_s)
        intercept=low.head_m-slope*low.flow_m3_s
        if not all(math.isfinite(v) for v in (slope,intercept)):
            raise ValueError('Required-speed segment partition exceeds the supported numeric range.')
        vertex=-(slope*target)/(2*intercept) if intercept else None
        if right==math.inf:
            # This segment starts at Qref=0. Its intercept is the nonnegative
            # shutoff head. Beyond a stationary point it is monotone; expand
            # only until a positive residual brackets all possible roots.
            if intercept==0 and slope==0:continue
            right=max(left,vertex if vertex is not None and math.isfinite(vertex) else left)
            f,_=value(right)
            while f<0:
                enlarged=right*2
                if not math.isfinite(enlarged):raise ValueError('Required speed exceeds the supported numeric range.')
                right=enlarged;f,_=value(right)
        positive(right,'Admissible speed ratio')
        cuts=[left,right]
        if vertex is not None and math.isfinite(vertex) and left<vertex<right:cuts.insert(1,vertex)
        evaluated=[value(r) for r in cuts]
        candidates.extend(r for r,(_,contact) in zip(cuts,evaluated) if contact)
        for l,r,(fl,cl),(fr,cr) in zip(cuts,cuts[1:],evaluated,evaluated[1:]):
            if not cl and not cr and (fl<0)!=(fr<0):candidates.append(bisect(l,r,fl))
    merged=[]
    for interval in sorted(intervals,key=lambda i:i.minimum_ratio):
        if merged and interval.minimum_ratio<=merged[-1].maximum_ratio:
            previous=merged.pop();merged.append(SpeedRatioInterval(previous.minimum_ratio,max(previous.maximum_ratio,interval.maximum_ratio)))
        else:merged.append(interval)
    ratios=[]
    for r in sorted(candidates):
        if any(i.minimum_ratio<=r<=i.maximum_ratio for i in merged):continue
        if ratios and abs(r-ratios[-1])<=8*max(math.ulp(r),math.ulp(ratios[-1])):continue
        ratios.append(r)
    solutions=tuple(verify_target_speed_solution(curve,speed,system_curve,target,r) for r in ratios)
    return TargetSpeedResult(speed,target,required,base,solutions,tuple(merged))


def compare_speed_limits(speed,minimum=None,maximum=None):
    value=positive(speed,'Required speed')
    low=positive(minimum,'Minimum Allowed Speed') if minimum is not None else None
    high=positive(maximum,'Maximum Allowed Speed') if maximum is not None else None
    if low is not None and high is not None and low>high:raise ValueError('Minimum Allowed Speed must not exceed Maximum Allowed Speed.')
    if low is not None and value<low:return 'Below entered minimum speed'
    if high is not None and value>high:return 'Above entered maximum speed'
    return 'Within entered speed range' if low is not None or high is not None else None
