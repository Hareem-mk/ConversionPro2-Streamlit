"""Required internal diameter, with SI inputs and outputs."""
import math
from dataclasses import dataclass


def positive(value, label):
    if value is None or isinstance(value, bool):
        raise ValueError(f'{label} is required and must be numeric.')
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'{label} must be numeric.') from None
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'{label} must be finite and greater than zero.')
    return value


@dataclass(frozen=True)
class PipeSize:
    diameter_m: float
    diameter_mm: float
    diameter_inches: float


def required_internal_diameter(flow_m3_s, target_velocity_m_s):
    q = positive(flow_m3_s, 'Flow rate')
    v = positive(target_velocity_m_s, 'Target velocity')
    # Algebraically equivalent to sqrt(4Q/(pi V)); avoids intermediate Q/V overflow.
    diameter = (2 / math.sqrt(math.pi)) * (math.sqrt(q) / math.sqrt(v))
    values = (diameter, diameter * 1000, diameter / .0254)
    if any(not math.isfinite(x) or x <= 0 for x in values):
        raise ValueError('Diameter exceeds the supported numeric range.')
    return PipeSize(*values)
