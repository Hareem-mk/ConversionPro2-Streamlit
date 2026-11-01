"""Deterministic wrappers around Phase 3W; no alternate cash-flow engine."""
from dataclasses import dataclass, replace
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pump_head import finite_signed
from . import annual_energy, lifecycle_cost

MANUAL='Manual Annual Operating Costs'
ENERGY='Phase 3V Annual Electrical Energy / Tariff'
POWER='Phase 3V Constant Electrical Input Power / Hours'
SOURCES=(MANUAL,ENERGY,POWER)
CAPEX='Proposed CAPEX'
DIFFERENCE='Annual Operating Cost Difference'
TARIFF='Electricity Tariff'
HOURS='Annual Operating Hours'
DISCOUNT='Discount Rate (%)'
PERIOD='Analysis Period (years)'
RANK_METRICS=('Highest NPV','Lowest Proposed Lifecycle Cost','Shortest Simple Payback')

@dataclass(frozen=True)
class EconomicCase:
    baseline_capex: float
    proposed_capex: float
    analysis_years: int
    discount_rate_percent: float
    source: str = MANUAL
    baseline_annual_cost: float | None = None
    proposed_annual_cost: float | None = None
    baseline_energy_kwh: float | None = None
    proposed_energy_kwh: float | None = None
    tariff: float | None = None
    baseline_power_kw: float | None = None
    proposed_power_kw: float | None = None
    operating_hours: float | None = None
    baseline_maintenance: float | None = None
    proposed_maintenance: float | None = None
    escalation_percent: float | None = None
    baseline_residual: float | None = None
    proposed_residual: float | None = None

@dataclass(frozen=True)
class EconomicScenarioResult:
    name: str
    case: EconomicCase
    result: lifecycle_cost.EconomicComparisonResult | None
    error: str | None = None

@dataclass(frozen=True)
class SensitivityPoint:
    value: float
    case: EconomicCase | None
    result: lifecycle_cost.EconomicComparisonResult | None
    error: str | None = None

@dataclass(frozen=True)
class SensitivitySeries:
    variable: str
    base_value: float
    base_result: lifecycle_cost.EconomicComparisonResult
    points: tuple[SensitivityPoint,...]

@dataclass(frozen=True)
class BreakEvenResult:
    label: str
    value: float | None
    unit: str
    guidance: str
    npv_at_threshold: float | None = None


def electrical_energies(case):
    if case.source==ENERGY:
        return (nonnegative(case.baseline_energy_kwh,'Baseline Annual Electrical Energy'),
                nonnegative(case.proposed_energy_kwh,'Proposed Annual Electrical Energy'))
    if case.source==POWER:
        # One constant supply electrical-input power per alternative; same entered hours.
        return (annual_energy.calculate_energy(case.baseline_power_kw,case.operating_hours),
                annual_energy.calculate_energy(case.proposed_power_kw,case.operating_hours))
    raise ValueError('Electrical-energy data require an explicit Phase 3V source.')


def annual_costs(case):
    if case.source==MANUAL:
        return (nonnegative(case.baseline_annual_cost,'Baseline Annual Operating Cost'),
                nonnegative(case.proposed_annual_cost,'Proposed Annual Operating Cost'))
    if case.source in (ENERGY,POWER):
        a,b=electrical_energies(case)
        return lifecycle_cost.annual_costs_from_energy(a,b,case.tariff)
    raise ValueError('Select a supported annual-cost source.')


def evaluate_economic_scenario(case,name='Scenario'):
    """Every defined economic result, including paybacks, comes from Phase 3W."""
    a,b=annual_costs(case)
    result=lifecycle_cost.calculate_economic_comparison(a,b,case.baseline_capex,case.proposed_capex,
        case.analysis_years,case.discount_rate_percent,baseline_maintenance=case.baseline_maintenance,
        proposed_maintenance=case.proposed_maintenance,escalation_percent=case.escalation_percent,
        baseline_residual=case.baseline_residual,proposed_residual=case.proposed_residual)
    return EconomicScenarioResult(str(name),case,result)


def available_variables(case):
    evaluate_economic_scenario(case)  # Do not offer variables for an invalid base.
    variables=[CAPEX,DISCOUNT,PERIOD]
    if case.source==MANUAL:variables.insert(1,DIFFERENCE)
    if case.source in (ENERGY,POWER):variables.insert(1,TARIFF)
    if case.source==POWER:variables.insert(2,HOURS)
    return tuple(variables)


def variable_value(case,variable):
    if variable==CAPEX:return finite_signed(case.proposed_capex,CAPEX)
    if variable==DIFFERENCE:
        a,b=annual_costs(case);return a-b
    mapping={TARIFF:'tariff',HOURS:'operating_hours',DISCOUNT:'discount_rate_percent',PERIOD:'analysis_years'}
    if variable not in mapping:raise ValueError('Select a supported sensitivity variable.')
    return finite_signed(getattr(case,mapping[variable]),variable)


def vary_case(case,variable,value):
    value=finite_signed(value,'Selected Variable Value')
    if variable==DIFFERENCE:
        a,_=annual_costs(case)
        return replace(case,proposed_annual_cost=finite_signed(a-value,'Proposed annual cost after difference change'))
    mapping={CAPEX:'proposed_capex',TARIFF:'tariff',HOURS:'operating_hours',DISCOUNT:'discount_rate_percent',PERIOD:'analysis_years'}
    if variable not in mapping:raise ValueError('Select a supported sensitivity variable.')
    return replace(case,**{mapping[variable]:value})


def run_one_variable_sensitivity(base_case,variable_name,values,*,percentage=False):
    base=evaluate_economic_scenario(base_case,'Base Case').result
    if variable_name not in available_variables(base_case):raise ValueError('Selected variable is not supported by the entered base data.')
    origin=variable_value(base_case,variable_name);values=tuple(values)
    if not values:raise ValueError('Enter at least one sensitivity value; no range is assumed.')
    points=[]
    for entered in values:
        value=finite_signed(entered,'Percentage Variation (%)' if percentage else 'Sensitivity Value')
        if percentage:value=finite_signed(origin*(1+value/100),'Value after percentage variation')
        case=None
        try:
            case=vary_case(base_case,variable_name,value)
            points.append(SensitivityPoint(value,case,evaluate_economic_scenario(case).result))
        except (ValueError,OverflowError) as error:
            points.append(SensitivityPoint(value,case,None,str(error)))
    return SensitivitySeries(variable_name,origin,base,tuple(points))


def evaluate_scenarios(named_cases):
    rows=[]
    for name,case in named_cases:
        try:rows.append(evaluate_economic_scenario(case,name))
        except (ValueError,OverflowError) as error:rows.append(EconomicScenarioResult(str(name),case,None,str(error)))
    if not rows:raise ValueError('Enter at least one explicit scenario.')
    return tuple(rows)


def rank_scenarios(results,metric):
    if metric not in RANK_METRICS:raise ValueError('Select a ranking metric explicitly.')
    def key(row):
        if row.result is None:return (True,0)
        r=row.result
        value=-r.npv if metric==RANK_METRICS[0] else (r.proposed.lifecycle_cost if metric==RANK_METRICS[1] else r.simple_payback_years)
        return (value is None,0 if value is None else value)
    return tuple(sorted(results,key=key))  # Stable ties; undefined metrics last, never zero payback.


def _unavailable(label,unit,reason):return BreakEvenResult(label,None,unit,reason)


def calculate_break_even_capex(case):
    evaluate_economic_scenario(case)
    label='Break-Even Incremental CAPEX under Entered Assumptions'
    result=evaluate_economic_scenario(replace(case,proposed_capex=case.baseline_capex)).result
    threshold=result.npv  # Phase 3W PV benefit with zero initial difference.
    proposed=finite_signed(case.baseline_capex+threshold,'Break-even proposed CAPEX')
    if proposed<0:return _unavailable(label,'currency','No feasible nonnegative proposed CAPEX gives zero NPV under the entered assumptions.')
    check=evaluate_economic_scenario(replace(case,proposed_capex=proposed)).result.npv
    return BreakEvenResult(label,threshold,'currency','Incremental threshold; corresponding proposed all-in CAPEX = baseline CAPEX + this value. Not an approved budget.',check)


def _operating_coefficient(case):
    # Evaluate a unit operating difference through Phase 3W. These numerical probes
    # are not user assumptions; optional maintenance/residual contributions are removed.
    probe=replace(case,source=MANUAL,baseline_annual_cost=1,proposed_annual_cost=0,
        baseline_capex=0,proposed_capex=0,baseline_maintenance=None,proposed_maintenance=None,
        baseline_residual=None,proposed_residual=None)
    return evaluate_economic_scenario(probe).result.npv


def calculate_break_even_annual_cost_difference(case):
    evaluate_economic_scenario(case)
    label='Break-Even Annual Operating Cost Difference under Entered Assumptions'
    if case.source!=MANUAL:return _unavailable(label,'currency/year','Available on a manual-cost basis; use tariff sensitivity for electrical-energy cases.')
    a,_=annual_costs(case)
    intercept=evaluate_economic_scenario(replace(case,proposed_annual_cost=a)).result.npv
    slope=_operating_coefficient(case)
    if slope<=0:return _unavailable(label,'currency/year','No numerically resolvable positive operating-cost coefficient.')
    threshold=finite_signed(-intercept/slope,'Break-even annual cost difference')
    if a-threshold<0:return _unavailable(label,'currency/year','Threshold would require a negative proposed annual operating cost while baseline cost is held fixed.')
    check=evaluate_economic_scenario(vary_case(case,DIFFERENCE,threshold)).result.npv
    return BreakEvenResult(label,threshold,'currency/year','Baseline operating cost is held fixed; proposed cost = baseline cost − entered difference. Maintenance, escalation and residuals remain included through Phase 3W.',check)


def calculate_break_even_analysis_period(case):
    label='Break-Even Analysis Period under Entered Assumptions'
    r=evaluate_economic_scenario(case).result
    if nonnegative(case.discount_rate_percent,'Discount Rate (%)')!=0 or finite_signed(case.escalation_percent if case.escalation_percent is not None else 0,'Escalation (%)')!=0 or nonnegative(case.baseline_residual if case.baseline_residual is not None else 0,'Baseline Residual')!=0 or nonnegative(case.proposed_residual if case.proposed_residual is not None else 0,'Proposed Residual')!=0:
        return _unavailable(label,'years','Decimal period threshold is available only at 0% discount, no escalation and no residual values, with constant annual cash flow.')
    annual=r.rows[1].net_cash_flow
    if r.incremental_capex<=0 or annual<=0:return _unavailable(label,'years','A positive incremental investment and positive constant annual net benefit are required.')
    value=finite_signed(r.incremental_capex/annual,'Break-even analysis period')
    return BreakEvenResult(label,value,'years','Decimal threshold uses the constant annual net cash flow returned by Phase 3W, including maintenance. The integer end-of-year model first recovers at the ceiling of this threshold; no fractional-year cash flow is added.')


def calculate_break_even_tariff(case):
    evaluate_economic_scenario(case)
    label='Break-Even Electricity Tariff under Entered Assumptions'
    if case.source not in (ENERGY,POWER):return _unavailable(label,'currency/kWh','Explicit annual electrical-energy data and tariff source are required.')
    a,b=electrical_energies(case)
    if a<=b:return _unavailable(label,'currency/kWh','A positive baseline-minus-proposed electrical-energy difference is required.')
    intercept=evaluate_economic_scenario(replace(case,tariff=0)).result.npv
    probe=replace(case,tariff=1,baseline_capex=0,proposed_capex=0,baseline_maintenance=None,proposed_maintenance=None,baseline_residual=None,proposed_residual=None)
    slope=evaluate_economic_scenario(probe).result.npv
    if slope<=0:return _unavailable(label,'currency/kWh','No numerically resolvable positive tariff coefficient.')
    threshold=finite_signed(-intercept/slope,'Break-even tariff')
    if threshold<0:return _unavailable(label,'currency/kWh','No nonnegative tariff gives zero NPV under the entered assumptions.')
    check=evaluate_economic_scenario(replace(case,tariff=threshold)).result.npv
    return BreakEvenResult(label,threshold,'currency/kWh','All entered maintenance, escalation, initial and residual contributions are included through Phase 3W; electrical costs use Phase 3V.',check)


def break_even_results(case):
    evaluate_economic_scenario(case)
    return (calculate_break_even_capex(case),calculate_break_even_annual_cost_difference(case),
        calculate_break_even_analysis_period(case),calculate_break_even_tariff(case))
