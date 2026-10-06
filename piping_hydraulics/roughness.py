"""Documented absolute roughness, not Hazen-Williams C or Manning n."""
from dataclasses import dataclass
import math
from .pipe_geometry import positive
from .pipe_capacity import nonnegative

SOURCE_URL = 'https://usepa.github.io/EPANET2.2/3_network_model.html'
CAUTION = ('Tabulated roughness values are representative, not universally exact. Effective roughness '
           'can change with age, corrosion, scaling/deposits, manufacturing method, internal coating/lining, '
           'pipe condition and service history. Confirm the engineering basis for your actual pipe.')


@dataclass(frozen=True)
class RoughnessRecord:
    id: str
    material: str
    condition: str
    original_value: float
    original_units: str
    epsilon_m: float
    source: str
    edition: str
    location: str
    url: str
    notes: str


def _record(id, material, original, epsilon):
    return RoughnessRecord(id, material, 'New pipe', original, '10⁻³ ft', epsilon,
        'US EPA, EPANET Users Manual', 'Release 2.2 (2020), EPA/600/R-20/133',
        'Section 3.1, Pipes; Table 3.2, Roughness Coefficients for New Pipe; printed page 18',
        SOURCE_URL, 'Generic new-pipe category; no product, grade, coating or aged-condition guarantee. '
        'Use the Darcy-Weisbach epsilon column only. ' + CAUTION)


RECORDS = (
    _record('epa_cast_iron', 'Cast Iron', .85, .00025908),
    _record('epa_galvanized_iron', 'Galvanized Iron', .5, .0001524),
    _record('epa_plastic', 'Plastic', .005, .000001524),
    _record('epa_steel', 'Steel', .15, .00004572),
)


def roughness_to_si(epsilon, unit):
    epsilon = nonnegative(epsilon, 'Absolute roughness ε')
    factors = {'m': 1.0, 'mm': .001, 'µm': 1e-6, '10⁻³ ft': .0003048}
    if unit not in factors:
        raise ValueError('Select a supported absolute roughness unit.')
    result = epsilon * factors[unit]
    if not math.isfinite(result) or (epsilon > 0 and result == 0):
        raise ValueError('Roughness exceeds the supported numeric range.')
    return result


def roughness_displays(epsilon_m):
    epsilon_m = nonnegative(epsilon_m, 'Absolute roughness ε')
    result = {'m': epsilon_m, 'mm': epsilon_m*1000, 'µm': epsilon_m*1e6}
    if any(not math.isfinite(x) for x in result.values()):
        raise ValueError('Roughness display exceeds the supported numeric range.')
    return result


def roughness_ratio(epsilon_m, internal_diameter_m):
    epsilon_m = nonnegative(epsilon_m, 'Absolute roughness ε')
    d = positive(internal_diameter_m, 'INTERNAL diameter')
    result = epsilon_m / d
    if not math.isfinite(result) or (epsilon_m > 0 and result == 0):
        raise ValueError('Relative roughness exceeds the supported numeric range.')
    # Pure geometric ratio, not a friction-factor correlation; no .05 clamp.
    return result
