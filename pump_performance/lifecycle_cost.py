"""End-of-year incremental economics. Rates enter as percent; no assumed finances."""
from dataclasses import dataclass
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pump_head import finite_signed
from . import annual_energy

NO_PAYBACK = 'Simple payback is not defined because the proposed case does not produce a positive annual operating-cost difference under the entered assumptions.'
LOWER_INITIAL = 'Proposed initial cost is lower than baseline initial cost under the entered assumptions.'
NOT_RECOVERED = 'Discounted payback is not reached within the selected analysis period.'

@dataclass(frozen=True)
class LifecycleCostResult:
    initial_cost: float
    pv_operating_cost: float
    pv_maintenance_cost: float
    pv_residual_value: float
    lifecycle_cost: float

@dataclass(frozen=True)
class AnnualEconomicCashFlow:
    year: int
    baseline_operating_cost: float
    proposed_operating_cost: float
    annual_cost_difference: float
    maintenance_difference: float
    terminal_residual_difference: float
    net_cash_flow: float
    discount_factor: float
    discounted_cash_flow: float
    cumulative_undiscounted: float
    cumulative_discounted: float

@dataclass(frozen=True)
class EconomicComparisonResult:
    annual_cost_difference: float
    incremental_capex: float
    simple_payback_years: float | None
    simple_payback_status: str
    npv: float
    discounted_payback_year: int | None
    discounted_payback_status: str
    baseline: LifecycleCostResult
    proposed: LifecycleCostResult
    lifecycle_cost_difference: float
    rows: tuple[AnnualEconomicCashFlow, ...]


def _sum(values):
    try: return finite_signed(math.fsum(values), 'Calculated cash-flow total')
    except OverflowError: raise ValueError('Cash-flow total exceeds supported numeric range.') from None


def _year(year, allow_zero=False):
    value=nonnegative(year,'Year / analysis period')
    if value != int(value) or value < (0 if allow_zero else 1):
        raise ValueError('Analysis period must be integer years >= 1 (cash-flow year may be 0).')
    return int(value)


def _optional(value,label):
    return 0.0 if value is None else nonnegative(value,label)


def initial_cost(capex, *, installation=None, engineering=None, commissioning=None, other=None):
    """Detailed mode receives equipment CAPEX only, never a simple all-in CAPEX."""
    return _sum([nonnegative(capex,'CAPEX')]+[_optional(x,label) for x,label in (
        (installation,'Installation cost'),(engineering,'Engineering cost'),
        (commissioning,'Commissioning cost'),(other,'Other one-time cost'))])


def annual_costs_from_energy(baseline_kwh, proposed_kwh, tariff):
    """Delegate electrical energy pricing to the accepted Phase 3V kernel."""
    return (annual_energy.calculate_operating_cost(baseline_kwh,tariff),
            annual_energy.calculate_operating_cost(proposed_kwh,tariff))


def calculate_simple_payback(incremental_capex, annual_cost_difference):
    capex=finite_signed(incremental_capex,'Incremental CAPEX')
    difference=finite_signed(annual_cost_difference,'Annual operating-cost difference')
    if capex <= 0 or difference <= 0: return None
    return finite_signed(capex/difference,'Simple payback')


def discount_cash_flow(cash_flow, discount_rate_percent, year):
    cash=finite_signed(cash_flow,'Cash flow'); rate=nonnegative(discount_rate_percent,'Discount Rate (%)')/100
    year=_year(year,True)
    # Negative exponent avoids overflowing the positive denominator at long horizons.
    factor=math.exp(-year*math.log1p(rate))
    return finite_signed(cash*factor,'Discounted cash flow')


def calculate_npv(incremental_capex, annual_cash_flows, discount_rate_percent):
    initial=finite_signed(incremental_capex,'Incremental CAPEX')
    nonnegative(discount_rate_percent,'Discount Rate (%)')
    return _sum([-initial]+[discount_cash_flow(cf,discount_rate_percent,i) for i,cf in enumerate(annual_cash_flows,1)])


def calculate_economic_comparison(baseline_annual_cost, proposed_annual_cost,
        baseline_initial_cost, proposed_initial_cost, analysis_years, discount_rate_percent,
        *, baseline_maintenance=None, proposed_maintenance=None, escalation_percent=None,
        baseline_residual=None, proposed_residual=None):
    """Year 1 is entered cost; escalation starts Year 2, on operating costs only.

    Blank optional contributions are excluded. Simple payback uses the entered
    operating-cost difference only; maintenance/escalation/residual enter NPV.
    Discounted payback is the first whole end-of-year crossing, without interpolation.
    """
    a=nonnegative(baseline_annual_cost,'Baseline Annual Operating Cost')
    b=nonnegative(proposed_annual_cost,'Proposed Annual Operating Cost')
    ia=nonnegative(baseline_initial_cost,'Baseline Initial Cost'); ib=nonnegative(proposed_initial_cost,'Proposed Initial Cost')
    years=_year(analysis_years); nonnegative(discount_rate_percent,'Discount Rate (%)')
    ma=_optional(baseline_maintenance,'Baseline Annual Maintenance Cost'); mb=_optional(proposed_maintenance,'Proposed Annual Maintenance Cost')
    ra=_optional(baseline_residual,'Baseline Residual Value'); rb=_optional(proposed_residual,'Proposed Residual Value')
    escalation=0.0 if escalation_percent is None else finite_signed(escalation_percent,'Annual Operating / Energy-Cost Escalation (%)')/100
    if escalation <= -1: raise ValueError('Escalation must be greater than -100%.')
    increment=ib-ia; difference=a-b
    payback=calculate_simple_payback(increment,difference)
    status=NO_PAYBACK if difference<=0 else ('Simple payback uses entered annual operating costs only.' if increment>0 else (LOWER_INITIAL if increment<0 else 'Simple payback is not defined because incremental initial cost is zero.'))
    rows=[AnnualEconomicCashFlow(0,0,0,0,0,0,-increment,1,-increment,-increment,-increment)]
    cash=[-increment]; discounted=[-increment]; opa=[]; opb=[]; mpa=[]; mpb=[]; recovered=None
    for year in range(1,years+1):
        factor=discount_cash_flow(1,discount_rate_percent,year)
        terminal=rb-ra if year==years else 0
        net=_sum([a,-b,ma,-mb,terminal]); pv=finite_signed(net*factor,'Discounted cash flow')
        cash.append(net); discounted.append(pv)
        cu=_sum(cash); cd=_sum(discounted)
        if increment>0 and recovered is None and cd>=0: recovered=year
        rows.append(AnnualEconomicCashFlow(year,a,b,a-b,ma-mb,terminal,net,factor,pv,cu,cd))
        opa.append(finite_signed(a*factor,'PV operating cost')); opb.append(finite_signed(b*factor,'PV operating cost'))
        mpa.append(ma*factor); mpb.append(mb*factor)
        if year<years:
            a=finite_signed(a*(1+escalation),'Escalated baseline cost'); b=finite_signed(b*(1+escalation),'Escalated proposed cost')
    def lifecycle(initial, operating, maintenance, residual):
        op=_sum(operating); maint=_sum(maintenance); res=discount_cash_flow(residual,discount_rate_percent,years)
        return LifecycleCostResult(initial,op,maint,res,_sum([initial,op,maint,-res]))
    baseline=lifecycle(ia,opa,mpa,ra); proposed=lifecycle(ib,opb,mpb,rb)
    dp=(f'First end-of-year recovery: year {recovered} (no interpolation).' if recovered is not None else NOT_RECOVERED) if increment>0 else 'Discounted payback is not applied because incremental initial cost is not positive.'
    return EconomicComparisonResult(difference,increment,payback,status,_sum(discounted),recovered,dp,baseline,proposed,finite_signed(baseline.lifecycle_cost-proposed.lifecycle_cost,'Lifecycle cost difference'),tuple(rows))
