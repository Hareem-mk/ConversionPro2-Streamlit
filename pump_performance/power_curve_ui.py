"""Phase 3N explicit vendor inputs, shared solver and optional power comparison."""
import math
from .power_curve import (create_power_curve,interpolate_power,find_maximum_supplied_power,
                          calculate_driver_margin,compare_driver_margin,compare_calculated_power)
from .pump_curve import curve_flow_to_si,create_pump_curve,HEAD_FACTORS,RISING_HEAD_WARNING
from .shaft_power import POWER_FACTORS
from .pump_efficiency import power_to_watts
from .efficiency_curve import create_efficiency_curve
from .system_curve import model_from_reference,model_from_k
from .system_curve_ui import METHODS,MODEL_GUIDANCE
from .operating_point import find_operating_points,NO_INTERSECTION,MULTIPLE_INTERSECTIONS
from piping_hydraulics.pipe_capacity import nonnegative

METHODS_3N=('Manual Operating Flow','From Phase 3G Operating Point')
COMPARISONS=('No Calculated Power Comparison','From Entered Pump Efficiency','From Phase 3M Vendor Efficiency Curve')
GUIDANCE='Use shaft/brake-power data from the applicable manufacturer/vendor pump performance curve for the selected pump speed and impeller diameter.'


def _shown(value,factor):
    converted=value/factor
    if not math.isfinite(converted) or (value != 0 and converted == 0):
        raise ValueError('Displayed value exceeds the supported numeric range.')
    return converted


def power_plot_spec(curve,flow_factor,flow_unit,power_unit,operating):
    factor=POWER_FACTORS[power_unit]
    maximum=find_maximum_supplied_power(curve)
    layers=[
        {'data':{'values':[{'flow':_shown(p.flow_m3_s,flow_factor),'power':_shown(p.shaft_power_w,factor)} for p in curve.points]},
         'mark':{'type':'line','point':True,'color':'#4e9de0'}},
        {'data':{'values':[{'flow':_shown(q,flow_factor),'power':_shown(maximum.shaft_power_w,factor)} for q in maximum.flows_m3_s]},
         'mark':{'type':'point','shape':'diamond','filled':True,'size':180,'color':'#ed9238'}},
        {'data':{'values':[{'flow':_shown(operating.flow_m3_s,flow_factor)}]},
         'mark':{'type':'rule','strokeDash':[4,4],'color':'#76bb85'}},
        {'data':{'values':[{'flow':_shown(operating.flow_m3_s,flow_factor),'power':_shown(operating.shaft_power_w,factor)}]},
         'mark':{'type':'point','filled':True,'size':150,'color':'#76bb85'}}]
    for index in (0,1,3):
        layers[index]['encoding']={'y':{'field':'power','type':'quantitative','title':f'Pump Shaft/Brake Power ({power_unit})'}}
    return {'title':'Vendor Pump Shaft/Brake Power Curve','layer':layers,'encoding':{
        'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
        'tooltip':[{'field':'flow','type':'quantitative'},{'field':'power','type':'quantitative'}]},
        'height':360,'config':{'view':{'stroke':None}}}


def render_power_curve(flow_factors,density_factors):
    import streamlit as st
    st.subheader('3N — Pump Power Curve / Driver Loading Check')
    st.info(GUIDANCE)
    method=st.selectbox('Power-Curve Calculation Method',METHODS_3N,key='p3n_method')
    st.markdown('**Vendor Pump Power Curve**')
    unit=st.selectbox('Power-Curve Flow Unit',list(flow_factors),index=None,key='p3n_curve_unit')
    power_unit=st.selectbox('Vendor Shaft/Brake Power Unit',list(POWER_FACTORS),index=None,key='p3n_power_unit')
    output_unit=st.selectbox('Power Results Unit',list(POWER_FACTORS),index=None,key='p3n_output_unit')
    count=st.number_input('Number of Vendor Power Points',min_value=3,max_value=20,value=3,step=1,key='p3n_count')
    rows=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'Power Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3n_q_{i}')
        with right:p=st.number_input(f'Power Point {i+1} — Shaft/Brake Power ({power_unit or "select unit above"})',value=None,format='%.12g',key=f'p3n_p_{i}')
        rows.append((q,p))
    st.caption('Enter 3–20 supplied points. Flows are sorted; duplicate flows are rejected. Non-monotonic power data are allowed. Changing units reinterprets entered numbers rather than rewriting them.')
    st.markdown('**Operating Flow**')
    op_unit=st.selectbox('Power Operating Flow Unit',list(flow_factors),index=None,key='p3n_op_unit')
    integrated=method==METHODS_3N[1]
    if not integrated:
        operating=st.number_input(f'Power Operating Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3n_operating')
    else:
        st.caption('Independent single-pump Q–H/system inputs reuse Phase 3G. No Phase 3L combined curve is used.')
        head_unit=st.selectbox('Power Operating-Point Head Unit',list(HEAD_FACTORS),index=None,key='p3n_head_unit')
        n=st.number_input('Power Integration — Number of Pump Q–H Points',min_value=3,max_value=20,value=3,step=1,key='p3n_qh_count')
        qh=[]
        for i in range(n):
            left,right=st.columns(2)
            with left:q=st.number_input(f'Power Pump Point {i+1} — Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key=f'p3n_pq_{i}')
            with right:h=st.number_input(f'Power Pump Point {i+1} — Head ({head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3n_ph_{i}')
            qh.append((q,h))
        sys_method=st.selectbox('Power Integration — System Method',METHODS,key='p3n_sys_method')
        static=st.number_input(f'Power System Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3n_static')
        if sys_method==METHODS[0]:
            reference=st.number_input(f'Power System Reference Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3n_reference')
            friction=st.number_input(f'Power System Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3n_friction')
        else:k=st.number_input('Power System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3n_k')
        st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional Driver Rating**')
    driver=st.number_input('Driver/Motor Rated Power',value=None,format='%.12g',key='p3n_driver')
    driver_unit=st.selectbox('Driver/Motor Rated Power Unit',list(POWER_FACTORS),index=None,key='p3n_driver_unit')
    required=st.number_input('User/Vendor/Project Required Driver Power Margin %',value=None,format='%.12g',key='p3n_required')
    st.caption('No default driver margin is assumed. Enter the applicable vendor/project criterion if available. Driver rating must be positive; required margin must be nonnegative.')
    st.markdown('**Optional Power Comparison**')
    comparison=st.selectbox('Calculated Shaft Power Comparison',COMPARISONS,key='p3n_comparison')
    if comparison!=COMPARISONS[0]:
        density=st.number_input('Power Comparison — Fluid Density',value=None,format='%.12g',key='p3n_density')
        density_unit=st.selectbox('Power Comparison — Density Unit',list(density_factors),index=None,key='p3n_density_unit')
        if not integrated:
            entered_head=st.number_input('Power Comparison — Pump Head',value=None,format='%.12g',key='p3n_comparison_head')
            comparison_head_unit=st.selectbox('Power Comparison — Head Unit',list(HEAD_FACTORS),index=None,key='p3n_comparison_head_unit')
        else:st.caption('Calculated power uses the Phase 3G operating head.')
        if comparison==COMPARISONS[1]:
            efficiency=st.number_input('Power Comparison — Pump Efficiency (%)',value=None,format='%.12g',key='p3n_efficiency')
        else:
            st.caption('Vendor efficiency points use the Power-Curve Flow Unit. Phase 3M interpolates efficiency at the same operating flow.')
            en=st.number_input('Power Comparison — Number of Efficiency Points',min_value=3,max_value=20,value=3,step=1,key='p3n_eff_count')
            efficiency_rows=[]
            for i in range(en):
                left,right=st.columns(2)
                with left:q=st.number_input(f'Power Comparison Efficiency Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3n_eq_{i}')
                with right:e=st.number_input(f'Power Comparison Efficiency Point {i+1} — Efficiency (%)',value=None,format='%.12g',key=f'p3n_ee_{i}')
                efficiency_rows.append((q,e))
    if st.button('Calculate Vendor Power / Driver Loading',key='p3n_calculate'):
        try:
            curve=create_power_curve(rows,unit,power_unit,flow_factors)
            if output_unit not in POWER_FACTORS:raise ValueError('Select a supported power results unit: W, kW or Mechanical hp.')
            curve_flow_to_si(0,op_unit,flow_factors)
            head=None
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
            result=interpolate_power(curve,operating_si)
            maximum=find_maximum_supplied_power(curve)
            margin=None if driver is None else calculate_driver_margin(result.shaft_power_w,power_to_watts(driver,driver_unit,'Driver/Motor Rated Power',allow_zero=False))
            criterion=None
            if required is not None:
                if margin is None:raise ValueError('Enter Driver/Motor Rated Power to apply the driver margin criterion.')
                criterion=compare_driver_margin(margin.margin_percent,required)
            calculated=None
            if comparison!=COMPARISONS[0]:
                if not integrated:
                    if comparison_head_unit not in HEAD_FACTORS:raise ValueError('Select a supported comparison head unit: m or ft.')
                    head=nonnegative(entered_head,'Pump head')*HEAD_FACTORS[comparison_head_unit]
                kwargs=({'efficiency_percent':efficiency} if comparison==COMPARISONS[1] else
                        {'efficiency_curve':create_efficiency_curve(efficiency_rows,unit,flow_factors)})
                calculated=compare_calculated_power(vendor_power_w=result.shaft_power_w,flow_si=operating_si,density=density,
                    density_unit=density_unit,head_m=head,density_factors=density_factors,flow_factors=flow_factors,**kwargs)
            f=POWER_FACTORS[output_unit]
            # Build all display data before emitting results, including overflow checks.
            plot=power_plot_spec(curve,flow_factors[unit],unit,output_unit,result)
            text=(f'Operating Flow: {_shown(operating_si,flow_factors[op_unit]):.12g} {op_unit}\n'
                  f'Vendor Interpolated Shaft Power: {_shown(result.shaft_power_w,f):.12g} {output_unit}\n'
                  f'Maximum Supplied Vendor Power Point\nMaximum Supplied Vendor Power: {_shown(maximum.shaft_power_w,f):.12g} {output_unit}\n'
                  'Flow(s) at Maximum Supplied Vendor Power: '+', '.join(f'{_shown(q,flow_factors[unit]):.12g}' for q in maximum.flows_m3_s)+' '+unit)
            if margin is not None:
                percent='N/A — shaft power is zero' if margin.margin_percent is None else f'{margin.margin_percent:.12g}%'
                text+=(f'\nDriver/Motor Rated Power: {_shown(margin.driver_rating_w,f):.12g} {output_unit}\n'
                       f'Driver Power Margin: {_shown(margin.margin_w,f):.12g} {output_unit}\nDriver Power Margin %: {percent}\n{margin.relationship_status}')
            if criterion is not None:text+=f'\nRequired Driver Margin %: {required:.12g}%\nCriterion Status: {criterion}'
            if calculated is not None:
                percent='N/A — vendor power is zero' if calculated.percent_difference is None else f'{calculated.percent_difference:.12g}%'
                text+=(f'\nCalculated Shaft Power: {_shown(calculated.calculated_power_w,f):.12g} {output_unit}\n'
                       f'Power Difference: {_shown(calculated.difference_w,f):.12g} {output_unit}\nPower Difference %: {percent}\n'
                       f'Comparison Pump Efficiency: {calculated.efficiency_percent:.12g}%')
            st.markdown('**Vendor Power Result**');st.text(text)
            if integrated:st.text(f'Phase 3G Operating Head: {head:.12g} m')
            st.vega_lite_chart(spec=plot,width='stretch')
            st.caption('Blue: supplied vendor points and straight segments. Green line: operating flow; green circle: interpolated power. Orange diamond(s): maximum supplied vendor power point(s).')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('Pump shaft/brake power normally varies with operating flow. '+GUIDANCE)
    st.caption('ConversionPro uses linear interpolation only between supplied vendor points. Power is not extrapolated beyond supplied data.')
    st.caption('Driver/motor sizing criteria are project-, service-, and vendor-specific. Check driver rating against pump power over the relevant operating range, not only one isolated operating point. No default motor-sizing margin or automatic motor selection is applied.')
    st.caption('Motor efficiency and electrical input power are separate from pump shaft power; Phase 3C addresses motor input power.')
    st.caption('Final driver selection should be verified against manufacturer/vendor pump and motor data and project specifications. Numerical relationship and criterion statuses do not establish driver approval.')
