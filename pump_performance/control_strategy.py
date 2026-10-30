"""Same-target control comparison using existing hydraulic and vendor kernels."""
from dataclasses import dataclass
import math
from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from .pump_curve import PumpCurve,interpolate_pump_head
from .system_curve import model_from_reference
from .operating_point import find_operating_points,FLOW_ABS_TOL_M3_S,FLOW_REL_TOL,head_tolerance
from .target_speed import solve_speed_for_target_flow
from .hydraulic_power import hydraulic_power
from .affinity_laws import calculate_speed_affinity
from .power_curve import create_power_curve,interpolate_power,calculate_driver_margin
from .motor_power import motor_power
from .shaft_power import POWER_FACTORS
from .system_sensitivity import numeric_change,NumericChange

INVALID_RESISTANCE='The requested target flow cannot be represented by a nonnegative quadratic system-resistance coefficient at the supplied static head and reference-speed pump curve.'

@dataclass(frozen=True)
class ConstantSpeedResult:
    system: object
    verification: object
    verified_point: object
    head_m: float
    friction_head_m: float

@dataclass(frozen=True)
class ControlStrategyComparisonResult:
    target_flow_m3_s: float
    base_system: object
    constant_speed: ConstantSpeedResult | None
    constant_speed_error: str | None
    vsd: object | None
    vsd_error: str | None
    constant_hydraulic_w: float | None
    vsd_hydraulic_w: tuple[float, ...]
    resistance_change: NumericChange | None

@dataclass(frozen=True)
class ShaftComparison:
    constant_w: float
    vsd_w: float
    scaled_curve: object
    difference: NumericChange

@dataclass(frozen=True)
class InputPowerComparison:
    constant_motor_input_w: float
    vsd_motor_input_w: float
    vsd_drive_input_w: float | None

@dataclass(frozen=True)
class AnnualComparison:
    constant_kwh: float
    vsd_kwh: float
    difference_kwh: float
    constant_cost: float | None
    vsd_cost: float | None
    difference_cost: float | None


def difference_relative_to_first(first,second):
    change=numeric_change(first,second)
    return NumericChange(-change.difference,None if change.percent is None else -change.percent)


def solve_constant_speed_system_for_target_flow(reference_pump_curve,static_head,target_flow):
    q=positive(target_flow,'Target Operating Flow')
    curve=PumpCurve(reference_pump_curve.points,'m³/s','m',1.0,1.0)
    pump=interpolate_pump_head(curve,q).head_m
    static=nonnegative(static_head,'Static head')
    # The requested 3U boundary explicitly rejects H_pump <= H_static,
    # including equality (zero added friction); never invent negative K.
    if pump<=static:raise ValueError(INVALID_RESISTANCE)
    model=model_from_reference(static_head=static,head_unit='m',reference_flow=q,
        reference_friction_head=pump-static,flow_unit='m³/s',flow_factors={'m³/s':1.0})
    roots=find_operating_points(curve,model)
    tol=FLOW_ABS_TOL_M3_S+FLOW_REL_TOL*max(q,curve.points[-1].flow_m3_s)
    matches=[p for p in roots.points if abs(p.flow_m3_s-q)<=tol]
    if not matches:raise ValueError('Constant-speed target failed Phase 3G flow verification; residual is material.')
    point=min(matches,key=lambda p:abs(p.flow_m3_s-q))
    if abs(point.residual_m)>head_tolerance(point.pump_head_m,point.system_head_m):raise ValueError('Constant-speed head residual is material.')
    return ConstantSpeedResult(model,roots,point,pump,pump-static)


def compare_throttling_and_vsd(reference_pump_curve,reference_speed,base_system,target_flow,density):
    q=positive(target_flow,'Target Operating Flow')
    calculate_speed_affinity(0,0,0,reference_speed,reference_speed)
    base_system.at_flow(q)
    def hydraulic(head):
        return hydraulic_power(density=density,density_unit='kg/m³',flow=q,flow_unit='m³/s',head_m=head,
            density_factors={'kg/m³':1.0},flow_factors={'m³/s':1.0}).watts
    hydraulic(0) # Validate required density independently of strategy availability.
    constant=vsd=None;ce=ve=None;cp=None;vp=();resistance=None
    try:
        constant=solve_constant_speed_system_for_target_flow(reference_pump_curve,base_system.static_head_m,q)
        cp=hydraulic(constant.head_m);resistance=numeric_change(base_system.k_si,constant.system.k_si)
    except (ValueError,OverflowError) as exc:ce=str(exc)
    try:
        vsd=solve_speed_for_target_flow(reference_pump_curve,reference_speed,base_system,q)
        vp=tuple(hydraulic(vsd.target_system_head_m) for _ in vsd.solutions)
    except (ValueError,OverflowError) as exc:ve=str(exc)
    return ControlStrategyComparisonResult(q,base_system,constant,ce,vsd,ve,cp,vp,resistance)


def scale_vendor_power_curve(reference_curve,reference_speed,new_speed):
    points=[]
    for p in reference_curve.points:
        s=calculate_speed_affinity(p.flow_m3_s,0,p.shaft_power_w,reference_speed,new_speed)
        points.append((s.estimated_flow_m3_s,s.estimated_power_w))
    return create_power_curve(points,'m³/s','W',{'m³/s':1.0})


def compare_shaft_power(reference_curve,reference_speed,new_speed,target_flow):
    # Interpolate only after the entire Q/P curve has been transformed.
    constant=interpolate_power(reference_curve,target_flow).shaft_power_w
    scaled=scale_vendor_power_curve(reference_curve,reference_speed,new_speed)
    vsd=interpolate_power(scaled,target_flow).shaft_power_w
    return ShaftComparison(constant,vsd,scaled,difference_relative_to_first(constant,vsd))



def validate_shaft_hydraulic_basis(shaft,constant_hydraulic_w,vsd_hydraulic_w):
    for name,p,h in [('Constant-Speed',shaft.constant_w,constant_hydraulic_w),('VSD',shaft.vsd_w,vsd_hydraulic_w)]:
        if p<h and not math.isclose(p,h,rel_tol=1e-12,abs_tol=1e-9):
            raise ValueError(name+' supplied/scaled shaft power is below calculated hydraulic power. Review head, power, fluid and speed data for the same duty. Electrical and annual-energy comparison is unavailable until the data basis is consistent.')


def compare_input_power(shaft,constant_motor_efficiency,vsd_motor_efficiency,vfd_efficiency=None):
    a=motor_power(shaft.constant_w,'W',constant_motor_efficiency).input_watts
    b=motor_power(shaft.vsd_w,'W',vsd_motor_efficiency).input_watts
    drive=None
    if vfd_efficiency is not None:
        # Reuse 3C percent validation/division, with drive-specific diagnostics.
        try:drive=motor_power(b,'W',vfd_efficiency).input_watts
        except ValueError as exc:raise ValueError(str(exc).replace('Motor efficiency','VFD efficiency')) from None
    return InputPowerComparison(a,b,drive)


def annual_energy(inputs,hours,tariff=None):
    if not isinstance(inputs,InputPowerComparison) or inputs.vsd_drive_input_w is None:
        raise ValueError('Annual electrical energy requires both motor efficiencies and explicit VFD efficiency on a comparable supply-input basis.')
    h=nonnegative(hours,'Annual Operating Hours')
    price=nonnegative(tariff,'Electricity Cost per kWh') if tariff is not None else None
    a=inputs.constant_motor_input_w/POWER_FACTORS['kW']*h;b=inputs.vsd_drive_input_w/POWER_FACTORS['kW']*h
    delta=a-b
    costs=(a*price,b*price,delta*price) if price is not None else (None,None,None)
    if any(not math.isfinite(v) for v in (a,b,delta)+tuple(v for v in costs if v is not None)):
        raise ValueError('Annual energy/cost exceeds the supported numeric range.')
    return AnnualComparison(a,b,delta,*costs)
