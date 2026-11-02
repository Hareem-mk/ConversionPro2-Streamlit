"""Independent-input sampling around the unchanged Phase 3V/3W economic model."""
from dataclasses import dataclass, replace
import math
import operator
import numpy as np
from piping_hydraulics.pump_head import finite_signed
from . import economic_sensitivity as economics

CAPEX=economics.CAPEX
BASELINE_CAPEX='Baseline CAPEX'
BASELINE_COST='Baseline Annual Operating Cost'
PROPOSED_COST='Proposed Annual Operating Cost'
DIFFERENCE=economics.DIFFERENCE
TARIFF=economics.TARIFF
HOURS=economics.HOURS
DISCOUNT=economics.DISCOUNT
PERIOD=economics.PERIOD
DIRECT_COSTS='Baseline / Proposed Annual Costs'
COST_DIFFERENCE='Annual Operating Cost Difference'
KINDS=('Fixed','Uniform','Triangular','Normal')
PERIOD_KINDS=('Fixed','Integer Uniform')
MIN_VALID_TRIALS=100  # Software display threshold, not a convergence guarantee.
MAX_TRIALS=50000
MAX_RESAMPLE_ATTEMPTS=100
NPV_ZERO_TOLERANCE=1e-8  # Absolute currency units; approximate-zero diagnostic, no sign clamping.
INSUFFICIENT='Insufficient valid simulation trials for reliable summary statistics.'
FIELDS={CAPEX:'proposed_capex',BASELINE_CAPEX:'baseline_capex',BASELINE_COST:'baseline_annual_cost',PROPOSED_COST:'proposed_annual_cost',TARIFF:'tariff',HOURS:'operating_hours',DISCOUNT:'discount_rate_percent',PERIOD:'analysis_years'}
ORDER=(CAPEX,BASELINE_CAPEX,BASELINE_COST,PROPOSED_COST,DIFFERENCE,TARIFF,HOURS,DISCOUNT,PERIOD)

@dataclass(frozen=True)
class DistributionSpec:
    kind: str
    value: float | None = None
    minimum: float | None = None
    most_likely: float | None = None
    maximum: float | None = None
    mean: float | None = None
    standard_deviation: float | None = None

@dataclass(frozen=True)
class SampleBatch:
    values: tuple[float,...]
    rejected_draws: int

@dataclass(frozen=True)
class MonteCarloTrialResult:
    trial: int
    sampled_inputs: tuple[tuple[str,float],...]
    npv: float | None
    simple_payback_years: float | None
    discounted_payback_year: int | None
    lifecycle_cost_difference: float | None
    baseline_lifecycle_cost: float | None
    proposed_lifecycle_cost: float | None
    error: str | None = None

@dataclass(frozen=True)
class DistributionStatistics:
    count: int
    mean: float
    median: float
    standard_deviation: float
    minimum: float
    maximum: float
    percentiles: tuple[tuple[int,float],...]

@dataclass(frozen=True)
class MonteCarloSummary:
    valid_trials: int
    npv: DistributionStatistics
    probability_positive_npv_percent: float
    probability_negative_npv_percent: float
    probability_zero_npv_percent: float
    simple_payback_defined_count: int
    simple_payback_defined_percent: float
    simple_payback: DistributionStatistics | None
    discounted_payback_reached_count: int
    discounted_payback_reached_percent: float
    discounted_payback: DistributionStatistics | None
    lifecycle_cost_difference: DistributionStatistics
    probability_proposed_lifecycle_cost_lower_percent: float

@dataclass(frozen=True)
class RankCorrelationResult:
    variable: str
    rho: float | None
    pairs: int
    guidance: str

@dataclass(frozen=True)
class MonteCarloSimulationResult:
    requested_trials: int
    valid_trials: int
    invalid_trials: int
    rejected_draws: int
    seed: int | None
    base_result: object
    trials: tuple[MonteCarloTrialResult,...]
    summary: MonteCarloSummary | None
    correlations: tuple[RankCorrelationResult,...]
    warning: str | None


def _integer(value,label,minimum=1,maximum=None):
    number=finite_signed(value,label)
    if number!=int(number) or number<minimum or (maximum is not None and number>maximum):
        raise ValueError(f'{label} must be integer >= {minimum}'+(f' and <= {maximum}.' if maximum is not None else '.'))
    return int(number)


def validate_distribution(spec,*,lower=None,upper=None,integer=False):
    if not isinstance(spec,DistributionSpec):raise ValueError('Provide an explicit DistributionSpec.')
    kinds=PERIOD_KINDS if integer else KINDS
    if spec.kind not in kinds:raise ValueError('Select '+('Fixed or Integer Uniform for analysis period.' if integer else 'Fixed, Uniform, Triangular or Normal.'))
    def number(value,label):return finite_signed(value,label)
    def in_domain(value):return (lower is None or value>=lower) and (upper is None or value<=upper)
    if spec.kind=='Fixed':
        value=number(spec.value,'Fixed Value')
        if integer:_integer(value,'Fixed Analysis Period',maximum=2**53-1)
        if not in_domain(value):raise ValueError('Fixed value is outside the valid domain; values are not clamped.')
        return (value,)
    if spec.kind in ('Uniform','Integer Uniform','Triangular'):
        lo=number(spec.minimum,'Minimum');hi=number(spec.maximum,'Maximum')
        if lo>hi:raise ValueError('Maximum must be >= Minimum.')
        if integer:
            _integer(lo,'Minimum Analysis Period');_integer(hi,'Maximum Analysis Period',maximum=2**53-1)
        if not in_domain(lo) or not in_domain(hi):raise ValueError('Distribution bounds must lie within the valid variable domain.')
        if spec.kind=='Triangular':
            mode=number(spec.most_likely,'Most Likely')
            if not lo<=mode<=hi:raise ValueError('Triangular parameters require Minimum <= Most Likely <= Maximum.')
            return lo,mode,hi
        return lo,hi
    mean=number(spec.mean,'Normal Mean');std=number(spec.standard_deviation,'Normal Standard Deviation')
    if std<0:raise ValueError('Normal Standard Deviation must be >= 0.')
    if std==0 and not in_domain(mean):raise ValueError('Zero-deviation normal mean is outside the valid domain.')
    return mean,std


def sample_distribution(spec,n,rng,*,lower=None,upper=None,integer=False):
    """Normal draws are conditioned on the valid domain by bounded rejection.

    Each sample gets at most 100 draws. Fixed/bounded supports must already be
    valid. Negative or nonfinite draws are never replaced with zero.
    """
    n=_integer(n,'Sample Count',maximum=MAX_TRIALS)
    if not isinstance(rng,np.random.Generator):raise ValueError('Use a numpy.random.Generator.')
    args=validate_distribution(spec,lower=lower,upper=upper,integer=integer)
    if spec.kind=='Fixed':values=np.full(n,args[0],dtype=float)
    elif spec.kind=='Integer Uniform':values=rng.integers(int(args[0]),int(args[1]),size=n,endpoint=True).astype(float)
    elif spec.kind=='Uniform':values=np.full(n,args[0]) if args[0]==args[1] else rng.uniform(*args,size=n)
    elif spec.kind=='Triangular':values=np.full(n,args[0]) if args[0]==args[2] else rng.triangular(*args,size=n)
    else:
        values=np.empty(n);pending=np.arange(n);rejected=0
        for _ in range(MAX_RESAMPLE_ATTEMPTS):
            with np.errstate(over='ignore',invalid='ignore'):draws=rng.normal(*args,size=len(pending))
            valid=np.isfinite(draws)
            if lower is not None:valid &= draws>=lower
            if upper is not None:valid &= draws<=upper
            values[pending[valid]]=draws[valid];rejected+=int(np.count_nonzero(~valid));pending=pending[~valid]
            if len(pending)==0:return SampleBatch(tuple(float(v) for v in values),rejected)
        raise ValueError(f'Simulation configuration invalid: normal sampling could not produce valid values within {MAX_RESAMPLE_ATTEMPTS} attempts per sample. Review the entered mean/deviation and valid domain; no clamping or partial summary is used.')
    if not np.all(np.isfinite(values)):raise ValueError('Sample generation exceeds the supported numeric range.')
    return SampleBatch(tuple(float(v) for v in values),0)


def available_variables(case,cost_basis=DIRECT_COSTS):
    economics.evaluate_economic_scenario(case)
    if cost_basis not in (DIRECT_COSTS,COST_DIFFERENCE):raise ValueError('Select an explicit annual-cost uncertainty basis.')
    items=[CAPEX,BASELINE_CAPEX,DISCOUNT,PERIOD]
    if case.source==economics.MANUAL:items.extend((BASELINE_COST,PROPOSED_COST) if cost_basis==DIRECT_COSTS else (DIFFERENCE,))
    elif case.source in (economics.ENERGY,economics.POWER):
        if cost_basis!=DIRECT_COSTS:raise ValueError('Annual-cost-difference sampling requires the manual annual-cost source.')
        items.append(TARIFF)
        if case.source==economics.POWER:items.append(HOURS)
    return tuple(v for v in ORDER if v in items)


def _domain(case,variable):
    if variable==DIFFERENCE:
        a,_=economics.annual_costs(case);return None,a
    return (1,None) if variable==PERIOD else (0,None)


def _case_with_draws(base,draws):
    changes={FIELDS[key]:(int(value) if key==PERIOD else value) for key,value in draws.items() if key!=DIFFERENCE}
    if DIFFERENCE in draws:
        a,_=economics.annual_costs(base)
        changes['proposed_annual_cost']=finite_signed(a-draws[DIFFERENCE],'Proposed Annual Cost from Difference')
    return replace(base,**changes)


def _percentile(sorted_values,percent):
    """Hyndman-Fan type 7: linear interpolation at (n-1)*p/100."""
    index=(len(sorted_values)-1)*percent/100;lo=int(math.floor(index));fraction=index-lo
    if fraction==0:return sorted_values[lo]
    return math.fsum([sorted_values[lo]*(1-fraction),sorted_values[lo+1]*fraction])


def distribution_statistics(values):
    values=tuple(finite_signed(v,'Simulation Output') for v in values)
    if not values:return None
    ordered=sorted(values);n=len(values);scale=max(abs(ordered[0]),abs(ordered[-1]))
    mean=finite_signed(math.fsum(v/n for v in values),'Mean Output')
    std=0.0 if scale==0 else finite_signed(float(np.std(np.asarray(values)/scale,ddof=0))*scale,'Output Standard Deviation')
    percentiles=tuple((p,_percentile(ordered,p)) for p in (5,10,25,50,75,90,95))
    return DistributionStatistics(n,mean,_percentile(ordered,50),std,ordered[0],ordered[-1],percentiles)


def calculate_monte_carlo_summary(trials):
    valid=tuple(t for t in trials if t.error is None and t.npv is not None)
    if len(valid)<MIN_VALID_TRIALS:return None
    npv=distribution_statistics(t.npv for t in valid);n=len(valid)
    zero=sum(abs(t.npv)<=NPV_ZERO_TOLERANCE for t in valid)
    positive=sum(t.npv>0 for t in valid);negative=sum(t.npv<0 for t in valid)
    paybacks=tuple(t.simple_payback_years for t in valid if t.simple_payback_years is not None)
    recovered=tuple(t.discounted_payback_year for t in valid if t.discounted_payback_year is not None)
    return MonteCarloSummary(n,npv,positive/n*100,negative/n*100,zero/n*100,
        len(paybacks),len(paybacks)/n*100,distribution_statistics(paybacks),len(recovered),len(recovered)/n*100,
        distribution_statistics(recovered),distribution_statistics(t.lifecycle_cost_difference for t in valid),
        sum(t.lifecycle_cost_difference>0 for t in valid)/n*100)


def _ranks(values):
    values=np.asarray(values,dtype=float);order=np.argsort(values,kind='stable');ranks=np.empty(len(values),dtype=float)
    start=0
    while start<len(values):
        end=start+1
        while end<len(values) and values[order[end]]==values[order[start]]:end+=1
        ranks[order[start:end]]=(start+1+end)/2;start=end
    return ranks


def calculate_rank_correlations(samples,npv_results):
    """Spearman rho = Pearson correlation of average ranks; paired valid trials only."""
    output=tuple(finite_signed(v,'NPV') for v in npv_results);n=len(output);rows=[]
    for variable,values in samples.items():
        values=tuple(finite_signed(v,variable) for v in values)
        if len(values)!=n:raise ValueError('Input and NPV samples must be paired and equal in count.')
        reason=''
        if n<2:reason='At least two paired values are required.'
        elif len(set(values))<2:reason='Sampled input has no variation; correlation is undefined.'
        elif len(set(output))<2:reason='NPV has no variation; correlation is undefined.'
        if reason:rows.append(RankCorrelationResult(variable,None,n,reason));continue
        x=_ranks(values);y=_ranks(output);x-=np.mean(x);y-=np.mean(y)
        rho=float(np.dot(x,y)/math.sqrt(float(np.dot(x,x))*float(np.dot(y,y))))
        rows.append(RankCorrelationResult(variable,rho,n,'Rank correlation with simulated NPV; association does not establish causation.'))
    return tuple(rows)


def run_economic_monte_carlo(base_case,uncertain_variables,trials,seed=None,*,cost_basis=DIRECT_COSTS):
    count=_integer(trials,'Requested Trials',maximum=MAX_TRIALS)
    if seed is not None:
        if isinstance(seed,(bool,np.bool_)):raise ValueError('Random Seed must be a nonnegative integer or blank.')
        try:seed=operator.index(seed)
        except TypeError:raise ValueError('Random Seed must be a nonnegative integer or blank.') from None
        if seed<0:raise ValueError('Random Seed must be a nonnegative integer or blank.')
    base_result=economics.evaluate_economic_scenario(base_case,'Deterministic Base Case').result
    allowed=available_variables(base_case,cost_basis)
    if not hasattr(uncertain_variables,'items'):raise ValueError('Provide a mapping of explicitly selected variables and distributions.')
    if any(v not in allowed for v in uncertain_variables):raise ValueError('Inconsistent or unavailable uncertainty variables. Use baseline/proposed costs OR their difference, and direct costs OR electrical energy/tariff.')
    ordered=tuple(v for v in ORDER if v in uncertain_variables)
    # Validate every specification before generating samples.
    for v in ordered:
        lo,hi=_domain(base_case,v);validate_distribution(uncertain_variables[v],lower=lo,upper=hi,integer=v==PERIOD)
    rng=np.random.default_rng(seed);samples={};rejected=0
    for v in ordered:
        lo,hi=_domain(base_case,v);batch=sample_distribution(uncertain_variables[v],count,rng,lower=lo,upper=hi,integer=v==PERIOD)
        samples[v]=batch.values;rejected+=batch.rejected_draws
    rows=[]
    for index in range(count):
        drawn={v:samples[v][index] for v in ordered}
        try:
            case=_case_with_draws(base_case,drawn)
            # The accepted Phase 3X wrapper calls Phase 3W for every trial.
            r=economics.evaluate_economic_scenario(case).result
            rows.append(MonteCarloTrialResult(index+1,tuple(drawn.items()),r.npv,r.simple_payback_years,r.discounted_payback_year,r.lifecycle_cost_difference,r.baseline.lifecycle_cost,r.proposed.lifecycle_cost))
        except (ValueError,OverflowError) as error:
            rows.append(MonteCarloTrialResult(index+1,tuple(drawn.items()),None,None,None,None,None,None,str(error)))
    rows=tuple(rows);valid=tuple(t for t in rows if t.error is None);invalid=count-len(valid)
    summary=calculate_monte_carlo_summary(rows)
    correlations=calculate_rank_correlations({v:[dict(t.sampled_inputs)[v] for t in valid] for v in ordered},[t.npv for t in valid]) if summary is not None else ()
    warning=INSUFFICIENT if summary is None else (f'{invalid} of {count} trials ({invalid/count*100:.6g}%) were invalid and excluded. Review the configuration; statistics are conditional on valid trials.' if invalid else None)
    return MonteCarloSimulationResult(count,len(valid),invalid,rejected,seed,base_result,rows,summary,correlations,warning)
