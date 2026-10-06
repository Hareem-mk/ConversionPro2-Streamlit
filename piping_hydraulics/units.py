"""Adapter receiving the validated Phase 1 FLOW table without duplicating it."""
import math
from .pipe_geometry import positive


def flow_to_si(value, unit, flow_factors):
    value = positive(value, 'Flow rate')
    if unit not in flow_factors:
        raise ValueError('Select a supported volumetric flow unit.')
    q = value * positive(flow_factors[unit], 'Flow conversion factor')
    if not math.isfinite(q) or q <= 0:
        raise ValueError('Converted flow exceeds the supported numeric range.')
    return q
