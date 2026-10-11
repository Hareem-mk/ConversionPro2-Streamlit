"""Phase 3A: useful hydraulic power only; no efficiency or shaft-power model."""
from dataclasses import dataclass
import math

from advanced_engineering import G
from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.units import flow_to_si

# Phase 1's display table rounds this factor; retain that accepted table unchanged.
MECHANICAL_HP_W = 745.6998715822702


@dataclass(frozen=True)
class HydraulicPower:
    density_kg_m3: float
    flow_m3_s: float
    head_m: float
    watts: float
    kilowatts: float
    mechanical_hp: float


def hydraulic_power(*, density, density_unit, flow, flow_unit, head_m,
                    density_factors, flow_factors):
    """Use the application's validated SI factor tables and positive-flow adapter."""
    rho = positive(density, 'Fluid density')
    if density_unit not in density_factors:
        raise ValueError('Select a supported fluid density unit.')
    rho *= positive(density_factors[density_unit], 'Density conversion factor')
    rho = positive(rho, 'Converted fluid density')
    q = nonnegative(flow, 'Volumetric flow rate')
    h = nonnegative(head_m, 'Pump head')
    if q == 0:
        # The Phase 2 adapter intentionally requires positive flow. Validate the
        # explicit unit and factor here without changing its existing contract.
        if flow_unit not in flow_factors:
            raise ValueError('Select a supported volumetric flow unit.')
        positive(flow_factors[flow_unit], 'Flow conversion factor')
    else:
        q = flow_to_si(q, flow_unit, flow_factors)
    watts = 0.0 if q == 0 or h == 0 else rho * G * q * h
    values = (watts, watts / 1000, watts / MECHANICAL_HP_W)
    if any(not math.isfinite(v) for v in values) or (
            q > 0 and h > 0 and any(v <= 0 for v in values)):
        raise ValueError('Hydraulic power exceeds the supported numeric range.')
    return HydraulicPower(rho, q, h, *values)
