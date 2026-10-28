"""Variable-speed UI; vendor data and theoretical estimates remain distinct."""
from .variable_speed import evaluate_variable_speed_operating_point, NO_SCALED_POINT
from .affinity_laws import calculate_speed_affinity
from .pump_curve import create_pump_curve, curve_flow_to_si, HEAD_FACTORS
from .system_curve import model_from_k, model_from_reference, head_to_metres
from .system_sensitivity import is_unique
from .system_sensitivity_ui import _shown
from .shaft_power import POWER_FACTORS
from .pump_efficiency import power_to_watts
from .bep_operating_range import compare_bep
from .npshr_curve import create_npshr_curve, interpolate_npshr
from .npsh_margin import calculate_npsh_margin

METHODS = ('Direct K', 'Reference Flow / Friction Head')
GUIDANCE = (
    'Affinity laws provide theoretical estimates for the same pump and impeller diameter: '
    'corresponding flow scales with speed, head with speed squared and shaft power with speed cubed '
    'under the Phase 3I similarity assumptions. Affinity-scaled curves are engineering estimates, '
    'not manufacturer-certified performance curves.',
    'The actual new operating point is the intersection of the affinity-scaled pump curve and '
    'the separately defined system curve. Static system head is not scaled with pump speed. '
    'Neither pump curve is extrapolated. Multiple intersections are retained; dynamic stability is not determined.',
    'Pump efficiency may change with speed. Affinity laws do not guarantee unchanged efficiency.',
    'Use manufacturer/vendor NPSHR data for the intended operating speed. ConversionPro does not automatically scale NPSHR with speed.',
    'Motor/VFD torque capability, current limits, thermal limits, minimum cooling speed, pump minimum speed, '
    'mechanical critical speeds and manufacturer restrictions require separate review. '
    'Final selection and operating limits require manufacturer/vendor confirmation; this module does not approve a speed.'
)


def variable_speed_plot_spec(reference, result, system, ff, flow_unit, head_unit):
    hf = HEAD_FACTORS[head_unit]
    s = result.scaling
    labels = [f'Reference-Speed Pump Curve — {s.reference_speed_rpm:.12g} rpm',
              f'Affinity-Law Scaled Pump Curve — {s.new_speed_rpm:.12g} rpm',
              'System Curve (unchanged)', 'Base Operating Point', 'New Operating Point']
    layers = []
    for curve, label in [(reference, labels[0]), (s.scaled_curve, labels[1])]:
        layers.append({'data': {'values': [dict(flow=_shown(p.flow_m3_s,ff), head=_shown(p.head_m,hf), series=label) for p in curve.points]},
                       'mark': {'type':'line', 'point':True, 'strokeWidth':2.5}})
    lo = min(reference.points[0].flow_m3_s, s.scaled_curve.points[0].flow_m3_s)
    hi = max(reference.points[-1].flow_m3_s, s.scaled_curve.points[-1].flow_m3_s)
    rows = []
    for i in range(81):
        q = lo + (hi-lo)*(i/80)
        rows.append(dict(flow=_shown(q,ff), head=_shown(system.at_flow(q).total_head_m,hf), series=labels[2]))
    layers.append({'data':{'values':rows},'mark':{'type':'line','strokeDash':[6,4]}})
    for roots,label,shape in [(result.base,labels[3],'circle'),(result.new,labels[4],'diamond')]:
        layers.append({'data':{'values':[dict(flow=_shown(p.flow_m3_s,ff),head=_shown(p.head_m,hf),series=label) for p in roots.points]},
                       'mark':{'type':'point','filled':True,'shape':shape,'size':150}})
    return {'title':'Reference and New-Speed Pump/System Intersections','layer':layers,
        'encoding':{'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
                    'y':{'field':'head','type':'quantitative','title':f'Head ({head_unit})'},
                    'color':{'field':'series','type':'nominal','scale':{'domain':labels,'range':['#4e9de0','#c39ce6','#76bb85','#ed9238','#f08bb4']},
                             'legend':{'title':None,'orient':'bottom','columns':1,'labelLimit':540}},
                    'tooltip':[{'field':'series'},{'field':'flow','type':'quantitative'},{'field':'head','type':'quantitative'}]},
        'height':380,'config':{'view':{'stroke':None}}}


def _points(st, label, prefix, flow_unit, value_unit):
    count = st.number_input(label+' — Number of Points',min_value=3,max_value=20,value=3,step=1,key=prefix+'_count')
    rows=[]
    for i in range(count):
        a,b=st.columns(2)
        with a:q=st.number_input(f'{label} Point {i+1} — Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key=f'{prefix}_q_{i}')
        with b:v=st.number_input(f'{label} Point {i+1} — Value ({value_unit or "select unit above"})',value=None,format='%.12g',key=f'{prefix}_v_{i}')
        rows.append((q,v))
    return rows


def render_variable_speed(flow_factors):
    import streamlit as st
    st.subheader('3S — Variable-Speed Pump Operating Point / VSD Analysis')
    st.info('Preliminary same-pump, same-impeller speed analysis. Supply reference-speed vendor head data. Manufacturer/vendor approval remains necessary.')
    fu=st.selectbox('VSD Flow Unit',list(flow_factors),index=None,key='p3s_flow_unit')
    hu=st.selectbox('VSD Head Unit',list(HEAD_FACTORS),index=None,key='p3s_head_unit')
    st.caption('Main curve and system inputs use the selected units. Changing units reinterprets entered numbers; it does not rewrite them. Speed is rpm; direct K is SI s²/m⁵.')
    st.markdown('**Vendor Reference Pump Curve**')
    rows=_points(st,'VSD Reference Head Curve','p3s_head',fu,hu)
    n1=st.number_input('Reference Pump Speed N1 (rpm)',value=None,format='%.12g',key='p3s_n1')
    n2=st.number_input('New Pump Speed N2 (rpm)',value=None,format='%.12g',key='p3s_n2')
    st.markdown('**System Curve — Used Unchanged at Both Speeds**')
    method=st.selectbox('VSD System Method',METHODS,key='p3s_method')
    static=st.number_input(f'VSD Static Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3s_static')
    k=ref=friction=None
    if method==METHODS[0]:k=st.number_input('VSD K — SI (s²/m⁵)',value=None,format='%.12g',key='p3s_k')
    else:
        ref=st.number_input(f'VSD Reference Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3s_reference_flow')
        friction=st.number_input(f'VSD Reference Friction Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3s_friction')
    st.markdown('**Optional BEP / Corresponding-Point Power / New-Speed NPSH Context**')
    bep=st.number_input('Reference-Speed Vendor BEP Flow (optional)',value=None,format='%.12g',key='p3s_bep')
    bu=st.selectbox('VSD BEP Flow Unit',list(flow_factors),index=None,key='p3s_bep_unit')
    power=st.number_input('Reference Shaft/Brake Power at a Corresponding Point (optional)',value=None,format='%.12g',key='p3s_power')
    pu=st.selectbox('VSD Corresponding-Point Power Unit',list(POWER_FACTORS),index=None,key='p3s_power_unit')
    st.caption('Scalar power is a theoretical corresponding-point estimate, not shaft power at the newly solved system intersection or motor input power. No driver loading is inferred from this scalar.')
    mode=st.selectbox('VSD NPSH Context',('No NPSH Context','Separate Vendor NPSHR Curve for the New Speed'),key='p3s_npsh_mode')
    nr=[];nfu=nhu=na=nau=None
    if mode!='No NPSH Context':
        st.caption('Enter separate manufacturer/vendor NPSHR data applicable to N2, the intended operating speed. Reference-speed NPSHR is not transformed.')
        nfu=st.selectbox('New-Speed NPSHR Flow Unit',list(flow_factors),index=None,key='p3s_npshr_flow_unit')
        nhu=st.selectbox('New-Speed NPSHR Head Unit',list(HEAD_FACTORS),index=None,key='p3s_npshr_head_unit')
        nr=_points(st,'New-Speed Vendor NPSHR Curve','p3s_npshr',nfu,nhu)
        na=st.number_input('VSD Entered NPSHA (optional)',value=None,format='%.12g',key='p3s_npsha')
        nau=st.selectbox('VSD NPSHA Unit',list(HEAD_FACTORS),index=None,key='p3s_npsha_unit')
    st.caption('Optional numerical inputs start blank. No efficiency correction, vendor limit, speed limit or acceptance criterion is assumed.')
    if st.button('Evaluate Variable-Speed Operating Point',key='p3s_evaluate'):
        try:
            curve=create_pump_curve(rows,fu,hu,flow_factors)
            system=(model_from_k(static,hu,k) if method==METHODS[0] else model_from_reference(static_head=static,head_unit=hu,reference_flow=ref,reference_friction_head=friction,flow_unit=fu,flow_factors=flow_factors))
            result=evaluate_variable_speed_operating_point(curve,n1,n2,system)
            ff=flow_factors[fu];hf=HEAD_FACTORS[hu];s=result.scaling
            spec=variable_speed_plot_spec(curve,result,system,ff,fu,hu)
            st.markdown('**Speed and System Summary**')
            st.text(f'Reference Speed: {s.reference_speed_rpm:.12g} rpm\nNew Speed: {s.new_speed_rpm:.12g} rpm\nSpeed Ratio: {s.ratio:.12g}\nSpeed Change: {s.speed_change_percent:+.12g}%\nUnchanged Static Head: {_shown(system.static_head_m,hf):.12g} {hu}\nUnchanged K: {system.k_si:.12g} s²/m⁵')
            st.markdown('**Affinity-Law Scaled Pump Curve**')
            st.markdown('| Flow ('+fu+') | Head ('+hu+') |\n|---:|---:|\n'+'\n'.join(f'| {_shown(p.flow_m3_s,ff):.12g} | {_shown(p.head_m,hf):.12g} |' for p in s.scaled_curve.points))
            st.markdown('**Operating Point Comparison**')
            for name,roots in [('Base',result.base),('New',result.new)]:
                if not roots.points and not roots.coincident_intervals:st.info(NO_SCALED_POINT if name=='New' else 'No valid base operating point exists within the supplied reference pump-curve range.')
                if len(roots.points)>1:st.warning(name+': Multiple intersections exist. All are reported; no operating point or dynamic stability is selected automatically.')
                for i,p in enumerate(roots.points,1):st.text(f'{name} Intersection {i}\nOperating Flow: {_shown(p.flow_m3_s,ff):.12g} {fu}\nOperating Head: {_shown(p.head_m,hf):.12g} {hu}\nPump/System Residual: {_shown(p.residual_m,hf):+.6g} {hu}')
                for interval in roots.coincident_intervals:
                    st.warning(f'{name}: Pump and system curves coincide; no unique operating point exists.')
                    st.text(f'{name} Coincident Flow Interval: {_shown(interval.minimum_flow_m3_s,ff):.12g} to {_shown(interval.maximum_flow_m3_s,ff):.12g} {fu}')
            if result.flow_change is not None:
                pct=lambda v:'N/A — base value is zero' if v is None else f'{v:+.12g}%'
                st.text(f'Flow Shift: {_shown(result.flow_change.difference,ff):+.12g} {fu}\nFlow Change: {pct(result.flow_change.percent)}\nHead Shift: {_shown(result.head_change.difference,hf):+.12g} {hu}\nHead Change: {pct(result.head_change.percent)}')
            else:st.info('Single shifts require exactly one isolated intersection at each speed and no coincident intervals. All returned intersections are retained.')
            if bep is not None:
                try:
                    b=curve_flow_to_si(bep,bu,flow_factors)
                    scaled_bep=calculate_speed_affinity(b,0,0,n1,n2).estimated_flow_m3_s
                    # Phase 3H rejects zero vendor BEP, including a supplied zero.
                    compare_bep(0,b)
                    st.text(f'Affinity-Law Scaled BEP Flow: {_shown(scaled_bep,ff):.12g} {fu}')
                    for name,roots,flow in [('Base',result.base,b),('New (theoretical scaled BEP basis)',result.new,scaled_bep)]:
                        for i,p in enumerate(roots.points,1):st.text(f'{name} Intersection {i} Percent of BEP: {compare_bep(p.flow_m3_s,flow).percent_bep:.12g}%')
                    st.caption('Scaled BEP flow is theoretical corresponding-flow context, not manufacturer-certified BEP at the new speed.')
                except (ValueError,OverflowError) as exc:st.error('BEP context: '+str(exc))
            if power is not None:
                try:
                    pw=power_to_watts(power,pu,'Reference corresponding-point shaft power',allow_zero=True)
                    scaled=calculate_speed_affinity(0,0,pw,n1,n2).estimated_power_w
                    st.text(f'Affinity-Law Scaled Power: {_shown(scaled,POWER_FACTORS[pu]):.12g} {pu}')
                    st.caption('Corresponding-point estimate only; not the solved new operating-point shaft power or motor input power. Similar-efficiency assumptions require review.')
                except (ValueError,OverflowError) as exc:st.error('Corresponding-point power: '+str(exc))
            if mode!='No NPSH Context':
                try:
                    nc=create_npshr_curve(nr,nfu,nhu,flow_factors)
                    available=head_to_metres(na,nau,'Entered NPSHA') if na is not None else None
                    for i,p in enumerate(result.new.points,1):
                        try:
                            required=interpolate_npshr(nc,p.flow_m3_s).npshr_m
                            text=f'New Intersection {i} Vendor NPSHR at N2: {_shown(required,hf):.12g} {hu}'
                            if available is not None:
                                margin=calculate_npsh_margin(available,required)
                                text+=f'\nNew-Speed NPSH Margin: {_shown(margin.margin_m,hf):+.12g} {hu}\n{margin.relationship_status}'
                            st.text(text)
                        except (ValueError,OverflowError) as exc:st.info(f'New Intersection {i} NPSH context: '+str(exc))
                except (ValueError,OverflowError) as exc:st.error('New-speed NPSH context: '+str(exc))
            st.vega_lite_chart(spec=spec,width='stretch')
            st.caption('Blue: reference head curve. Purple: affinity-scaled head curve. Green: unchanged system curve. Orange circles: base intersections. Pink diamonds: new intersections. Curves stop at their respective supplied/scaled flow endpoints.')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.caption(text)
