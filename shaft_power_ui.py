"""Phase 3B interface; explicit independent inputs with no assumed efficiency."""
from .hydraulic_power import MECHANICAL_HP_W
from .shaft_power import POWER_FACTORS, shaft_power, shaft_power_from_conditions


METHODS = ('From Hydraulic Power', 'From Flow, Head and Density')


def render_shaft_power(flow_factors, density_factors):
    import streamlit as st
    st.subheader('3B — Pump Shaft / Brake Power')
    st.write('Pump shaft power is the mechanical power required at the pump shaft after accounting for pump efficiency.')
    st.info('Pump shaft power is the mechanical power required at the pump shaft. '
            'It is higher than hydraulic power because real pumps have efficiency losses.')
    st.caption('Brake power and shaft power refer here to the mechanical power delivered to the pump shaft.')
    st.latex(r'P_{shaft}=\frac{P_h}{\eta_p}')
    method = st.selectbox('Calculation Method', METHODS, key='p3b_method')
    inputs = {}
    if method == METHODS[0]:
        inputs['power_unit'] = st.selectbox('Hydraulic Power Unit', list(POWER_FACTORS), index=None,
                                            placeholder='Select power unit', key='p3b_power_unit')
        unit = inputs['power_unit']
        label = f'Hydraulic Power ({unit})' if unit else 'Hydraulic Power (select unit above)'
        inputs['hydraulic_value'] = st.number_input(label, value=None, min_value=0.0,
                                                    format='%.10g', key='p3b_power')
        st.caption('Enter reviewed hydraulic power explicitly; Phase 3A provides hydraulic power. '
                   'No result is automatically transferred between modules.')
    else:
        inputs['density_unit'] = st.selectbox('Fluid Density Unit', list(density_factors), index=None,
                                              placeholder='Select density unit', key='p3b_density_unit')
        unit = inputs['density_unit']
        label = f'Fluid Density ({unit})' if unit else 'Fluid Density (select unit above)'
        inputs['density'] = st.number_input(label, value=None, min_value=0.0,
                                            format='%.10g', key='p3b_density')
        inputs['flow_unit'] = st.selectbox('Volumetric Flow Unit', list(flow_factors), index=None,
                                           placeholder='Select flow unit', key='p3b_flow_unit')
        unit = inputs['flow_unit']
        label = f'Volumetric Flow Rate ({unit})' if unit else 'Volumetric Flow Rate (select unit above)'
        inputs['flow'] = st.number_input(label, value=None, min_value=0.0,
                                         format='%.10g', key='p3b_flow')
        inputs['head_m'] = st.number_input('Pump Head (m)', value=None, min_value=0.0,
                                           format='%.10g', key='p3b_head')
        st.caption('Hydraulic power uses the validated Phase 3A calculation: density must be positive; '
                   'flow and head must be nonnegative. Internally kg/m³, m³/s and m; g = 9.80665 m/s².')
    efficiency = st.number_input('Pump Efficiency (%)', value=None, min_value=0.0,
                                 format='%.10g', key='p3b_efficiency')
    st.caption('Enter pump efficiency as a percent, for example 80 for 80%. '
               'Required range: greater than 0% and no more than 100%. No default efficiency is assumed.')
    # Like Phase 3A, result output exists only for the current calculation rerun.
    if st.button('Calculate Pump Shaft / Brake Power', key='p3b_calculate'):
        try:
            if method == METHODS[0]:
                r = shaft_power(efficiency_percent=efficiency, **inputs)
            else:
                r = shaft_power_from_conditions(efficiency_percent=efficiency,
                                                flow_factors=flow_factors,
                                                density_factors=density_factors, **inputs)
            st.text(f'Hydraulic Power\n{r.hydraulic_watts:.12g} W\n'
                    f'{r.hydraulic_watts / POWER_FACTORS["kW"]:.12g} kW\n'
                    f'{r.hydraulic_watts / MECHANICAL_HP_W:.12g} Mechanical hp\n\n'
                    f'Pump Efficiency: {r.efficiency_percent:.12g}%\n\n'
                    f'Pump Shaft / Brake Power\n{r.shaft_watts:.12g} W\n'
                    f'{r.shaft_kilowatts:.12g} kW\n{r.shaft_mechanical_hp:.12g} Mechanical hp')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Pump shaft power is not motor electrical input power. '
               'Motor losses will be handled separately in Phase 3C.')
