"""Target-flow speed solver UI, with explicit theoretical/vendor distinctions."""
from types import SimpleNamespace
from .target_speed import solve_speed_for_target_flow, compare_speed_limits, NO_SOLUTION
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS
from .system_curve import model_from_k,model_from_reference
from .variable_speed_ui import _points,variable_speed_plot_spec
from .system_sensitivity_ui import _shown
from .affinity_laws import calculate_speed_affinity
from .bep_operating_range import compare_bep
from .pump_efficiency import power_to_watts
from .shaft_power import POWER_FACTORS

METHODS=('Direct K','Reference Flow / Friction Head')
GUIDANCE=(
    'Required speed matches the affinity-scaled pump curve to the system head at the target flow. '
    'Required speed is not generally proportional to flow when static head is present. '
    'Static system head is not affinity-scaled with pump speed.',
    'Affinity laws provide approximate corresponding-point scaling for the same pump and impeller diameter. '
    'Every isolated solved speed is verified against the full scaled pump/system intersection. '
    'Neither the reference nor scaled pump curve is extrapolated. Multiple solutions are retained; dynamic stability is not determined.',
    'Efficiency may change with speed. Affinity laws do not guarantee unchanged efficiency.',
    'NPSHR at the solved speed is not calculated automatically. Use applicable manufacturer/vendor data.',
    'Pump rpm is not identical to VFD electrical frequency. Motor pole count, slip, and drive/motor configuration must be considered.',
    'Actual allowable speed must follow manufacturer, motor, coupling, mechanical and VFD limits. '
    'Affinity-scaled curves are engineering estimates, not manufacturer-certified curves. '
    'Final operating limits require manufacturer/vendor confirmation; a solved speed is not automatic approval.'
)


def target_speed_plot_spec(curve,result,solution,system,ff,fu,hu):
    scaling=SimpleNamespace(reference_speed_rpm=result.reference_speed_rpm,new_speed_rpm=solution.required_speed_rpm,
                            scaled_curve=solution.scaled_curve)
    forward=SimpleNamespace(scaling=scaling,base=result.base,new=solution.verification)
    spec=variable_speed_plot_spec(curve,forward,system,ff,fu,hu)
    old=spec['encoding']['color']['scale']['domain']
    new=[old[0],f'Required-Speed Affinity-Scaled Curve — {solution.required_speed_rpm:.12g} rpm',old[2],
         'Reference-Speed Operating Point','Verified Operating Point(s)']
    for layer in spec['layer']:
        for row in layer['data']['values']:row['series']=new[old.index(row['series'])]
    spec['encoding']['color']['scale']['domain']=new
    spec['title']='Required Speed — Full Pump/System Verification'
    return spec


def render_target_speed(flow_factors):
    import streamlit as st
    st.subheader('3T — Required Pump Speed for Target Flow / VSD Setpoint Solver')
    st.info('Preliminary same-pump, same-impeller target-flow analysis. Required speed is solved against the separately defined system curve and verified using Phase 3G.')
    fu=st.selectbox('Target Speed Flow Unit',list(flow_factors),index=None,key='p3t_flow_unit')
    hu=st.selectbox('Target Speed Head Unit',list(HEAD_FACTORS),index=None,key='p3t_head_unit')
    st.caption('Main curve, system and target inputs use the selected units. Changing units reinterprets numbers rather than rewriting them. Speed is rpm; direct K is SI s²/m⁵.')
    st.markdown('**Vendor Reference Pump Curve**')
    rows=_points(st,'Target Speed Reference Head Curve','p3t_head',fu,hu)
    speed=st.number_input('Target Solver Reference Speed (rpm)',value=None,format='%.12g',key='p3t_speed')
    st.markdown('**System Curve — Static Head Remains Unchanged**')
    method=st.selectbox('Target Speed System Method',METHODS,key='p3t_method')
    static=st.number_input(f'Target Solver Static Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3t_static')
    k=ref=friction=None
    if method==METHODS[0]:k=st.number_input('Target Solver K — SI (s²/m⁵)',value=None,format='%.12g',key='p3t_k')
    else:
        ref=st.number_input(f'Target Solver Reference Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3t_reference_flow')
        friction=st.number_input(f'Target Solver Reference Friction Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3t_friction')
    target=st.number_input(f'Target Operating Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3t_target')
    st.markdown('**Optional User/Vendor/Project Speed Limits**')
    minimum=st.number_input('Minimum Allowed Speed (rpm, optional)',value=None,format='%.12g',key='p3t_minimum')
    maximum=st.number_input('Maximum Allowed Speed (rpm, optional)',value=None,format='%.12g',key='p3t_maximum')
    st.caption('Entered speed limits are compared separately; they do not restrict the mathematical root search. No generic rpm or VFD limit is assumed.')
    st.markdown('**Optional Corresponding-Point BEP / Power Context**')
    bep=st.number_input('Target Solver Reference-Speed Vendor BEP Flow (optional)',value=None,format='%.12g',key='p3t_bep')
    bu=st.selectbox('Target Solver BEP Flow Unit',list(flow_factors),index=None,key='p3t_bep_unit')
    power=st.number_input('Target Solver Reference Corresponding-Point Shaft Power (optional)',value=None,format='%.12g',key='p3t_power')
    pu=st.selectbox('Target Solver Power Unit',list(POWER_FACTORS),index=None,key='p3t_power_unit')
    st.caption('Scalar power is only a theoretical corresponding-point estimate. It is not shaft power at the verified target operating point or motor input power, and is not used for driver loading.')
    st.caption('Optional numerical fields start blank. No efficiency, power margin, vendor speed range or frequency is invented.')
    if st.button('Solve Required Pump Speed',key='p3t_solve'):
        try:
            curve=create_pump_curve(rows,fu,hu,flow_factors)
            model=(model_from_k(static,hu,k) if method==METHODS[0] else model_from_reference(static_head=static,head_unit=hu,reference_flow=ref,reference_friction_head=friction,flow_unit=fu,flow_factors=flow_factors))
            q=curve_flow_to_si(target,fu,flow_factors)
            result=solve_speed_for_target_flow(curve,speed,model,q)
            ff=flow_factors[fu];hf=HEAD_FACTORS[hu]
            st.markdown('**Target and System Summary**')
            st.text(f'Reference Speed: {result.reference_speed_rpm:.12g} rpm\nTarget Flow: {_shown(q,ff):.12g} {fu}\nTarget System Head: {_shown(result.target_system_head_m,hf):.12g} {hu}\nUnchanged Static Head: {_shown(model.static_head_m,hf):.12g} {hu}\nUnchanged K: {model.k_si:.12g} s²/m⁵')
            for i,p in enumerate(result.base.points,1):st.text(f'Reference-Speed Intersection {i}\nOperating Flow: {_shown(p.flow_m3_s,ff):.12g} {fu}\nOperating Head: {_shown(p.head_m,hf):.12g} {hu}')
            if not result.solutions and not result.coincident_ratio_intervals:st.info(NO_SOLUTION)
            if len(result.solutions)>1:st.warning('Multiple valid speed solutions exist. All are reported; none is selected automatically and dynamic stability is not determined.')
            for interval in result.coincident_ratio_intervals:
                st.warning('Infinitely many speed solutions exist over a coincident ratio interval. No single speed is selected.')
                upper='unbounded' if interval.maximum_ratio==float('inf') else f'{interval.maximum_ratio:.12g}'
                st.text(f'Coincident Speed-Ratio Interval: {interval.minimum_ratio:.12g} to {upper}')
            for index,solution in enumerate(result.solutions,1):
                st.markdown(f'**Required Speed Solution {index}**')
                st.text(f'Required Speed: {solution.required_speed_rpm:.12g} rpm\nSpeed Ratio: {solution.ratio:.12g}\nSpeed Change: {solution.speed_change_percent:+.12g}%\nVerified Operating Flow: {_shown(solution.verified_flow_m3_s,ff):.12g} {fu}\nVerified Operating Head: {_shown(solution.verified_head_m,hf):.12g} {hu}\nFlow Residual: {_shown(solution.flow_residual_m3_s,ff):+.12g} {fu}\nHead Residual at Target: {_shown(solution.head_residual_m,hf):+.12g} {hu}')
                if len(solution.verification.points)>1:st.warning('Phase 3G found multiple operating intersections at this speed. The target-matching point is identified only for verification; all intersections are retained.')
                for j,p in enumerate(solution.verification.points,1):st.text(f'Solution {index} — Phase 3G Intersection {j}\nOperating Flow: {_shown(p.flow_m3_s,ff):.12g} {fu}\nOperating Head: {_shown(p.head_m,hf):.12g} {hu}')
                for interval in solution.verification.coincident_intervals:st.text(f'Solution {index} — Phase 3G Coincident Flow Interval: {_shown(interval.minimum_flow_m3_s,ff):.12g} to {_shown(interval.maximum_flow_m3_s,ff):.12g} {fu}')
                try:
                    status=compare_speed_limits(solution.required_speed_rpm,minimum,maximum)
                    if status:
                        st.text(f'Entered Minimum Speed: {"not entered" if minimum is None else str(minimum)+" rpm"}\nEntered Maximum Speed: {"not entered" if maximum is None else str(maximum)+" rpm"}\nSpeed Limit Status: {status}')
                except ValueError as exc:st.error('Entered speed limits: '+str(exc))
                if bep is not None:
                    try:
                        b=curve_flow_to_si(bep,bu,flow_factors);compare_bep(q,b)
                        scaled=calculate_speed_affinity(b,0,0,speed,solution.required_speed_rpm).estimated_flow_m3_s
                        st.text(f'Affinity-Law Scaled BEP Flow: {_shown(scaled,ff):.12g} {fu}\nTarget / Scaled BEP Flow: {compare_bep(q,scaled).percent_bep:.12g}%')
                        st.caption('Theoretical corresponding BEP-flow estimate only; not manufacturer-certified BEP at the solved speed.')
                    except (ValueError,OverflowError) as exc:st.error('BEP context: '+str(exc))
                if power is not None:
                    try:
                        watts=power_to_watts(power,pu,'Reference corresponding-point shaft power',allow_zero=True)
                        scaled=calculate_speed_affinity(0,0,watts,speed,solution.required_speed_rpm).estimated_power_w
                        st.text(f'Affinity-Law Scaled Power: {_shown(scaled,POWER_FACTORS[pu]):.12g} {pu}')
                    except (ValueError,OverflowError) as exc:st.error('Corresponding-point power: '+str(exc))
                st.vega_lite_chart(spec=target_speed_plot_spec(curve,result,solution,model,ff,fu,hu),width='stretch')
            st.caption('Each solution plot shows the reference curve, required-speed curve, unchanged system and all isolated Phase 3G intersections. Pump curves stop at their respective valid flow endpoints.')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.caption(text)
