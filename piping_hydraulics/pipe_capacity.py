"""Stage 2B: full circular pipe capacity, using SI internally."""
from dataclasses import dataclass
import math
from .pipe_geometry import positive


def nonnegative(value, label):
    if value is None or isinstance(value, bool):
        raise ValueError(f'{label} is required and must be numeric.')
    try:
        value = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f'{label} must be numeric.') from None
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{label} must be finite and nonnegative.')
    return value


@dataclass(frozen=True)
class PipeCapacity:
    area_m2: float
    velocity_m_s: float
    flow_m3_s: float


def pipe_capacity(internal_diameter_m, velocity_m_s):
    d = positive(internal_diameter_m, 'INTERNAL pipe diameter')
    v = nonnegative(velocity_m_s, 'Velocity')
    area = (math.pi / 4 * d) * d
    if not math.isfinite(area) or area <= 0:
        raise ValueError('Pipe area exceeds the supported numeric range.')
    q = area * v
    if not math.isfinite(q) or (v > 0 and q == 0):
        raise ValueError('Flow exceeds the supported numeric range.')
    return PipeCapacity(area, v, q)


def capacity_flow_outputs(flow_m3_s, flow_factors):
    """Receive the existing validated FLOW table; do not duplicate factors."""
    q = nonnegative(flow_m3_s, 'SI flow')
    outputs = {}
    for unit in ('m³/s', 'm³/hr', 'L/s', 'L/min', 'Gallon/min (US GPM)'):
        if unit not in flow_factors:
            raise ValueError(f'Missing validated conversion factor: {unit}.')
        factor = positive(flow_factors[unit], 'Flow conversion factor')
        value = q / factor
        if not math.isfinite(value) or (q > 0 and value == 0):
            raise ValueError('Converted flow exceeds the supported numeric range.')
        outputs[unit] = value
    return outputs
