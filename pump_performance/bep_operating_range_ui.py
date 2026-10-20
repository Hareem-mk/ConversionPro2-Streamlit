"""Explicit vendor BEP inputs; manual or shared Phase 3G operating-point kernel."""
from piping_hydraulics.pipe_geometry import positive

from .pump_curve import create_pump_curve, HEAD_FACTORS, curve_flow_to_si, RISING_HEAD_WARNING
from .system_curve import model_from_k, model_from_reference
from .system_curve_ui import METHODS, MODEL_GUIDANCE
from .operating_point import find_operating_points, NO_INTERSECTION, MULTIPLE_INTERSECTIONS
from .bep_operating_range import compare_bep, validate_user_range, classify_user_range

BEP_METHODS = ('Manual Operating Flow', 'From Phase 3G Operating Point')


def _system_inputs(st, flow_unit, head_unit):
    st.markdown('**Pump Curve Data**')
    st.caption('Enter manufacturer/vendor Q–H data only. Minimum 3 unique points, sorted automatically. '
               'Do not mix speeds or impeller diameters. No default pump curve is loaded.')
    count = st.number_input('Number of Pump Q–H Points', min_value=3, max_value=20, value=3, step=1, key='p3h_count')
    points = []
    for index in range(count):
        left, right = st.columns(2)
        with left:
            q = st.number_input(f'Pump Point {index + 1} — Flow ({flow_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3h_q_{index}')
        with right:
            h = st.number_input(f'Pump Point {index + 1} — Head ({head_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3h_h_{index}')
        points.append((q, h))
    st.markdown('**System Curve Definition**')
    method = st.selectbox('BEP System Method', METHODS, key='p3h_method')
    static = st.number_input(f'System Static Head ({head_unit or "select unit above"})', value=None,
                             format='%.12g', key='p3h_static')
    if method == METHODS[0]:
        reference = st.number_input(f'System Reference Flow ({flow_unit or "select unit above"})',
                                    value=None, format='%.12g', key='p3h_reference_flow')
        friction = st.number_input(f'System Reference Friction Head ({head_unit or "select unit above"})',
                                   value=None, format='%.12g', key='p3h_reference_friction')
    else:
        k = st.number_input('BEP System K [for Q in m³/s] (s²/m⁵)',
                             value=None, format='%.12g', key='p3h_k')
    st.caption(MODEL_GUIDANCE)
    st.caption('Enter reviewed static and friction components without double-counting. '
               'A Phase 2F friction loss may be entered manually at its corresponding reference flow.')
    return points, method, static, (reference, friction) if method == METHODS[0] else k


def render_bep_operating_range(flow_factors):
    import streamlit as st
    st.subheader('3H — BEP / Operating Range')
    st.write('BEP is the Best Efficiency Point specified by the pump manufacturer. This module compares the operating flow with the vendor-supplied BEP flow.')
    st.info('Enter the BEP flow from the applicable manufacturer/vendor performance curve for the selected pump speed and impeller diameter.')
    st.caption('ConversionPro does not estimate or generate BEP automatically.')
    method = st.selectbox('BEP Calculation Method', BEP_METHODS, key='p3h_method_main')
    flow_unit = st.selectbox('Operating Flow Unit', list(flow_factors), index=None,
                             placeholder='Select flow unit', key='p3h_flow_unit')
    st.caption('Changing a unit reinterprets entered numbers; it does not convert them automatically. No data are transferred from other module forms.')
    if method == BEP_METHODS[0]:
        operating = st.number_input(f'Operating Flow ({flow_unit or "select unit above"})', value=None,
                                     format='%.12g', key='p3h_operating')
    else:
        st.caption('Calculate operating flow here using the unchanged Phase 3G intersection kernel and independently entered pump/system data. All isolated intersections are compared; none is selected as preferred. No pump-curve extrapolation is performed.')
        head_unit = st.selectbox('BEP Pump/System Head Unit', list(HEAD_FACTORS), index=None,
                                 placeholder='Select head unit', key='p3h_head_unit')
        points, system_method, static, system_inputs = _system_inputs(st, flow_unit, head_unit)
    st.markdown('**Vendor BEP Flow**')
    bep_unit = st.selectbox('Vendor BEP Flow Unit', list(flow_factors), index=None,
                            placeholder='Select flow unit', key='p3h_bep_unit')
    bep = st.number_input(f'Vendor BEP Flow ({bep_unit or "select unit above"})', value=None,
                          format='%.12g', key='p3h_bep')
    st.markdown('**Optional User/Vendor Defined Operating Range**')
    st.caption('Acceptable operating range depends on pump design and manufacturer guidance. Enter vendor/project limits if available. Leave both limits blank to report the BEP comparison only.')
    minimum = st.number_input('Minimum Recommended Flow (% of BEP)', value=None,
                              format='%.12g', key='p3h_minimum')
    maximum = st.number_input('Maximum Recommended Flow (% of BEP)', value=None,
                              format='%.12g', key='p3h_maximum')
    if st.button('Calculate BEP Comparison', key='p3h_calculate'):
        try:
            # Validate BEP before any ratio division, and the complete optional pair.
            positive(bep, 'Vendor BEP Flow')
            bep_si = curve_flow_to_si(bep, bep_unit, flow_factors)
            limits = None
            if minimum is not None or maximum is not None:
                limits = validate_user_range(minimum, maximum)
            if method == BEP_METHODS[0]:
                flows = [curve_flow_to_si(operating, flow_unit, flow_factors)]
            else:
                curve = create_pump_curve(points, flow_unit, head_unit, flow_factors)
                if system_method == METHODS[0]:
                    reference, friction = system_inputs
                    model = model_from_reference(static_head=static, head_unit=head_unit, reference_flow=reference,
                                                 reference_friction_head=friction, flow_unit=flow_unit, flow_factors=flow_factors)
                else:
                    model = model_from_k(static, head_unit, system_inputs)
                roots = find_operating_points(curve, model)
                if curve.has_rising_head:
                    st.warning(RISING_HEAD_WARNING)
                if roots.coincident_intervals:
                    st.warning('Pump and system curves coincide over a flow interval; no unique operating flow exists there. Use Manual Operating Flow to compare an explicitly chosen flow. Isolated intersections, if present, are compared below.')
                if len(roots.points) > 1:
                    st.warning(MULTIPLE_INTERSECTIONS)
                    st.caption('Each isolated intersection is compared separately. No stability or preferred-operation decision is made.')
                if not roots.points and not roots.coincident_intervals:
                    st.info(NO_INTERSECTION)
                flows = [point.flow_m3_s for point in roots.points]
            # Compute all results before displaying any partial result.
            comparisons = [compare_bep(flow, bep_si) for flow in flows]
            if comparisons:
                st.markdown('**BEP Comparison**')
                st.caption(f'Flow deviation is displayed in the selected Operating Flow Unit ({flow_unit}).')
            for index, result in enumerate(comparisons, 1):
                prefix = f'Intersection {index}\n' if len(comparisons) > 1 else ''
                st.text(prefix + f'Operating Flow: {result.operating_flow_m3_s / flow_factors[flow_unit]:.6g} {flow_unit}\n'
                        f'Vendor BEP Flow: {bep:.6g} {bep_unit}\n'
                        f'Percent of BEP: {result.percent_bep:.6g}%\n'
                        f'Flow Deviation from BEP: {result.deviation_m3_s / flow_factors[flow_unit]:+.6g} {flow_unit}\n'
                        f'Percent Deviation from BEP: {result.percent_deviation:+.6g}%')
                if limits:
                    st.text('Operating Range Status — User/Vendor Defined Operating Range: '
                            + classify_user_range(result.percent_bep, *limits))
        except ValueError as exc:
            st.error(str(exc))
    st.caption('BEP data must come from the applicable manufacturer/vendor pump performance curve. '
               'Use BEP data corresponding to the same pump speed and impeller diameter as the operating-point calculation.')
    st.caption('Operating at or near BEP is generally associated with favorable hydraulic performance, but acceptable operating limits are pump-specific. '
               'Do not infer acceptable range from Percent of BEP alone without vendor/project criteria.')
