"""User-defined ranges and independent scenarios; no financial defaults."""
from html import escape
from . import economic_sensitivity as core

TITLE='3X — Economic Sensitivity / Scenario Analysis'
GUIDANCE=(
    'Sensitivity analysis shows how economic results change when individual assumptions change. Scenario analysis evaluates combinations of explicit user-entered assumptions.',
    'A single payback or NPV result should not be treated as certain when CAPEX, energy cost, operating hours or project life are uncertain. NPV sensitivity to discount rate depends on the timing and duration of future cash flows.',
    'Break-even values identify input thresholds under the entered assumptions, not approved budgets or investment decisions. Results use the same underlying Phase 3W end-of-year cash-flow conventions.',
    'This analysis is deterministic and does not quantify likelihood. Final investment decisions should also consider engineering reliability, operability, project risk and company economic criteria.',
    'Discount rate and escalation assumptions should be applied consistently on either a nominal or real basis. Year 1 uses entered operating costs; escalation starts in Year 2 on operating costs only. Maintenance is constant; residuals are terminal benefits. Simple payback excludes optional maintenance, escalation and residuals; NPV includes them.'
)


def parse_values(text):
    if not text.strip():raise ValueError('Enter at least one sensitivity value; no range is assumed.')
    from piping_hydraulics.pump_head import finite_signed
    return tuple(finite_signed(line.strip(),'Sensitivity value (one number per line; no thousands separators)') for line in text.splitlines() if line.strip())


def variable_unit(variable,currency):
    return {core.CAPEX:currency,core.DIFFERENCE:currency+'/year',core.TARIFF:currency+'/kWh',core.HOURS:'h/year',core.DISCOUNT:'%',core.PERIOD:'years'}[variable]


def _table(st,headers,rows):
    # Only escaped text enters HTML. Scrolling is local to this new panel.
    style='padding:8px;border:1px solid #666;text-align:left'
    html='<div role="region" aria-label="Scrollable Economic Results" tabindex="0" style="overflow-x:auto;max-width:100%"><table style="border-collapse:collapse;min-width:100%"><thead><tr>'
    html+=''.join(f'<th style="{style};min-width:95px">{escape(str(h))}</th>' for h in headers)+'</tr></thead><tbody>'
    for row in rows:html+='<tr>'+''.join(f'<td style="{style};white-space:nowrap">{escape(str(v))}</td>' for v in row)+'</tr>'
    st.markdown(html+'</tbody></table></div>',unsafe_allow_html=True)


def _number(value):return 'N/A' if value is None else f'{value:.12g}'


def _payback(r):
    if r.discounted_payback_year is not None:return str(r.discounted_payback_year)+' years (year end)'
    if r.incremental_capex<=0:return 'N/A — nonpositive incremental CAPEX'
    return 'Not reached within selected analysis period.'


def _metrics(r):
    return [_number(r.annual_cost_difference),_number(r.incremental_capex),_number(r.simple_payback_years),_number(r.npv),_payback(r),_number(r.baseline.lifecycle_cost),_number(r.proposed.lifecycle_cost),_number(r.lifecycle_cost_difference),('Negative NPV under entered assumptions.' if r.npv<0 else 'NPV under entered assumptions.')]


def sensitivity_plot_spec(series,currency,payback=False):
    attr='simple_payback_years' if payback else 'npv'
    # Undefined points retain null y values so the line does not bridge them.
    points=[{'value':p.value,'metric':getattr(p.result,attr) if p.result else None} for p in series.points]
    points.sort(key=lambda p:p['value'])
    segment=0
    for point in points:
        point['segment']=segment
        if point['metric'] is None:segment+=1
    layers=[{'data':{'values':points},'mark':{'type':'line','point':True},'encoding':{'x':{'field':'value','type':'quantitative'},'y':{'field':'metric','type':'quantitative'},'detail':{'field':'segment','type':'nominal'},'tooltip':[{'field':'value'},{'field':'metric','type':'quantitative','format':'.12g'}]}}]
    base=getattr(series.base_result,attr)
    # A vertical marker remains visible even when base payback is undefined.
    layers.append({'data':{'values':[{'value':series.base_value}]},'mark':{'type':'rule','strokeDash':[4,4],'color':'#e6a34a'},'encoding':{'x':{'field':'value','type':'quantitative'}}})
    if base is not None:layers.append({'data':{'values':[{'value':series.base_value,'metric':base,'label':'Base case (entered; not recommended)'}]},'mark':{'type':'point','shape':'diamond','filled':True,'size':160,'color':'#e6a34a'},'encoding':{'x':{'field':'value','type':'quantitative'},'y':{'field':'metric','type':'quantitative'},'tooltip':[{'field':'label'},{'field':'value'},{'field':'metric','type':'quantitative','format':'.12g'}]}})
    if not payback:layers.append({'data':{'values':[{'zero':0}]},'mark':{'type':'rule','color':'#999'},'encoding':{'y':{'field':'zero','type':'quantitative'}}})
    return {'title':('Simple Payback' if payback else 'NPV')+' vs '+series.variable,'layer':layers,'encoding':{'x':{'title':series.variable+' ('+variable_unit(series.variable,currency)+')'},'y':{'title':'Simple Payback (years)' if payback else 'NPV ('+currency+')'}},'height':300}


def scenario_plot_spec(results,currency):
    values=[{'scenario':f'{i}. {r.name}','npv':r.result.npv} for i,r in enumerate(results,1) if r.result is not None]
    return {'title':'Scenario NPV — Current Table Order','layer':[{'data':{'values':values},'mark':'bar'}],
        'encoding':{'x':{'field':'scenario','type':'nominal','sort':None,'axis':{'labelAngle':-25,'labelLimit':140},'title':'Scenario'},'y':{'field':'npv','type':'quantitative','title':'NPV ('+currency+')'},'tooltip':[{'field':'scenario'},{'field':'npv','type':'quantitative','format':'.12g'}]},'height':300}


def _case_inputs(st,prefix,title,unit):
    st.markdown('**'+title+'**')
    name=st.text_input(title+' Name',value='',key=prefix+'name')
    source=st.selectbox(title+' Annual-Cost Source',core.SOURCES,key=prefix+'source')
    def num(label,key):return st.number_input(title+' '+label,value=None,format='%.12g',key=prefix+key)
    fields={}
    if source==core.MANUAL:
        fields['baseline_annual_cost']=num(f'Baseline Annual Operating Cost ({unit}/year)','cost_a')
        fields['proposed_annual_cost']=num(f'Proposed Annual Operating Cost ({unit}/year)','cost_b')
    elif source==core.ENERGY:
        fields['baseline_energy_kwh']=num('Baseline Annual Electrical Energy (kWh/year)','energy_a')
        fields['proposed_energy_kwh']=num('Proposed Annual Electrical Energy (kWh/year)','energy_b')
        fields['tariff']=num(f'Electricity Tariff ({unit}/kWh)','tariff')
    else:
        st.caption('Constant supply electrical-input power only: one operating point per alternative and the same annual hours. Multi-point duty profiles are not proportionally rescaled. Energy and pricing call Phase 3V.')
        fields['baseline_power_kw']=num('Baseline Constant Electrical Input Power (kW)','power_a')
        fields['proposed_power_kw']=num('Proposed Constant Electrical Input Power (kW)','power_b')
        fields['operating_hours']=num('Annual Operating Hours (h/year)','hours')
        fields['tariff']=num(f'Electricity Tariff ({unit}/kWh)','tariff')
    fields['baseline_capex']=num(f'Baseline All-In CAPEX ({unit})','capex_a')
    fields['proposed_capex']=num(f'Proposed All-In CAPEX ({unit})','capex_b')
    fields['analysis_years']=st.number_input(title+' Analysis Period (integer years)',value=None,step=1,key=prefix+'years')
    fields['discount_rate_percent']=num('Discount Rate (%)','discount')
    st.caption('Optional fields below start blank and are excluded when not entered. Operating costs must exclude maintenance entered separately. CAPEX is all-in; no separate one-time cost is added.')
    for field,label,key in [('baseline_maintenance',f'Baseline Annual Maintenance ({unit}/year)','maintenance_a'),('proposed_maintenance',f'Proposed Annual Maintenance ({unit}/year)','maintenance_b'),('escalation_percent','Operating / Energy-Cost Escalation (%)','escalation'),('baseline_residual',f'Baseline Terminal Residual ({unit})','residual_a'),('proposed_residual',f'Proposed Terminal Residual ({unit})','residual_b')]:fields[field]=num(label,key)
    return name,core.EconomicCase(source=source,**fields)


def render_economic_sensitivity():
    import streamlit as st
    st.subheader(TITLE)
    st.caption('Deterministic evaluation through Phase 3W. No financial values or sensitivity ranges are prepopulated. Currency is a label only; no conversion.')
    currency=st.text_input('Sensitivity Currency Label',value='',key='p3x_currency').strip()
    unit=currency or 'currency (label not entered)'
    mode=st.selectbox('Economic Analysis Type',('One-Variable Sensitivity','Multi-Scenario Comparison'),key='p3x_analysis')
    headers=['Annual Operating Cost Difference ('+unit+'/year)','Incremental CAPEX ('+unit+')','Simple Payback (years)','NPV ('+unit+')','Discounted Payback','Baseline Lifecycle Cost ('+unit+')','Proposed Lifecycle Cost ('+unit+')','Lifecycle Cost Difference ('+unit+')','Status']
    if mode=='One-Variable Sensitivity':
        name,case=_case_inputs(st,'p3x_base_','Base Case',unit)
        valid=True
        try:variables=core.available_variables(case)
        except (ValueError,OverflowError):variables=();valid=False
        variable=st.selectbox('Sensitivity Variable',variables,index=None,key='p3x_variable',placeholder='Enter a valid base case, then select a variable')
        method=st.selectbox('Sensitivity Value Method',('Explicit Values','Percentage Variation (%)'),key='p3x_value_method')
        values=st.text_area('Sensitivity Values — One Number per Line',value='',key='p3x_values',help='No thousands separators. For percentage variation enter percent numbers, e.g. a typed 10 means +10% of the entered base value. No example is prefilled.')
        st.caption('Only the selected input changes. Annual-cost-difference sensitivity holds baseline cost fixed and derives proposed cost; negative derived operating costs are invalid. Tariff requires electrical-energy data; hours requires the constant-power source. Percentage variations multiply the base value, including for rates; a zero base remains zero. Analysis years must remain integers, with no rounding.')
        if st.button('Evaluate Economic Sensitivity',key='p3x_evaluate'):
            try:
                if not valid:core.evaluate_economic_scenario(case) # Return the real base validation message.
                series=core.run_one_variable_sensitivity(case,variable,parse_values(values),percentage=method.startswith('Percentage'))
                r=series.base_result
                st.markdown('**Base Economic Results**')
                st.text(f'Base Case: {name or "Base Case"}\nSource: {case.source}\nSelected Variable: {variable}\nBase Variable Value: {series.base_value:.12g} {variable_unit(variable,unit)}\nAnnual Operating Cost Difference: {r.annual_cost_difference:.12g} {unit}/year\nIncremental CAPEX: {r.incremental_capex:.12g} {unit}\nSimple Payback: {_number(r.simple_payback_years)} years\nNPV: {r.npv:.12g} {unit}\nDiscounted Payback: {_payback(r)}\nBaseline Lifecycle Cost: {r.baseline.lifecycle_cost:.12g} {unit}\nProposed Lifecycle Cost: {r.proposed.lifecycle_cost:.12g} {unit}\nLifecycle Cost Difference: {r.lifecycle_cost_difference:.12g} {unit}')
                st.markdown('**Sensitivity Results**')
                rows=[]
                for point in series.points:
                    rows.append([_number(point.value)]+(_metrics(point.result) if point.result is not None else ['N/A']*8+['Invalid input: '+point.error]))
                _table(st,['Selected Variable Value ('+variable_unit(variable,unit)+')']+headers,rows)
                st.markdown('**Break-Even Results — Base Assumptions**')
                for item in core.break_even_results(case):
                    label_unit=item.unit.replace('currency',unit)
                    st.text(item.label+': '+_number(item.value)+' '+label_unit)
                    st.caption(item.guidance)
                    if item.npv_at_threshold is not None:st.text(f'NPV at calculated threshold: {item.npv_at_threshold:.12g} {unit}')
                st.caption('Plots: orange dashed vertical line and diamond mark the entered base case, not a recommendation. The NPV plot includes a neutral horizontal zero-NPV reference. N/A paybacks are not replaced with zero; invalid points and undefined paybacks are gaps.')
                st.vega_lite_chart(sensitivity_plot_spec(series,unit),use_container_width=True)
                st.vega_lite_chart(sensitivity_plot_spec(series,unit,True),use_container_width=True)
            except (ValueError,OverflowError) as error:st.error(str(error))
    else:
        st.caption('Every scenario is independent. Enter every required field in each scenario; no missing assumption is inherited from another scenario or the base case. Blank optional costs are excluded. Results retain entry order until a ranking metric is explicitly selected.')
        count=st.number_input('Number of Economic Scenarios',min_value=1,max_value=10,value=2,step=1,key='p3x_count')
        cases=[]
        for i in range(count):
            name,case=_case_inputs(st,f'p3x_s{i}_',f'Scenario {i+1}',unit)
            cases.append((name or f'Scenario {i+1}',case))
        metric=st.selectbox('Scenario Ranking Metric',core.RANK_METRICS,index=None,key='p3x_rank',placeholder='No ranking selected')
        if st.button('Evaluate Economic Scenarios',key='p3x_scenarios'):
            results=core.evaluate_scenarios(cases)
            if metric is not None:results=core.rank_scenarios(results,metric);st.info('Ranked by selected metric. '+metric)
            else:st.caption('Unranked — entry order. Select a metric to rank scenarios.')
            st.markdown('**Scenario Comparison Results**')
            _table(st,['Scenario']+headers,[[r.name]+(_metrics(r.result) if r.result is not None else ['N/A']*8+['Invalid input: '+r.error]) for r in results])
            st.caption('Undefined metrics remain N/A and rank after defined metrics. Equal metrics retain entry order. No scenario is automatically selected for investment.')
            st.vega_lite_chart(scenario_plot_spec(results,unit),use_container_width=True)
    st.markdown('**Engineering / Economic Guidance**')
    for text in GUIDANCE:st.write(text)
