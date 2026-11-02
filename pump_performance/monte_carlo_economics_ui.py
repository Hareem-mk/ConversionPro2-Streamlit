"""Explicit uncertainty inputs, stored completed runs, and bounded-size plots."""
import math
import numpy as np
from . import monte_carlo_economics as core
from .economic_sensitivity_ui import _case_inputs, _table

TITLE='3Y — Probabilistic Economic Risk / Monte Carlo Analysis'
GUIDANCE=(
    'Monte Carlo analysis propagates uncertainty in user-defined inputs through the Phase 3W lifecycle-economic model. Output probabilities depend directly on the entered distributions and assumptions.',
    'Triangular distributions use low, most-likely and high estimates; these inputs are not P10/P50/P90. Normal draws outside the valid variable domain are rejected/resampled, never clamped. This conditions the normal distribution on that domain; its accepted mean may differ from the entered unbounded mean.',
    'Phase 3Y assumes uncertain inputs are statistically independent unless otherwise stated.',
    'Derived energy, costs and cost differences are linked by their equations. Real project tariff, hours and cost assumptions may be dependent; this module does not model correlated uncertain inputs.',
    'Rank correlation measures association with simulated NPV and does not establish causation. It is not a Sobol sensitivity index or a measure of probability importance.',
    'P10, P50 and P90 mean the 10th, 50th and 90th statistical percentiles of the output; P10 is a low NPV percentile. Percentiles use linear interpolation at (n−1) × p, also known as Hyndman–Fan type 7. Standard deviation uses the simulated population (ddof=0).',
    'The simulation quantifies economic uncertainty under the entered distributions. Decision criteria remain user/company specific.',
    'Monte Carlo results do not replace engineering review, vendor data, project-risk assessment or company investment criteria. Phase 3W timing is unchanged: initial costs at Year 0, future costs at year end, escalation from Year 2 on operating costs only, and terminal residual benefits. Currency is a label only; no currency conversion.'
)


def histogram_spec(result,currency):
    values=np.asarray([t.npv for t in result.trials if t.error is None],dtype=float)
    lo=float(np.min(values));hi=float(np.max(values))
    if lo==hi:
        width=max(1.0,abs(lo)*.05);edges=np.array([lo-width/2,hi+width/2]);counts=np.array([len(values)])
    else:counts,edges=np.histogram(values,bins=30)
    if not np.all(np.isfinite(edges)):raise ValueError('Histogram bounds exceed the supported plot range.')
    rows=[{'low':float(edges[i]),'high':float(edges[i+1]),'trials':int(count)} for i,count in enumerate(counts)]
    return {'title':'NPV Histogram — Valid Trials','layer':[
        {'data':{'values':rows},'mark':{'type':'bar','color':'#91bcea'},'encoding':{'x':{'field':'low','type':'quantitative','bin':'binned','title':'NPV ('+currency+')'},'x2':{'field':'high'},'y':{'field':'trials','type':'quantitative','title':'Valid Trial Count'},'tooltip':[{'field':'low','format':'.12g'},{'field':'high','format':'.12g'},{'field':'trials'}]}},
        {'data':{'values':[{'zero':0}]},'mark':{'type':'rule','color':'#b7b7b7','strokeWidth':2},'encoding':{'x':{'field':'zero','type':'quantitative'},'tooltip':[{'field':'zero','title':'Zero NPV'}]}}],'height':320}


def correlation_spec(rows):
    return {'title':'Rank Correlation with Simulated NPV','layer':[
        {'data':{'values':[{'input':r.variable,'rho':r.rho} for r in rows]},'mark':{'type':'bar','color':'#91bcea'},'encoding':{
            'y':{'field':'input','type':'nominal','sort':None,'title':'Sampled Input','axis':{'labelLimit':200}},
            'x':{'field':'rho','type':'quantitative','scale':{'domain':[-1,1]},'title':'Spearman rho vs NPV'},
            'tooltip':[{'field':'input'},{'field':'rho','format':'.6g'}]}},
        {'data':{'values':[{'zero':0}]},'mark':{'type':'rule','color':'#aaa'},'encoding':{'x':{'field':'zero','type':'quantitative'}}}],
        'height':max(260,60*len(rows)+160)}


def _statistics_text(stats,label,unit):
    return '\n'.join([f'{label} Mean: {stats.mean:.12g} {unit}',f'{label} Median: {stats.median:.12g} {unit}',f'{label} Standard Deviation: {stats.standard_deviation:.12g} {unit}',f'{label} Minimum: {stats.minimum:.12g} {unit}',f'{label} Maximum: {stats.maximum:.12g} {unit}']+[f'{label} P{p}: {v:.12g} {unit}' for p,v in stats.percentiles])


def distribution_description(variable,spec,currency):
    unit={core.CAPEX:currency,core.BASELINE_CAPEX:currency,core.BASELINE_COST:currency+'/year',core.PROPOSED_COST:currency+'/year',core.DIFFERENCE:currency+'/year',core.TARIFF:currency+'/kWh',core.HOURS:'h/year',core.DISCOUNT:'%',core.PERIOD:'years'}[variable]
    fields={'Fixed':(('Value',spec.value),),'Uniform':(('Minimum',spec.minimum),('Maximum',spec.maximum)),'Integer Uniform':(('Minimum',spec.minimum),('Maximum',spec.maximum)),'Triangular':(('Minimum',spec.minimum),('Most Likely',spec.most_likely),('Maximum',spec.maximum)),'Normal':(('Mean',spec.mean),('Standard Deviation',spec.standard_deviation))}[spec.kind]
    return '; '.join(f'{label}: {value:.12g} {unit}' for label,value in fields)


def render_monte_carlo_economics():
    import streamlit as st
    st.subheader(TITLE)
    st.caption('Enter the deterministic base first, then explicitly select uncertain variables and distributions. Unselected variables retain entered base values. No distribution or distribution parameter is prepopulated.')
    currency=st.text_input('Monte Carlo Currency Label',value='',key='p3y_currency').strip()
    unit=currency or 'currency (label not entered)'
    name,case=_case_inputs(st,'p3y_base_','Risk Base Case',unit)
    base_result=None;valid=False
    try:
        base_result=core.economics.evaluate_economic_scenario(case).result;valid=True
    except (ValueError,OverflowError):pass
    st.markdown('**Deterministic Base Economic Result — Current Inputs**')
    if base_result is not None:
        r=base_result
        st.text(f'Annual Operating Cost Difference: {r.annual_cost_difference:.12g} {unit}/year\nIncremental CAPEX: {r.incremental_capex:.12g} {unit}\nSimple Payback: {str(r.simple_payback_years)+" years" if r.simple_payback_years is not None else "N/A"}\nBase NPV: {r.npv:.12g} {unit}\nBaseline Lifecycle Cost: {r.baseline.lifecycle_cost:.12g} {unit}\nProposed Lifecycle Cost: {r.proposed.lifecycle_cost:.12g} {unit}')
    else:st.caption('Complete a valid base case to show its deterministic result before simulation.')
    basis=core.DIRECT_COSTS
    if case.source==core.economics.MANUAL:
        basis=st.selectbox('Annual-Cost Uncertainty Basis',(core.DIRECT_COSTS,core.COST_DIFFERENCE),key='p3y_cost_basis')
    else:st.caption('Energy-cost source: tariff and constant-power hours may be sampled where available; the resulting annual operating costs are not sampled again.')
    allowed=core.available_variables(case,basis) if valid else ()
    selected=st.multiselect('Uncertain Variables',allowed,default=[],key='p3y_variables')
    specs={}
    st.markdown('**Distribution Parameters**')
    for variable in selected:
        key=core.ORDER.index(variable);prefix=f'p3y_d{key}_'
        kind=st.selectbox(variable+' Distribution',core.PERIOD_KINDS if variable==core.PERIOD else core.KINDS,index=None,key=prefix+'kind')
        def num(label,field):
            if variable==core.PERIOD:return st.number_input(variable+' '+label,value=None,step=1,key=prefix+field)
            return st.number_input(variable+' '+label,value=None,format='%.12g',key=prefix+field)
        fields={}
        if kind=='Fixed':fields['value']=num('Fixed Value','value')
        elif kind in ('Uniform','Integer Uniform','Triangular'):
            fields['minimum']=num('Minimum','minimum')
            if kind=='Triangular':fields['most_likely']=num('Most Likely','most_likely')
            fields['maximum']=num('Maximum','maximum')
        elif kind=='Normal':
            fields['mean']=num('Mean','mean');fields['standard_deviation']=num('Standard Deviation','std')
        specs[variable]=core.DistributionSpec(kind,**fields)
    st.caption('Rates and their deviations are percentage entries. Annual-cost difference holds baseline cost fixed and derives proposed cost. No simultaneous independent cost/difference sampling is allowed. Analysis period uses only Fixed integer or inclusive Integer Uniform years. Bounded distributions must fit the valid domain; normal rejection permits at most 100 draws per sample before invalidating the configuration. Rejected normal draws are counted separately from invalid economic trials.')
    st.markdown('**Simulation Settings**')
    trials=st.selectbox('Requested Trials — Computational Setting',(1000,5000,10000,25000,50000),index=1,key='p3y_trials')
    st.caption('5,000 is a computational starting setting, not an engineering assumption. Simulations run only on the Run Simulation button.')
    seed=st.number_input('Random Seed — Optional Nonnegative Integer',value=None,step=1,key='p3y_seed')
    fingerprint=repr((name,case,basis,tuple(specs.items()),trials,seed,currency))
    if st.button('Run Simulation',key='p3y_run'):
        try:
            with st.spinner('Sampling entered distributions and evaluating Phase 3W trials…'):
                result=core.run_economic_monte_carlo(case,specs,trials,seed,cost_basis=basis)
            st.session_state['p3y_last']={'fingerprint':fingerprint,'result':result,'unit':unit,'specs':tuple(specs.items()),'basis':basis,'name':name or 'Base Case'}
            st.session_state['p3y_failed']=False
        except (ValueError,OverflowError) as error:
            st.error(str(error));st.session_state['p3y_failed']=True
    previous=st.session_state.get('p3y_last')
    if previous is not None:
        if previous['fingerprint']!=fingerprint:st.warning('Inputs have changed. Results shown are from the previous simulation; select Run Simulation to update.')
        elif st.session_state.get('p3y_failed'):st.warning('The latest attempt failed. The last completed simulation remains shown below.')
        result=previous['result'];out_unit=previous['unit']
        st.markdown('**Last Completed Simulation**')
        st.text(f'Completed Base Case: {previous["name"]}\nCurrency Label: {out_unit}\nRequested Trials: {result.requested_trials}\nValid Trials: {result.valid_trials}\nInvalid Trials: {result.invalid_trials}\nRejected Normal Draws (resampled, not invalid trials): {result.rejected_draws}\nRandom Seed: {result.seed if result.seed is not None else "not supplied — non-deterministic random generator"}\nAnnual-Cost Uncertainty Basis: {previous["basis"]}')
        st.caption('Completed-run distributions (unselected inputs were held at that run’s base values):')
        if previous['specs']:
            _table(st,['Input Variable','Distribution','Entered Parameters'],[[variable,spec.kind,distribution_description(variable,spec,out_unit)] for variable,spec in previous['specs']])
        else:st.caption('No uncertain variables selected. All entered base inputs were held fixed.')
        if result.warning:st.warning(result.warning)
        summary=result.summary
        if summary is not None:
            st.markdown('**NPV Risk Summary**')
            st.text(_statistics_text(summary.npv,'NPV',out_unit))
            st.text(f'Probability NPV > 0: {summary.probability_positive_npv_percent:.12g}%\nProbability NPV < 0: {summary.probability_negative_npv_percent:.12g}%\nProbability NPV ≈ 0: {summary.probability_zero_npv_percent:.12g}%')
            st.caption('NPV probabilities use valid trials as denominator. Positive means strictly NPV > 0; negative means strictly NPV < 0. Approximate zero is a separate numerical diagnostic: |NPV| ≤ 1e-8 currency units. Tiny nonzero values can count in both a strict-sign category and the approximate-zero diagnostic; the three values are not forcibly rescaled. Exact zeros count in neither strict-sign category. This tolerance is numerical, not an economic decision threshold. Statistics exclude invalid trials. The 100-valid-trial minimum is a software display threshold, not a general sufficiency or convergence claim.')
            st.markdown('**Payback Risk Summary**')
            st.text(f'Simple-Payback Defined: {summary.simple_payback_defined_count} / {result.valid_trials} valid trials ({summary.simple_payback_defined_percent:.12g}%)\nDiscounted-Payback Reached Within Analysis Period: {summary.discounted_payback_reached_count} / {result.valid_trials} valid trials ({summary.discounted_payback_reached_percent:.12g}%)')
            if summary.simple_payback is not None:st.text(_statistics_text(summary.simple_payback,'Simple Payback — Defined Trials Only','years'))
            else:st.caption('Simple-payback distribution: N/A — no defined paybacks. Undefined values are not replaced with zero.')
            if summary.discounted_payback is not None:st.text(_statistics_text(summary.discounted_payback,'Discounted Payback — Reached Trials Only','years'))
            st.caption('Payback percentiles and medians are conditional on the displayed defined/reached subset. The reached percentage uses all valid trials; Phase 3W does not assign discounted payback for nonpositive incremental investment. Unrecovered cases are not assigned the analysis-period endpoint.')
            st.markdown('**Lifecycle Cost Risk Summary**')
            st.text(_statistics_text(summary.lifecycle_cost_difference,'Lifecycle Cost Difference',out_unit))
            st.text(f'Probability Proposed Lifecycle Cost Lower: {summary.probability_proposed_lifecycle_cost_lower_percent:.12g}%')
            st.caption('Phase 3W sign convention: baseline minus proposed lifecycle cost. Lower-cost probability counts strictly positive differences over all valid trials.')
            st.markdown('**Sensitivity / Rank Correlation**')
            defined=[r for r in result.correlations if r.rho is not None]
            if defined:
                order=st.selectbox('Rank-Correlation Display Order',('Input Order','Descending Absolute Spearman rho'),key='p3y_corr_order')
                if order.startswith('Descending'):defined=sorted(defined,key=lambda row:abs(row.rho),reverse=True)
                _table(st,['Input Variable','Spearman rho vs NPV','Paired Valid Trials'],[[r.variable,f'{r.rho:.12g}',r.pairs] for r in defined])
                st.caption('Rank correlation with simulated NPV. Association does not establish causation. Fixed/zero-variance inputs and constant NPV do not receive a correlation value.')
                st.vega_lite_chart(correlation_spec(defined),use_container_width=True)
            else:st.caption('Rank correlations are undefined: no varying paired input/output data. Fixed inputs and constant NPV do not receive a misleading zero correlation.')
            st.markdown('**Distribution Plots**')
            st.caption('Neutral gray vertical rule marks zero NPV. Histogram bars show valid-trial frequency; colors do not classify investment risk.')
            try:st.vega_lite_chart(histogram_spec(result,out_unit),use_container_width=True)
            except ValueError as error:st.warning(str(error))
    st.markdown('**Engineering / Economic Guidance**')
    for text in GUIDANCE:st.write(text)
