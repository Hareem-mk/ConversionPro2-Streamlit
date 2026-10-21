"""Phase 3I: scalar speed affinity estimates, SI performance and common speed unit."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative


@dataclass(frozen=True)
class AffinityResult:
    ratio: float
    original_flow_m3_s: float
    estimated_flow_m3_s: float
    original_head_m: float
    estimated_head_m: float
    original_power_w: float
    estimated_power_w: float
    flow_change_percent: float | None
    head_change_percent: float | None
    power_change_percent: float | None


def _scaled(value, ratio, exponent):
    if value == 0:
        return 0.0, None
    estimated = value
    # Sequential multiplication avoids overflow of R**3 when the scaled
    # performance value itself is representable. Ratio is always positive.
    for _ in range(exponent):
        estimated *= ratio
    if not math.isfinite(estimated) or estimated <= 0:
        raise ValueError('Affinity-law estimate exceeds the supported numeric range.')
    change = ((estimated - value) / value) * 100
    if not math.isfinite(change):
        raise ValueError('Affinity-law percent change exceeds the supported numeric range.')
    return estimated, change


def calculate_speed_affinity(flow_si, head_si, power_si, original_speed, new_speed):
    """Estimate one corresponding pump point; this is not a system intersection.

    Both speeds must be in the same unit (UI: rpm). Same pump and impeller;
    cubic shaft-power scaling assumes sufficiently similar efficiency.
    """
    flow = nonnegative(flow_si, 'Original Flow')
    head = nonnegative(head_si, 'Original Head')
    power = nonnegative(power_si, 'Original Pump Shaft/Brake Power')
    original = positive(original_speed, 'Original Rotational Speed')
    new = positive(new_speed, 'New Rotational Speed')
    ratio = new / original
    if not math.isfinite(ratio) or ratio <= 0:
        raise ValueError('Speed Ratio exceeds the supported numeric range.')
    q2, q_change = _scaled(flow, ratio, 1)
    h2, h_change = _scaled(head, ratio, 2)
    p2, p_change = _scaled(power, ratio, 3)
    return AffinityResult(ratio, flow, q2, head, h2, power, p2, q_change, h_change, p_change)
