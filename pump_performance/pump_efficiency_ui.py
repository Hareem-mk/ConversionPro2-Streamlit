"""Phase 3D independent-input interface consistent with Phase 3A–3C."""
from .shaft_power import POWER_FACTORS
from .pump_efficiency import calculate_pump_efficiency, pump_efficiency_from_conditions

METHODS = ('From Hydraulic Power and Shaft Power', 'From Flow, Head, Density and Shaft Power')


def render_pump_efficiency(flow_factors, density_factors):
    import streamlit as st
    st.subheader('3D — Pump Efficiency')
    st.write('Pump efficiency compares the hydraulic power delivered to the fluid with the mechanical power supplied at the pump shaft.')
    st.info('Pump efficiency is the ratio of hydraulic power delivered to the fluid to the mechanical power supplied at the pump shaft.')
    st.latex(r'\eta_p=\frac{P_h}{P_{shaft}},\qquad\eta_p(\%)=\frac{P_h}{P_{shaft}}\times100')
    method = st.selectbox('Calculation Method', METHODS, key='p3d_method')
    inputs = {}
    if method == METHODS[0]:
        inputs['hydraulic_unit'] = st.selectbox('Hydraulic Power Unit', list(POWER_FACTORS),
                                                index=None, placeholder='Select power unit', key='p3d_hydraulic_unit')
        unit = inputs['hydraulic_unit']
        label = f'Hydraulic Power ({unit})' if unit else 'Hydraulic Power (select unit above)'
        inputs['hydraulic_value'] = st.number_input(label, value=None, min_value=0.0,
                                                    format='%.10g', key='p3d_hydraulic')
    else:
        inputs['density_unit'] = st.selectbox('Fluid Density Unit', list(density_factors), index=None,
                                              placeholder='Select density unit', key='p3d_density_unit')
        unit = inputs['density_unit']
        label = f'Fluid Density ({unit})' if unit else 'Fluid Density (select unit above)'
        inputs['density'] = st.number_input(label, value=None, min_value=0.0,
                                            format='%.10g', key='p3d_density')
        inputs['flow_unit'] = st.selectbox('Volumetric Flow Unit', list(flow_factors), index=None,
                                           placeholder='Select flow unit', key='p3d_flow_unit')
        unit = inputs['flow_unit']
        label = f'Volumetric Flow Rate ({unit})' if unit else 'Volumetric Flow Rate (select unit above)'
        inputs['flow'] = st.number_input(label, value=None, min_value=0.0,
                                         format='%.10g', key='p3d_flow')
        inputs['head_m'] = st.number_input('Pump Head (m)', value=None, min_value=0.0,
                                           format='%.10g', key='p3d_head')
        st.caption('Hydraulic power uses the validated Phase 3A calculation. Density must be positive; '
                   'flow and head must be nonnegative. Internally kg/m³, m³/s and m; g = 9.80665 m/s².')
    inputs['shaft_unit'] = st.selectbox('Pump Shaft / Brake Power Unit', list(POWER_FACTORS),
                                        index=None, placeholder='Select power unit', key='p3d_shaft_unit')
    unit = inputs['shaft_unit']
    label = f'Pump Shaft / Brake Power ({unit})' if unit else 'Pump Shaft / Brake Power (select unit above)'
    inputs['shaft_value'] = st.number_input(label, value=None, min_value=0.0,
                                            format='%.10g', key='p3d_shaft')
    st.caption('Shaft power must be greater than zero. Hydraulic power may be zero but cannot exceed shaft power. '
               'Enter reviewed values explicitly; no results are automatically transferred between modules.')
    if st.button('Calculate Pump Efficiency', key='p3d_calculate'):
        try:
            if method == METHODS[0]:
                r = calculate_pump_efficiency(**inputs)
            else:
                r = pump_efficiency_from_conditions(density_factors=density_factors,
                                                     flow_factors=flow_factors, **inputs)
            def power_text(label, watts):
                return (f'{label}\n{watts:.12g} W\n{watts / POWER_FACTORS["kW"]:.12g} kW\n'
                        f'{watts / POWER_FACTORS["Mechanical hp"]:.12g} Mechanical hp')
            st.text(power_text('Hydraulic Power', r.hydraulic_watts) + '\n\n' +
                    power_text('Pump Shaft / Brake Power', r.shaft_watts) + '\n\n' +
                    f'Pump Efficiency: {r.percent:.2f} %\nEfficiency ratio: {r.ratio:.4f}')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Pump efficiency must be between 0% and 100% for a physically valid pump operating condition.')
    st.caption('Pump efficiency is separate from motor efficiency. Motor efficiency is handled independently in Phase 3C.')
