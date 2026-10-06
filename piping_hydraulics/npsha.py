"""Stage 2H: NPSH available; SI inputs, distinct source and flange boundaries."""
from dataclasses import dataclass
import math
from advanced_engineering import G
from .pipe_geometry import positive
from .pipe_capacity import nonnegative
from .pump_head import finite_signed

COMPARISON = ('NPSHA must be compared with pump/vendor NPSHR plus the applicable '
              'design margin or project/company requirement.')


def absolute_pressure(pressure_pa, basis, atmospheric_pa=None):
    """Gauge requires explicit local atmosphere; absolute liquid pressure must be > 0."""
    p = finite_signed(pressure_pa, 'Suction/source pressure')
    if basis == 'Gauge':
        atm = positive(atmospheric_pa, 'Local atmospheric absolute pressure')
        return positive(p + atm, 'Converted absolute suction/source pressure')
    if basis == 'Absolute':
        if atmospheric_pa is not None:
            raise ValueError('Atmospheric conversion applies only to Gauge pressure.')
        return positive(p, 'Absolute suction/source pressure')
    raise ValueError('Select Absolute or Gauge pressure basis.')


@dataclass(frozen=True)
class NPSHAvailable:
    mode: str
    absolute_pressure_pa: float
    vapor_pressure_pa: float
    vapor_head_m: float
    pressure_above_vapor_head_m: float
    velocity_head_m: float
    elevation_head_m: float
    suction_loss_m: float | None
    total_npsha_m: float
    warnings: tuple[str, ...]


def _calculate(mode, pressure_pa, basis, atmospheric_pa, vapor_pressure_pa,
               density, velocity, elevation, datum_elevation, suction_loss):
    p = absolute_pressure(pressure_pa, basis, atmospheric_pa)
    pv = nonnegative(vapor_pressure_pa, 'Liquid Vapor Pressure — Absolute')
    rho = positive(density, 'Density')
    v = nonnegative(velocity, 'Velocity')
    z = finite_signed(elevation, 'Reference point elevation')
    datum = finite_signed(datum_elevation, 'Pump/NPSH datum elevation')
    hv = finite_signed(pv / rho / G, 'Vapor-pressure head')
    hp = finite_signed((p - pv) / rho / G, 'Pressure-above-vapor head')
    hk = finite_signed((v / (2 * G)) * v, 'Velocity head')
    hz = finite_signed(z - datum, 'Elevation contribution')
    loss = None if suction_loss is None else nonnegative(suction_loss, 'Total suction loss')
    try:
        total = math.fsum([hp, hk, hz, -(loss if loss is not None else 0)])
    except OverflowError:
        raise ValueError('Calculated NPSHA exceeds numeric range.') from None
    total = finite_signed(total, 'Calculated NPSHA')
    warnings = []
    if p <= pv:
        warnings.append('Absolute suction/source pressure is at or below liquid vapor pressure. '
                        'Vapor formation is indicated; the assumed single-phase liquid model may not be sustainable.')
    if total <= 0:
        warnings.append('NPSHA is at/below the vapor-pressure energy reference and is not an acceptable '
                        'normal pump suction condition. The calculated value is retained; verify the '
                        'inputs and the single-phase assumption.')
    return NPSHAvailable(mode, p, pv, hv, hp, hk, hz, loss, total, tuple(warnings))


def flange_npsha(*, pressure_pa, basis, vapor_pressure_pa, density, velocity,
                 elevation, datum_elevation, atmospheric_pa=None):
    """Measured suction pressure already reflects upstream losses: no loss argument."""
    return _calculate('SUCTION-FLANGE NPSHA', pressure_pa, basis, atmospheric_pa,
                      vapor_pressure_pa, density, velocity, elevation, datum_elevation, None)


def source_npsha(*, pressure_pa, basis, vapor_pressure_pa, density, velocity,
                 elevation, datum_elevation, suction_loss, atmospheric_pa=None):
    # Validate separately so None cannot be mistaken for the flange no-loss mode.
    loss = nonnegative(suction_loss, 'Total suction loss')
    return _calculate('SUCTION-VESSEL / SOURCE NPSHA', pressure_pa, basis, atmospheric_pa,
                      vapor_pressure_pa, density, velocity, elevation, datum_elevation, loss)
