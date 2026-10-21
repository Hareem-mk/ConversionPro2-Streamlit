"""Phase 3J: supplied vendor NPSHR comparison; no NPSHR prediction."""
from dataclasses import dataclass
import math

from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pump_head import finite_signed
from piping_hydraulics.npsha import NPSHAvailable

STATUS_ABS_TOL_M = 1e-9
STATUS_REL_TOL = 1e-10


@dataclass(frozen=True)
class NPSHMarginResult:
    npsha_m: float
    npshr_m: float
    margin_m: float
    ratio: float
    percent_margin: float
    relationship_status: str


@dataclass(frozen=True)
class RequiredMarginResult:
    actual_margin_m: float
    required_margin_m: float
    excess_margin_m: float
    criterion_status: str


def _compare(npsha_m, npshr_m):
    # Manual and Phase 2H adapters establish their respective available-head
    # contracts before entering this shared comparison. R is checked before /.
    required = positive(npshr_m, 'Vendor NPSHR')
    available = finite_signed(npsha_m, 'NPSHA')
    margin = available - required
    ratio = available / required
    percent = (margin / required) * 100
    if any(not math.isfinite(v) for v in (margin, ratio, percent)) or (
            available != 0 and ratio == 0) or (margin != 0 and percent == 0):
        raise ValueError('NPSH comparison exceeds the supported numeric range.')
    if math.isclose(available, required, rel_tol=STATUS_REL_TOL, abs_tol=STATUS_ABS_TOL_M):
        status = 'NPSHA equals entered NPSHR.'
    elif available > required:
        status = 'NPSHA is above entered NPSHR.'
    else:
        status = 'NPSHA is below entered NPSHR.'
    return NPSHMarginResult(available, required, margin, ratio, percent, status)


def calculate_npsh_margin(npsha_m, npshr_m):
    """Manual entry requires nonnegative NPSHA; vendor NPSHR is strictly >0."""
    return _compare(nonnegative(npsha_m, 'Manual NPSHA'), npshr_m)


def margin_from_phase2h(available, npshr_m):
    """Preserve the signed result and warnings of a validated Phase 2H result.

    This adapter performs no available-head equation; call flange_npsha or
    source_npsha first. UI retains/displays that object's engineering warnings.
    """
    if not isinstance(available, NPSHAvailable):
        raise ValueError('Use a calculated Phase 2H NPSHA result.')
    return _compare(available.total_npsha_m, npshr_m)


def compare_required_margin(actual_margin_m, required_margin_m):
    actual = finite_signed(actual_margin_m, 'Actual NPSH Margin')
    required = nonnegative(required_margin_m, 'User/Vendor/Project Required NPSH Margin')
    excess = actual - required
    if not math.isfinite(excess):
        raise ValueError('Required-margin comparison exceeds the supported numeric range.')
    # Exact inclusive comparison of the represented values. Relationship-status
    # tolerance above does not alter raw values or relax the entered criterion.
    status = 'Meets entered required margin' if actual >= required else 'Does not meet entered required margin'
    return RequiredMarginResult(actual, required, excess, status)
