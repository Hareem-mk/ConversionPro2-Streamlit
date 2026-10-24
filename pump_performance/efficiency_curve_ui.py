"""Phase 3M interface; explicit inputs, shared 3G/3H/3A/3B kernels."""
from .efficiency_curve import create_efficiency_curve, interpolate_efficiency, find_peak_supplied_efficiency
from .pump_curve import curve_flow_to_si, create_pump_curve, HEAD_FACTORS, RISING_HEAD_WARNING
from .system_curve import model_from_reference, model_from_k
from .system_curve_ui import METHODS, MODEL_GUIDANCE
from .operating_point import find_operating_points, NO_INTERSECTION, MULTIPLE_INTERSECTIONS
from .bep_operating_range import compare_bep
from .hydraulic_power import hydraulic_power
from .shaft_power import shaft_power

METHODS_3M = ('Manual Operating Flow', 'From Phase 3G Operating Point')
GUIDANCE = 'Use efficiency data from the applicable manufacturer/vendor pump performance curve for the selected pump speed and impeller diameter.'


def efficiency_plot_spec(curve, factor, unit, operating=None):
    rows = [{'flow':p.flow_m3_s/factor,'efficiency':p.efficiency_percent} for p in curve.points]
    peak = find_peak_supplied_efficiency(curve)
    layers = [
        {'data':{'values':rows},'mark':{'type':'line','point':True,'color':'#4e9de0'}},
        {'data':{'values':[{'flow':q/factor,'efficiency':peak.efficiency_percent} for q in peak.flows_m3_s]},
         'mark':{'type':'point','shape':'diamond','filled':True,'size':180,'color':'#ed9238'}},
    ]
    if operating is not None:
        layers.append({'data':{'values':[{'flow':operating.flow_m3_s/factor,'efficiency':operating.efficiency_percent}]},
                       'mark':{'type':'point','shape':'circle','filled':True,'size':150,'color':'#76bb85'}})
    return {'title':'Vendor Pump Efficiency Curve','layer':layers,'encoding':{
        'x':{'field':'flow','type':'quantitative','title':f'Flow ({unit})','scale':{'zero':False}},
        'y':{'field':'efficiency','type':'quantitative','title':'Efficiency (%)','scale':{'domain':[0,100]}},
        'tooltip':[{'field':'flow','type':'quantitative'},{'field':'efficiency','type':'quantitative'}]},
        'height':360,'config':{'view':{'stroke':None}}}


def render_efficiency_curve(flow_factors, density_factors):
    import streamlit as st
    st.subheader('3M — Pump Efficiency Curve / Operating Efficiency')
    st.info(GUIDANCE)
    method = st.selectbox('Efficiency Calculation Method', METHODS_3M, key='p3m_method')
    st.markdown('**Vendor Efficiency Curve**')
    unit = st.selectbox('Efficiency-Curve Flow Unit', list(flow_factors), index=None, key='p3m_curve_unit')
    count = st.number_input('Number of Efficiency Points', min_value=3, max_value=20, value=3, step=1, key='p3m_count')
    points = []
    for i in range(count):
        left,right = st.columns(2)
        with left:q=st.number_input(f'Efficiency Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3m_q_{i}')
        with right:e=st.number_input(f'Efficiency Point {i+1} — Efficiency (%)',value=None,format='%.12g',key=f'p3m_e_{i}')
        points.append((q,e))
    st.caption('Enter 3–20 supplied points. Points are sorted by flow; duplicate flows are rejected. Unit changes reinterpret entered numbers, rather than converting them.')
    st.markdown('**Operating Flow**')
    op_unit = st.selectbox('Operating Flow Unit', list(flow_factors), index=None, key='p3m_op_unit')
    integrated = method == METHODS_3M[1]
    if not integrated:
        operating = st.number_input(f'Efficiency Operating Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3m_operating')
    else:
        st.caption('Independent single-pump Q–H and system inputs reuse Phase 3G. No Phase 3L combined curve is used.')
        head_unit = st.selectbox('Efficiency Operating-Point Head Unit',list(HEAD_FACTORS),index=None,key='p3m_head_unit')
        qh_count=st.number_input('Efficiency Integration — Number of Pump Q–H Points',min_value=3,max_value=20,value=3,step=1,key='p3m_qh_count')
        qh=[]
        for i in range(qh_count):
            left,right=st.columns(2)
            with left:q=st.number_input(f'Efficiency Pump Point {i+1} — Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key=f'p3m_pq_{i}')
            with right:h=st.number_input(f'Efficiency Pump Point {i+1} — Head ({head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3m_ph_{i}')
            qh.append((q,h))
        sys_method=st.selectbox('Efficiency Integration — System Method',METHODS,key='p3m_sys_method')
        static=st.number_input(f'Efficiency System Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3m_static')
        if sys_method==METHODS[0]:
            reference=st.number_input(f'Efficiency System Reference Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3m_reference')
            friction=st.number_input(f'Efficiency System Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3m_friction')
        else:k=st.number_input('Efficiency System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3m_k')
        st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional Vendor BEP Comparison**')
    bep=st.number_input('Vendor BEP Flow (optional)',value=None,format='%.12g',key='p3m_bep')
    bep_unit=st.selectbox('Vendor BEP Flow Unit',list(flow_factors),index=None,key='p3m_bep_unit')
    st.caption('Vendor BEP Flow starts blank and is never inferred from the efficiency-curve peak.')
    power=st.selectbox('Optional Power Calculation',['Do not calculate power','Calculate hydraulic and shaft power'],key='p3m_power')
    if power!='Do not calculate power':
        density=st.number_input('Efficiency Power — Fluid Density',value=None,format='%.12g',key='p3m_density')
        density_unit=st.selectbox('Efficiency Power — Density Unit',list(density_factors),index=None,key='p3m_density_unit')
        if not integrated:
            power_head=st.number_input('Efficiency Power — Pump Head',value=None,format='%.12g',key='p3m_power_head')
            power_head_unit=st.selectbox('Efficiency Power — Head Unit',list(HEAD_FACTORS),index=None,key='p3m_power_head_unit')
        else:st.caption('Power calculation uses the Phase 3G operating head.')
    if st.button('Calculate Operating Efficiency',key='p3m_calculate'):
        try:
            curve=create_efficiency_curve(points,unit,flow_factors)
            # Validate an explicit operating unit even in integrated mode.
            curve_flow_to_si(0,op_unit,flow_factors)
            head=None
            if integrated:
                pump=create_pump_curve(qh,op_unit,head_unit,flow_factors)
                model=(model_from_reference(static_head=static,head_unit=head_unit,reference_flow=reference,
                       reference_friction_head=friction,flow_unit=op_unit,flow_factors=flow_factors)
                       if sys_method==METHODS[0] else model_from_k(static,head_unit,k))
                roots=find_operating_points(pump,model)
                if roots.coincident_intervals:
                    raise ValueError('Pump and system curves coincide over an interval; no unique operating flow is selected.')
                if not roots.points:raise ValueError(NO_INTERSECTION)
                if len(roots.points)!=1:raise ValueError(MULTIPLE_INTERSECTIONS+' No operating flow is selected; use manual mode for an explicitly chosen flow.')
                operating_si=roots.points[0].flow_m3_s
                head=roots.points[0].head_m
                if pump.has_rising_head:st.warning(RISING_HEAD_WARNING)
            else:operating_si=curve_flow_to_si(operating,op_unit,flow_factors)
            result=interpolate_efficiency(curve,operating_si)
            peak=find_peak_supplied_efficiency(curve)
            comparison=compare_bep(operating_si,curve_flow_to_si(bep,bep_unit,flow_factors)) if bep is not None else None
            hydraulic=shaft=None
            if power!='Do not calculate power':
                if not integrated:
                    if power_head_unit not in HEAD_FACTORS:raise ValueError('Select a supported head unit: m or ft.')
                    from piping_hydraulics.pipe_capacity import nonnegative
                    head=nonnegative(power_head,'Pump head')*HEAD_FACTORS[power_head_unit]
                hydraulic=hydraulic_power(density=density,density_unit=density_unit,flow=operating_si,
                    flow_unit='m³/s',head_m=head,density_factors=density_factors,flow_factors=flow_factors)
                shaft=shaft_power(hydraulic.watts,'W',result.efficiency_percent)
            st.markdown('**Efficiency Results**')
            st.text(f'Operating Flow: {operating_si/flow_factors[op_unit]:.12g} {op_unit}\nInterpolated Vendor Efficiency: {result.efficiency_percent:.12g}%')
            if integrated:st.text(f'Phase 3G Operating Head: {head:.12g} m')
            st.text(f'Peak Supplied Efficiency Point\nPeak Supplied Efficiency: {peak.efficiency_percent:.12g}%\nPeak Supplied Efficiency Flow(s): '+', '.join(f'{q/flow_factors[unit]:.12g}' for q in peak.flows_m3_s)+' '+unit)
            # Compare to every tied peak; no silent selection of a single peak.
            st.text('Operating Flow Minus Peak Supplied Flow(s): '+', '.join(f'{(operating_si-q)/flow_factors[unit]:+.12g}' for q in peak.flows_m3_s)+' '+unit)
            if comparison:st.text(f'Percent of BEP: {comparison.percent_bep:.12g}%')
            if hydraulic:st.text(f'Hydraulic Power: {hydraulic.watts:.12g} W\nEstimated Shaft Power using interpolated efficiency: {shaft.shaft_watts:.12g} W')
            st.vega_lite_chart(spec=efficiency_plot_spec(curve,flow_factors[unit],unit,result),width='stretch')
            st.caption('Blue: supplied points and straight segments. Green circle: operating point. Orange diamond(s): Peak Supplied Efficiency Point(s).')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('Pump efficiency varies with operating flow. '+GUIDANCE)
    st.caption('ConversionPro uses linear interpolation only between supplied efficiency points. Efficiency is not extrapolated beyond supplied data.')
    st.caption('The automatically identified Peak Supplied Efficiency Point is not automatically the official vendor BEP. No universal efficiency acceptance tolerance is assumed.')
    st.caption('Final pump selection and performance verification should use complete manufacturer/vendor data. No automatic pump selection is performed.')
