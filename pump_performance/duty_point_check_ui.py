"""Explicit duty/vendor data and independent criteria; no overall approval."""
import math
from piping_hydraulics.pipe_capacity import nonnegative
from piping_hydraulics.pipe_geometry import positive
from .pump_curve import create_pump_curve, curve_flow_to_si, HEAD_FACTORS, RISING_HEAD_WARNING
from .system_curve import head_to_metres, model_from_reference, model_from_k
from .system_curve_ui import METHODS, MODEL_GUIDANCE
from .shaft_power import POWER_FACTORS
from .operating_point import find_operating_points, NO_INTERSECTION, MULTIPLE_INTERSECTIONS
from .duty_point_check import check_duty_point

CHECK_METHODS = ('Manual Check','Integrated Phase 3G Operating Point')


def _system_inputs(st, flow_unit, head_unit):
    st.markdown('**Pump Curve Data**')
    st.caption('Enter manufacturer/vendor Q–H data only. Minimum 3 unique points, sorted automatically. '
               'Do not mix speeds or impeller diameters. No default pump curve is loaded.')
    count = st.number_input('Number of Pump Q–H Points', min_value=3, max_value=20, value=3, step=1, key='p3k_count')
    points = []
    for index in range(count):
        left, right = st.columns(2)
        with left:
            q = st.number_input(f'Pump Point {index + 1} — Flow ({flow_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3k_q_{index}')
        with right:
            h = st.number_input(f'Pump Point {index + 1} — Head ({head_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3k_h_{index}')
        points.append((q, h))
    st.markdown('**System Curve Definition**')
    method = st.selectbox('Duty System Method', METHODS, key='p3k_method')
    static = st.number_input(f'System Static Head ({head_unit or "select unit above"})', value=None,
                             format='%.12g', key='p3k_static')
    if method == METHODS[0]:
        reference = st.number_input(f'System Reference Flow ({flow_unit or "select unit above"})',
                                    value=None, format='%.12g', key='p3k_reference_flow')
        friction = st.number_input(f'System Reference Friction Head ({head_unit or "select unit above"})',
                                   value=None, format='%.12g', key='p3k_reference_friction')
    else:
        k = st.number_input('Duty System K [for Q in m³/s] (s²/m⁵)',
                             value=None, format='%.12g', key='p3k_k')
    st.caption(MODEL_GUIDANCE)
    st.caption('Enter reviewed static and friction components without double-counting. '
               'A Phase 2F friction loss may be entered manually at its corresponding reference flow.')
    return points, method, static, (reference, friction) if method == METHODS[0] else k


def _unit(st,label,options,key):
    return st.selectbox(label,list(options),index=None,placeholder='Select unit',key=key)


def _value(st,label,key):
    return st.number_input(label,value=None,format='%.12g',key=key)


def _power_to_w(value,unit,label):
    value = nonnegative(value,label)
    if unit not in POWER_FACTORS:raise ValueError('Select a supported power unit: W, kW or Mechanical hp.')
    watts = value * POWER_FACTORS[unit]
    if not math.isfinite(watts) or (value > 0 and watts == 0):raise ValueError(label+' exceeds the supported numeric range.')
    return watts


def _shown(value,factor):
    result=value/factor
    if not math.isfinite(result) or (value != 0 and result == 0):raise ValueError('Displayed duty result exceeds the supported numeric range.')
    return result


def render_duty_point_check(flow_factors):
    import streamlit as st
    st.subheader('3K — Pump Duty Point / Selection Check')
    st.info('Review individual entered criteria below. ConversionPro does not replace manufacturer/vendor pump selection review.')
    method=st.selectbox('Duty Check Calculation Method',CHECK_METHODS,key='p3k_method_main')
    st.markdown('**Required Duty Point**')
    rq_unit=_unit(st,'Required Duty Flow Unit',flow_factors,'p3k_rq_unit')
    rq=_value(st,f'Required Duty Flow ({rq_unit or "select unit above"})','p3k_rq')
    rh_unit=_unit(st,'Required Duty Head Unit',HEAD_FACTORS,'p3k_rh_unit')
    rh=_value(st,f'Required Duty Head ({rh_unit or "select unit above"})','p3k_rh')
    st.markdown('**Pump Operating Point**')
    oq_unit=_unit(st,'Pump Operating Flow Unit',flow_factors,'p3k_oq_unit')
    oh_unit=_unit(st,'Pump Operating Head Unit',HEAD_FACTORS,'p3k_oh_unit')
    if method==CHECK_METHODS[0]:
        oq=_value(st,f'Pump Operating Flow ({oq_unit or "select unit above"})','p3k_oq')
        oh=_value(st,f'Pump Operating Head ({oh_unit or "select unit above"})','p3k_oh')
    else:
        st.caption('Calculate operating points with the unchanged Phase 3G kernel from independently entered vendor Q–H data and system definition. No extrapolation. All isolated intersections are checked separately; none is selected as preferred.')
        points,system_method,static,system_inputs=_system_inputs(st,oq_unit,oh_unit)
    st.markdown('**Vendor / Pump Data**')
    st.caption('BEP and NPSH checks are optional: leave BEP blank to omit it; leave both NPSHA and NPSHR blank to omit NPSH. Missing checks require vendor/project review.')
    b_unit=_unit(st,'Duty Check Vendor BEP Flow Unit',flow_factors,'p3k_bep_unit')
    bep=_value(st,f'Duty Check Vendor BEP Flow ({b_unit or "select unit above"})','p3k_bep')
    a_unit=_unit(st,'Duty Check NPSHA Unit',HEAD_FACTORS,'p3k_a_unit')
    available=_value(st,f'Duty Check Manual NPSHA ({a_unit or "select unit above"})','p3k_available')
    n_unit=_unit(st,'Duty Check Vendor NPSHR Unit',HEAD_FACTORS,'p3k_n_unit')
    required=_value(st,f'Duty Check Vendor NPSHR ({n_unit or "select unit above"})','p3k_required')
    p_unit=_unit(st,'Pump Shaft Power Unit',POWER_FACTORS,'p3k_power_unit')
    shaft=_value(st,f'Pump Shaft Power ({p_unit or "select unit above"})','p3k_shaft')
    d_unit=_unit(st,'Driver Rated Power Unit',POWER_FACTORS,'p3k_driver_unit')
    rating=_value(st,f'Optional Driver/Motor Rated Power ({d_unit or "select unit above"})','p3k_rating')
    st.caption('Enter pump mechanical shaft/brake power and available driver mechanical output rating on a compatible basis. Motor electrical input power is not the driver output rating. Shaft power is manually supplied in both methods; no efficiency or power at an intersection is invented.')
    st.markdown('**Optional Project / Vendor Criteria**')
    ft=_value(st,'Allowed Flow Deviation (%)','p3k_flow_tol')
    ht=_value(st,'Allowed Head Deviation (%)','p3k_head_tol')
    bmin=_value(st,'Minimum Allowed Percent of BEP','p3k_bep_min')
    bmax=_value(st,'Maximum Allowed Percent of BEP','p3k_bep_max')
    nm=_value(st,'Minimum Required NPSH Margin','p3k_npsh_min')
    nm_unit=_unit(st,'Required NPSH Criterion Unit',HEAD_FACTORS,'p3k_npsh_min_unit')
    dm=_value(st,'Minimum Required Driver Power Margin (%)','p3k_driver_min')
    st.caption('All criteria are user/vendor/project supplied and start blank. Duty tolerances and required margins must be nonnegative. BEP limits must both be entered, minimum >0 and maximum > minimum. No generic acceptance limits or required ratio are assumed.')
    st.caption('Input units are independent. Differences use the required-duty flow/head units, driver margin uses the shaft-power unit, and NPSH margin uses the NPSHA unit. Unit changes reinterpret entered numbers; no automatic conversion or cross-module form transfer occurs.')
    if st.button('Check Pump Duty Point',key='p3k_calculate'):
        try:
            required_q=positive(curve_flow_to_si(rq,rq_unit,flow_factors),'Required Duty Flow')
            required_h=positive(head_to_metres(rh,rh_unit,'Required Duty Head'),'Required Duty Head')
            if oq_unit not in flow_factors or oh_unit not in HEAD_FACTORS:
                raise ValueError('Select explicit pump operating flow and head units.')
            shaft_w=_power_to_w(shaft,p_unit,'Pump Shaft Power')
            rating_w=None if rating is None else _power_to_w(rating,d_unit,'Driver Rated Power')
            bep_si=None if bep is None else curve_flow_to_si(bep,b_unit,flow_factors)
            a_m=None if available is None else head_to_metres(available,a_unit,'Manual NPSHA')
            n_m=None if required is None else head_to_metres(required,n_unit,'Vendor NPSHR')
            min_n_m=None if nm is None else head_to_metres(nm,nm_unit,'Required NPSH Margin')
            root_result=None
            if method==CHECK_METHODS[0]:
                operating=[(curve_flow_to_si(oq,oq_unit,flow_factors),head_to_metres(oh,oh_unit,'Pump Operating Head'))]
            else:
                curve=create_pump_curve(points,oq_unit,oh_unit,flow_factors)
                if system_method==METHODS[0]:
                    reference,friction=system_inputs
                    model=model_from_reference(static_head=static,head_unit=oh_unit,reference_flow=reference,
                        reference_friction_head=friction,flow_unit=oq_unit,flow_factors=flow_factors)
                else:model=model_from_k(static,oh_unit,system_inputs)
                root_result=find_operating_points(curve,model)
                operating=[(p.flow_m3_s,p.head_m) for p in root_result.points]
                if curve.has_rising_head:st.warning(RISING_HEAD_WARNING)
            results=[check_duty_point(required_flow_si=required_q,operating_flow_si=q,required_head_m=required_h,
                operating_head_m=h,shaft_power_w=shaft_w,bep_flow_si=bep_si,npsha_m=a_m,npshr_m=n_m,driver_rating_w=rating_w,
                flow_tolerance_percent=ft,head_tolerance_percent=ht,bep_min_percent=bmin,bep_max_percent=bmax,
                required_npsh_margin_m=min_n_m,required_driver_margin_percent=dm) for q,h in operating]
            if root_result is not None:
                if root_result.coincident_intervals:
                    st.warning('Coincident pump/system flow interval: no unique operating point. Use Manual Check for an explicitly chosen point. Isolated intersections are checked below if present.')
                if len(root_result.points)>1:st.warning(MULTIPLE_INTERSECTIONS)
                if not root_result.points and not root_result.coincident_intervals:st.info(NO_INTERSECTION)
            # Preformat all values before displaying so conversion errors cannot
            # leave a partially rendered comparison.
            outputs=[]
            for index,result in enumerate(results,1):
                d=result.duty
                dq=0 if d.flow_matches else _shown(d.flow_difference_m3_s,flow_factors[rq_unit])
                dh=0 if d.head_matches else _shown(d.head_difference_m,HEAD_FACTORS[rh_unit])
                qp=0 if d.flow_matches else d.flow_deviation_percent
                hp=0 if d.head_matches else d.head_deviation_percent
                text=(f'Required Flow: {rq:.6g} {rq_unit}\n'
                    f'Operating Flow: {_shown(d.operating_flow_m3_s,flow_factors[oq_unit]):.6g} {oq_unit}\n'
                    f'Duty Flow Difference: {dq:+.6g} {rq_unit}\nFlow Deviation: {qp:+.6g}%\n'
                    f'Required Head: {rh:.6g} {rh_unit}\n'
                    f'Operating Head: {_shown(d.operating_head_m,HEAD_FACTORS[oh_unit]):.6g} {oh_unit}\n'
                    f'Duty Head Difference: {dh:+.6g} {rh_unit}\nHead Deviation: {hp:+.6g}%\n'
                    f'Pump Shaft Power: {shaft:.6g} {p_unit}')
                rows=[{'Criterion':'Duty Flow','Calculated Result':f'{qp:+.6g}% deviation','Entered Requirement':'No criterion entered' if ft is None else f'±{ft:.6g}%', 'Status':result.flow_tolerance_status or 'No criterion entered'},
                      {'Criterion':'Duty Head','Calculated Result':f'{hp:+.6g}% deviation','Entered Requirement':'No criterion entered' if ht is None else f'±{ht:.6g}%', 'Status':result.head_tolerance_status or 'No criterion entered'}]
                if result.bep:
                    text+=f'\nPercent of BEP: {result.bep.percent_bep:.6g}%'
                else:text+='\nPercent of BEP: N/A — Vendor BEP Flow not entered'
                rows.append({'Criterion':'BEP Range','Calculated Result':'N/A' if not result.bep else f'{result.bep.percent_bep:.6g}% BEP',
                    'Entered Requirement':'No criterion entered' if bmin is None else f'{bmin:.6g}–{bmax:.6g}% BEP',
                    'Status':result.bep_range_status or ('No criterion entered' if result.bep else 'Requires vendor/project review — no BEP data')})
                if result.npsh:
                    text+=(f'\nNPSH Margin: {_shown(result.npsh.margin_m,HEAD_FACTORS[a_unit]):+.6g} {a_unit}'
                           f'\nNPSHA / NPSHR Ratio: {result.npsh.ratio:.6g}\nPercent NPSH Margin: {result.npsh.percent_margin:+.6g}%'
                           f'\nNPSH Relationship: {result.npsh.relationship_status}')
                else:text+='\nNPSH Margin: N/A — NPSHA / Vendor NPSHR not entered\nNPSHA / NPSHR Ratio: N/A'
                rows.append({'Criterion':'NPSH Margin','Calculated Result':'N/A' if not result.npsh else f'{_shown(result.npsh.margin_m,HEAD_FACTORS[a_unit]):+.6g} {a_unit}',
                    'Entered Requirement':'No criterion entered' if nm is None else f'{nm:.6g} {nm_unit}',
                    'Status':result.required_npsh_margin.criterion_status if result.required_npsh_margin else ('No criterion entered' if result.npsh else 'Requires vendor/project review — no NPSH data')})
                if result.driver:
                    driver=result.driver
                    text+=(f'\nDriver Rated Power: {rating:.6g} {d_unit}'
                           f'\nDriver Power Margin: {_shown(driver.margin_w,POWER_FACTORS[p_unit]):+.6g} {p_unit}'
                           f'\nDriver Power Margin %: {"N/A — shaft power is zero" if driver.margin_percent is None else f"{driver.margin_percent:+.6g}%"}'
                           f'\nDriver Relationship: {driver.relationship_status}')
                else:text+='\nDriver Power Margin: N/A — Driver Rated Power not entered\nDriver Power Margin %: N/A'
                rows.append({'Criterion':'Driver Power Margin','Calculated Result':'N/A' if not result.driver or result.driver.margin_percent is None else f'{result.driver.margin_percent:+.6g}%',
                    'Entered Requirement':'No criterion entered' if dm is None else f'≥{dm:.6g}%',
                    'Status':result.driver_criterion_status or ('No criterion entered' if result.driver else 'Requires vendor/project review — no driver rating')})
                outputs.append((index,text,rows))
            if outputs:st.markdown('**Duty Point Check Results**')
            for index,text,rows in outputs:
                if len(outputs)>1:st.markdown(f'**Intersection {index}**')
                st.text(text)
                st.markdown('**Entered Criterion Summary**')
                for row in rows:
                    st.text(f'Criterion: {row["Criterion"]}\n'
                            f'Calculated Result: {row["Calculated Result"]}\n'
                            f'Entered Requirement: {row["Entered Requirement"]}\n'
                            f'Status: {row["Status"]}')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('Pump selection requires comparing the Required Duty Point with manufacturer performance data. The Pump Operating Point is determined by the pump/system curve intersection. This screening does not rank or automatically select pumps.')
    st.caption('BEP must be vendor supplied; acceptable operating ranges depend on manufacturer/project criteria. NPSHR must come from manufacturer/vendor data at the applicable operating flow, speed and impeller diameter. Neither BEP nor NPSHR is estimated.')
    st.caption('Driver sizing criteria are project/vendor specific; no universal motor margin is assumed. Positive NPSH margin alone does not establish complete pump suitability. Pump speed, impeller diameter, efficiency, NPSHR and mechanical limits must correspond to applicable vendor data.')
    st.caption('Final pump selection should be confirmed against the complete manufacturer/vendor performance curve and project specifications. Review missing data and each entered criterion separately; no overall approval result is generated.')
    st.caption('Exact-duty reporting suppresses only numerical roundoff: relative tolerance 1e-12; absolute flow tolerance 1e-15 m³/s and head tolerance 1e-9 m. Core differences retain full precision. Entered duty tolerance boundaries use 1e-9 percentage points absolute / 1e-12 relative numerical comparison tolerance, not an assumed engineering acceptance allowance.')
