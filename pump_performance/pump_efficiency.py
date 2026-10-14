"""Phase 3D: pump efficiency from hydraulic and mechanical shaft power."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from .hydraulic_power import hydraulic_power
from .shaft_power import POWER_FACTORS


@dataclass(frozen=True)
class PumpEfficiency:
    hydraulic_watts: float
    shaft_watts: float
    ratio: float
    percent: float


def power_to_watts(value, unit, label, *, allow_zero):
    """Use accepted Phase 3B power factors with this module's input rules."""
    value = nonnegative(value, label) if allow_zero else positive(value, label)
    if unit not in POWER_FACTORS:
        raise ValueError(f'Select a supported {label.lower()} unit: W, kW or Mechanical hp.')
    watts = value * POWER_FACTORS[unit]
    if not math.isfinite(watts) or (value > 0 and watts == 0):
        raise ValueError(f'{label} exceeds the supported numeric range.')
    return watts


def _efficiency_from_watts(hydraulic_watts, shaft_watts):
    if hydraulic_watts > shaft_watts:
        raise ValueError('Hydraulic power cannot exceed pump shaft power for a physically valid pump-efficiency calculation.')
    ratio = hydraulic_watts / shaft_watts
    if hydraulic_watts > 0 and ratio == 0:
        raise ValueError('Pump efficiency exceeds the supported numeric range.')
    return PumpEfficiency(hydraulic_watts, shaft_watts, ratio, ratio * 100)


def calculate_pump_efficiency(*, hydraulic_value, hydraulic_unit, shaft_value, shaft_unit):
    # A positive shaft is required even for zero hydraulic power (0/0 undefined).
    shaft = power_to_watts(shaft_value, shaft_unit, 'Pump Shaft / Brake Power', allow_zero=False)
    hydraulic = power_to_watts(hydraulic_value, hydraulic_unit, 'Hydraulic Power', allow_zero=True)
    return _efficiency_from_watts(hydraulic, shaft)


def pump_efficiency_from_conditions(*, density, density_unit, flow, flow_unit, head_m,
                                   shaft_value, shaft_unit, density_factors, flow_factors):
    shaft = power_to_watts(shaft_value, shaft_unit, 'Pump Shaft / Brake Power', allow_zero=False)
    hydraulic = hydraulic_power(density=density, density_unit=density_unit,
                                flow=flow, flow_unit=flow_unit, head_m=head_m,
                                density_factors=density_factors, flow_factors=flow_factors)
    return _efficiency_from_watts(hydraulic.watts, shaft)
