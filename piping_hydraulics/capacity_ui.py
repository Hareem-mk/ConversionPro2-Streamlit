"""Stage 2B interface, separate from the approved Stage 2A interface."""
from .pipe_capacity import pipe_capacity, capacity_flow_outputs


def render_pipe_capacity(flow_factors):
    import streamlit as st
    st.divider()
    st.subheader('Stage 2B — Pipe Capacity / Flow')
    st.latex(r'A=\frac{\pi D^2}{4},\qquad Q=AV')
    st.write('Enter INTERNAL pipe diameter in metres and mean velocity in m/s. '
             'Diameter must be positive; zero velocity is allowed and gives zero flow.')
    st.caption('Full circular pipe, steady single-phase incompressible liquid flow. '
               'This calculates flow at the supplied velocity, not maximum allowable pipe capacity. '
               'No nominal pipe size or schedule is selected.')
    d = st.number_input('INTERNAL pipe diameter (m)', value=None, min_value=0.0,
                        format='%.10g', key='p2b_diameter')
    v = st.number_input('Velocity (m/s)', value=None, min_value=0.0,
                        format='%.10g', key='p2b_velocity')
    if st.button('Calculate pipe capacity / flow', key='p2b_calculate'):
        try:
            result = pipe_capacity(d, v)
            flows = capacity_flow_outputs(result.flow_m3_s, flow_factors)
            st.text(f'Cross-sectional area: {result.area_m2:.12g} m²\n'
                    f'Velocity: {result.velocity_m_s:.12g} m/s\n'
                    + '\n'.join(f'Flow: {q:.12g} {unit}' for unit, q in flows.items()))
        except ValueError as exc:
            st.error(str(exc))
