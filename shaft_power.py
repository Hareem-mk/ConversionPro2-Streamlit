"""Phase 3B: mechanical pump shaft/brake power, excluding motor losses."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from .hydraulic_power import hydraulic_power, MECHANICAL_HP_W

POWER_FACTORS = {'W': 1, 'kW': 1000, 'Mechanical hp': MECHANICAL_HP_W}


@dataclass(frozen=True)
class ShaftPower:
    hydraulic_watts: float
    efficiency_percent: float
    shaft_watts: float
    shaft_kilowatts: float
    shaft_mechanical_hp: float


def pump_efficiency(efficiency_percent):
    percent = positive(efficiency_percent, 'Pump efficiency (%)')
    if percent > 100:
        raise ValueError('Pump efficiency (%) must be greater than 0 and no more than 100.')
    eta = percent / 100
    if eta == 0:
        raise ValueError('Pump efficiency (%) exceeds the supported numeric range.')
    return percent, eta


def shaft_power(hydraulic_value, power_unit, efficiency_percent):
    """Convert explicit hydraulic power to W and apply P_shaft = P_h / eta_p."""
    percent, eta = pump_efficiency(efficiency_percent)
    value = nonnegative(hydraulic_value, 'Hydraulic power')
    if power_unit not in POWER_FACTORS:
        raise ValueError('Select a supported hydraulic power unit: W, kW or Mechanical hp.')
    watts = value * POWER_FACTORS[power_unit]
    if not math.isfinite(watts) or (value > 0 and watts == 0):
        raise ValueError('Hydraulic power exceeds the supported numeric range.')
    shaft = watts / eta
    outputs = (shaft, shaft / POWER_FACTORS['kW'], shaft / MECHANICAL_HP_W)
    if any(not math.isfinite(v) for v in outputs) or (watts > 0 and any(v <= 0 for v in outputs)):
        raise ValueError('Pump shaft power exceeds the supported numeric range.')
    return ShaftPower(watts, percent, *outputs)


def shaft_power_from_conditions(*, density, density_unit, flow, flow_unit,
                                head_m, efficiency_percent, density_factors, flow_factors):
    """Share the accepted Phase 3A kernel; no hydraulic equation duplication."""
    pump_efficiency(efficiency_percent)
    hydraulic = hydraulic_power(density=density, density_unit=density_unit,
                                flow=flow, flow_unit=flow_unit, head_m=head_m,
                                density_factors=density_factors, flow_factors=flow_factors)
    return shaft_power(hydraulic.watts, 'W', efficiency_percent)
