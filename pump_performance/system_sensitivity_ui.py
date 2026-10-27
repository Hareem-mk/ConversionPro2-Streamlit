"""Independent base/modified cases, preserved roots and neutral comparisons."""
import math
from .system_sensitivity import (evaluate_system_sensitivity,modified_resistance_model,
    evaluate_point_context,numeric_change,is_unique,NO_VALID_POINT)
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS
from .system_curve import model_from_k,model_from_reference,head_to_metres
from .system_curve_ui import MODEL_GUIDANCE
from .power_curve import create_power_curve
from .npshr_curve import create_npshr_curve
from .shaft_power import POWER_FACTORS
from piping_hydraulics.pump_head import finite_signed

METHODS_3R=('Direct K Sensitivity','Reference Flow / Friction Head Sensitivity')
MODIFIED_METHODS=('Explicit Modified System','Percent Resistance Change from Base K')
GUIDANCE='Changes in system resistance can represent effects such as throttling, fouling, filter loading, exchanger pressure-drop changes, or piping configuration changes.'


def _shown(value,factor):
    result=value/factor
    if not math.isfinite(result) or (value!=0 and result==0):raise ValueError('Displayed sensitivity value exceeds numeric range.')
    return result


def sensitivity_plot_spec(curve,base_model,modified_model,result,flow_factor,flow_unit,head_unit):
    hf=HEAD_FACTORS[head_unit]
    layers=[]
    labels=['Vendor Pump Head Curve','Base System Curve','Modified System Curve','Base Operating Point','Modified Operating Point']
    def layer(rows,mark):layers.append({'data':{'values':rows},'mark':mark})
    layer([{'flow':_shown(p.flow_m3_s,flow_factor),'head':_shown(p.head_m,hf),'series':labels[0]} for p in curve.points],{'type':'line','point':True,'strokeWidth':2.5})
    lower,upper=curve.points[0].flow_m3_s,curve.points[-1].flow_m3_s
    for label,model,roots,shape in [(labels[1],base_model,result.base,'circle'),(labels[2],modified_model,result.modified,'diamond')]:
        rows=[]
        for i in range(81):
            q=lower+(upper-lower)*(i/80)
            rows.append({'flow':_shown(q,flow_factor),'head':_shown(model.at_flow(q).total_head_m,hf),'series':label})
        layer(rows,{'type':'line','strokeDash':[6,4]})
        if roots.points:
            point_label=labels[3] if label==labels[1] else labels[4]
            layer([{'flow':_shown(p.flow_m3_s,flow_factor),'head':_shown(p.head_m,hf),'series':point_label} for p in roots.points],
                  {'type':'point','filled':True,'shape':shape,'size':150})
    return {'title':'System Curve Sensitivity — Base and Modified Cases','layer':layers,'encoding':{
        'x':{'field':'flow','type':'quantitative','title':f'Flow ({flow_unit})','scale':{'zero':False}},
        'y':{'field':'head','type':'quantitative','title':f'Head ({head_unit})'},
        'color':{'field':'series','type':'nominal','scale':{'domain':labels,'range':['#4e9de0','#76bb85','#c39ce6','#ed9238','#f08bb4']},'legend':{'title':None,'orient':'bottom','columns':2,'labelLimit':280}},
        'tooltip':[{'field':'flow','type':'quantitative'},{'field':'head','type':'quantitative'},{'field':'series','type':'nominal'}]},
        'height':380,'config':{'view':{'stroke':None}}}


def _optional_curve_inputs(st,label,key,flow_factors,value_units):
    st.markdown('**'+label+'**')
    unit=st.selectbox(label+' Flow Unit',list(flow_factors),index=None,key='p3r_'+key+'_flow_unit')
    vu=st.selectbox(label+' Value Unit',list(value_units),index=None,key='p3r_'+key+'_value_unit')
    count=st.number_input(label+' — Number of Points',min_value=3,max_value=20,value=3,step=1,key='p3r_'+key+'_count')
    rows=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'{label} Point {i+1} — Flow ({unit or "select unit above"})',value=None,format='%.12g',key=f'p3r_{key}_q_{i}')
        with right:v=st.number_input(f'{label} Point {i+1} — Value ({vu or "select unit above"})',value=None,format='%.12g',key=f'p3r_{key}_v_{i}')
        rows.append((q,v))
    return rows,unit,vu


def render_system_sensitivity(flow_factors,density_factors):
    import streamlit as st
    st.subheader('3R — System Curve Sensitivity / Operating Point Shift Analysis')
    st.info('Use manufacturer/vendor pump head data for the applicable pump speed and impeller diameter. Both cases use the same supplied pump curve.')
    method=st.selectbox('System Sensitivity Method',METHODS_3R,key='p3r_method')
    flow_unit=st.selectbox('Sensitivity Flow Unit',list(flow_factors),index=None,key='p3r_flow_unit')
    head_unit=st.selectbox('Sensitivity Head Unit',list(HEAD_FACTORS),index=None,key='p3r_head_unit')
    st.caption('Selected flow/head units apply to main curve, case inputs and displays. Direct K is always SI s²/m⁵. Changing units reinterprets entered numbers rather than rewriting them.')
    st.markdown('**Vendor Pump Curve**')
    count=st.number_input('Sensitivity — Number of Pump Points',min_value=3,max_value=20,value=3,step=1,key='p3r_count')
    points=[]
    for i in range(count):
        left,right=st.columns(2)
        with left:q=st.number_input(f'Sensitivity Pump Point {i+1} — Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key=f'p3r_q_{i}')
        with right:h=st.number_input(f'Sensitivity Pump Point {i+1} — Head ({head_unit or "select unit above"})',value=None,format='%.12g',key=f'p3r_h_{i}')
        points.append((q,h))
    st.markdown('**Base System Case**')
    base_static=st.number_input(f'Base Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3r_base_static')
    if method==METHODS_3R[0]:base_k=st.number_input('Base K — SI (s²/m⁵)',value=None,format='%.12g',key='p3r_base_k')
    else:
        base_ref=st.number_input(f'Base Reference Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key='p3r_base_ref')
        base_friction=st.number_input(f'Base Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3r_base_friction')
    st.markdown('**Modified System Case**')
    modified_method=st.selectbox('Modified Resistance Input',MODIFIED_METHODS,key='p3r_modified_method')
    modified_static=st.number_input(f'Modified Static Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3r_modified_static')
    if modified_method==MODIFIED_METHODS[1]:
        change=st.number_input('Resistance Change (%)',value=None,format='%.12g',key='p3r_percent')
        st.caption('Active method: modified K is derived from base K and this entered percentage. Explicit modified-K/reference inputs are not used in this mode. Static head remains independently entered. Minimum change is -100%.')
    elif method==METHODS_3R[0]:modified_k=st.number_input('Modified K — SI (s²/m⁵)',value=None,format='%.12g',key='p3r_modified_k')
    else:
        modified_ref=st.number_input(f'Modified Reference Flow ({flow_unit or "select unit above"})',value=None,format='%.12g',key='p3r_modified_ref')
        modified_friction=st.number_input(f'Modified Reference Friction Head ({head_unit or "select unit above"})',value=None,format='%.12g',key='p3r_modified_friction')
    st.caption(MODEL_GUIDANCE)
    st.markdown('**Optional Power / BEP / NPSH Context**')
    density=st.number_input('Sensitivity Fluid Density (optional)',value=None,format='%.12g',key='p3r_density')
    density_unit=st.selectbox('Sensitivity Density Unit',list(density_factors),index=None,key='p3r_density_unit')
    bep=st.number_input('Sensitivity Vendor BEP Flow (optional)',value=None,format='%.12g',key='p3r_bep')
    bep_unit=st.selectbox('Sensitivity Vendor BEP Flow Unit',list(flow_factors),index=None,key='p3r_bep_unit')
    power_mode=st.selectbox('Optional Shaft Power Context',['No Shaft Power Context','Use Vendor Shaft/Brake Power Curve'],key='p3r_power_mode')
    if power_mode!='No Shaft Power Context':power_rows,power_flow_unit,power_value_unit=_optional_curve_inputs(st,'Sensitivity Vendor Shaft Power','power',flow_factors,POWER_FACTORS)
    npsh_mode=st.selectbox('Optional NPSH Context',['No NPSH Context','Use Vendor NPSHR Curve and Entered NPSHA'],key='p3r_npsh_mode')
    if npsh_mode!='No NPSH Context':
        npshr_rows,npshr_flow_unit,npshr_head_unit=_optional_curve_inputs(st,'Sensitivity Vendor NPSHR','npshr',flow_factors,HEAD_FACTORS)
        npsha=st.number_input('Sensitivity NPSHA (same entered value for both cases)',value=None,format='%.12g',key='p3r_npsha')
        npsha_unit=st.selectbox('Sensitivity NPSHA Unit',list(HEAD_FACTORS),index=None,key='p3r_npsha_unit')
        st.caption('NPSHA is held at the same explicitly entered value in both cases. No NPSHA change is invented from the operating-flow change.')
    st.caption('Optional numerical inputs start blank. No vendor limits, default acceptance criteria or automatic shaft efficiency assumption are introduced.')
    if st.button('Evaluate System Curve Sensitivity',key='p3r_calculate'):
        try:
            curve=create_pump_curve(points,flow_unit,head_unit,flow_factors)
            if method==METHODS_3R[0]:base=model_from_k(base_static,head_unit,base_k)
            else:base=model_from_reference(static_head=base_static,head_unit=head_unit,reference_flow=base_ref,reference_friction_head=base_friction,flow_unit=flow_unit,flow_factors=flow_factors)
            if modified_method==MODIFIED_METHODS[1]:modified=modified_resistance_model(base,head_to_metres(modified_static,head_unit,'Modified static head'),change)
            elif method==METHODS_3R[0]:modified=model_from_k(modified_static,head_unit,modified_k)
            else:modified=model_from_reference(static_head=modified_static,head_unit=head_unit,reference_flow=modified_ref,reference_friction_head=modified_friction,flow_unit=flow_unit,flow_factors=flow_factors)
            result=evaluate_system_sensitivity(curve,base,modified)
            ff,hf=flow_factors[flow_unit],HEAD_FACTORS[head_unit]
            plot=sensitivity_plot_spec(curve,base,modified,result,ff,flow_unit,head_unit)
            st.markdown('**Operating Point Comparison**')
            st.text(f'Base K: {result.base_k_si:.12g} s²/m⁵\nModified K: {result.modified_k_si:.12g} s²/m⁵\nBase Static Head: {_shown(base.static_head_m,hf):.12g} {head_unit}\nModified Static Head: {_shown(modified.static_head_m,hf):.12g} {head_unit}')
            for name,roots in [('Base',result.base),('Modified',result.modified)]:
                st.markdown('**'+name+' Operating Point(s)**')
                if not roots.points and not roots.coincident_intervals:st.info(name+': '+NO_VALID_POINT)
                if len(roots.points)>1:st.warning(name+': Multiple intersections exist. All isolated intersections are reported; no single point or dynamic stability is determined.')
                for i,p in enumerate(roots.points,1):st.text(f'{name} Intersection {i}\nOperating Flow: {_shown(p.flow_m3_s,ff):.12g} {flow_unit}\nOperating Head: {_shown(p.head_m,hf):.12g} {head_unit}\nPump/System Residual: {_shown(p.residual_m,hf):+.6g} {head_unit}')
                if roots.coincident_intervals:
                    st.warning(name+': Pump and system curves coincide over interval(s); infinitely many intersections exist. No unique operating point is selected.')
                    for interval in roots.coincident_intervals:st.text(f'{name} Coincident Flow Interval: {_shown(interval.minimum_flow_m3_s,ff):.12g} to {_shown(interval.maximum_flow_m3_s,ff):.12g} {flow_unit}\nHead: {_shown(interval.head_m,hf):.12g} {head_unit}')
            if result.flow_change is not None:
                pct=lambda value,den:'N/A — base '+den+' is zero' if value is None else f'{value:.12g}%'
                st.text(f'Flow Shift: {_shown(result.flow_change.difference,ff):+.12g} {flow_unit}\nPercent Flow Change: {pct(result.flow_change.percent,"flow")}\nHead Shift: {_shown(result.head_change.difference,hf):+.12g} {head_unit}\nPercent Head Change: {pct(result.head_change.percent,"head")}')
            else:st.info('Single flow/head shifts are unavailable: both cases must have exactly one isolated operating point and no coincident intervals. All returned intersections remain listed.')
            st.markdown('**Sensitivity Direction Summary**')
            comparisons=[('System resistance',base.k_si,modified.k_si),('Static head',base.static_head_m,modified.static_head_m)]
            if result.flow_change is not None:comparisons += [('Operating flow',result.base.points[0].flow_m3_s,result.modified.points[0].flow_m3_s),('Operating head',result.base.points[0].head_m,result.modified.points[0].head_m)]
            for label,a,b in comparisons:st.write(label+(' increased.' if b>a else ' decreased.' if b<a else ' is unchanged.'))
            # Optional setup failures do not hide either case or the plot.
            options=dict(density=density,density_unit=density_unit,density_factors=density_factors)
            if bep is not None:
                try:options['bep_flow_si']=curve_flow_to_si(bep,bep_unit,flow_factors)
                except (ValueError,OverflowError) as exc:st.error('BEP context: '+str(exc))
            if power_mode!='No Shaft Power Context':
                try:options['vendor_power_curve']=create_power_curve(power_rows,power_flow_unit,power_value_unit,flow_factors)
                except (ValueError,OverflowError) as exc:st.error('Vendor power context: '+str(exc))
            if npsh_mode!='No NPSH Context':
                try:
                    options['npshr_curve']=create_npshr_curve(npshr_rows,npshr_flow_unit,npshr_head_unit,flow_factors)
                    options['npsha_m']=head_to_metres(npsha,npsha_unit,'Entered NPSHA')
                except (ValueError,OverflowError) as exc:
                    options.pop('npshr_curve',None);st.error('NPSH context: '+str(exc))
            contexts={}
            if density is not None or bep is not None or power_mode!='No Shaft Power Context' or npsh_mode!='No NPSH Context':
                st.markdown('**Optional Context at Each Isolated Intersection**')
                for name,roots in [('Base',result.base),('Modified',result.modified)]:
                    contexts[name]=[]
                    for i,p in enumerate(roots.points,1):
                        context=evaluate_point_context(p,flow_factors,**options);contexts[name].append(context)
                        text=f'{name} Intersection {i} Context'
                        for label,value,factor,unit in [('Hydraulic Power',context.hydraulic_w,POWER_FACTORS['kW'],'kW'),('Vendor Interpolated Shaft Power',context.vendor_shaft_w,POWER_FACTORS['kW'],'kW'),('Percent of BEP',context.percent_bep,1,'%'),('Vendor NPSHR',context.npshr_m,hf,head_unit),('NPSH Margin',context.npsh_margin_m,hf,head_unit)]:
                            if value is not None:text+=f'\n{label}: {_shown(value,factor):.12g} {unit}'
                        st.text(text)
                        for error in context.errors:st.info(f'{name} Intersection {i}: '+error)
                if is_unique(result.base) and is_unique(result.modified):
                    a,b=contexts['Base'][0],contexts['Modified'][0]
                    for label,field,factor,unit in [('Hydraulic Power','hydraulic_w',POWER_FACTORS['kW'],'kW'),('Vendor Shaft Power','vendor_shaft_w',POWER_FACTORS['kW'],'kW'),('BEP','percent_bep',1,'percentage points'),('NPSH Margin','npsh_margin_m',hf,head_unit)]:
                        av,bv=getattr(a,field),getattr(b,field)
                        if av is None or bv is None:continue
                        change_result=numeric_change(av,bv) if field in ('hydraulic_w','vendor_shaft_w') else None
                        difference=change_result.difference if change_result is not None else finite_signed(bv-av,label+' change')
                        text=f'{label} Change: {_shown(difference,factor):+.12g} {unit}'
                        if change_result is not None:text+='\nPercent '+label+' Change: '+('N/A — base power is zero' if change_result.percent is None else f'{change_result.percent:.12g}%')
                        st.text(text)
            st.vega_lite_chart(spec=plot,width='stretch')
            st.caption('Blue: supplied pump curve; green/purple dashed lines: base/modified systems. Orange circles and pink diamonds: all isolated base/modified operating points. Vendor pump data are not extrapolated.')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('The operating point is determined by the pump/system intersection. For a conventional falling pump curve, increased system resistance generally reduces flow; reduced resistance generally increases flow. Increased static head generally reduces flow.')
    st.caption('Sensitivity results depend on the supplied pump curve and system representation. Vendor pump data are not extrapolated. '+GUIDANCE)
    st.caption('This module does not determine the physical cause of a system-curve change, dynamic stability, an acceptance decision or corrective action. Final assessment should consider BEP, NPSH, driver loading, minimum flow and vendor/project limits where applicable.')
