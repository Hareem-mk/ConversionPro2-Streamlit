"""Vendor NPSHR interpolation with unchanged Phase 3G, 2H and 3J kernels."""
import math
from .npshr_curve import create_npshr_curve,interpolate_npshr,find_npshr_extrema
from .pump_curve import curve_flow_to_si,create_pump_curve,HEAD_FACTORS,RISING_HEAD_WARNING
from .system_curve import head_to_metres,model_from_reference,model_from_k
from .system_curve_ui import METHODS,MODEL_GUIDANCE
from .operating_point import find_operating_points,NO_INTERSECTION,MULTIPLE_INTERSECTIONS
from .npsh_margin import calculate_npsh_margin,margin_from_phase2h,compare_required_margin
from piping_hydraulics.pump_head import pressure_to_pa
from piping_hydraulics.npsha import source_npsha,flange_npsha

METHODS_3O=('Manual Operating Flow','From Phase 3G Operating Point')
AVAILABLE_METHODS=('No NPSHA Comparison','Manual NPSHA','Suction-Flange Method','Vessel/Source Method')
GUIDANCE='Use NPSHR data from the applicable manufacturer/vendor pump performance curve for the selected pump speed and impeller diameter.'


def _shown(value,factor):
    converted=value/factor
    if not math.isfinite(converted) or (value != 0 and converted == 0):
        raise ValueError('Displayed NPSHR/head value exceeds the supported numeric range.')
    return converted


def npshr_plot_spec(curve,flow_factor,flow_unit,head_unit,operating):
    factor=HEAD_FACTORS[head_unit]
    layers=[
        {'data':{'values':[{'flow':_shown(p.flow_m3_s,flow_factor),'npshr':_shown(p.npshr_m,factor)} for p in curve.points]},
         'mark':{'type':'line','point':True,'color':'#4e9de0'},
         'encoding':{'y':{'field':'npshr','type':'quantitative','title':f'Vendor NPSHR ({head_unit})'}}},
        {'data':{'values':[{'flow':_shown(operating.flow_m3_s,flow_factor)}]},
         'mark':{'type':'rule','strokeDash':[4,4],'color':'#76bb85'}},
        {'data':{'values':[{'flow':_shown(operating.flow_m3_s,flow_factor),'npshr':_shown(operating.npshr_m,factor)}]},
         'mark':{'type':'point','filled':True,'size':150,'color':'#ed9238'},
         'encoding':{'y':{'field':'npshr','type':'quantitative','title':f'Vendor NPSHR ({head_unit})'}}}]
    return {'title':'Vendor NPSHR Curve','layer':layers,'encoding':{
        'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
        'tooltip':[{'field':'flow','type':'quantitative'},{'field':'npshr','type':'quantitative'}]},
        'height':360,'config':{'view':{'stroke':None}}}


def _available_inputs(st,source,pressure_factors):
    st.caption('Use one common elevation datum, positive upward. Enter the actual liquid vapor pressure at pumping temperature/composition; no liquid-property assumptions are made.')
    if source:
        st.caption('Vessel/source reference: subtract source-to-pump suction losses once. Enter surface velocity explicitly, including zero where justified.')
    else:
        st.caption('Suction-flange reference: measured pressure already reflects upstream losses; no additional suction-loss subtraction applies.')
    basis=st.selectbox('NPSHR Check — Pressure Basis',['Absolute','Gauge'],index=None,key='p3o_basis')
    unit=st.selectbox('NPSHR Check — Pressure Unit',list(pressure_factors),index=None,key='p3o_pressure_unit')
    pressure=st.number_input('NPSHR Check — Source Surface Pressure' if source else 'NPSHR Check — Suction Pressure',value=None,format='%.12g',key='p3o_pressure')
    atmosphere=atm_unit=None
    if basis=='Gauge':
        atmosphere=st.number_input('NPSHR Check — Local Atmospheric Pressure (absolute)',value=None,format='%.12g',key='p3o_atmosphere')
        atm_unit=st.selectbox('NPSHR Check — Atmospheric Pressure Unit',list(pressure_factors),index=None,key='p3o_atm_unit')
        st.caption('Gauge pressure requires explicit local atmospheric absolute pressure. No standard atmosphere is assumed.')
    vapor=st.number_input('NPSHR Check — Vapor Pressure (absolute)',value=None,format='%.12g',key='p3o_vapor')
    vapor_unit=st.selectbox('NPSHR Check — Vapor Pressure Unit',list(pressure_factors),index=None,key='p3o_vapor_unit')
    datum=st.text_input('NPSHR Check — Describe Common Elevation Datum',key='p3o_datum')
    args={}
    for key,label in [('density','Liquid Density (kg/m³)'),('velocity','Source Surface Velocity (m/s)' if source else 'Suction Velocity (m/s)'),
                      ('elevation','Source Surface Elevation (m)' if source else 'Suction Measurement Elevation (m)'),('datum_elevation','Pump/NPSH Datum Elevation (m)')]:
        args[key]=st.number_input('NPSHR Check — '+label,value=None,format='%.12g',key='p3o_'+key)
    if source:args['suction_loss']=st.number_input('NPSHR Check — Total Suction Loss (m)',value=None,format='%.12g',key='p3o_suction_loss')
    st.caption('Phase 2H: steady-state single-phase incompressible liquid, kinetic-energy correction α=1. Signed calculated NPSHA and kernel warnings are retained.')
    return basis,unit,pressure,atmosphere,atm_unit,vapor,vapor_unit,datum,args


def render_npshr_curve(flow_factors,pressure_factors):
    import streamlit as st
    st.subheader('3O — NPSHR Curve / Operating NPSHR')
    st.info(GUIDANCE)
    st.caption('ConversionPro does not generate or estimate an NPSHR curve.')
    method=st.selectbox('NPSHR Calculation Method',METHODS_3O,key='p3o_method')
    st.markdown('**Vendor NPSHR Curve**')
    unit=st.selectbox('NPSHR-Curve Flow Unit',list(flow_factors),index=None,key='p3o_curve_unit')
    r_unit=st.selectbox('Vendor NPSHR Curve Unit',list(HEAD_FACTORS),index=None,key='p3o_r_unit')
    output_unit=st.selectbox('NPSHR / Margin Results Unit',list(HEAD_FACTORS),index=None,key='p3o_output_unit')
    count=st.number_input('Number of Vendor NPSHR Points',min_value=3,max_value=20,value=3,step=1,key='p3o_count')
    rows=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'NPSHR Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3o_q_{i}')
        with right:r=st.number_input(f'NPSHR Point {i+1} — NPSHR ({r_unit or "select unit above"})',value=None,format='%.12g',key=f'p3o_r_{i}')
        rows.append((q,r))
    st.caption('Enter 3–20 unique-flow supplied points. Flows are sorted; valid non-monotonic NPSHR data are accepted. Unit changes reinterpret entered numbers rather than rewriting them.')
    st.markdown('**Operating Flow**')
    op_unit=st.selectbox('NPSHR Operating Flow Unit',list(flow_factors),index=None,key='p3o_op_unit')
    integrated=method==METHODS_3O[1]
    if not integrated:
        operating=st.number_input(f'NPSHR Operating Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3o_operating')
    else:
        st.caption('Independent single-pump Q–H/system inputs reuse Phase 3G. No Phase 3L combined curve is used.')
        head_unit=st.selectbox('NPSHR Operating-Point Head Unit',list(HEAD_FACTORS),index=None,key='p3o_head_unit')
        n=st.number_input('NPSHR Integration — Number of Pump Q–H Points',min_value=3,max_value=20,value=3,step=1,key='p3o_qh_count')
        qh=[]
        for i in range(n):
            left,right=st.columns(2)
            with left:q=st.number_input(f'NPSHR Pump Point {i+1} — Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key=f'p3o_pq_{i}')
            with right:h=st.number_input(f'NPSHR Pump Point {i+1} — Head ({head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3o_ph_{i}')
            qh.append((q,h))
        sys_method=st.selectbox('NPSHR Integration — System Method',METHODS,key='p3o_sys_method')
        static=st.number_input(f'NPSHR System Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3o_static')
        if sys_method==METHODS[0]:
            reference=st.number_input(f'NPSHR System Reference Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3o_reference')
            friction=st.number_input(f'NPSHR System Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3o_friction')
        else:k=st.number_input('NPSHR System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3o_k')
        st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional NPSHA / Margin Check**')
    available_method=st.selectbox('NPSHA Comparison Method',AVAILABLE_METHODS,key='p3o_available_method')
    if available_method!=AVAILABLE_METHODS[0]:
        if available_method==AVAILABLE_METHODS[1]:
            available=st.number_input('NPSHR Check — Manual NPSHA',value=None,format='%.12g',key='p3o_available')
            a_unit=st.selectbox('NPSHR Check — Manual NPSHA Unit',list(HEAD_FACTORS),index=None,key='p3o_a_unit')
        else:phase2_inputs=_available_inputs(st,available_method==AVAILABLE_METHODS[3],pressure_factors)
        criterion=st.number_input('User/Vendor/Project Required NPSH Margin',value=None,format='%.12g',key='p3o_criterion')
        criterion_unit=st.selectbox('NPSHR Check — Required Margin Unit',list(HEAD_FACTORS),index=None,key='p3o_criterion_unit')
        st.caption('Required NPSH margin is pump-, service-, and project-specific. Enter the applicable vendor/project criterion if available. No margin or ratio is assumed. Entered required margin must be nonnegative.')
    if st.button('Calculate Operating NPSHR',key='p3o_calculate'):
        try:
            curve=create_npshr_curve(rows,unit,r_unit,flow_factors)
            if output_unit not in HEAD_FACTORS:raise ValueError('Select a supported NPSHR / margin results unit: m or ft.')
            curve_flow_to_si(0,op_unit,flow_factors)
            if integrated:
                pump=create_pump_curve(qh,op_unit,head_unit,flow_factors)
                model=(model_from_reference(static_head=static,head_unit=head_unit,reference_flow=reference,
                       reference_friction_head=friction,flow_unit=op_unit,flow_factors=flow_factors)
                       if sys_method==METHODS[0] else model_from_k(static,head_unit,k))
                roots=find_operating_points(pump,model)
                if roots.coincident_intervals:raise ValueError('Pump and system curves coincide over an interval; no unique operating flow is selected.')
                if not roots.points:raise ValueError(NO_INTERSECTION)
                if len(roots.points)!=1:raise ValueError(MULTIPLE_INTERSECTIONS+' No operating flow is selected; use manual mode for an explicitly chosen flow.')
                operating_si=roots.points[0].flow_m3_s;head=roots.points[0].head_m
                if pump.has_rising_head:st.warning(RISING_HEAD_WARNING)
            else:operating_si=curve_flow_to_si(operating,op_unit,flow_factors)
            result=interpolate_npshr(curve,operating_si)
            extrema=find_npshr_extrema(curve)
            margin=comparison=phase2h=None
            if available_method!=AVAILABLE_METHODS[0]:
                if available_method==AVAILABLE_METHODS[1]:
                    a_m=head_to_metres(available,a_unit,'Manual NPSHA')
                    margin=calculate_npsh_margin(a_m,result.npshr_m)
                else:
                    basis,p_unit,pressure,atmosphere,atm_unit,vapor,vapor_unit,datum,args=phase2_inputs
                    if not datum.strip():raise ValueError('Describe the common elevation datum and use it for both elevations.')
                    p_pa=pressure_to_pa(pressure,p_unit,pressure_factors)
                    atm_pa=pressure_to_pa(atmosphere,atm_unit,pressure_factors) if basis=='Gauge' else None
                    vapor_pa=pressure_to_pa(vapor,vapor_unit,pressure_factors)
                    phase2h=(source_npsha if available_method==AVAILABLE_METHODS[3] else flange_npsha)(
                        pressure_pa=p_pa,basis=basis,atmospheric_pa=atm_pa,vapor_pressure_pa=vapor_pa,**args)
                    margin=margin_from_phase2h(phase2h,result.npshr_m)
                if criterion is not None:
                    required=head_to_metres(criterion,criterion_unit,'User/Vendor/Project Required NPSH Margin')
                    comparison=compare_required_margin(margin.margin_m,required)
            f=HEAD_FACTORS[output_unit]
            plot=npshr_plot_spec(curve,flow_factors[unit],unit,output_unit,result)
            text=(f'Operating Flow: {_shown(operating_si,flow_factors[op_unit]):.12g} {op_unit}\n'
                  f'Interpolated Vendor NPSHR: {_shown(result.npshr_m,f):.12g} {output_unit}\n'
                  f'Supplied NPSHR Flow Range: {_shown(curve.points[0].flow_m3_s,flow_factors[unit]):.12g} to {_shown(curve.points[-1].flow_m3_s,flow_factors[unit]):.12g} {unit}\n'
                  f'Minimum Supplied NPSHR: {_shown(extrema.minimum_m,f):.12g} {output_unit}\n'
                  'Flow(s) at Minimum Supplied NPSHR: '+', '.join(f'{_shown(q,flow_factors[unit]):.12g}' for q in extrema.minimum_flows_m3_s)+' '+unit+'\n'
                  f'Maximum Supplied NPSHR: {_shown(extrema.maximum_m,f):.12g} {output_unit}\n'
                  'Flow(s) at Maximum Supplied NPSHR: '+', '.join(f'{_shown(q,flow_factors[unit]):.12g}' for q in extrema.maximum_flows_m3_s)+' '+unit)
            if margin is not None:
                text+=(f'\nNPSHA: {_shown(margin.npsha_m,f):.12g} {output_unit}\nNPSH Margin: {_shown(margin.margin_m,f):.12g} {output_unit}\n'
                       f'NPSHA / NPSHR Ratio: {margin.ratio:.12g}\nPercent Margin: {margin.percent_margin:.12g}%\nRelationship Status: {margin.relationship_status}')
            if comparison is not None:
                text+=(f'\nRequired Margin: {_shown(comparison.required_margin_m,f):.12g} {output_unit}\n'
                       f'Excess Above Required Margin: {_shown(comparison.excess_margin_m,f):.12g} {output_unit}\nCriterion Status: {comparison.criterion_status}')
            st.markdown('**Interpolated NPSHR Result**');st.text(text)
            if integrated:st.text(f'Phase 3G Operating Head: {head:.12g} m')
            if phase2h is not None:
                st.caption('NPSHA calculated by the existing Phase 2H kernel: '+phase2h.mode)
                for warning in phase2h.warnings:st.warning(warning)
            st.vega_lite_chart(spec=plot,width='stretch')
            st.caption('Blue: supplied vendor points and straight segments. Green dashed line: operating flow. Orange circle: interpolated vendor NPSHR. Supplied extrema are descriptive data, not operating limits.')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('NPSHR normally varies with pump flow. '+GUIDANCE+' Use the same vendor test basis represented by the supplied curve.')
    st.caption('ConversionPro uses linear interpolation only between supplied NPSHR points. NPSHR is not extrapolated outside the supplied vendor data range.')
    st.caption('Positive NPSH margin alone does not establish all cavitation or reliability criteria. Final NPSH assessment should follow manufacturer/vendor and project requirements.')
    st.caption('Pump speed changes may alter NPSHR; do not assume Phase 3I affinity-law scaling applies to NPSHR. Verify changed speed or impeller diameter against applicable vendor data.')
