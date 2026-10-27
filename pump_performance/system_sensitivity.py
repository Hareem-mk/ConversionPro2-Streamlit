"""System-case orchestration using existing system and bounded root kernels."""
from dataclasses import dataclass
import math
from piping_hydraulics.pump_head import finite_signed
from .system_curve import model_from_k
from .operating_point import find_operating_points,OperatingPointResult
from .hydraulic_power import hydraulic_power
from .power_curve import interpolate_power
from .npshr_curve import interpolate_npshr
from .npsh_margin import calculate_npsh_margin
from .bep_operating_range import compare_bep

NO_VALID_POINT='No valid pump/system operating point exists within the supplied pump-curve range.'


@dataclass(frozen=True)
class NumericChange:
    difference: float
    percent: float | None


@dataclass(frozen=True)
class SystemSensitivityResult:
    base: OperatingPointResult
    modified: OperatingPointResult
    base_k_si: float
    modified_k_si: float
    base_static_head_m: float
    modified_static_head_m: float
    flow_change: NumericChange | None
    head_change: NumericChange | None


@dataclass(frozen=True)
class PointContext:
    hydraulic_w: float | None
    vendor_shaft_w: float | None
    percent_bep: float | None
    npshr_m: float | None
    npsh_margin_m: float | None
    errors: tuple[str, ...]


def numeric_change(base,modified):
    a=finite_signed(base,'Base value');b=finite_signed(modified,'Modified value')
    delta=b-a
    percent=None if a==0 else delta/a*100
    if not math.isfinite(delta) or (percent is not None and not math.isfinite(percent)):
        raise ValueError('Case difference exceeds the supported numeric range.')
    return NumericChange(delta,percent)


def modified_resistance_model(base_system,modified_static_head_m,change_percent):
    change=finite_signed(change_percent,'Resistance Change (%)')
    if change < -100:raise ValueError('Resistance Change (%) must be at least -100%; negative K is not permitted.')
    k=base_system.k_si*(1+change/100)
    if not math.isfinite(k) or (base_system.k_si>0 and change>-100 and k==0):
        raise ValueError('Modified system resistance exceeds the supported numeric range.')
    return model_from_k(modified_static_head_m,'m',k)


def is_unique(result):
    return len(result.points)==1 and not result.coincident_intervals


def evaluate_system_sensitivity(pump_curve,base_system,modified_system):
    base=find_operating_points(pump_curve,base_system)
    modified=find_operating_points(pump_curve,modified_system)
    unique=is_unique(base) and is_unique(modified)
    return SystemSensitivityResult(base,modified,base_system.k_si,modified_system.k_si,
        base_system.static_head_m,modified_system.static_head_m,
        numeric_change(base.points[0].flow_m3_s,modified.points[0].flow_m3_s) if unique else None,
        numeric_change(base.points[0].head_m,modified.points[0].head_m) if unique else None)


def evaluate_point_context(point,flow_factors,*,density=None,density_unit=None,density_factors=None,
                           vendor_power_curve=None,bep_flow_si=None,npshr_curve=None,npsha_m=None):
    hydraulic=shaft=bep=npshr=margin=None
    errors=[]
    if density is not None:
        try:
            hydraulic=hydraulic_power(density=density,density_unit=density_unit,flow=point.flow_m3_s,
                flow_unit='m³/s',head_m=point.head_m,density_factors=density_factors,flow_factors=flow_factors).watts
        except (ValueError,OverflowError) as exc:errors.append('Hydraulic power: '+str(exc))
    if vendor_power_curve is not None:
        try:shaft=interpolate_power(vendor_power_curve,point.flow_m3_s).shaft_power_w
        except (ValueError,OverflowError) as exc:errors.append('Vendor shaft power: '+str(exc))
    if bep_flow_si is not None:
        try:bep=compare_bep(point.flow_m3_s,bep_flow_si).percent_bep
        except (ValueError,OverflowError) as exc:errors.append('BEP: '+str(exc))
    if npshr_curve is not None:
        try:
            npshr=interpolate_npshr(npshr_curve,point.flow_m3_s).npshr_m
            margin=calculate_npsh_margin(npsha_m,npshr).margin_m
        except (ValueError,OverflowError) as exc:errors.append('NPSH: '+str(exc))
    return PointContext(hydraulic,shaft,bep,npshr,margin,tuple(errors))
