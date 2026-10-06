"""Stage 2G: separate system-required and measured flange head functions."""
from dataclasses import dataclass
import math
from advanced_engineering import G
from .pipe_geometry import positive
from .pipe_capacity import nonnegative


def finite_signed(value, label):
    """Signed elevations and gauge pressures must not use nonnegative validation."""
    if value is None or isinstance(value, bool):
        raise ValueError(f'{label} is required and must be numeric.')
    try:
        value=float(value)
    except (TypeError,ValueError,OverflowError):
        raise ValueError(f'{label} must be numeric.') from None
    if not math.isfinite(value):raise ValueError(f'{label} must be finite.')
    return value


def pressure_to_pa(value, unit, factors):
    value=finite_signed(value,'Pressure')
    if unit not in factors:raise ValueError('Select a supported pressure unit.')
    factor=positive(factors[unit],'Pressure conversion factor')
    result=finite_signed(value*factor,'Converted pressure')
    if value != 0 and result == 0:raise ValueError('Pressure conversion underflow.')
    return result


@dataclass(frozen=True)
class PumpHead:
    mode: str
    pressure_basis: str
    datum: str
    pressure_head_m: float
    elevation_head_m: float
    velocity_head_m: float
    total_head_m: float
    # None means not part of this mode, rather than an entered zero loss.
    suction_loss_m: float | None = None
    discharge_loss_m: float | None = None
    equipment_head_m: float | None = None


def _sum(values):
    try:total=math.fsum(values)
    except OverflowError:raise ValueError('Head sum exceeds numeric range.') from None
    return finite_signed(total,'Calculated head')


def _common(density,p1_pa,p2_pa,z1,z2,v1,v2,basis1,basis2,datum,reference_confirmed):
    rho=positive(density,'Density')
    if basis1 not in ('Gauge','Absolute') or basis2 not in ('Gauge','Absolute'):
        raise ValueError('Select Gauge or Absolute pressure basis.')
    if basis1 != basis2:
        raise ValueError('Mixed gauge/absolute pressure bases are not allowed. Convert explicitly first.')
    if reference_confirmed is not True:
        raise ValueError('Confirm a common elevation datum and consistent pressure reference; gauge pressures need the same atmospheric reference.')
    if not isinstance(datum,str) or not datum.strip():
        raise ValueError('State the common elevation datum.')
    p1=finite_signed(p1_pa,'Point 1 pressure');p2=finite_signed(p2_pa,'Point 2 pressure')
    if basis1=='Absolute' and (p1<0 or p2<0):
        raise ValueError('Absolute pressures cannot be negative.')
    z1=finite_signed(z1,'Point 1 elevation');z2=finite_signed(z2,'Point 2 elevation')
    v1=nonnegative(v1,'Point 1 velocity');v2=nonnegative(v2,'Point 2 velocity')
    # Difference of separately converted heads avoids overflowing rho*g or P2-P1.
    pressure_head=finite_signed(p2/rho/G-p1/rho/G,'Pressure-head contribution')
    elevation_head=finite_signed(z2-z1,'Elevation-head contribution')
    velocity_head=finite_signed((v2-v1)*((v2/2+v1/2)/G),'Velocity-head contribution')
    return rho,pressure_head,elevation_head,velocity_head


def system_required_head(*,density,p1_pa,p2_pa,z1,z2,v1,v2,basis1,basis2,datum,
                         reference_confirmed=False,suction_loss,discharge_loss,equipment_dp_pa,
                         losses_already_in_reference_pressures=False):
    rho,p,z,v=_common(density,p1_pa,p2_pa,z1,z2,v1,v2,basis1,basis2,datum,reference_confirmed)
    hs=nonnegative(suction_loss,'Suction piping loss')
    hd=nonnegative(discharge_loss,'Discharge piping loss')
    dp=nonnegative(equipment_dp_pa,'Equipment pressure loss')
    if losses_already_in_reference_pressures:
        raise ValueError('Do not re-add losses already represented by the supplied reference pressures; review endpoints or use flange mode.')
    he=finite_signed(dp/rho/G,'Equipment-loss head')
    return PumpHead('SYSTEM REQUIRED PUMP HEAD',basis1,datum.strip(),p,z,v,_sum([p,z,v,hs,hd,he]),hs,hd,he)


def flange_differential_head(*,density,p1_pa,p2_pa,z1,z2,v1,v2,basis1,basis2,datum,
                             reference_confirmed=False):
    _,p,z,v=_common(density,p1_pa,p2_pa,z1,z2,v1,v2,basis1,basis2,datum,reference_confirmed)
    # Intentionally no external-loss arguments or access to system-mode state.
    return PumpHead('PUMP-FLANGE DIFFERENTIAL HEAD',basis1,datum.strip(),p,z,v,_sum([p,z,v]))
