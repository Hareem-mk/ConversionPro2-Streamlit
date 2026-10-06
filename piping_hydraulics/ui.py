"""Stage 2A interface; later stages are intentionally absent."""
from .pipe_geometry import required_internal_diameter
from .units import flow_to_si


def render_pipe_sizing(flow_factors):
    import streamlit as st
    st.subheader('Stage 2A — Pipe Sizing')
    st.latex(r'D=\sqrt{\frac{4Q}{\pi V}}')
    st.write('Calculate the required INTERNAL diameter for a circular pipe flowing full. '
             'Q is actual volumetric flow at operating conditions; V is the target mean velocity.')
    st.caption('SI internally: Q in m³/s, V in m/s, D in m. Flow and velocity must both be greater than zero. '
               'Steady, single-phase, incompressible liquid sizing; not a pressure-loss or mechanical-design check.')
    st.info('No nominal pipe size or schedule is selected. Confirm the actual internal diameter separately.')
    # Results disappear on input changes so a previous answer is not mistaken for current inputs.
    q = st.number_input('Flow rate', value=None, min_value=0.0, format='%.10g', key='p2a_flow')
    unit = st.selectbox('Flow-rate unit', list(flow_factors), index=None,
                       placeholder='Select flow unit', key='p2a_flow_unit')
    v = st.number_input('Target velocity (m/s)', value=None, min_value=0.0,
                        format='%.10g', key='p2a_velocity')
    if st.button('Calculate required internal diameter', key='p2a_calculate'):
        try:
            flow = flow_to_si(q, unit, flow_factors)
            result = required_internal_diameter(flow, v)
            st.caption(f'Input basis: Q = {flow:.12g} m³/s; target V = {v:.12g} m/s.')
            st.text(f'Required INTERNAL diameter\n{result.diameter_m:.12g} m\n'
                    f'{result.diameter_mm:.12g} mm\n{result.diameter_inches:.12g} inches')
        except ValueError as exc:
            st.error(str(exc))
