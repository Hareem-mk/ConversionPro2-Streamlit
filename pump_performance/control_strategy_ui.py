"""Control strategies at the same target; explicit power and economics boundaries."""
from .control_strategy import (compare_throttling_and_vsd,difference_relative_to_first,compare_shaft_power,
    compare_input_power,annual_energy,calculate_driver_margin,validate_shaft_hydraulic_basis)
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS
from .system_curve import model_from_k,model_from_reference
from .variable_speed_ui import _points
from .system_sensitivity_ui import _shown
from .power_curve import create_power_curve
from .pump_efficiency import power_to_watts
from .shaft_power import POWER_FACTORS
from .affinity_laws import calculate_speed_affinity
from .bep_operating_range import compare_bep
from .target_speed import NO_SOLUTION

METHODS=('Direct K','Reference Flow / Friction Head')
GUIDANCE=(
    'Throttling controls flow by changing system resistance while pump speed remains constant. Variable-speed control changes the pump curve by changing speed. For the same reduced flow, a VSD case may require less head.',
    'Hydraulic power comparison does not by itself establish shaft or electrical energy savings.',
    'Hydraulic power is not shaft power, motor input power or electrical input power. Electrical energy comparisons require valid shaft power and motor/VFD efficiencies. Affinity-scaled power is an engineering estimate; check manufacturer data. Pump efficiency may change with speed.',
    'VSD NPSHR is not calculated automatically; use manufacturer/vendor data for the intended speed.',
    'The hydraulic and power consequences of each control method are shown separately. Final control-strategy selection should also consider process requirements, minimum flow, pump operating range, NPSH, reliability, control response, motor/VFD limits, CAPEX, and lifecycle economics.',
    'Affinity estimates apply to the same pump and impeller diameter. No pump curve is extrapolated. Multiple speed solutions and operating intersections do not establish dynamic stability. Manufacturer/vendor data should be used for final design.'
)


def comparison_plot_spec(curve,result,solution,ff,fu,hu):
    hf=HEAD_FACTORS[hu];layers=[]
    labels=['Reference-Speed Pump Curve','Base System Curve','Required Constant-Speed System Curve','VSD Affinity-Scaled Pump Curve','Target Constant-Speed Point','Target VSD Point']
    def add(rows,mark):layers.append({'data':{'values':rows},'mark':mark})
    def pump(c,label):add([dict(flow=_shown(p.flow_m3_s,ff),head=_shown(p.head_m,hf),series=label) for p in c.points],{'type':'line','point':True,'strokeWidth':2.5})
    pump(curve,labels[0])
    domain=[curve]
    if solution is not None:domain.append(solution.scaled_curve)
    lo=min(c.points[0].flow_m3_s for c in domain);hi=max(c.points[-1].flow_m3_s for c in domain)
    for model,label in [(result.base_system,labels[1]),(result.constant_speed.system if result.constant_speed else None,labels[2])]:
        if model is None:continue
        rows=[]
        for i in range(81):
            q=lo+(hi-lo)*i/80;rows.append(dict(flow=_shown(q,ff),head=_shown(model.at_flow(q).total_head_m,hf),series=label))
        add(rows,{'type':'line','strokeDash':[6,4]})
    if solution is not None:pump(solution.scaled_curve,labels[3])
    for head,label,shape in [(result.constant_speed.head_m if result.constant_speed else None,labels[4],'circle'),(result.vsd.target_system_head_m if solution is not None else None,labels[5],'diamond')]:
        if head is not None:add([dict(flow=_shown(result.target_flow_m3_s,ff),head=_shown(head,hf),series=label)],{'type':'point','filled':True,'shape':shape,'size':150})
    return _spec(layers,labels,fu,f'Head ({hu})','Control Comparison — Same Target Flow')


def _spec(layers,labels,fu,ytitle,title):
    return {'title':title,'layer':layers,'encoding':{'x':{'field':'flow','type':'quantitative','title':f'Flow ({fu})','scale':{'zero':False}},
        'y':{'field':'head','type':'quantitative','title':ytitle},'color':{'field':'series','type':'nominal','scale':{'domain':labels,'range':['#4e9de0','#76bb85','#ed9238','#c39ce6','#f2b567','#f08bb4'][:len(labels)]},'legend':{'title':None,'orient':'bottom','columns':1,'labelLimit':540}},
        'tooltip':[{'field':'series'},{'field':'flow','type':'quantitative'},{'field':'head','type':'quantitative'}]},'height':520,'config':{'view':{'stroke':None}}}


def power_plot_spec(reference,comparison,q,ff,fu,pu):
    pf=POWER_FACTORS[pu];labels=['Reference-Speed Vendor Power Curve','Affinity-Scaled VSD Power Curve','Constant-Speed Shaft-Power Point','VSD Shaft-Power Point'];layers=[]
    for c,label in [(reference,labels[0]),(comparison.scaled_curve,labels[1])]:
        layers.append({'data':{'values':[dict(flow=_shown(p.flow_m3_s,ff),head=_shown(p.shaft_power_w,pf),series=label) for p in c.points]},'mark':{'type':'line','point':True}})
    for p,label,shape in [(comparison.constant_w,labels[2],'circle'),(comparison.vsd_w,labels[3],'diamond')]:
        layers.append({'data':{'values':[dict(flow=_shown(q,ff),head=_shown(p,pf),series=label)]},'mark':{'type':'point','filled':True,'shape':shape,'size':150}})
    spec=_spec(layers,labels,fu,f'Shaft Power ({pu})','Shaft-Power Context — Supplied / Affinity-Scaled Data')
    spec['encoding']['tooltip'][-1]['title']=f'Shaft Power ({pu})'
    return spec


def render_control_strategy(flow_factors):
    import streamlit as st
    st.subheader('3U — Throttling vs VSD Control Comparison / Energy Impact Analysis')
    st.info('Compare the same pump at the same target flow. Hydraulic, shaft and supply-input power are separate quantities; no overall control strategy is selected automatically.')
    fu=st.selectbox('Control Comparison Flow Unit',list(flow_factors),index=None,key='p3u_flow_unit')
    hu=st.selectbox('Control Comparison Head Unit',list(HEAD_FACTORS),index=None,key='p3u_head_unit')
    pu=st.selectbox('Control Comparison Display Power Unit',list(POWER_FACTORS),key='p3u_display_power_unit')
    st.caption('Main curve/system/target units apply together. Changing units reinterprets numbers rather than rewriting them. Speed is rpm; density is kg/m³; direct K is SI s²/m⁵.')
    rows=_points(st,'Control Reference Head Curve','p3u_head',fu,hu)
    speed=st.number_input('Control Reference Speed (rpm)',value=None,format='%.12g',key='p3u_speed')
    method=st.selectbox('Control Base System Method',METHODS,key='p3u_method')
    static=st.number_input(f'Control Static Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3u_static')
    k=ref=friction=None
    if method==METHODS[0]:k=st.number_input('Control Base K — SI (s²/m⁵)',value=None,format='%.12g',key='p3u_k')
    else:
        ref=st.number_input(f'Control Reference Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3u_reference_flow')
        friction=st.number_input(f'Control Reference Friction Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3u_friction')
    target=st.number_input(f'Control Target Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3u_target')
    density=st.number_input('Control Fluid Density (kg/m³)',value=None,format='%.12g',key='p3u_density')
    st.markdown('**Optional Vendor Shaft-Power / Input-Power Data**')
    power_mode=st.selectbox('Control Shaft-Power Context',('No Shaft-Power Context','Reference-Speed Vendor Power Curve'),key='p3u_power_mode')
    prows=[];pfu=ppu=driver=driver_unit=em1=em2=evfd=None
    if power_mode!='No Shaft-Power Context':
        pfu=st.selectbox('Control Vendor Power Flow Unit',list(flow_factors),index=None,key='p3u_power_flow_unit')
        ppu=st.selectbox('Control Vendor Power Value Unit',list(POWER_FACTORS),index=None,key='p3u_power_value_unit')
        prows=_points(st,'Control Vendor Power Curve','p3u_power',pfu,ppu)
        driver=st.number_input('Control Driver Rated Power (optional)',value=None,format='%.12g',key='p3u_driver')
        driver_unit=st.selectbox('Control Driver Power Unit',list(POWER_FACTORS),index=None,key='p3u_driver_unit')
        em1=st.number_input('Constant-Speed Motor Efficiency (%) — optional',value=None,format='%.12g',key='p3u_motor_constant')
        em2=st.number_input('VSD-Case Motor Efficiency (%) — optional',value=None,format='%.12g',key='p3u_motor_vsd')
        evfd=st.number_input('VFD Efficiency (%) — optional',value=None,format='%.12g',key='p3u_vfd_efficiency')
    st.markdown('**Optional Annual Electrical Energy / Cost**')
    hours=st.number_input('Annual Operating Hours (optional)',value=None,format='%.12g',key='p3u_hours')
    tariff=st.number_input('Electricity Cost per kWh (optional)',value=None,format='%.12g',key='p3u_tariff')
    currency=st.text_input('User-Defined Currency Label (optional)',value='',key='p3u_currency')
    st.caption('Annual electrical energy requires valid shaft powers, both entered motor efficiencies and entered VFD efficiency. Costs additionally require a tariff and currency label. No hours, tariff, efficiency, CAPEX or payback is assumed.')
    bep=st.number_input('Control Reference-Speed Vendor BEP Flow (optional)',value=None,format='%.12g',key='p3u_bep')
    bu=st.selectbox('Control BEP Flow Unit',list(flow_factors),index=None,key='p3u_bep_unit')
    if st.button('Compare Throttling and VSD',key='p3u_compare'):
        try:
            curve=create_pump_curve(rows,fu,hu,flow_factors)
            model=(model_from_k(static,hu,k) if method==METHODS[0] else model_from_reference(static_head=static,head_unit=hu,reference_flow=ref,reference_friction_head=friction,flow_unit=fu,flow_factors=flow_factors))
            q=curve_flow_to_si(target,fu,flow_factors);result=compare_throttling_and_vsd(curve,speed,model,q,density)
            ff=flow_factors[fu];hf=HEAD_FACTORS[hu];power_factor=POWER_FACTORS[pu]
            st.markdown('**Same-Target Control Summary**')
            st.text(f'Target Flow: {_shown(q,ff):.12g} {fu}\nReference Speed: {speed:.12g} rpm\nBase K: {model.k_si:.12g} s²/m⁵\nUnchanged Static Head: {_shown(model.static_head_m,hf):.12g} {hu}')
            cs=result.constant_speed
            if result.constant_speed_error:st.info('Constant-Speed Strategy Unavailable: '+result.constant_speed_error)
            if cs:
                direction='increased' if cs.system.k_si>model.k_si else 'decreased' if cs.system.k_si<model.k_si else 'unchanged'
                st.markdown('**'+('Constant-Speed Throttling Case' if direction=='increased' else 'Required Constant-Speed System Resistance')+'**')
                pct='N/A — base K is zero' if result.resistance_change.percent is None else f'{result.resistance_change.percent:+.12g}%'
                st.text(f'Constant-Speed Pump Speed: {speed:.12g} rpm\nReference Pump Head at Target: {_shown(cs.head_m,hf):.12g} {hu}\nRequired Friction Head at Target: {_shown(cs.friction_head_m,hf):.12g} {hu}\nRequired Constant-Speed System K: {cs.system.k_si:.12g} s²/m⁵\nResistance Change: {result.resistance_change.difference:+.12g} s²/m⁵\nResistance Change Percent: {pct}\nConstant-Speed Verified Flow: {_shown(cs.verified_point.flow_m3_s,ff):.12g} {fu}\nConstant-Speed Verified Head: {_shown(cs.verified_point.head_m,hf):.12g} {hu}\nConstant-Speed Hydraulic Power: {_shown(result.constant_hydraulic_w,power_factor):.12g} {pu}')
                st.write('Required constant-speed system resistance '+direction+'.')
                if direction=='decreased':st.info('This target requires reduced resistance, so the constant-speed case is not a throttling-only interpretation. A valve is not assumed to create negative resistance.')
                for i,p in enumerate(cs.verification.points,1):st.text(f'Constant-Speed Phase 3G Intersection {i}: {_shown(p.flow_m3_s,ff):.12g} {fu}, {_shown(p.head_m,hf):.12g} {hu}')
            if result.vsd_error:st.info('VSD Strategy Unavailable: '+result.vsd_error)
            vsd=result.vsd
            if vsd:
                for i,p in enumerate(vsd.base.points,1):st.text(f'Base Operating Intersection {i}: {_shown(p.flow_m3_s,ff):.12g} {fu}, {_shown(p.head_m,hf):.12g} {hu}')
                if not vsd.solutions and not vsd.coincident_ratio_intervals:st.info('VSD Strategy Unavailable: '+NO_SOLUTION)
                if len(vsd.solutions)>1:st.warning('Multiple VSD speed solutions exist. Every solution is reported separately; no strategy or dynamic stability is selected.')
                for interval in vsd.coincident_ratio_intervals:st.warning(f'VSD has a continuous speed-ratio solution interval: {interval.minimum_ratio:.12g} to {interval.maximum_ratio:.12g}. No representative speed is selected.')
            power_curve=None
            if power_mode!='No Shaft-Power Context':
                try:power_curve=create_power_curve(prows,pfu,ppu,flow_factors)
                except (ValueError,OverflowError) as exc:st.error('Vendor power context: '+str(exc))
            solutions=vsd.solutions if vsd else ()
            for index,solution in enumerate(solutions,1):
                st.markdown(f'**VSD Case {index}**')
                st.text(f'VSD Required Speed: {solution.required_speed_rpm:.12g} rpm\nVSD Speed Ratio: {solution.ratio:.12g}\nVSD Verified Flow: {_shown(solution.verified_flow_m3_s,ff):.12g} {fu}\nVSD Verified Head: {_shown(solution.verified_head_m,hf):.12g} {hu}\nVSD Hydraulic Power: {_shown(result.vsd_hydraulic_w[index-1],power_factor):.12g} {pu}')
                if cs:
                    st.markdown('| Quantity | Constant-Speed | VSD |\n|---|---:|---:|\n'
                        f'| Target Flow ({fu}) | {_shown(q,ff):.12g} | {_shown(q,ff):.12g} |\n'
                        f'| Pump Speed (rpm) | {speed:.12g} | {solution.required_speed_rpm:.12g} |\n'
                        f'| System K (s²/m⁵) | {cs.system.k_si:.12g} | {model.k_si:.12g} |\n'
                        f'| Operating Head ({hu}) | {_shown(cs.head_m,hf):.12g} | {_shown(vsd.target_system_head_m,hf):.12g} |\n'
                        f'| Hydraulic Power ({pu}) | {_shown(result.constant_hydraulic_w,power_factor):.12g} | {_shown(result.vsd_hydraulic_w[index-1],power_factor):.12g} |')
                    hd=difference_relative_to_first(cs.head_m,vsd.target_system_head_m);pd=difference_relative_to_first(result.constant_hydraulic_w,result.vsd_hydraulic_w[index-1])
                    st.text(f'Head Difference (Constant-Speed minus VSD): {_shown(hd.difference,hf):+.12g} {hu}\nHead Difference Percent: {hd.percent:+.12g}%\nHydraulic Power Difference: {_shown(pd.difference,power_factor):+.12g} {pu}\nHydraulic Power Difference Percent: {pd.percent:+.12g}%')
                for i,p in enumerate(solution.verification.points,1):st.text(f'VSD Case {index} — Phase 3G Intersection {i}: {_shown(p.flow_m3_s,ff):.12g} {fu}, {_shown(p.head_m,hf):.12g} {hu}')
                shaft=inputs=None
                if power_curve is not None and cs:
                    try:
                        shaft=compare_shaft_power(power_curve,speed,solution.required_speed_rpm,q)
                        pct='N/A — constant-speed shaft power is zero' if shaft.difference.percent is None else f'{shaft.difference.percent:+.12g}%'
                        shaft_label='Vendor-Interpolated Throttling Shaft Power' if cs.system.k_si>model.k_si else 'Vendor-Interpolated Constant-Speed Shaft Power'
                        st.text(f'{shaft_label}: {_shown(shaft.constant_w,power_factor):.12g} {pu}\nAffinity-Law Scaled VSD Shaft Power: {_shown(shaft.vsd_w,power_factor):.12g} {pu}\nShaft Power Difference: {_shown(shaft.difference.difference,power_factor):+.12g} {pu}\nShaft Power Difference Percent: {pct}')
                        st.caption('Calculated shaft-power reduction under the supplied/affinity-scaled data assumptions. This is not a guaranteed electrical energy saving.')
                        consistent=True
                        try:validate_shaft_hydraulic_basis(shaft,result.constant_hydraulic_w,result.vsd_hydraulic_w[index-1])
                        except ValueError as exc:
                            consistent=False;st.info('Supplied Power Data Basis: '+str(exc))
                        if driver is not None and consistent:
                            try:
                                rating=power_to_watts(driver,driver_unit,'Driver rated power',allow_zero=False)
                                for name,value in [('Constant-Speed',shaft.constant_w),('VSD',shaft.vsd_w)]:
                                    margin=calculate_driver_margin(value,rating);st.text(f'{name} Driver Margin: {_shown(margin.margin_w,power_factor):+.12g} {pu}')
                            except (ValueError,OverflowError) as exc:st.error('Driver context: '+str(exc))
                        if consistent and (em1 is not None or em2 is not None or evfd is not None):
                            try:
                                inputs=compare_input_power(shaft,em1,em2,evfd)
                                st.text(f'Constant-Speed Motor Input Power: {_shown(inputs.constant_motor_input_w,power_factor):.12g} {pu}\nVSD-Case Motor Input Power: {_shown(inputs.vsd_motor_input_w,power_factor):.12g} {pu}')
                                if inputs.vsd_drive_input_w is not None:st.text(f'VFD Supply Input Power: {_shown(inputs.vsd_drive_input_w,power_factor):.12g} {pu}')
                            except (ValueError,OverflowError) as exc:st.error('Input-power context: '+str(exc))
                        if hours is not None:
                            try:
                                if not consistent:raise ValueError('Supplied shaft and hydraulic powers are inconsistent; use applicable data before estimating electrical energy.')
                                energy=annual_energy(inputs,hours,tariff)
                                st.text(f'Constant-Speed Annual Electrical Energy: {energy.constant_kwh:.12g} kWh\nVSD Annual Electrical Energy: {energy.vsd_kwh:.12g} kWh\nAnnual Electrical Energy Difference: {energy.difference_kwh:+.12g} kWh')
                                st.caption('Calculated supply-input energy under entered steady-duty hours and motor/VFD efficiencies; excludes unmodeled auxiliaries and varying duty.')
                                if tariff is not None:
                                    if currency.strip():st.text(f'Annual Cost Difference: {energy.difference_cost:+.12g} {currency.strip()}')
                                    else:st.info('Enter a currency label to display the entered-tariff cost comparison.')
                            except (ValueError,OverflowError) as exc:st.info('Annual Electrical Energy Unavailable: '+str(exc))
                        st.vega_lite_chart(spec=power_plot_spec(power_curve,shaft,q,ff,fu,pu),width='stretch')
                    except (ValueError,OverflowError) as exc:st.info('Shaft-Power Comparison Unavailable: '+str(exc))
                if hours is not None and shaft is None:st.info('Annual Electrical Energy Unavailable: valid comparable shaft and supply-input powers have not been established. Hydraulic power is not used as electrical input.')
                if bep is not None:
                    try:
                        base_bep=curve_flow_to_si(bep,bu,flow_factors);constant_bep=compare_bep(q,base_bep)
                        scaled=calculate_speed_affinity(base_bep,0,0,speed,solution.required_speed_rpm).estimated_flow_m3_s
                        st.text(f'Constant-Speed Percent of Vendor BEP: {constant_bep.percent_bep:.12g}%\nAffinity-Law Scaled VSD BEP Flow: {_shown(scaled,ff):.12g} {fu}\nVSD Percent of Affinity-Scaled BEP: {compare_bep(q,scaled).percent_bep:.12g}%')
                        st.caption('VSD BEP context is theoretical affinity-law corresponding flow, not manufacturer certification.')
                    except (ValueError,OverflowError) as exc:st.error('BEP context: '+str(exc))
                st.vega_lite_chart(spec=comparison_plot_spec(curve,result,solution,ff,fu,hu),width='stretch')
            if not solutions:st.vega_lite_chart(spec=comparison_plot_spec(curve,result,None,ff,fu,hu),width='stretch')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.caption(text)
