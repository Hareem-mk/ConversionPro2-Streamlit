"""Phase 3C explicit-input interface, consistent with Phase 3A and Phase 3B."""
from .shaft_power import POWER_FACTORS
from .motor_power import motor_power, motor_power_from_conditions

METHODS = ('From Pump Shaft Power', 'From Hydraulic Conditions')


def render_motor_power(flow_factors, density_factors):
    import streamlit as st
    st.subheader('3C — Motor Input Power')
    st.info('Motor input power is the power supplied to the motor. '
            'It is higher than pump shaft power because the motor has efficiency losses.')
    st.latex(r'P_{motor,input}=\frac{P_{shaft}}{\eta_m}')
    method = st.selectbox('Calculation Method', METHODS, key='p3c_method')
    inputs = {}
    if method == METHODS[0]:
        inputs['power_unit'] = st.selectbox('Pump Shaft / Brake Power Unit', list(POWER_FACTORS),
                                            index=None, placeholder='Select power unit', key='p3c_power_unit')
        unit = inputs['power_unit']
        label = f'Pump Shaft / Brake Power ({unit})' if unit else 'Pump Shaft / Brake Power (select unit above)'
        inputs['shaft_value'] = st.number_input(label, value=None, min_value=0.0,
                                                format='%.10g', key='p3c_power')
        st.caption('Enter reviewed shaft power explicitly; Phase 3B provides pump shaft / brake power. '
                   'No result is automatically transferred between modules.')
    else:
        inputs['density_unit'] = st.selectbox('Fluid Density Unit', list(density_factors), index=None,
                                              placeholder='Select density unit', key='p3c_density_unit')
        unit = inputs['density_unit']
        label = f'Fluid Density ({unit})' if unit else 'Fluid Density (select unit above)'
        inputs['density'] = st.number_input(label, value=None, min_value=0.0,
                                            format='%.10g', key='p3c_density')
        inputs['flow_unit'] = st.selectbox('Volumetric Flow Unit', list(flow_factors), index=None,
                                           placeholder='Select flow unit', key='p3c_flow_unit')
        unit = inputs['flow_unit']
        label = f'Volumetric Flow Rate ({unit})' if unit else 'Volumetric Flow Rate (select unit above)'
        inputs['flow'] = st.number_input(label, value=None, min_value=0.0,
                                         format='%.10g', key='p3c_flow')
        inputs['head_m'] = st.number_input('Pump Head (m)', value=None, min_value=0.0,
                                           format='%.10g', key='p3c_head')
        inputs['pump_efficiency_percent'] = st.number_input('Pump Efficiency (%)', value=None,
                                                             min_value=0.0, format='%.10g', key='p3c_pump_efficiency')
        st.caption('Uses the validated Phase 3A and Phase 3B calculations. Density must be positive; '
                   'flow and head must be nonnegative. Internally kg/m³, m³/s and m; g = 9.80665 m/s².')
    efficiency = st.number_input('Motor Efficiency (%)', value=None, min_value=0.0,
                                 format='%.10g', key='p3c_motor_efficiency')
    st.caption('Enter efficiency as a percent, for example 90 for 90%. Each efficiency must be greater '
               'than 0% and no more than 100%. No default efficiency is assumed.')
    if st.button('Calculate Motor Input Power', key='p3c_calculate'):
        try:
            if method == METHODS[0]:
                r = motor_power(motor_efficiency_percent=efficiency, **inputs)
            else:
                r = motor_power_from_conditions(motor_efficiency_percent=efficiency,
                                                 density_factors=density_factors,
                                                 flow_factors=flow_factors, **inputs)
            def power_text(label, watts):
                return (f'{label}\n{watts:.12g} W\n{watts / POWER_FACTORS["kW"]:.12g} kW\n'
                        f'{watts / POWER_FACTORS["Mechanical hp"]:.12g} Mechanical hp')
            parts = []
            if r.hydraulic_watts is not None:
                parts.extend([power_text('Hydraulic Power', r.hydraulic_watts),
                              f'Pump Efficiency: {r.pump_efficiency_percent:.12g}%'])
            parts.extend([power_text('Pump Shaft / Brake Power', r.shaft_watts),
                          f'Motor Efficiency: {r.motor_efficiency_percent:.12g}%',
                          power_text('Motor Input Power', r.input_watts)])
            st.text('\n\n'.join(parts))
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Motor input power alone does not determine electrical current or motor selection. '
               'This module does not calculate voltage, power factor or equipment sizing.')
