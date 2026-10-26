"""Consolidated vendor data review; delegates every interpolation to its owner."""
from dataclasses import dataclass,replace
import math
from piping_hydraulics.pipe_capacity import nonnegative
from .pump_curve import interpolate_pump_head,InterpolatedHead
from .efficiency_curve import interpolate_efficiency,EfficiencyInterpolationResult
from .power_curve import interpolate_power,PowerInterpolationResult
from .npshr_curve import interpolate_npshr,NPSHRInterpolationResult


@dataclass(frozen=True)
class CommonFlowRange:
    minimum_m3_s: float
    maximum_m3_s: float


@dataclass(frozen=True)
class PumpPerformanceMapResult:
    operating_flow_m3_s: float
    head_result: InterpolatedHead | None
    efficiency_result: EfficiencyInterpolationResult | None
    power_result: PowerInterpolationResult | None
    npshr_result: NPSHRInterpolationResult | None
    common_flow_range: CommonFlowRange | None
    range_statuses: tuple[tuple[str,str], ...]


def determine_common_flow_range(head_curve,efficiency_curve,power_curve,npshr_curve):
    curves=(head_curve,efficiency_curve,power_curve,npshr_curve)
    minimum=max(c.points[0].flow_m3_s for c in curves)
    maximum=min(c.points[-1].flow_m3_s for c in curves)
    return None if minimum > maximum else CommonFlowRange(minimum,maximum)


def _endpoint_flow(q,curve):
    # Consistent with Phases 3M–3O: absorb eight ULPs of conversion noise
    # at endpoints only, without a fixed physical flow allowance.
    for point in (curve.points[0],curve.points[-1]):
        boundary=point.flow_m3_s
        if abs(q-boundary) <= 8*max(math.ulp(q),math.ulp(boundary)):
            return boundary
    return q


def evaluate_performance_map(operating_flow_si,head_curve,efficiency_curve,power_curve,npshr_curve):
    q=nonnegative(operating_flow_si,'Operating flow')
    # Phase 3E accepts flow in its curve's input unit. Use its stored SI
    # coordinates with SI metadata to avoid a second flow-unit conversion.
    head_si=replace(head_curve,flow_unit='m³/s',flow_factor=1.0)
    results=[];statuses=[]
    for name,curve,interpolator in (
        ('Pump Head',head_si,interpolate_pump_head),
        ('Pump Efficiency',efficiency_curve,interpolate_efficiency),
        ('Pump Shaft/Brake Power',power_curve,interpolate_power),
        ('Pump NPSHR',npshr_curve,interpolate_npshr)):
        selected=_endpoint_flow(q,curve)
        if selected < curve.points[0].flow_m3_s or selected > curve.points[-1].flow_m3_s:
            results.append(None)
            statuses.append((name,f'Unavailable — operating flow is outside the supplied {name} curve range; no extrapolation.'))
        else:
            # Errors other than range unavailability propagate, rather than
            # being mislabeled as missing vendor coverage.
            results.append(interpolator(curve,selected))
            statuses.append((name,'Available — vendor interpolated'))
    return PumpPerformanceMapResult(q,*results,determine_common_flow_range(
        head_curve,efficiency_curve,power_curve,npshr_curve),tuple(statuses))
