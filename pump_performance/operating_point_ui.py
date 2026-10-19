"""Phase 3G explicit inputs and combined plot; no hidden transfers or selection."""
from .pump_curve import create_pump_curve, HEAD_FACTORS, RISING_HEAD_WARNING
from .system_curve import model_from_k, model_from_reference, head_from_metres
from .system_curve_ui import METHODS, MODEL_GUIDANCE
from .operating_point import find_operating_points, NO_INTERSECTION, MULTIPLE_INTERSECTIONS


def operating_plot_spec(curve, model, result):
    flow_factor = curve.flow_factor
    pump_rows = [{'flow': p.flow_m3_s / flow_factor, 'head': head_from_metres(p.head_m, curve.head_unit),
                  'series': 'Pump Curve'} for p in curve.points]
    minimum, maximum = curve.points[0].flow_m3_s, curve.points[-1].flow_m3_s
    system_rows = []
    for index in range(81):
        q = minimum + (maximum - minimum) * (index / 80)
        head = model.at_flow(q).total_head_m
        system_rows.append({'flow': q / flow_factor, 'head': head_from_metres(head, curve.head_unit),
                            'series': 'System Curve'})
    root_rows = [{'flow': p.flow_m3_s / flow_factor, 'head': head_from_metres(p.head_m, curve.head_unit),
                 'series': 'Operating Point'} for p in result.points]
    layers = [
        {'data': {'values': pump_rows}, 'mark': {'type': 'line', 'point': {'filled': True, 'size': 40}}},
        {'data': {'values': system_rows}, 'mark': {'type': 'line', 'strokeDash': [6, 4]}},
    ]
    if root_rows:
        layers.append({'data': {'values': root_rows},
                       'mark': {'type': 'point', 'shape': 'diamond', 'filled': True, 'size': 180}})
    return {
        'title': 'Pump and System Curves', 'layer': layers,
        'encoding': {
            'x': {'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({curve.flow_unit})',
                  'scale': {'zero': False}},
            'y': {'field': 'head', 'type': 'quantitative', 'title': f'Head ({curve.head_unit})'},
            'color': {'field': 'series', 'type': 'nominal',
                      'scale': {'domain': ['Pump Curve', 'System Curve'] + (['Operating Point'] if root_rows else []),
                                'range': ['#4e9de0', '#76bb85'] + (['#ed9238'] if root_rows else [])},
                      'legend': {'title': None, 'orient': 'bottom'}},
            'tooltip': [{'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({curve.flow_unit})'},
                        {'field': 'head', 'type': 'quantitative', 'title': f'Head ({curve.head_unit})'},
                        {'field': 'series', 'type': 'nominal', 'title': 'Series'}],
        },
        'height': 360, 'config': {'view': {'stroke': None}},
    }


def render_operating_point(flow_factors):
    import streamlit as st
    st.subheader('3G — Pump/System Operating Point')
    st.write('The operating point is the flow and head where the pump curve intersects the system curve.')
    st.info('The operating point is determined by the intersection of the supplied pump curve and calculated system curve.')
    st.caption('Operating point calculation uses only the supplied pump-curve range. No pump-curve extrapolation is performed. '
               'Use vendor/manufacturer pump data for the applicable speed and impeller diameter.')
    flow_unit = st.selectbox('Operating-Point Flow Unit', list(flow_factors), index=None,
                             placeholder='Select flow unit', key='p3g_flow_unit')
    head_unit = st.selectbox('Operating-Point Head Unit', list(HEAD_FACTORS), index=None,
                             placeholder='Select head unit', key='p3g_head_unit')
    st.caption('Selected units apply to all inputs and displayed curves/results, except direct K which is always SI. '
               'Changing units reinterprets entered numbers; it does not rewrite them. No other module data are transferred automatically.')
    st.markdown('**Pump Curve Data**')
    st.caption('Enter manufacturer/vendor Q–H data only. Minimum 3 unique points, sorted automatically. '
               'Do not mix speeds or impeller diameters. No default pump curve is loaded.')
    count = st.number_input('Number of Pump Q–H Points', min_value=3, max_value=20, value=3, step=1, key='p3g_count')
    points = []
    for index in range(count):
        left, right = st.columns(2)
        with left:
            q = st.number_input(f'Pump Point {index + 1} — Flow ({flow_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3g_q_{index}')
        with right:
            h = st.number_input(f'Pump Point {index + 1} — Head ({head_unit or "select unit above"})',
                                value=None, format='%.12g', key=f'p3g_h_{index}')
        points.append((q, h))
    st.markdown('**System Curve Definition**')
    method = st.selectbox('Operating-Point System Method', METHODS, key='p3g_method')
    static = st.number_input(f'System Static Head ({head_unit or "select unit above"})', value=None,
                             format='%.12g', key='p3g_static')
    if method == METHODS[0]:
        reference = st.number_input(f'System Reference Flow ({flow_unit or "select unit above"})',
                                    value=None, format='%.12g', key='p3g_reference_flow')
        friction = st.number_input(f'System Reference Friction Head ({head_unit or "select unit above"})',
                                   value=None, format='%.12g', key='p3g_reference_friction')
    else:
        k = st.number_input('Operating-Point System K [for Q in m³/s] (s²/m⁵)',
                             value=None, format='%.12g', key='p3g_k')
    st.caption(MODEL_GUIDANCE)
    st.caption('Enter reviewed static and friction components without double-counting. '
               'A Phase 2F friction loss may be entered manually at its corresponding reference flow.')
    if st.button('Calculate Operating Point', key='p3g_calculate'):
        try:
            curve = create_pump_curve(points, flow_unit, head_unit, flow_factors)
            if method == METHODS[0]:
                model = model_from_reference(static_head=static, head_unit=head_unit, reference_flow=reference,
                                             reference_friction_head=friction, flow_unit=flow_unit, flow_factors=flow_factors)
            else:
                model = model_from_k(static, head_unit, k)
            result = find_operating_points(curve, model)
            st.markdown('**Combined Pump/System Plot**')
            st.vega_lite_chart(spec=operating_plot_spec(curve, model, result), width='stretch')
            st.caption('Pump Curve: solid line and supplied markers. System Curve: dashed line. '
                       'Operating Point: orange diamond; all isolated intersections are marked.')
            if curve.has_rising_head:
                st.warning(RISING_HEAD_WARNING)
            st.markdown('**Operating Point Result**')
            if result.coincident_intervals:
                st.warning('Pump and system curves coincide over a flow interval; infinitely many intersections exist there. '
                           'No unique operating point is selected.')
                for interval in result.coincident_intervals:
                    st.text(f'Coincident Flow Interval: {interval.minimum_flow_m3_s / curve.flow_factor:.12g} to '
                            f'{interval.maximum_flow_m3_s / curve.flow_factor:.12g} {flow_unit}\n'
                            f'Head: {head_from_metres(interval.head_m, head_unit):.12g} {head_unit}')
            if len(result.points) > 1:
                st.warning(MULTIPLE_INTERSECTIONS)
                st.caption('All intersections are listed in ascending flow. Stability or preferred operation is not determined.')
            elif not result.points and not result.coincident_intervals:
                st.info(NO_INTERSECTION)
            for index, point in enumerate(result.points, 1):
                prefix = f'Intersection {index}\n' if len(result.points) > 1 else ''
                factor = HEAD_FACTORS[head_unit]
                st.text(prefix + f'Operating Flow: {point.flow_m3_s / curve.flow_factor:.6g} {flow_unit}\n'
                        f'Operating Head: {head_from_metres(point.head_m, head_unit):.6g} {head_unit}\n'
                        f'Pump Head at Operating Point: {head_from_metres(point.pump_head_m, head_unit):.12g} {head_unit}\n'
                        f'System Head at Operating Point: {head_from_metres(point.system_head_m, head_unit):.12g} {head_unit}\n'
                        f'Head Difference (pump − system): {point.residual_m / factor:.6g} {head_unit}')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Residual check in SI: |pump head − system head| ≤ 1e-9 m + 1e-10 × max(|pump head|, |system head|). '
               'Duplicate-root flow tolerance: 1e-14 m³/s + 1e-12 × maximum supplied SI flow.')
    st.caption('The calculated operating point does not by itself establish acceptable pump operation. '
               'BEP and preferred operating range will be handled separately.')
