"""Phase 3K: duty screening with explicitly supplied criteria; no pump selection."""
from dataclasses import dataclass
import math
from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pump_head import finite_signed
from .bep_operating_range import BEPComparison, compare_bep, classify_user_range
from .npsh_margin import NPSHMarginResult, RequiredMarginResult, calculate_npsh_margin, compare_required_margin

# Numerical reporting tolerance, not an engineering acceptance allowance.
DUTY_REL_TOL = 1e-12
FLOW_ABS_TOL_M3_S = 1e-15
HEAD_ABS_TOL_M = 1e-9
PERCENT_ROUNDOFF_TOL = 1e-9


@dataclass(frozen=True)
class DutyPointCheckResult:
    required_flow_m3_s: float
    operating_flow_m3_s: float
    required_head_m: float
    operating_head_m: float
    flow_difference_m3_s: float
    flow_deviation_percent: float
    head_difference_m: float
    head_deviation_percent: float
    flow_matches: bool
    head_matches: bool


@dataclass(frozen=True)
class DriverPowerMarginResult:
    shaft_power_w: float
    driver_rating_w: float
    margin_w: float
    margin_percent: float | None
    relationship_status: str


@dataclass(frozen=True)
class DutyScreeningResult:
    duty: DutyPointCheckResult
    bep: BEPComparison | None
    npsh: NPSHMarginResult | None
    driver: DriverPowerMarginResult | None
    flow_tolerance_status: str | None
    head_tolerance_status: str | None
    bep_range_status: str | None
    required_npsh_margin: RequiredMarginResult | None
    driver_criterion_status: str | None


def _deviation(required, operating):
    difference = operating - required
    percent = (difference / required) * 100
    if not math.isfinite(difference) or not math.isfinite(percent) or (difference != 0 and percent == 0):
        raise ValueError('Duty deviation exceeds the supported numeric range.')
    return difference, percent


def calculate_duty_deviation(required_flow_si, operating_flow_si, required_head_m, operating_head_m):
    required_q = positive(required_flow_si, 'Required Duty Flow')
    q = nonnegative(operating_flow_si, 'Pump Operating Flow')
    required_h = positive(required_head_m, 'Required Duty Head')
    h = nonnegative(operating_head_m, 'Pump Operating Head')
    dq, qp = _deviation(required_q, q)
    dh, hp = _deviation(required_h, h)
    return DutyPointCheckResult(required_q, q, required_h, h, dq, qp, dh, hp,
        abs(qp) <= PERCENT_ROUNDOFF_TOL and math.isclose(q,required_q,rel_tol=DUTY_REL_TOL,abs_tol=FLOW_ABS_TOL_M3_S),
        abs(hp) <= PERCENT_ROUNDOFF_TOL and math.isclose(h,required_h,rel_tol=DUTY_REL_TOL,abs_tol=HEAD_ABS_TOL_M))


def compare_tolerance(deviation_percent, entered_tolerance_percent):
    deviation = abs(finite_signed(deviation_percent, 'Duty deviation (%)'))
    tolerance = nonnegative(entered_tolerance_percent, 'Allowed Duty Deviation (%)')
    met = deviation <= tolerance or math.isclose(deviation,tolerance,rel_tol=DUTY_REL_TOL,abs_tol=PERCENT_ROUNDOFF_TOL)
    return 'Meets entered duty tolerance' if met else 'Outside entered duty tolerance'


def calculate_driver_margin(shaft_power_w, driver_rating_w):
    shaft = nonnegative(shaft_power_w, 'Pump Shaft Power')
    rating = positive(driver_rating_w, 'Driver Rated Power')
    margin = rating - shaft
    percent = None if shaft == 0 else (margin / shaft) * 100
    if not math.isfinite(margin) or (percent is not None and (not math.isfinite(percent) or (margin != 0 and percent == 0))):
        raise ValueError('Driver power margin exceeds the supported numeric range.')
    status = ('Entered driver rating is below calculated shaft power.' if rating < shaft else
              'Entered driver rating equals calculated shaft power.' if rating == shaft else
              'Entered driver rating is above calculated shaft power.')
    return DriverPowerMarginResult(shaft,rating,margin,percent,status)


def check_duty_point(*, required_flow_si, operating_flow_si, required_head_m, operating_head_m,
                     shaft_power_w, bep_flow_si=None, npsha_m=None, npshr_m=None, driver_rating_w=None,
                     flow_tolerance_percent=None, head_tolerance_percent=None,
                     bep_min_percent=None, bep_max_percent=None, required_npsh_margin_m=None,
                     required_driver_margin_percent=None):
    duty = calculate_duty_deviation(required_flow_si,operating_flow_si,required_head_m,operating_head_m)
    shaft = nonnegative(shaft_power_w,'Pump Shaft Power')
    bep = None if bep_flow_si is None else compare_bep(duty.operating_flow_m3_s,bep_flow_si)
    bep_status = None
    if bep_min_percent is not None or bep_max_percent is not None:
        if bep is None:raise ValueError('Enter Vendor BEP Flow to apply BEP range criteria.')
        bep_status = classify_user_range(bep.percent_bep,bep_min_percent,bep_max_percent)
    npsh = None
    if npsha_m is not None or npshr_m is not None:
        npsh = calculate_npsh_margin(npsha_m,npshr_m)
    npsh_criterion = None
    if required_npsh_margin_m is not None:
        if npsh is None:raise ValueError('Enter NPSHA and Vendor NPSHR to apply the required NPSH margin.')
        npsh_criterion = compare_required_margin(npsh.margin_m,required_npsh_margin_m)
    driver = None if driver_rating_w is None else calculate_driver_margin(shaft,driver_rating_w)
    driver_status = None
    if required_driver_margin_percent is not None:
        minimum = nonnegative(required_driver_margin_percent,'Minimum Required Driver Power Margin (%)')
        if driver is None:raise ValueError('Enter Driver Rated Power to apply the driver margin criterion.')
        if driver.margin_percent is None:
            driver_status = 'Requires vendor/project review — percent margin is N/A because shaft power is zero.'
        else:
            driver_status = ('Meets entered driver power margin' if driver.margin_percent >= minimum else
                             'Does not meet entered driver power margin')
    return DutyScreeningResult(duty,bep,npsh,driver,
        None if flow_tolerance_percent is None else compare_tolerance(duty.flow_deviation_percent,flow_tolerance_percent),
        None if head_tolerance_percent is None else compare_tolerance(duty.head_deviation_percent,head_tolerance_percent),
        bep_status,npsh_criterion,driver_status)
