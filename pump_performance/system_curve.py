"""Phase 3F: independent quadratic system model, SI kernel, no pump intersection."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from .pump_curve import HEAD_FACTORS, curve_flow_to_si


@dataclass(frozen=True)
class SystemHead:
    flow_m3_s: float
    static_head_m: float
    friction_head_m: float
    total_head_m: float


@dataclass(frozen=True)
class SystemModel:
    static_head_m: float
    k_si: float  # s²/m⁵; H_friction(m) = k_si * Q(m³/s)²

    def at_flow(self, flow_m3_s):
        q = nonnegative(flow_m3_s, 'Flow rate')
        static = nonnegative(self.static_head_m, 'Static head')
        friction = system_friction_head(q, self.k_si)
        total = static + friction
        if not math.isfinite(total):
            raise ValueError('Total system head exceeds the supported numeric range.')
        return SystemHead(q, static, friction, total)


def derive_system_k(reference_flow_m3_s, reference_friction_head_m):
    q = positive(reference_flow_m3_s, 'Reference flow')
    head = nonnegative(reference_friction_head_m, 'Reference friction head')
    # Dividing sequentially avoids overflow from squaring a large reference Q.
    k = (head / q) / q if head > 0 else 0.0
    if not math.isfinite(k) or (head > 0 and k == 0):
        raise ValueError('System resistance coefficient exceeds the supported numeric range.')
    return k


def system_friction_head(flow_m3_s, k_si):
    q = nonnegative(flow_m3_s, 'Flow rate')
    k = nonnegative(k_si, 'System resistance coefficient K')
    friction = (k * q) * q if q > 0 and k > 0 else 0.0
    if not math.isfinite(friction) or (q > 0 and k > 0 and friction == 0):
        raise ValueError('Friction head exceeds the supported numeric range.')
    return friction


def system_head(flow_m3_s, static_head_m, k_si):
    return SystemModel(static_head_m, k_si).at_flow(flow_m3_s).total_head_m


def generate_system_curve(model, maximum_flow_m3_s, point_count=81):
    maximum = positive(maximum_flow_m3_s, 'Maximum flow for plot')
    if isinstance(point_count, bool) or not isinstance(point_count, int) or not 25 <= point_count <= 100:
        raise ValueError('Plot point count must be an integer from 25 to 100.')
    flows = [maximum * (index / (point_count - 1)) for index in range(point_count)]
    if any(b <= a for a, b in zip(flows, flows[1:])):
        raise ValueError('Plot flow spacing exceeds the supported numeric range.')
    return tuple(model.at_flow(q) for q in flows)


def head_to_metres(value, unit, label):
    head = nonnegative(value, label)
    if unit not in HEAD_FACTORS:
        raise ValueError('Select a supported head unit: m or ft.')
    metres = head * HEAD_FACTORS[unit]
    if not math.isfinite(metres) or (head > 0 and metres == 0):
        raise ValueError(f'{label} exceeds the supported numeric range.')
    return metres


def head_from_metres(value, unit):
    head = nonnegative(value, 'System head')
    if unit not in HEAD_FACTORS:
        raise ValueError('Select a supported head unit: m or ft.')
    converted = head / HEAD_FACTORS[unit]
    if not math.isfinite(converted):
        raise ValueError('Converted system head exceeds the supported numeric range.')
    return converted


def model_from_k(static_head, head_unit, k_si):
    return SystemModel(head_to_metres(static_head, head_unit, 'Static head'),
                       nonnegative(k_si, 'System resistance coefficient K'))


def model_from_reference(*, static_head, head_unit, reference_flow,
                         reference_friction_head, flow_unit, flow_factors):
    static = head_to_metres(static_head, head_unit, 'Static head')
    q = curve_flow_to_si(reference_flow, flow_unit, flow_factors)
    friction = head_to_metres(reference_friction_head, head_unit, 'Reference friction head')
    return SystemModel(static, derive_system_k(q, friction))
