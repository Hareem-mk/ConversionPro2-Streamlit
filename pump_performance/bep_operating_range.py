"""Phase 3H: compare SI flows with explicitly supplied vendor BEP and limits."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative


@dataclass(frozen=True)
class BEPComparison:
    operating_flow_m3_s: float
    bep_flow_m3_s: float
    percent_bep: float
    deviation_m3_s: float
    percent_deviation: float


def compare_bep(operating_flow_si, bep_flow_si):
    operating = nonnegative(operating_flow_si, 'Operating Flow')
    bep = positive(bep_flow_si, 'Vendor BEP Flow')
    deviation = operating - bep
    percent = (operating / bep) * 100
    percent_deviation = (deviation / bep) * 100
    if not all(math.isfinite(v) for v in (percent, deviation, percent_deviation)):
        raise ValueError('BEP comparison exceeds the supported numeric range.')
    if operating > 0 and percent == 0:
        raise ValueError('BEP comparison exceeds the supported numeric range.')
    return BEPComparison(operating, bep, percent, deviation, percent_deviation)


def validate_user_range(min_percent, max_percent):
    minimum = positive(min_percent, 'Minimum Recommended Flow (% of BEP)')
    maximum = positive(max_percent, 'Maximum Recommended Flow (% of BEP)')
    if maximum <= minimum:
        raise ValueError('Maximum Recommended Flow must be greater than Minimum Recommended Flow; limits are not swapped.')
    return minimum, maximum


def classify_user_range(percent_bep, min_percent, max_percent):
    percent = nonnegative(percent_bep, 'Percent of BEP')
    minimum, maximum = validate_user_range(min_percent, max_percent)
    if percent < minimum:
        return 'Below entered operating range'
    if percent > maximum:
        return 'Above entered operating range'
    return 'Within entered operating range'
