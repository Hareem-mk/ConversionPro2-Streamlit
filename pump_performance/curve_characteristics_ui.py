"""Phase 3Q descriptive head-curve diagnostics and explicit vendor context."""
import math
from .curve_characteristics import (analyze_curve_characteristics,local_curve_slope,
    calculate_shutoff_head_rise,display_slope,compare_minimum_flow,NO_SHUTOFF)
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS
from .system_curve import model_from_reference,model_from_k
from .system_curve_ui import METHODS,MODEL_GUIDANCE
from .operating_point import find_operating_points,NO_INTERSECTION,MULTIPLE_INTERSECTIONS
from .bep_operating_range import compare_bep

METHODS_3Q=('Manual Operating Flow','From Phase 3G Operating Point')
GUIDANCE='Use the applicable manufacturer/vendor pump head curve for the selected pump speed and impeller diameter.'


def _shown(value,factor):
    result=value/factor
    if not math.isfinite(result) or (value!=0 and result==0):raise ValueError('Displayed curve-characteristic value exceeds numeric range.')
    return result


def characteristics_plot_spec(curve,analysis,operating,flow_factor,flow_unit,head_unit):
    hf=HEAD_FACTORS[head_unit]
    row=lambda p:{'flow':_shown(p.flow_m3_s,flow_factor),'head':_shown(p.head_m,hf)}
    layers=[{'data':{'values':[row(p) for p in curve.points]},'mark':{'type':'line','point':True,'color':'#4e9de0'}}]
    def marker(flow,head,label,color,shape):
        layers.append({'data':{'values':[{'flow':_shown(flow,flow_factor),'head':_shown(head,hf),'label':label}]},
                       'mark':{'type':'point','filled':True,'size':160,'color':color,'shape':shape}})
    marker(operating.evaluated_flow_m3_s,operating.operating_head_m,'Operating Point','#ed9238','circle')
    if analysis.shutoff_head_m is not None:marker(0,analysis.shutoff_head_m,'Supplied Shutoff Head','#c39ce6','diamond')
    marker(analysis.maximum_flow_point.flow_m3_s,analysis.maximum_flow_point.head_m,'Maximum Supplied Flow Point','#76bb85','square')
    return {'title':'Supplied Pump Head Curve — Characteristics','layer':layers,'encoding':{
        'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
        'y':{'field':'head','type':'quantitative','title':f'Head ({head_unit})'},
        'tooltip':[{'field':'flow','type':'quantitative'},{'field':'head','type':'quantitative'},{'field':'label','type':'nominal'}]},
        'height':340,'config':{'view':{'stroke':None}}}


def render_curve_characteristics(flow_factors):
    import streamlit as st
    st.subheader('3Q — Pump Curve Characteristics / Shutoff & Slope Analysis')
    st.info(GUIDANCE)
    method=st.selectbox('Characteristics Calculation Method',METHODS_3Q,key='p3q_method')
    st.markdown('**Vendor Pump Head Curve**')
    curve_unit=st.selectbox('Characteristics Curve Flow Unit',list(flow_factors),index=None,key='p3q_curve_unit')
    curve_head_unit=st.selectbox('Characteristics Curve Head Unit',list(HEAD_FACTORS),index=None,key='p3q_curve_head_unit')
    count=st.number_input('Characteristics — Number of Pump Points',min_value=3,max_value=20,value=3,step=1,key='p3q_count')
    points=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'Characteristics Point {i+1} — Flow ({curve_unit or "select unit above"})',value=None,format='%.12g',key=f'p3q_q_{i}')
        with right:h=st.number_input(f'Characteristics Point {i+1} — Head ({curve_head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3q_h_{i}')
        points.append((q,h))
    st.caption('Enter 3–20 supplied Q–H points. Phase 3E validates and sorts them. No default pump points are loaded. Unit changes reinterpret entered numbers rather than rewriting them.')
    st.markdown('**Operating Flow / Display Units**')
    display_flow_unit=st.selectbox('Characteristics Display / Slope Flow Unit',list(flow_factors),index=None,key='p3q_display_flow_unit')
    display_head_unit=st.selectbox('Characteristics Display / Slope Head Unit',list(HEAD_FACTORS),index=None,key='p3q_display_head_unit')
    integrated=method==METHODS_3Q[1]
    if not integrated:
        operating_unit=st.selectbox('Characteristics Operating Flow Unit',list(flow_factors),index=None,key='p3q_operating_unit')
        operating=st.number_input('Characteristics Operating Flow',value=None,format='%.12g',key='p3q_operating')
    else:
        sys_method=st.selectbox('Characteristics System Method',METHODS,key='p3q_sys_method')
        static=st.number_input(f'Characteristics System Static Head ({display_head_unit or "select unit above"})',value=None,format='%.12g',key='p3q_static')
        if sys_method==METHODS[0]:
            reference=st.number_input(f'Characteristics System Reference Flow ({display_flow_unit or "select unit above"})',value=None,format='%.12g',key='p3q_reference')
            friction=st.number_input(f'Characteristics System Friction Head ({display_head_unit or "select unit above"})',value=None,format='%.12g',key='p3q_friction')
        else:k=st.number_input('Characteristics System K [Q in m³/s] (s²/m⁵)',value=None,format='%.12g',key='p3q_k')
        st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional Vendor Limits / Context**')
    runout=st.number_input('Vendor-Defined Runout Flow',value=None,format='%.12g',key='p3q_runout')
    runout_unit=st.selectbox('Vendor-Defined Runout Flow Unit',list(flow_factors),index=None,key='p3q_runout_unit')
    minimum=st.number_input('Vendor/Project Minimum Flow',value=None,format='%.12g',key='p3q_minimum')
    minimum_unit=st.selectbox('Vendor/Project Minimum Flow Unit',list(flow_factors),index=None,key='p3q_minimum_unit')
    bep=st.number_input('Characteristics Vendor BEP Flow',value=None,format='%.12g',key='p3q_bep')
    bep_unit=st.selectbox('Characteristics Vendor BEP Flow Unit',list(flow_factors),index=None,key='p3q_bep_unit')
    st.caption('These optional vendor/project values start blank. No endpoint, slope or curve geometry is used to infer runout, minimum flow or BEP.')
    if st.button('Analyze Pump Curve Characteristics',key='p3q_calculate'):
        try:
            curve=create_pump_curve(points,curve_unit,curve_head_unit,flow_factors)
            curve_flow_to_si(0,display_flow_unit,flow_factors)
            if display_head_unit not in HEAD_FACTORS:raise ValueError('Select a supported display head unit: m or ft.')
            if integrated:
                model=(model_from_reference(static_head=static,head_unit=display_head_unit,reference_flow=reference,
                       reference_friction_head=friction,flow_unit=display_flow_unit,flow_factors=flow_factors)
                       if sys_method==METHODS[0] else model_from_k(static,display_head_unit,k))
                roots=find_operating_points(curve,model)
                if roots.coincident_intervals:raise ValueError('Pump and system curves coincide over an interval; no unique operating flow is selected.')
                if not roots.points:raise ValueError(NO_INTERSECTION)
                if len(roots.points)!=1:raise ValueError(MULTIPLE_INTERSECTIONS+' No operating flow is selected; use manual mode for an explicitly chosen flow.')
                q=roots.points[0].flow_m3_s
            else:q=curve_flow_to_si(operating,operating_unit,flow_factors)
            analysis=analyze_curve_characteristics(curve)
            selected=local_curve_slope(curve,q)
            rise=None if analysis.shutoff_head_m is None else calculate_shutoff_head_rise(analysis.shutoff_head_m,selected.operating_head_m)
            ff,hf=flow_factors[display_flow_unit],HEAD_FACTORS[display_head_unit]
            slope_label=f'{display_head_unit} per ({display_flow_unit})'
            plot=characteristics_plot_spec(curve,analysis,selected,ff,display_flow_unit,display_head_unit)
            text=(f'Supplied Flow Range: {_shown(analysis.minimum_flow_m3_s,ff):.12g} to {_shown(analysis.maximum_flow_m3_s,ff):.12g} {display_flow_unit}\n'
                  f'Supplied Head Range: {_shown(analysis.minimum_head_m,hf):.12g} to {_shown(analysis.maximum_head_m,hf):.12g} {display_head_unit}\n'
                  f'Maximum Supplied Flow Point: {_shown(analysis.maximum_flow_point.flow_m3_s,ff):.12g} {display_flow_unit} at {_shown(analysis.maximum_flow_point.head_m,hf):.12g} {display_head_unit}\n'
                  f'Operating Flow: {_shown(q,ff):.12g} {display_flow_unit}\nOperating Head: {_shown(selected.operating_head_m,hf):.12g} {display_head_unit}\n'
                  f'Monotonicity Status: {analysis.monotonicity_status}\nFlat Segment Count: {analysis.flat_segment_count}\nRising Segment Count: {analysis.rising_segment_count}')
            if analysis.shutoff_head_m is None:text+='\n'+NO_SHUTOFF
            else:
                text+=f'\nSupplied Shutoff Head: {_shown(analysis.shutoff_head_m,hf):.12g} {display_head_unit}\nHead Rise to Shutoff: {_shown(rise.rise_m,hf):.12g} {display_head_unit}'
                pct=lambda v,den:'N/A — '+den+' is zero' if v is None else f'{v:.12g}%'
                text+='\nPercent Head Rise relative to Operating Head: '+pct(rise.percent_of_operating_head,'operating head')
                text+='\nPercent Head Rise relative to Shutoff Head: '+pct(rise.percent_of_shutoff_head,'shutoff head')
            for i,s in enumerate(selected.local_segments):
                side=('Left' if i==0 else 'Right')+' Segment' if len(selected.local_segments)==2 else 'Adjacent Segment'
                text+=f'\nLocal Pump-Curve Slope — {side}: {display_slope(s.slope_si,display_flow_unit,display_head_unit,flow_factors):.12g} {slope_label}'
            st.markdown('**Curve Characteristics**');st.text(text)
            st.caption('Internal exact supplied operating points report both left and right slopes. Endpoints report only the adjacent supplied segment. Slopes are not averaged.')
            st.markdown('**Segment Slope Analysis**')
            table=[]
            for s in analysis.segments:
                table.append({'Segment':s.index,f'From Flow ({display_flow_unit})':_shown(s.lower.flow_m3_s,ff),f'To Flow ({display_flow_unit})':_shown(s.upper.flow_m3_s,ff),
                              'Slope ('+slope_label+')':display_slope(s.slope_si,display_flow_unit,display_head_unit,flow_factors),'Classification':s.classification})
                if s.classification=='Flat':st.info(f'Flat head segment detected. Segment {s.index}: {_shown(s.lower.flow_m3_s,ff):.12g} to {_shown(s.upper.flow_m3_s,ff):.12g} {display_flow_unit}.')
                if s.classification=='Rising':st.info(f'Rising-head segment detected in supplied curve. Segment {s.index}: {_shown(s.lower.flow_m3_s,ff):.12g} to {_shown(s.upper.flow_m3_s,ff):.12g} {display_flow_unit}.')
            columns=list(table[0])
            formatted=lambda value:f'{value:.12g}' if isinstance(value,float) else str(value)
            st.markdown('| '+' | '.join(columns)+' |\n| '+' | '.join(['---']*len(columns))+' |\n'+'\n'.join(
                '| '+' | '.join(formatted(row[column]) for column in columns)+' |' for row in table))
            st.caption('Flat classification uses numerical head equality: relative tolerance 1e-12 or absolute tolerance 1e-9 m. Raw segment slopes retain full precision; this is not an engineering flatness or stability criterion.')
            for label,value,unit in [('Vendor-Defined Runout Flow',runout,runout_unit),('Vendor/Project Minimum Flow',minimum,minimum_unit),('Vendor BEP Flow',bep,bep_unit)]:
                if value is None:continue
                try:
                    entered=curve_flow_to_si(value,unit,flow_factors)
                    if label=='Vendor/Project Minimum Flow':st.text(f'{label} (user-entered): {value:.12g} {unit}\n'+compare_minimum_flow(q,entered))
                    else:
                        comparison=compare_bep(q,entered)
                        title='Operating Flow / Vendor Runout Flow %' if label=='Vendor-Defined Runout Flow' else 'Percent of BEP'
                        st.text(f'{label} (user-entered): {value:.12g} {unit}\n{title}: {comparison.percent_bep:.12g}%')
                except (ValueError,OverflowError) as exc:st.error(label+': '+str(exc))
            st.vega_lite_chart(spec=plot,width='stretch')
            st.caption('Blue line/points: supplied curve. Orange circle: operating point. Purple diamond: Supplied Shutoff Head, only if Q=0 supplied. Green square: Maximum Supplied Flow Point. Hover markers for their labels. No curve extrapolation.')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption(GUIDANCE+' Shutoff head is reported only when a Q = 0 point is supplied.')
    st.caption('Maximum supplied flow is not automatically manufacturer-defined runout or an allowable limit. Vendor BEP, minimum flow, runout, NPSHR and allowable operating range must come from applicable vendor/project data where required.')
    st.caption('Pump-curve slope is descriptive and must be considered together with the connected system curve and control philosophy. Rising or flat portions may require manufacturer/system review depending on the pump and control arrangement.')
    st.caption('ConversionPro does not determine hydraulic stability from pump-curve slope alone. Final pump assessment should use complete manufacturer/vendor performance documentation.')
