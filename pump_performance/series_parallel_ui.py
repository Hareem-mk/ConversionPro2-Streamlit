"""Two-pump curve combination with optional shared 3F/3G system intersection."""
import math
from .pump_curve import create_pump_curve,interpolate_pump_head,curve_flow_to_si,HEAD_FACTORS,RISING_HEAD_WARNING
from .series_parallel import (combine_series_curves,combine_parallel_curves,
                              combine_identical_series,combine_identical_parallel)
from .system_curve import model_from_reference,model_from_k
from .system_curve_ui import METHODS,MODEL_GUIDANCE
from .operating_point import find_operating_points,NO_INTERSECTION,MULTIPLE_INTERSECTIONS

CONFIGURATIONS=('Pumps in Series','Pumps in Parallel')
PUMP_MODES=('Identical Pumps','Different Pump Curves')


def _curve_inputs(st,number,flow_unit,head_unit):
    st.markdown(f'**Manufacturer/Vendor Pump Curve {number}**')
    count=st.number_input(f'Pump {number} — Number of Q–H Points',min_value=3,max_value=20,value=3,step=1,key=f'p3l_count_{number}')
    rows=[]
    for index in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'Pump {number} Point {index+1} — Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key=f'p3l_q_{number}_{index}')
        with right:h=st.number_input(f'Pump {number} Point {index+1} — Head ({head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3l_h_{number}_{index}')
        rows.append((q,h))
    return rows


def _display(value,factor):
    converted=value/factor
    if not math.isfinite(converted) or (value!=0 and converted==0):
        raise ValueError('Displayed combined-curve value exceeds the supported numeric range.')
    return converted


def combined_plot_spec(result,flow_factor,flow_unit,head_unit,model=None,roots=None):
    factor=HEAD_FACTORS[head_unit]
    layers=[]
    labels=['Pump 1 Curve']+(['Pump 2 Curve'] if result.pump_mode=='Different' else [])+['Combined Pump Curve']
    colors=['#4e9de0']+(['#c39ce6'] if result.pump_mode=='Different' else [])+['#ed9238']
    curves=[('Pump 1 Curve',result.pump_1)]
    if result.pump_mode=='Different':curves.append(('Pump 2 Curve',result.pump_2))
    curves.append(('Combined Pump Curve',result.combined))
    for label,curve in curves:
        rows=[{'flow':_display(p.flow_m3_s,flow_factor),'head':_display(p.head_m,factor),'series':label} for p in curve.points]
        layers.append({'data':{'values':rows},'mark':{'type':'line','point':{'filled':True,'size':35},'strokeWidth':3 if label=='Combined Pump Curve' else 1.5}})
    if model is not None:
        lower,upper=result.combined.points[0].flow_m3_s,result.combined.points[-1].flow_m3_s
        rows=[]
        for index in range(81):
            q=lower+(upper-lower)*(index/80)
            rows.append({'flow':_display(q,flow_factor),'head':_display(model.at_flow(q).total_head_m,factor),'series':'System Curve'})
        layers.append({'data':{'values':rows},'mark':{'type':'line','strokeDash':[6,4]}})
        labels.append('System Curve');colors.append('#76bb85')
    if roots is not None and roots.points:
        rows=[{'flow':_display(p.flow_m3_s,flow_factor),'head':_display(p.head_m,factor),'series':'Operating Point'} for p in roots.points]
        layers.append({'data':{'values':rows},'mark':{'type':'point','shape':'diamond','filled':True,'size':180}})
        labels.append('Operating Point');colors.append('#f5dc5c')
    return {'title':'Combined Pump Curve — '+result.configuration,'layer':layers,
        'encoding':{'x':{'field':'flow','type':'quantitative','title':f'Flow Rate ({flow_unit})','scale':{'zero':False}},
                    'y':{'field':'head','type':'quantitative','title':f'Head ({head_unit})'},
                    'color':{'field':'series','type':'nominal','scale':{'domain':labels,'range':colors},'legend':{'title':None,'orient':'bottom'}},
                    'tooltip':[{'field':'flow','type':'quantitative'},{'field':'head','type':'quantitative'},{'field':'series','type':'nominal'}]},
        'height':360,'config':{'view':{'stroke':None}}}


def render_series_parallel(flow_factors):
    import streamlit as st
    st.subheader('3L — Pumps in Series / Parallel')
    st.write('Combine two supplied centrifugal-pump curves on a Common Flow basis for series or Common Head basis for parallel operation.')
    configuration=st.selectbox('Pump Configuration',CONFIGURATIONS,key='p3l_configuration')
    mode=st.selectbox('Pump Curve Mode',PUMP_MODES,key='p3l_mode')
    flow_unit=st.selectbox('Series/Parallel Flow Unit',list(flow_factors),index=None,placeholder='Select flow unit',key='p3l_flow_unit')
    head_unit=st.selectbox('Series/Parallel Head Unit',list(HEAD_FACTORS),index=None,placeholder='Select head unit',key='p3l_head_unit')
    st.info('Use manufacturer/vendor pump curves applicable to the selected pump speed and impeller diameter.')
    st.caption('Enter at least 3 unique Q–H points per curve; points are sorted automatically. No default pump data, polynomial fit, smoothing or extrapolation. Selected units apply to all pump/system inputs and displayed results; direct K is always SI. Unit changes reinterpret entered numbers, not convert them.')
    points1=_curve_inputs(st,1,flow_unit,head_unit)
    points2=_curve_inputs(st,2,flow_unit,head_unit) if mode==PUMP_MODES[1] else None
    st.markdown('**Combined Pump Curve**')
    selected=st.number_input(f'Optional Combined Flow for Head Check ({flow_unit or "select unit above"})',value=None,format='%.12g',key='p3l_selected')
    comparison=st.selectbox('Optional System Curve Comparison',['No System Curve','Compare with System Curve'],key='p3l_comparison')
    if comparison=='Compare with System Curve':
        method=st.selectbox('Combined System Curve Method',METHODS,key='p3l_system_method')
        static=st.number_input(f'Combined System Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3l_static')
        if method==METHODS[0]:
            reference=st.number_input(f'Combined System Reference Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key='p3l_reference')
            friction=st.number_input(f'Combined System Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3l_friction')
        else:k=st.number_input('Combined System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3l_k')
        st.caption(MODEL_GUIDANCE)
    if st.button('Calculate Combined Pump Curve',key='p3l_calculate'):
        try:
            first=create_pump_curve(points1,flow_unit,head_unit,flow_factors)
            series=configuration==CONFIGURATIONS[0]
            if mode==PUMP_MODES[0]:
                result=(combine_identical_series if series else combine_identical_parallel)(first)
            else:
                second=create_pump_curve(points2,flow_unit,head_unit,flow_factors)
                result=(combine_series_curves if series else combine_parallel_curves)(first,second)
            model=roots=None
            if comparison=='Compare with System Curve':
                if method==METHODS[0]:
                    model=model_from_reference(static_head=static,head_unit=head_unit,reference_flow=reference,
                        reference_friction_head=friction,flow_unit=flow_unit,flow_factors=flow_factors)
                else:model=model_from_k(static,head_unit,k)
                roots=find_operating_points(result.combined,model)
            selected_result=None
            if selected is not None:
                selected_result=interpolate_pump_head(result.combined,curve_flow_to_si(selected,flow_unit,flow_factors))
            f,h=flow_factors[flow_unit],HEAD_FACTORS[head_unit]
            ranges=(min(p.head_m for p in result.combined.points),max(p.head_m for p in result.combined.points))
            st.text(f'Configuration: {result.configuration}\nPump Mode: {result.pump_mode}\n'
                f'Combined Valid Flow Range: {_display(result.combined.points[0].flow_m3_s,f):.12g} to {_display(result.combined.points[-1].flow_m3_s,f):.12g} {flow_unit}\n'
                f'Combined Valid Head Range: {_display(ranges[0],h):.12g} to {_display(ranges[1],h):.12g} {head_unit}')
            overlap_factor=f if result.common_basis=='flow_m3_s' else h
            st.text(f'Valid Overlap Range — {"Common Flow" if series else "Common Head"}: '
                f'{_display(result.overlap_minimum,overlap_factor):.12g} to {_display(result.overlap_maximum,overlap_factor):.12g} {flow_unit if series else head_unit}')
            st.vega_lite_chart(spec=combined_plot_spec(result,f,flow_unit,head_unit,model,roots),width='stretch')
            for label,curve in [('Pump 1 Curve',result.pump_1)]+([('Pump 2 Curve',result.pump_2)] if mode==PUMP_MODES[1] else [])+[('Combined Pump Curve',result.combined)]:
                st.markdown('**'+label+'**')
                st.text('Flow ('+flow_unit+') | Head ('+head_unit+')\n'+'\n'.join(f'{_display(p.flow_m3_s,f):.12g} | {_display(p.head_m,h):.12g}' for p in curve.points))
            if result.pump_1.has_rising_head or result.pump_2.has_rising_head:st.warning(RISING_HEAD_WARNING)
            if selected_result is not None:
                st.text(f'Combined Flow Check: {selected:.12g} {flow_unit}\nCombined Head: {_display(selected_result.head_m,h):.12g} {head_unit}')
            if roots is not None:
                st.markdown('**Operating Point**')
                if roots.coincident_intervals:
                    st.warning('Pump and system curves coincide over an interval; infinitely many intersections exist. No unique operating point is selected.')
                    for interval in roots.coincident_intervals:
                        st.text(f'Coincident Flow Interval: {_display(interval.minimum_flow_m3_s,f):.12g} to {_display(interval.maximum_flow_m3_s,f):.12g} {flow_unit}\nHead: {_display(interval.head_m,h):.12g} {head_unit}')
                if len(roots.points)>1:
                    st.warning(MULTIPLE_INTERSECTIONS)
                    st.caption('All isolated intersections are reported. Stability or preferred operation is not determined.')
                if not roots.points and not roots.coincident_intervals:st.info(NO_INTERSECTION)
                for index,p in enumerate(roots.points,1):
                    prefix=f'Intersection {index}\n' if len(roots.points)>1 else ''
                    st.text(prefix+f'Operating Flow: {_display(p.flow_m3_s,f):.12g} {flow_unit}\nOperating Head: {_display(p.head_m,h):.12g} {head_unit}\nPump/System Residual: {_display(p.residual_m,h):+.6g} {head_unit}')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('Pumps in series operate at approximately the same flow while heads add. Pumps in parallel operate at approximately the same head while flows add. The actual operating point is the intersection of the combined pump curve and connected system curve.')
    st.caption('Dissimilar parallel pumps require compatible curves and hydraulic conditions. Equal flow sharing is assumed only for identical pumps; different pumps are evaluated at the same head using their own supplied curves. Different shutoff heads are not treated as equal.')
    st.caption('Check valves, minimum-flow requirements, controls and pump interaction may materially affect real parallel operation. No start/stop transients, check-valve dynamics or stability decision is modeled.')
    st.caption('Combined performance must remain within manufacturer/vendor operating limits. Check BEP, NPSHR, power and driver loading for each operating pump. ConversionPro does not replace detailed manufacturer/vendor or hydraulic-system review.')
