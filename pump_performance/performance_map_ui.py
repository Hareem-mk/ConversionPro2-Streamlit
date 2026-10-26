"""Explicit four-curve inputs, partial results and independent vendor criteria."""
import math
from .performance_map import evaluate_performance_map
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS,RISING_HEAD_WARNING
from .efficiency_curve import create_efficiency_curve
from .power_curve import create_power_curve,calculate_driver_margin,compare_driver_margin
from .npshr_curve import create_npshr_curve
from .shaft_power import POWER_FACTORS
from .pump_efficiency import power_to_watts
from .system_curve import model_from_reference,model_from_k,head_to_metres
from .system_curve_ui import METHODS,MODEL_GUIDANCE
from .operating_point import find_operating_points,NO_INTERSECTION,MULTIPLE_INTERSECTIONS
from .bep_operating_range import compare_bep,classify_user_range
from .npsh_margin import calculate_npsh_margin,compare_required_margin

METHODS_3P=('Manual Operating Flow','From Phase 3G Operating Point')
GUIDANCE='Use manufacturer/vendor performance data applicable to the same pump speed and impeller diameter.'
CONSISTENCY='Head, efficiency, power and NPSHR curves should correspond to the same pump configuration, speed and impeller diameter.'
REVIEW='Review each vendor/project criterion individually. ConversionPro does not replace manufacturer pump selection review.'


def _shown(value,factor):
    result=value/factor
    if not math.isfinite(result) or (value != 0 and result == 0):
        raise ValueError('Displayed performance-map value exceeds the supported numeric range.')
    return result


def _curve_inputs(st,label,key,flow_factors,value_units=None):
    st.markdown('**'+label+' Curve**')
    unit=st.selectbox(label+' Curve Flow Unit',list(flow_factors),index=None,key='p3p_'+key+'_flow_unit')
    value_unit=('%' if value_units is None else st.selectbox(label+' Curve Value Unit',list(value_units),index=None,key='p3p_'+key+'_value_unit'))
    count=st.number_input(label+' Curve — Number of Points',min_value=3,max_value=20,value=3,step=1,key='p3p_'+key+'_count')
    rows=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'{label} Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3p_{key}_q_{i}')
        with right:v=st.number_input(f'{label} Point {i+1} — Value ({value_unit or "select unit above"})',value=None,format='%.12g',key=f'p3p_{key}_v_{i}')
        rows.append((q,v))
    return rows,unit,value_unit


def performance_plot_specs(result,head_curve,efficiency_curve,power_curve,npshr_curve,
                           flow_factor,flow_unit,head_unit,power_unit,model=None):
    specs=[]
    for label,curve,field,factor,unit,selected,attribute in (
        ('Pump Head',head_curve,'head_m',HEAD_FACTORS[head_unit],head_unit,result.head_result,'head_m'),
        ('Pump Efficiency',efficiency_curve,'efficiency_percent',1.0,'%',result.efficiency_result,'efficiency_percent'),
        ('Pump Shaft/Brake Power',power_curve,'shaft_power_w',POWER_FACTORS[power_unit],power_unit,result.power_result,'shaft_power_w'),
        ('Pump NPSHR',npshr_curve,'npshr_m',HEAD_FACTORS[head_unit],head_unit,result.npshr_result,'npshr_m')):
        y={'field':'value','type':'quantitative','title':f'{label} ({unit})'}
        layers=[{'data':{'values':[{'flow':_shown(p.flow_m3_s,flow_factor),'value':_shown(getattr(p,field),factor)} for p in curve.points]},
                 'mark':{'type':'line','point':True,'color':'#4e9de0'},'encoding':{'y':y}}]
        if model is not None and label=='Pump Head':
            lo,hi=curve.points[0].flow_m3_s,curve.points[-1].flow_m3_s
            rows=[]
            for i in range(81):
                q=lo+(hi-lo)*(i/80)
                rows.append({'flow':_shown(q,flow_factor),'value':_shown(model.at_flow(q).total_head_m,factor)})
            layers.append({'data':{'values':rows},'mark':{'type':'line','strokeDash':[6,4],'color':'#76bb85'},'encoding':{'y':y}})
        if selected is not None:
            q=_shown(selected.flow_m3_s,flow_factor)
            layers.append({'data':{'values':[{'flow':q}]},'mark':{'type':'rule','strokeDash':[4,4],'color':'#ed9238'}})
            layers.append({'data':{'values':[{'flow':q,'value':_shown(getattr(selected,attribute),factor)}]},
                           'mark':{'type':'point','filled':True,'size':120,'color':'#ed9238'},'encoding':{'y':y}})
        specs.append({'title':label+' — Vendor Curve','layer':layers,'encoding':{
            'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
            'tooltip':[{'field':'flow','type':'quantitative'},{'field':'value','type':'quantitative'}]},
            'height':280,'config':{'view':{'stroke':None}}})
    return specs


def render_performance_map(flow_factors):
    import streamlit as st
    st.subheader('3P — Pump Performance Map / Integrated Vendor Curve Check')
    st.info(GUIDANCE)
    st.caption(CONSISTENCY+' ConversionPro cannot verify that independently entered data are mutually consistent.')
    method=st.selectbox('Performance Map Calculation Method',METHODS_3P,key='p3p_method')
    st.caption('Supply every curve independently. No sample vendor data, BEP or operating limits are preloaded. Changing units reinterprets entered numbers rather than rewriting them.')
    hp,hfu,hhu=_curve_inputs(st,'Pump Head','head',flow_factors,HEAD_FACTORS)
    ep,efu,_=_curve_inputs(st,'Pump Efficiency','eff',flow_factors)
    pp,pfu,ppu=_curve_inputs(st,'Pump Shaft/Brake Power','power',flow_factors,POWER_FACTORS)
    rp,rfu,rhu=_curve_inputs(st,'Pump NPSHR','npshr',flow_factors,HEAD_FACTORS)
    st.markdown('**Operating Point / Results Units**')
    op_unit=st.selectbox('Performance Map Operating Flow Unit',list(flow_factors),index=None,key='p3p_op_unit')
    head_unit=st.selectbox('Performance Map Head / NPSH Results Unit',list(HEAD_FACTORS),index=None,key='p3p_result_head_unit')
    power_unit=st.selectbox('Performance Map Power Results Unit',list(POWER_FACTORS),index=None,key='p3p_result_power_unit')
    integrated=method==METHODS_3P[1]
    if not integrated:
        operating=st.number_input(f'Performance Map Operating Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3p_operating')
    else:
        st.caption('Phase 3G uses this panel’s supplied single-pump head curve and system definition. No Phase 3L combined curve is used.')
        sys_method=st.selectbox('Performance Map System Method',METHODS,key='p3p_sys_method')
        static=st.number_input(f'Map System Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3p_static')
        if sys_method==METHODS[0]:
            reference=st.number_input(f'Map System Reference Flow ({op_unit or "select unit above"})',value=None,format='%.12g',key='p3p_reference')
            friction=st.number_input(f'Map System Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3p_friction')
        else:k=st.number_input('Map System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3p_k')
        st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional Vendor/Project Criteria**')
    bep=st.number_input('Map Vendor BEP Flow',value=None,format='%.12g',key='p3p_bep')
    bep_unit=st.selectbox('Map Vendor BEP Flow Unit',list(flow_factors),index=None,key='p3p_bep_unit')
    minimum=st.number_input('User/Vendor/Project Minimum % of BEP',value=None,format='%.12g',key='p3p_bep_min')
    maximum=st.number_input('User/Vendor/Project Maximum % of BEP',value=None,format='%.12g',key='p3p_bep_max')
    available=st.number_input('Map Manual NPSHA',value=None,format='%.12g',key='p3p_npsha')
    available_unit=st.selectbox('Map Manual NPSHA Unit',list(HEAD_FACTORS),index=None,key='p3p_npsha_unit')
    required=st.number_input('Map User/Vendor/Project Required NPSH Margin',value=None,format='%.12g',key='p3p_required_npsh')
    required_unit=st.selectbox('Map Required NPSH Margin Unit',list(HEAD_FACTORS),index=None,key='p3p_required_npsh_unit')
    driver=st.number_input('Map Driver/Motor Rated Power',value=None,format='%.12g',key='p3p_driver')
    driver_unit=st.selectbox('Map Driver/Motor Rated Power Unit',list(POWER_FACTORS),index=None,key='p3p_driver_unit')
    driver_required=st.number_input('Map User/Vendor/Project Required Driver Power Margin %',value=None,format='%.12g',key='p3p_required_driver')
    st.caption('All optional values start blank. No acceptance criteria or vendor BEP are inferred from efficiency data. BEP limits must be supplied as a pair. Criteria are reviewed individually.')
    if st.button('Evaluate Pump Performance Map',key='p3p_calculate'):
        try:
            head=create_pump_curve(hp,hfu,hhu,flow_factors)
            efficiency=create_efficiency_curve(ep,efu,flow_factors)
            power=create_power_curve(pp,pfu,ppu,flow_factors)
            npshr=create_npshr_curve(rp,rfu,rhu,flow_factors)
            curve_flow_to_si(0,op_unit,flow_factors)
            if head_unit not in HEAD_FACTORS:raise ValueError('Select a supported head / NPSH results unit: m or ft.')
            if power_unit not in POWER_FACTORS:raise ValueError('Select a supported power results unit: W, kW or Mechanical hp.')
            model=roots=None
            if integrated:
                model=(model_from_reference(static_head=static,head_unit=head_unit,reference_flow=reference,
                    reference_friction_head=friction,flow_unit=op_unit,flow_factors=flow_factors)
                    if sys_method==METHODS[0] else model_from_k(static,head_unit,k))
                roots=find_operating_points(head,model)
                if roots.coincident_intervals:raise ValueError('Pump and system curves coincide over an interval; no unique operating flow is selected.')
                if not roots.points:raise ValueError(NO_INTERSECTION)
                if len(roots.points)!=1:raise ValueError(MULTIPLE_INTERSECTIONS+' No operating flow is selected. Use manual mode for an explicitly chosen flow.')
                q=roots.points[0].flow_m3_s
            else:q=curve_flow_to_si(operating,op_unit,flow_factors)
            result=evaluate_performance_map(q,head,efficiency,power,npshr)
            plots=performance_plot_specs(result,head,efficiency,power,npshr,flow_factors[op_unit],op_unit,head_unit,power_unit,model)
            common=result.common_flow_range
            text=f'Operating Flow ({"calculated by Phase 3G" if integrated else "user-entered"}): {_shown(q,flow_factors[op_unit]):.12g} {op_unit}\n'
            text+=('Common Valid Vendor Data Flow Range: None — supplied curve ranges do not overlap.' if common is None else
                   f'Common Valid Vendor Data Flow Range: {_shown(common.minimum_m3_s,flow_factors[op_unit]):.12g} to {_shown(common.maximum_m3_s,flow_factors[op_unit]):.12g} {op_unit}')
            for label,value,field,factor,unit in (
                ('Pump Head',result.head_result,'head_m',HEAD_FACTORS[head_unit],head_unit),
                ('Pump Efficiency',result.efficiency_result,'efficiency_percent',1.0,'%'),
                ('Pump Shaft/Brake Power',result.power_result,'shaft_power_w',POWER_FACTORS[power_unit],power_unit),
                ('Pump NPSHR',result.npshr_result,'npshr_m',HEAD_FACTORS[head_unit],head_unit)):
                text+='\n'+label+(': Unavailable' if value is None else f' (vendor interpolated): {_shown(getattr(value,field),factor):.12g} {unit}')
            st.markdown('**Integrated Performance Summary**');st.text(text)
            if integrated:st.text(f'Pump/System Operating Head (calculated): {_shown(roots.points[0].head_m,HEAD_FACTORS[head_unit]):.12g} {head_unit}')
            for name,status in result.range_statuses:
                if status.startswith('Unavailable'):st.warning(name+': '+status)
            if head.has_rising_head:st.warning(RISING_HEAD_WARNING)
            # Optional errors/coverage gaps are local to their own comparison;
            # they never suppress valid vendor interpolation from other curves.
            try:
                comparison=None if bep is None else compare_bep(q,curve_flow_to_si(bep,bep_unit,flow_factors))
                if comparison is not None:st.text(f'Vendor BEP Flow (user-entered): {bep:.12g} {bep_unit}\nPercent of BEP (calculated): {comparison.percent_bep:.12g}%')
                if minimum is not None or maximum is not None:
                    if comparison is None:raise ValueError('Enter Vendor BEP Flow to apply the entered BEP range.')
                    st.text('BEP Criterion Status: '+classify_user_range(comparison.percent_bep,minimum,maximum))
            except (ValueError,OverflowError) as exc:st.error('BEP comparison: '+str(exc))
            try:
                if available is None and required is not None:raise ValueError('Enter NPSHA to apply the required NPSH margin.')
                if available is not None:
                    a_m=head_to_metres(available,available_unit,'Manual NPSHA')
                    if result.npshr_result is None:st.info('NPSH margin unavailable: operating flow is outside the supplied NPSHR curve range.')
                    else:
                        margin=calculate_npsh_margin(a_m,result.npshr_result.npshr_m)
                        st.text(f'NPSHA (user-entered): {_shown(a_m,HEAD_FACTORS[head_unit]):.12g} {head_unit}\nNPSH Margin (calculated): {_shown(margin.margin_m,HEAD_FACTORS[head_unit]):.12g} {head_unit}\nNPSHA / NPSHR Ratio: {margin.ratio:.12g}\nPercent NPSH Margin: {margin.percent_margin:.12g}%\n{margin.relationship_status}')
                        if required is not None:
                            criterion=compare_required_margin(margin.margin_m,head_to_metres(required,required_unit,'Required NPSH Margin'))
                            st.text(f'Required NPSH Margin (user-entered): {_shown(criterion.required_margin_m,HEAD_FACTORS[head_unit]):.12g} {head_unit}\nExcess Above Required NPSH Margin: {_shown(criterion.excess_margin_m,HEAD_FACTORS[head_unit]):.12g} {head_unit}\nNPSH Criterion Status: {criterion.criterion_status}')
            except (ValueError,OverflowError) as exc:st.error('NPSH comparison: '+str(exc))
            try:
                if driver is None and driver_required is not None:raise ValueError('Enter Driver/Motor Rated Power to apply the driver margin criterion.')
                if driver is not None:
                    rating=power_to_watts(driver,driver_unit,'Driver/Motor Rated Power',allow_zero=False)
                    if result.power_result is None:st.info('Driver margin unavailable: operating flow is outside the supplied shaft/brake power curve range.')
                    else:
                        margin=calculate_driver_margin(result.power_result.shaft_power_w,rating)
                        percent='N/A — shaft power is zero' if margin.margin_percent is None else f'{margin.margin_percent:.12g}%'
                        st.text(f'Driver Rating (user-entered): {_shown(rating,POWER_FACTORS[power_unit]):.12g} {power_unit}\nDriver Power Margin (calculated): {_shown(margin.margin_w,POWER_FACTORS[power_unit]):.12g} {power_unit}\nDriver Power Margin %: {percent}\n{margin.relationship_status}')
                        if driver_required is not None:st.text(f'Required Driver Margin % (user-entered): {driver_required:.12g}%\nDriver Criterion Status: '+compare_driver_margin(margin.margin_percent,driver_required))
            except (ValueError,OverflowError) as exc:st.error('Driver comparison: '+str(exc))
            st.markdown('**Performance Plots**')
            for spec in plots:st.vega_lite_chart(spec=spec,width='stretch')
            st.caption('Separate y-axes are used in separate plots. Blue: supplied vendor points and straight segments; orange markers: in-range operating results only. Green dashed curve: system model when enabled.')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption(CONSISTENCY+' Performance must be reviewed using consistent vendor data; independently supplied data are not verified as mutually consistent.')
    st.caption('Head, efficiency, power and NPSHR all vary with operating flow. The actual operating point is determined by the pump/system intersection. Interpolation is only between supplied vendor points; no vendor performance curve is extrapolated.')
    st.caption('BEP must come from applicable vendor data and is not automatically inferred from peak supplied efficiency. NPSHR must correspond to the same pump configuration and operating condition. Positive NPSH margin alone does not establish all vendor/project criteria.')
    st.caption('Driver rating should be checked across the relevant operating range, not only one point. Confirm final selection using complete manufacturer/vendor documentation and project criteria.')
    st.info(REVIEW)
