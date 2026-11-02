"""Screen review, explicit section selection, and plots of validated result objects."""
from . import integrated_summary as core
from .economic_sensitivity_ui import _case_inputs,_table,sensitivity_plot_spec
from .lifecycle_cost_ui import cash_flow_chart_spec
from .monte_carlo_economics_ui import histogram_spec,distribution_description
from .pump_curve import HEAD_FACTORS
from .shaft_power import POWER_FACTORS

TITLE='3Z — Integrated Pump Technical–Economic Decision Summary'
VENDOR=('Vendor BEP','Efficiency Curve','Shaft Power Curve','NPSHR Curve','NPSHA','Driver Rating')
EXTENSIONS=('Modified System','Variable-Speed Operating Point','Target-Flow Required Speed','Throttling vs VSD')
GUIDANCE=(
    'Phase 3Z consolidates results from validated Phase 3 modules and does not replace manufacturer/vendor pump selection.',
    'Performance results are valid only within supplied curve ranges. Vendor curves must match the relevant pump configuration, speed and impeller diameter.',
    'NPSH review requires applicable vendor NPSHR and valid NPSHA assumptions. Positive margin alone does not establish all vendor/project criteria.',
    'Affinity-law results are theoretical estimates requiring manufacturer verification. NPSHR is not automatically scaled with speed.',
    'Hydraulic power, shaft power, motor input power and electrical energy are distinct quantities. Hydraulic-power reduction is not electrical-energy saving.',
    'Economic outputs depend on entered assumptions. Monte Carlo probabilities depend on explicitly selected distributions and Phase 3Y independence assumptions.',
    'Phase 3Z provides no automatic engineering, safety or investment approval, overall score or traffic-light decision.'
)


def display_item(item,flow_unit,head_unit,power_unit,currency,flow_factors):
    value=item.value;unit=item.unit
    if value is None:
        unit={'m³/s':flow_unit,'m':head_unit,'W':power_unit,'m per (m³/s)':head_unit+' per ('+flow_unit+')'}.get(unit,unit)
        return 'N/A',unit.replace('currency',currency)
    if isinstance(value,str):return value,unit
    if unit=='m³/s':value=value/flow_factors[flow_unit];unit=flow_unit
    elif unit=='m':value=value/HEAD_FACTORS[head_unit];unit=head_unit
    elif unit=='W':value=value/POWER_FACTORS[power_unit];unit=power_unit
    elif unit=='m per (m³/s)':
        value=core.curve_characteristics.display_slope(value,flow_unit,head_unit,flow_factors);unit=head_unit+' per ('+flow_unit+')'
    unit=unit.replace('currency',currency)
    return f'{value:.12g}',unit


def technical_plot_spec(summary,flow_unit,head_unit,flow_factors):
    t=summary.technical;factor=flow_factors[flow_unit];rows=[]
    def curve_rows(curve,label):return [{'flow':p.flow_m3_s/factor,'head':core.system_curve.head_from_metres(p.head_m,head_unit),'series':label} for p in curve.points]
    if t.pump:rows.extend(curve_rows(t.pump,'Supplied Pump — Phase 3E'))
    if t.variable_speed:rows.extend(curve_rows(t.variable_speed.scaling.scaled_curve,'Speed-Scaled Pump — Phase 3S'))
    if t.target_speed:
        for i,s in enumerate(t.target_speed.solutions,1):rows.extend(curve_rows(s.scaled_curve,f'Target-Speed Pump {i} — Phase 3T'))
    if t.system and t.pump:
        maximum=max([t.pump.points[-1].flow_m3_s]+([t.variable_speed.scaling.scaled_curve.points[-1].flow_m3_s] if t.variable_speed else [])+([s.scaled_curve.points[-1].flow_m3_s for s in t.target_speed.solutions] if t.target_speed else []))
        rows.extend({'flow':p.flow_m3_s/factor,'head':core.system_curve.head_from_metres(p.total_head_m,head_unit),'series':'System — Phase 3F'} for p in core.system_curve.generate_system_curve(t.system,maximum))
    if t.system_sensitivity and t.pump:
        modified=core.system_curve.model_from_k(t.system_sensitivity.modified_static_head_m,'m',t.system_sensitivity.modified_k_si)
        rows.extend({'flow':p.flow_m3_s/factor,'head':core.system_curve.head_from_metres(p.total_head_m,head_unit),'series':'Modified System — Phase 3R'} for p in core.system_curve.generate_system_curve(modified,t.pump.points[-1].flow_m3_s))
    points=[]
    for label,roots in [('Reference Operating Points — Phase 3G',t.operating_points),('VSD Operating Points — Phase 3S',t.variable_speed.new if t.variable_speed else None),('Modified-System Points — Phase 3R',t.system_sensitivity.modified if t.system_sensitivity else None)]:
        if roots:points.extend({'flow':p.flow_m3_s/factor,'head':core.system_curve.head_from_metres(p.head_m,head_unit),'series':label} for p in roots.points)
    if t.target_speed:points.extend({'flow':s.verified_flow_m3_s/factor,'head':core.system_curve.head_from_metres(s.verified_head_m,head_unit),'series':'Verified Target Points — Phase 3T'} for s in t.target_speed.solutions)
    return {'title':'Pump / System / Optional Speed Curves','layer':[{'data':{'values':rows},'mark':{'type':'line'},'encoding':{'detail':{'field':'series'}}},{'data':{'values':points},'mark':{'type':'point','filled':True,'size':110}}],
        'encoding':{'x':{'field':'flow','type':'quantitative','title':'Flow ('+flow_unit+')'},'y':{'field':'head','type':'quantitative','title':'Head ('+head_unit+')'},'color':{'field':'series','type':'nominal','legend':{'orient':'bottom','columns':1,'labelLimit':500}},'tooltip':[{'field':'series'},{'field':'flow','format':'.12g'},{'field':'head','format':'.12g'}]},'height':480+24*max(0,len({r['series'] for r in rows+points})-3)}


def vendor_plot_spec(curve,metric,attribute,unit,source,summary,flow_unit,flow_factors,factor=1):
    rows=[{'flow':p.flow_m3_s/flow_factors[flow_unit],'value':getattr(p,attribute)/factor} for p in curve.points]
    item=summary.metric(metric);point=summary.technical.selected_point
    op=[{'flow':point.flow_m3_s/flow_factors[flow_unit],'value':item.value/factor}] if point and item.value is not None else []
    return {'title':metric+' — '+source,'layer':[{'data':{'values':rows},'mark':{'type':'line','point':True}},{'data':{'values':op},'mark':{'type':'point','filled':True,'size':140,'color':'#e6a34a'}}],
        'encoding':{'x':{'field':'flow','type':'quantitative','title':'Flow ('+flow_unit+')'},'y':{'field':'value','type':'quantitative','title':metric+' ('+unit+')'},'tooltip':[{'field':'flow','format':'.12g'},{'field':'value','format':'.12g'}]},'height':290}


def _render_report(st,result,flow_unit,head_unit,power_unit,currency,flow_factors):
    def chart(builder,*args):
        try:st.vega_lite_chart(builder(*args),use_container_width=True)
        except (ValueError,OverflowError) as error:st.caption('Plot Not Evaluated: '+str(error))
    st.markdown('**Case Identification**')
    for label,value in result.identification:
        if value:st.text(label+': '+str(value))
    st.caption('Metrics retain source-module labels. N/A means no evaluated result, not zero. Availability describes supplied inputs; validation/evaluation status is shown separately. There is no global approval or completeness score.')
    st.markdown('**Integrated Summary / Traceability**')
    compact={'Operating Flow','Operating Head','Percent of BEP','Operating Efficiency','Pump Shaft Power','Driver Power Margin','Vendor NPSHR','NPSH Margin','Required Speed','Annual Supply Electrical Energy','Annual Supply Electrical Operating Cost','Incremental CAPEX','Simple Payback','NPV','P10 NPV','P50 NPV','P90 NPV','Probability NPV > 0'}
    rows=[]
    for item in result.items:
        if item.metric not in compact:continue
        value,unit=display_item(item,flow_unit,head_unit,power_unit,currency,flow_factors)
        rows.append([item.section,item.metric,value,unit,item.source,item.status])
    _table(st,['Section','Metric','Value','Unit','Source Module','Evaluation Status'],rows)
    for section,title in [('Hydraulics','Hydraulic Summary'),('Pump Performance','Pump Performance'),('NPSH','NPSH Review'),('Curve Characteristics','Pump Curve Characteristics'),('System Sensitivity','System Sensitivity'),('Variable Speed','Variable-Speed Review'),('Target Speed','Target-Speed Review'),('Control Strategy','Control Strategy'),('Criteria','Entered Criteria — Individual Comparisons Only'),('Energy','Annual Energy Summary'),('Economics','Lifecycle Economics'),('Economic Sensitivity','Economic Sensitivity Summary'),('Probabilistic Risk','Probabilistic Summary')]:
        section_items=[item for item in result.items if item.section==section]
        if section=='Energy' and result.mode not in (core.MODES[1],core.MODES[3]):continue
        if section in ('Economics','Economic Sensitivity','Probabilistic Risk') and result.mode not in (core.MODES[2],core.MODES[3]):continue
        if section in ('System Sensitivity','Variable Speed','Target Speed','Control Strategy') and not any(item.value is not None for item in section_items) and not any(flag.section==section for flag in result.flags):continue
        st.markdown('**'+title+'**')
        st.text('\n'.join(f'{item.metric}: '+(' '.join(display_item(item,flow_unit,head_unit,power_unit,currency,flow_factors))).rstrip()+f' [{item.source}; {item.status}]' for item in section_items))
        for item in section_items:
            if item.note:st.caption(item.metric+': '+item.note)
    t=result.technical
    def show_roots(label,roots):
        if roots is None:return
        st.markdown('**'+label+'**')
        _table(st,['Index','Flow ('+flow_unit+')','Head ('+head_unit+')','Pump/System Residual (m)'],[[i,f'{p.flow_m3_s/flow_factors[flow_unit]:.12g}',f'{core.system_curve.head_from_metres(p.head_m,head_unit):.12g}',f'{p.residual_m:.12g}'] for i,p in enumerate(roots.points)])
        for interval in roots.coincident_intervals:st.text(f'Coincident flow interval: {interval.minimum_flow_m3_s/flow_factors[flow_unit]:.12g} to {interval.maximum_flow_m3_s/flow_factors[flow_unit]:.12g} {flow_unit}; no individual point chosen automatically.')
    show_roots('Hydraulic Intersections — Phase 3G',t.operating_points)
    if t.variable_speed:show_roots('Variable-Speed Intersections — Phase 3S',t.variable_speed.new)
    if t.system_sensitivity:show_roots('Modified-System Intersections — Phase 3R',t.system_sensitivity.modified)
    if t.target_speed:
        st.markdown('**Required-Speed Solutions — Phase 3T**')
        _table(st,['Required Speed (rpm)','Speed Ratio','Verified Flow ('+flow_unit+')','Verified Head ('+head_unit+')'],[[f'{s.required_speed_rpm:.12g}',f'{s.ratio:.12g}',f'{s.verified_flow_m3_s/flow_factors[flow_unit]:.12g}',f'{core.system_curve.head_from_metres(s.verified_head_m,head_unit):.12g}'] for s in t.target_speed.solutions])
        for interval in t.target_speed.coincident_ratio_intervals:st.text(f'Coincident speed-ratio interval: {interval.minimum_ratio:.12g} to {interval.maximum_ratio:.12g}; no required speed selected automatically.')
    if t.pump:
        chart(technical_plot_spec,result,flow_unit,head_unit,flow_factors)
        for curve,metric,attribute,unit,source,factor in [(t.efficiency_curve,'Operating Efficiency','efficiency_percent','%','Phase 3M',1),(t.power_curve,'Pump Shaft Power','shaft_power_w',power_unit,'Phase 3N',POWER_FACTORS[power_unit]),(t.npshr_curve,'Vendor NPSHR','npshr_m',head_unit,'Phase 3O',HEAD_FACTORS[head_unit])]:
            if curve:chart(vendor_plot_spec,curve,metric,attribute,unit,source,result,flow_unit,flow_factors,factor)
    if result.energy:
        st.markdown('**Annual Duty Results — Phase 3V**')
        _table(st,['Period','Entered Basis','Energy (kWh/year)','Cost ('+currency+'/year)','Status'],[[r.case,r.energy_basis or 'N/A','N/A' if r.energy_kwh is None else f'{r.energy_kwh:.12g}','N/A' if r.cost is None else f'{r.cost:.12g}',r.status] for r in result.energy.rows])
    if result.economic:
        st.markdown('**Lifecycle Cost Components — Phase 3W**')
        for label,c in [('Baseline',result.economic.baseline),('Proposed',result.economic.proposed)]:st.text(f'{label}: Initial {c.initial_cost:.12g}; PV Operating {c.pv_operating_cost:.12g}; PV Maintenance {c.pv_maintenance_cost:.12g}; less PV Residual {c.pv_residual_value:.12g}; Lifecycle Cost {c.lifecycle_cost:.12g} {currency}')
        chart(cash_flow_chart_spec,result.economic.rows,currency,False)
        chart(cash_flow_chart_spec,result.economic.rows,currency,True)
    if result.sensitivity:
        st.markdown('**Economic Sensitivity — Phase 3X**')
        _table(st,['Selected Variable Value','Simple Payback (years)','NPV ('+currency+')','Evaluation Status'],[[f'{p.value:.12g}','N/A' if p.result is None or p.result.simple_payback_years is None else f'{p.result.simple_payback_years:.12g}','N/A' if p.result is None else f'{p.result.npv:.12g}',p.error or 'Data Available'] for p in result.sensitivity.points])
        chart(sensitivity_plot_spec,result.sensitivity,currency)
    if result.risk:
        st.markdown('**Monte Carlo — Phase 3Y**')
        st.text(f'Requested Trials: {result.risk.requested_trials}\nValid Trials: {result.risk.valid_trials}\nInvalid Trials: {result.risk.invalid_trials}\nRandom Seed: {result.risk.seed if result.risk.seed is not None else "not supplied"}')
        if result.risk.summary:chart(histogram_spec,result.risk,currency)
    st.markdown('**Review Flags — Informational**')
    for flag in result.flags:st.write(flag.section+': '+flag.message)
    if not result.flags:st.caption('No informational flags generated from the entered datasets; this is not an approval result.')
    st.markdown('**Data Completeness**')
    _table(st,['Dataset','Input Availability'],[[r.dataset,r.status] for r in result.completeness])
    st.markdown('**Assumptions / Limitations — Modules Used**')
    for text in result.assumptions:st.write(text)


def render_integrated_summary(flow_factors):
    import streamlit as st
    st.subheader(TITLE)
    mode=st.selectbox('Integrated Review Mode',core.MODES,key='p3z_mode')
    st.caption('Own structured inputs call the accepted cores. Existing panels and their widget state are not imported or modified. Build Review executes only the selected analyses; optional Monte Carlo runs only on that button.')
    identification=tuple((label,st.text_input('Review '+label,value='',key='p3z_id_'+key)) for label,key in [('Case Name','name'),('Pump Tag','tag'),('Service','service'),('Project','project'),('Notes','notes')])
    fu=st.selectbox('Review Curve Flow Unit',list(flow_factors),index=None,key='p3z_flow_unit')
    hu=st.selectbox('Review Head Unit',list(HEAD_FACTORS),index=None,key='p3z_head_unit')
    power_unit='kW'
    pump_text=st.text_area('Review Pump Head Curve — Flow, Head per Line',value='',key='p3z_pump')
    st.caption('Enter at least 3 unique supplied points, one flow,value pair per line; no thousands separators. All vendor-curve flows use the explicit review flow unit. Units reinterpret entered values; they do not rewrite numbers. No benchmark curve is preloaded.')
    system_method=st.selectbox('Review System Method',('Reference Flow / Friction Head','Direct K'),key='p3z_system_method')
    def num(label,key):return st.number_input(label,value=None,format='%.12g',key='p3z_'+key)
    static=num('Review Static Head ('+(hu or 'select unit')+')','static')
    rf=friction=k=None
    if system_method=='Direct K':k=num('Review System K — SI (s²/m⁵)','k')
    else:
        rf=num('Review System Reference Flow ('+(fu or 'select unit')+')','reference_flow')
        friction=num('Review Reference Friction Head ('+(hu or 'select unit')+')','friction')
    system=core.SystemInput(static,hu,system_method,rf,friction,fu,k)
    index=st.number_input('Operating Intersection Index — Optional 0-Based Selection',value=None,step=1,key='p3z_index')
    st.caption('A unique isolated intersection is used automatically. With multiple intersections or coincident intervals, all are shown and no point is silently selected. Enter an isolated point index explicitly for downstream vendor evaluation.')
    selected=st.multiselect('Vendor Datasets to Include',VENDOR,default=[],key='p3z_vendor')
    bep=eff=power=npshr=npsha=driver=None;required_npsh=required_driver=None
    if 'Vendor BEP' in selected:bep=num('Review Vendor BEP Flow ('+(fu or 'select unit')+')','bep')
    if 'Efficiency Curve' in selected:eff=core.parse_curve_text(st.text_area('Review Efficiency Curve — Flow, Efficiency (%) per Line',value='',key='p3z_eff'),fu,'%')
    if 'Shaft Power Curve' in selected or 'Driver Rating' in selected:power_unit=st.selectbox('Review Power Unit',list(POWER_FACTORS),index=None,key='p3z_power_unit')
    if 'Shaft Power Curve' in selected:power=core.parse_curve_text(st.text_area('Review Shaft Power Curve — Flow, Power per Line',value='',key='p3z_power'),fu,power_unit)
    if 'NPSHR Curve' in selected:npshr=core.parse_curve_text(st.text_area('Review NPSHR Curve — Flow, NPSHR per Line',value='',key='p3z_npshr'),fu,hu)
    if 'NPSHA' in selected:
        npsha=num('Review Manual NPSHA ('+(hu or 'select unit')+')','npsha')
        required_npsh=num('User/Vendor/Project Required NPSH Margin — Optional (m)','required_npsh')
    if 'Driver Rating' in selected:
        driver=num('Review Driver Rating ('+(power_unit or 'select unit')+')','driver')
        required_driver=num('User/Vendor/Project Required Driver Power Margin — Optional (%)','required_driver')
    extensions=st.multiselect('Optional Technical Analyses',EXTENSIONS,default=[],key='p3z_extensions')
    reference=new_speed=target=density=None;modified=None;minimum=maximum=None
    if any(v in extensions for v in EXTENSIONS[1:]):reference=num('Review Reference Pump Speed (rpm)','reference_speed')
    if 'Variable-Speed Operating Point' in extensions:new_speed=num('Review New / VSD Speed (rpm)','new_speed')
    if 'Target-Flow Required Speed' in extensions or 'Throttling vs VSD' in extensions:
        target=num('Review Target Flow ('+(fu or 'select unit')+')','target')
        minimum=num('User/Vendor Minimum Required-Speed Limit — Optional (rpm)','minimum_speed')
        maximum=num('User/Vendor Maximum Required-Speed Limit — Optional (rpm)','maximum_speed')
    if 'Throttling vs VSD' in extensions:density=num('Control Comparison Fluid Density (kg/m³)','density')
    if 'Modified System' in extensions:
        ms=num('Modified-System Static Head ('+(hu or 'select unit')+')','modified_static');mk=num('Modified-System K — SI (s²/m⁵)','modified_k')
        modified=core.SystemInput(ms,hu,'Direct K',k_si=mk)
    technical=core.TechnicalInputs(core.parse_curve_text(pump_text,fu,hu),system,bep,fu,eff,power,npshr,npsha,hu,driver,power_unit,index,reference,new_speed,target,fu,'Throttling vs VSD' in extensions,density,modified,required_npsh,required_driver,minimum,maximum)
    currency='currency (label not entered)';energy=econ=sensitivity=risk=None
    if mode in (core.MODES[1],core.MODES[2],core.MODES[3]):currency=st.text_input('Review Currency Label',value='',key='p3z_currency').strip() or 'currency (label not entered)'
    if mode in (core.MODES[1],core.MODES[3]):
        st.markdown('**Optional Annual Duty Profile — Phase 3V**')
        count=st.number_input('Review Duty Period Count',min_value=1,max_value=20,value=1,step=1,key='p3z_energy_count');rows=[];present=False
        for i in range(count):
            label=st.text_input(f'Review Duty {i+1} Name',value='',key=f'p3z_en{i}_name')
            watts=num(f'Review Duty {i+1} Input Power (kW)',f'en{i}_power');hours=num(f'Review Duty {i+1} Hours (h/year)',f'en{i}_hours')
            basis=st.selectbox(f'Review Duty {i+1} Power / Energy Basis',core.annual_energy.BASES,index=None,key=f'p3z_en{i}_basis')
            rows.append(core.annual_energy.DutyPoint(label or f'Duty {i+1}',core.annual_energy.METHODS[2],hours,input_power=watts,power_unit='kW',power_basis=basis))
            present=present or watts is not None or hours is not None or basis is not None
        tariff=num('Review Duty Electricity Tariff ('+currency+'/kWh)','tariff')
        if present:energy=core.EnergyInputs(tuple(rows),tariff)
        st.caption('This explicit duty profile is separate from financial baseline/proposed costs. No power, tariff, efficiency or annual hours are inferred from the hydraulic review; energy bases retain Phase 3V separation.')
    if mode in (core.MODES[2],core.MODES[3]):
        _,economic_case=_case_inputs(st,'p3z_econ_','Integrated Economic Base',currency)
        if any(v is not None for k,v in vars(economic_case).items() if k!='source'):econ=economic_case
        option=st.selectbox('Integrated Economic Sensitivity',('Not Evaluated','One-Variable Phase 3X Analysis'),key='p3z_sensitivity_mode')
        if option!='Not Evaluated':
            try:variables=core.economic_sensitivity.available_variables(economic_case)
            except (ValueError,OverflowError):variables=()
            variable=st.selectbox('Integrated Sensitivity Variable',variables,index=None,key='p3z_sensitivity_variable')
            method=st.selectbox('Integrated Sensitivity Value Method',('Explicit Values','Percentage Variation (%)'),key='p3z_sensitivity_method')
            text=st.text_area('Integrated Sensitivity Values — One Number per Line',value='',key='p3z_sensitivity_values')
            if variable is not None and text.strip():sensitivity=core.SensitivityInputs(variable,tuple(line.strip() for line in text.splitlines() if line.strip()),method.startswith('Percentage'))
        risk_mode=st.selectbox('Integrated Monte Carlo Review',('Not Evaluated','All Entered Economic Inputs Fixed','Explicit Phase 3Y Distributions'),key='p3z_risk_mode')
        if risk_mode!='Not Evaluated':
            specs={};basis=core.monte_carlo_economics.DIRECT_COSTS
            if risk_mode.startswith('Explicit'):
                if economic_case.source==core.economic_sensitivity.MANUAL:basis=st.selectbox('Integrated Risk Cost Basis',(core.monte_carlo_economics.DIRECT_COSTS,core.monte_carlo_economics.COST_DIFFERENCE),key='p3z_risk_basis')
                try:allowed=core.monte_carlo_economics.available_variables(economic_case,basis)
                except (ValueError,OverflowError):allowed=()
                uncertain=st.multiselect('Integrated Risk Variables',allowed,default=[],key='p3z_risk_variables')
                for variable in uncertain:
                    vkey=core.monte_carlo_economics.ORDER.index(variable)
                    kind=st.selectbox(variable+' Review Distribution',core.monte_carlo_economics.PERIOD_KINDS if variable==core.monte_carlo_economics.PERIOD else core.monte_carlo_economics.KINDS,index=None,key=f'p3z_dist{vkey}_kind')
                    fields={}
                    for field,label in ({'Fixed':[('value','Fixed Value')],'Uniform':[('minimum','Minimum'),('maximum','Maximum')],'Integer Uniform':[('minimum','Minimum'),('maximum','Maximum')],'Triangular':[('minimum','Minimum'),('most_likely','Most Likely'),('maximum','Maximum')],'Normal':[('mean','Mean'),('standard_deviation','Standard Deviation')]}.get(kind,[])):
                        fields[field]=num(variable+' Review '+label,f'dist{vkey}_{field}')
                    specs[variable]=core.monte_carlo_economics.DistributionSpec(kind,**fields)
                st.caption('Only the displayed explicit distributions are sampled; other entered financial inputs are held at their base values. Fixed and Integer Uniform period values must be integers. Phase 3Y owns distribution and domain validation.')
            trials=st.selectbox('Integrated Monte Carlo Trials — Computational Setting',(1000,5000,10000,25000,50000),index=1,key='p3z_trials')
            seed=st.number_input('Integrated Monte Carlo Seed — Optional',value=None,step=1,key='p3z_seed')
            risk=core.RiskInputs(tuple(specs.items()),trials,seed,basis)
            st.caption('The trial count is a computational setting. Monte Carlo runs only when Build Integrated Review is selected. No distribution parameters or seed are invented.')
    fingerprint=repr((mode,identification,technical,energy,econ,sensitivity,risk,currency))
    if st.button('Build Integrated Review',key='p3z_build'):
        with st.spinner('Calling selected validated Phase 3 modules…'):
            result=core.build_integrated_pump_summary(technical,flow_factors,mode=mode,identification=identification,optional_energy_inputs=energy,optional_economic_inputs=econ,optional_sensitivity_inputs=sensitivity,optional_risk_inputs=risk)
        st.session_state['p3z_last']=(fingerprint,result,fu,hu,power_unit or 'kW',currency)
    if 'p3z_last' in st.session_state:
        old,result,dfu,dhu,dpu,dcur=st.session_state['p3z_last']
        if old!=fingerprint:st.warning('Inputs changed. The report below is the previous review; select Build Integrated Review to update it.')
        # If mandatory units were absent, only unavailable metrics can use neutral
        # display labels; valid SI results keep their explicit canonical units.
        dfu=dfu if dfu in flow_factors else 'm³/s';dhu=dhu if dhu in HEAD_FACTORS else 'm'
        _render_report(st,result,dfu,dhu,dpu,dcur,flow_factors)
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.write(text)
