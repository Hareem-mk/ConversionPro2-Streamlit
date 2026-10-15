"""Phase 3E: blank numbered Q–H rows, supplied-point plot, optional interpolation."""
from .pump_curve import create_pump_curve, interpolate_pump_head, HEAD_FACTORS, RISING_HEAD_WARNING


def curve_plot_spec(flow_unit, head_unit, points=()):
    """Vega-Lite connects supplied points only; no fit or generated samples."""
    return {
        'title': 'Pump Q–H Curve',
        'layer': [{'data': {'values': [{'flow': q, 'head': h} for q, h in points]},
                   'mark': {'type': 'line', 'point': {'filled': True, 'size': 70}}}],
        'encoding': {
            'x': {'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({flow_unit})'},
            'y': {'field': 'head', 'type': 'quantitative', 'title': f'Pump Head ({head_unit})'},
            'order': {'field': 'flow', 'type': 'quantitative'},
            'tooltip': [{'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({flow_unit})'},
                        {'field': 'head', 'type': 'quantitative', 'title': f'Pump Head ({head_unit})'}],
        },
        'height': 320,
        'config': {'axis': {'labelLimit': 120, 'titleLimit': 400}, 'view': {'stroke': None}},
    }


def render_pump_curve(flow_factors):
    import streamlit as st
    st.subheader('3E — Pump Curve')
    st.write('A pump Q–H curve shows the head produced by the pump at different flow rates using manufacturer/vendor-supplied performance data.')
    st.info('Enter pump manufacturer/vendor Q–H data. ConversionPro does not generate or assume pump performance data.')
    st.caption('Use vendor/manufacturer pump data for the applicable impeller diameter and pump speed. '
               'Do not mix curve points from different pump speeds or impeller diameters.')
    st.markdown('**Curve Units**')
    flow_unit = st.selectbox('Curve Flow Unit', list(flow_factors), index=None,
                             placeholder='Select flow unit', key='p3e_flow_unit')
    head_unit = st.selectbox('Curve Head Unit', list(HEAD_FACTORS), index=None,
                             placeholder='Select head unit', key='p3e_head_unit')
    st.caption('Selected units apply to all points, the plot and interpolation. '
               'Changing units reinterprets entered numbers; it does not automatically rewrite them. '
               'Head is not pressure or differential pressure.')
    st.markdown('**Pump Curve Data**')
    count = st.number_input('Number of Q–H Points', min_value=3, max_value=20, value=3, step=1, key='p3e_count')
    st.caption('Minimum 3 valid unique Q–H points. Enter data in any order; points are sorted by flow. '
               'All displayed rows must contain flow and head. No default curve is loaded.')
    points = []
    for index in range(count):
        left, right = st.columns(2)
        with left:
            q = st.number_input(f'Point {index + 1} — Flow ({flow_unit or "select unit above"})',
                                value=None, min_value=0.0, format='%.12g', key=f'p3e_q_{index}')
        with right:
            h = st.number_input(f'Point {index + 1} — Head ({head_unit or "select unit above"})',
                                value=None, min_value=0.0, format='%.12g', key=f'p3e_h_{index}')
        points.append((q, h))
    plot_requested = st.button('Plot Pump Curve', key='p3e_plot')
    # Rebuild from current inputs only. Invalid edits remove any previous plot;
    # valid curves stay visible while an interpolation target is entered.
    curve = None
    validation_error = None
    try:
        curve = create_pump_curve(points, flow_unit, head_unit, flow_factors)
    except ValueError as exc:
        validation_error = str(exc)
    if curve is not None:
        rows = curve.display_points()
        # Inline layer values keep the small supplied dataset in Vega-Lite JSON,
        # avoiding unnecessary dataframe/Arrow conversion on each rerun.
        st.vega_lite_chart(spec=curve_plot_spec(flow_unit, head_unit, rows), width='stretch')
        st.caption('Supplied points are marked; straight lines connect adjacent supplied points. '
                   'The plot updates when valid input changes are committed.')
        st.markdown(f'| Flow Rate ({flow_unit}) | Pump Head ({head_unit}) |\n|---:|---:|\n' +
                    '\n'.join(f'| {q:.12g} | {h:.12g} |' for q, h in rows))
        if curve.shutoff_head_m is not None:
            st.text(f'Shutoff / zero-flow head: {curve.shutoff_head_m / curve.head_factor:.12g} {head_unit}')
        if curve.has_rising_head:
            st.warning(RISING_HEAD_WARNING)
    st.markdown('**Interpolation**')
    target = st.number_input(f'Flow for Interpolation ({flow_unit or "select unit above"})', value=None,
                             min_value=0.0, format='%.12g', key='p3e_target')
    interpolate_requested = st.button('Interpolate Pump Head', key='p3e_interpolate')
    if validation_error and (plot_requested or interpolate_requested):
        st.error(validation_error)
    elif interpolate_requested:
        try:
            result = interpolate_pump_head(curve, target)
            q1, h1 = result.lower.flow_m3_s / curve.flow_factor, result.lower.head_m / curve.head_factor
            q2, h2 = result.upper.flow_m3_s / curve.flow_factor, result.upper.head_m / curve.head_factor
            text = (f'Requested Flow: {result.flow_m3_s / curve.flow_factor:.12g} {flow_unit}\n'
                    + (f'Exact Supplied Point: {q1:.12g} {flow_unit} → {h1:.12g} {head_unit}\n'
                       if result.exact_point else
                       f'Bounding Data Points:\n{q1:.12g} {flow_unit} → {h1:.12g} {head_unit}\n'
                       f'{q2:.12g} {flow_unit} → {h2:.12g} {head_unit}\n'))
            label = 'Pump Head (exact supplied point)' if result.exact_point else 'Interpolated Pump Head'
            st.text(text + f'{label}: {result.head_m / curve.head_factor:.12g} {head_unit}')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Interpolation is performed only between supplied data points. '
               'No extrapolation is performed outside the supplied curve range.')
