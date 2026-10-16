"""Phase 3F interface: independent inputs and a quadratic approximation."""
from .pump_curve import HEAD_FACTORS, curve_flow_to_si
from .system_curve import model_from_k, model_from_reference, generate_system_curve, head_from_metres

METHODS = ('From Reference Flow and Friction Head', 'From System Resistance Coefficient K')
MODEL_GUIDANCE = ('The quadratic system curve H = H_static + KQ² is appropriate when system resistance '
                  'is dominated by flow-dependent losses that vary approximately with velocity squared. '
                  'It is not a substitute for a full hydraulic model when friction factor, fluid properties, '
                  'control-valve behavior or operating configuration change materially with flow.')


def system_plot_spec(samples, flow_factor, flow_unit, head_unit):
    rows = []
    for sample in samples:
        for label, head in [('System Total Head', sample.total_head_m), ('Static Head', sample.static_head_m)]:
            rows.append({'flow': sample.flow_m3_s / flow_factor,
                         'head': head_from_metres(head, head_unit), 'component': label})
    return {
        'title': 'System Curve',
        'layer': [{'data': {'values': rows}, 'mark': {'type': 'line'}}],
        'encoding': {
            'x': {'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({flow_unit})'},
            'y': {'field': 'head', 'type': 'quantitative', 'title': f'System Head ({head_unit})'},
            'color': {'field': 'component', 'type': 'nominal',
                      'scale': {'domain': ['System Total Head', 'Static Head'], 'range': ['#4e9de0', '#e4a340']},
                      'legend': {'title': None, 'orient': 'bottom'}},
            'strokeDash': {'field': 'component', 'type': 'nominal',
                           'scale': {'domain': ['System Total Head', 'Static Head'], 'range': [[1, 0], [6, 4]]},
                           'legend': {'title': None, 'orient': 'bottom'}},
            'order': {'field': 'flow', 'type': 'quantitative'},
            'tooltip': [{'field': 'flow', 'type': 'quantitative', 'title': f'Flow Rate ({flow_unit})'},
                        {'field': 'head', 'type': 'quantitative', 'title': f'System Head ({head_unit})'},
                        {'field': 'component', 'type': 'nominal', 'title': 'Component'}],
        },
        'height': 320,
        'config': {'view': {'stroke': None}},
    }


def render_system_curve(flow_factors):
    import streamlit as st
    st.subheader('3F — System Curve')
    st.write('A system curve shows the total head required by the piping system at different flow rates. '
             'It combines static head with flow-dependent hydraulic losses.')
    st.info(MODEL_GUIDANCE)
    st.latex(r'H_{system}(Q)=H_{static}+K_{SI}Q^2')
    method = st.selectbox('Calculation Method', METHODS, key='p3f_method')
    flow_unit = st.selectbox('System Flow Unit', list(flow_factors), index=None,
                             placeholder='Select flow unit', key='p3f_flow_unit')
    head_unit = st.selectbox('System Head Unit', list(HEAD_FACTORS), index=None,
                             placeholder='Select head unit', key='p3f_head_unit')
    st.caption('Selected units apply to the reference inputs, plot and selected-flow result. '
               'Changing units reinterprets entered numbers; it does not rewrite them. Direct K always uses SI units.')
    static = st.number_input(f'Static Head ({head_unit or "select unit above"})', value=None,
                             format='%.12g', key='p3f_static')
    st.caption('Static head is independent of flow. Variable piping losses are represented here using a quadratic Q² approximation.')
    if method == METHODS[0]:
        reference = st.number_input(f'Reference Flow ({flow_unit or "select unit above"})', value=None,
                                    format='%.12g', key='p3f_reference_flow')
        friction = st.number_input(f'Friction Head at Reference Flow ({head_unit or "select unit above"})',
                                   value=None, format='%.12g', key='p3f_reference_friction')
        st.caption('Reference flow must be greater than zero; reference friction head may be zero. '
                   'Use a reference friction-loss value from a valid hydraulic calculation, such as Phase 2F, when available. '
                   'Manually enter that frictional head loss at its corresponding flow. No data are transferred automatically.')
    else:
        k = st.number_input('System Resistance Coefficient K [for Q in m³/s] (s²/m⁵)', value=None,
                             format='%.12g', key='p3f_k')
        st.caption('Direct K is defined by H_friction(m) = K_SI × Q(m³/s)², regardless of selected display units.')
    st.markdown('**Plot Range**')
    maximum = st.number_input(f'Maximum Flow for Plot ({flow_unit or "select unit above"})', value=None,
                              format='%.12g', key='p3f_maximum')
    plot_requested = st.button('Generate System Curve', key='p3f_plot')
    model, model_error = None, None
    try:
        if method == METHODS[0]:
            model = model_from_reference(static_head=static, head_unit=head_unit, reference_flow=reference,
                                         reference_friction_head=friction, flow_unit=flow_unit, flow_factors=flow_factors)
        else:
            model = model_from_k(static, head_unit, k)
        # Require an explicit valid flow unit even at zero flow and in direct-K mode.
        curve_flow_to_si(0, flow_unit, flow_factors)
    except ValueError as exc:
        model_error = str(exc)
        model = None
    if model is not None:
        st.text(f'Static Head: {model.static_head_m / HEAD_FACTORS[head_unit]:.12g} {head_unit}\n'
                f'System Resistance Coefficient K_SI: {model.k_si:.12g} s²/m⁵\n'
                'K basis: Q in m³/s; friction head in m.')
        try:
            samples = generate_system_curve(model, curve_flow_to_si(maximum, flow_unit, flow_factors))
            st.vega_lite_chart(spec=system_plot_spec(samples, flow_factors[flow_unit],
                                                     flow_unit, head_unit), width='stretch')
            st.caption('System Total Head is the solid line; Static Head is the dashed horizontal reference. '
                       '81 calculated points span zero to the selected maximum flow.')
        except ValueError as exc:
            if plot_requested:
                st.error(str(exc))
    elif plot_requested:
        st.error(model_error)
    st.markdown('**Selected Flow Calculation**')
    selected = st.number_input(f'Flow for System-Head Calculation ({flow_unit or "select unit above"})',
                               value=None, format='%.12g', key='p3f_selected')
    st.caption('The plot maximum limits the displayed range. A selected nonnegative flow is calculated directly '
               'from the same quadratic model, including when it is outside the plotted range.')
    if st.button('Calculate System Head', key='p3f_calculate'):
        if model is None:
            st.error(model_error)
        else:
            try:
                r = model.at_flow(curve_flow_to_si(selected, flow_unit, flow_factors))
                st.text(f'Selected Flow: {r.flow_m3_s / flow_factors[flow_unit]:.12g} {flow_unit}\n'
                        f'Static Head: {head_from_metres(r.static_head_m, head_unit):.12g} {head_unit}\n'
                        f'Friction Head: {head_from_metres(r.friction_head_m, head_unit):.12g} {head_unit}\n'
                        f'Total System Head: {head_from_metres(r.total_head_m, head_unit):.12g} {head_unit}')
            except ValueError as exc:
                st.error(str(exc))
    st.caption('Do not include the same static or friction component twice. '
               'Phase 3F does not yet calculate the intersection with a pump curve.')
