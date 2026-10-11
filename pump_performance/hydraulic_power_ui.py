"""Phase 3A interface using the existing explicit-input calculation pattern."""
from .hydraulic_power import hydraulic_power


def render_hydraulic_power(flow_factors, density_factors):
    import streamlit as st
    st.subheader('3A — Hydraulic Power')
    st.write('Hydraulic power is the useful power transferred to the fluid by the pump.')
    st.info('Hydraulic power is the useful power transferred to the fluid. '
            'It does not include pump or motor efficiency losses.')
    st.latex(r'P_h=\rho\,g\,Q\,H')
    st.caption('SI internally: density in kg/m³, flow in m³/s, head in m; g = 9.80665 m/s². '
               'Density must be positive; flow and pump head may be zero and must be nonnegative.')
    density_unit = st.selectbox('Fluid Density Unit', list(density_factors),
                               index=None, placeholder='Select density unit', key='p3a_density_unit')
    density_label = f'Fluid Density ({density_unit})' if density_unit else 'Fluid Density (select unit above)'
    density = st.number_input(density_label, value=None, min_value=0.0,
                              format='%.10g', key='p3a_density')
    flow_unit = st.selectbox('Volumetric Flow Unit', list(flow_factors),
                            index=None, placeholder='Select flow unit', key='p3a_flow_unit')
    flow_label = f'Volumetric Flow Rate ({flow_unit})' if flow_unit else 'Volumetric Flow Rate (select unit above)'
    flow = st.number_input(flow_label, value=None, min_value=0.0,
                           format='%.10g', key='p3a_flow')
    head = st.number_input('Pump Head (m)', value=None, min_value=0.0,
                           format='%.10g', key='p3a_head')
    # Results are transient, as in Phase 2, so changed inputs clear stale answers.
    if st.button('Calculate Hydraulic Power', key='p3a_calculate'):
        try:
            r = hydraulic_power(density=density, density_unit=density_unit,
                                flow=flow, flow_unit=flow_unit, head_m=head,
                                density_factors=density_factors, flow_factors=flow_factors)
            st.caption(f'Input basis: density = {r.density_kg_m3:.12g} kg/m³; '
                       f'flow = {r.flow_m3_s:.12g} m³/s; head = {r.head_m:.12g} m.')
            st.text(f'Hydraulic Power\n{r.watts:.12g} W\n{r.kilowatts:.12g} kW\n'
                    f'{r.mechanical_hp:.12g} Mechanical hp')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Pump shaft power will be higher than hydraulic power because real pumps have efficiency losses. '
               'Shaft/brake power will be handled separately in Phase 3B.')
