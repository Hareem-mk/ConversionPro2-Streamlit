"""Phase 3C: motor input power only, excluding electrical sizing/selection."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_capacity import nonnegative
from .shaft_power import POWER_FACTORS, pump_efficiency, shaft_power_from_conditions


@dataclass(frozen=True)
class MotorPower:
    shaft_watts: float
    motor_efficiency_percent: float
    input_watts: float
    input_kilowatts: float
    input_mechanical_hp: float
    hydraulic_watts: float | None = None
    pump_efficiency_percent: float | None = None


def motor_efficiency(efficiency_percent):
    """Reuse Phase 3B's percent validation with motor-specific diagnostics."""
    try:
        return pump_efficiency(efficiency_percent)
    except ValueError as exc:
        raise ValueError(str(exc).replace('Pump efficiency', 'Motor efficiency')) from None


def motor_power(shaft_value, power_unit, motor_efficiency_percent):
    percent, eta = motor_efficiency(motor_efficiency_percent)
    value = nonnegative(shaft_value, 'Pump shaft / brake power')
    if power_unit not in POWER_FACTORS:
        raise ValueError('Select a supported shaft power unit: W, kW or Mechanical hp.')
    watts = value * POWER_FACTORS[power_unit]
    if not math.isfinite(watts) or (value > 0 and watts == 0):
        raise ValueError('Pump shaft power exceeds the supported numeric range.')
    input_watts = watts / eta
    outputs = (input_watts, input_watts / POWER_FACTORS['kW'],
               input_watts / POWER_FACTORS['Mechanical hp'])
    if any(not math.isfinite(v) for v in outputs) or (watts > 0 and any(v <= 0 for v in outputs)):
        raise ValueError('Motor input power exceeds the supported numeric range.')
    return MotorPower(watts, percent, *outputs)


def motor_power_from_conditions(*, density, density_unit, flow, flow_unit, head_m,
                                pump_efficiency_percent, motor_efficiency_percent,
                                density_factors, flow_factors):
    """Chain the validated Phase 3A/3B kernels without repeating their equations."""
    motor_efficiency(motor_efficiency_percent)
    shaft = shaft_power_from_conditions(density=density, density_unit=density_unit,
                                        flow=flow, flow_unit=flow_unit, head_m=head_m,
                                        efficiency_percent=pump_efficiency_percent,
                                        density_factors=density_factors, flow_factors=flow_factors)
    motor = motor_power(shaft.shaft_watts, 'W', motor_efficiency_percent)
    return MotorPower(motor.shaft_watts, motor.motor_efficiency_percent,
                      motor.input_watts, motor.input_kilowatts, motor.input_mechanical_hp,
                      shaft.hydraulic_watts, shaft.efficiency_percent)
