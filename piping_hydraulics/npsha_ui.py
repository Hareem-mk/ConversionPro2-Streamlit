"""Stage 2H UI: explicit references, no automatic transfers, no NPSHR prediction."""
from .npsha import flange_npsha, source_npsha, COMPARISON
from .pump_head import pressure_to_pa


def render_npsha(pressure_factors):
    import streamlit as st
    st.divider()
    st.subheader('Stage 2H — NPSH Available (NPSHA)')
    st.caption('Steady-state, single-phase liquid upstream of the evaluated point; incompressible '
               'hydraulics; kinetic-energy correction α = 1; g = 9.80665 m/s². '
               'Use one common elevation datum, positive upward, and absolute pressure for NPSH.')
    st.info('NPSHA is a SYSTEM property. NPSHR is a PUMP/vendor property and is not calculated here. '
            'Vendor NPSHR comparison is deferred. Positive NPSHA alone does not establish adequate NPSH margin. '
            + COMPARISON)
    st.write('Enter vapor pressure for the actual liquid, actual pumping temperature and appropriate '
             'composition. Hydrocarbon mixtures require appropriate process/property data; do not assume '
             'water vapor pressure. No vapor-pressure database or automatic transfer from other modules is used.')
    mode = st.selectbox('NPSHA method', ['SUCTION-FLANGE NPSHA', 'SUCTION-VESSEL / SOURCE NPSHA'],
                        index=None, key='p2h_mode')
    if mode is None:
        return
    source = mode == 'SUCTION-VESSEL / SOURCE NPSHA'
    prefix = 'p2h_source_' if source else 'p2h_flange_'
    if source:
        st.latex(r'NPSHA=\frac{P_{surface,abs}-P_v}{\rho g}+(z_{surface}-z_{datum})+\frac{V_{surface}^2}{2g}-h_{suction,total}')
        st.write('Reference point: vessel liquid surface/source. Enter pressure above the liquid surface '
                 'and losses from that source to the pump reference once. Do not use measured flange '
                 'pressure here and subtract upstream losses again. Enter surface velocity explicitly, '
                 'including zero for a large vessel when justified.')
    else:
        st.latex(r'NPSHA=\frac{P_{s,abs}-P_v}{\rho g}+\frac{V_s^2}{2g}+(z_s-z_{datum})')
        st.write('Reference point: defined pump suction pressure measurement point. Its pressure already '
                 'reflects upstream suction losses; do NOT add or subtract those losses again. '
                 'There are no upstream-loss inputs in this mode. Equal measurement and pump datum '
                 'elevations give zero elevation contribution.')
    basis = st.selectbox('Suction/source pressure basis', ['Absolute', 'Gauge'], index=None, key=prefix+'basis')
    unit = st.selectbox('Suction/source pressure unit', list(pressure_factors), index=None, key=prefix+'unit')
    pressure = st.number_input('Source surface pressure' if source else 'Suction measurement pressure',
                               value=None, key=prefix+'pressure', format='%.12g')
    atm = atm_unit = None
    if basis == 'Gauge':
        st.caption('P_abs = P_gauge + P_atm. Supply local atmospheric ABSOLUTE pressure; no standard-atmosphere default.')
        atm = st.number_input('Local atmospheric pressure — Absolute', value=None, min_value=0.0,
                              key=prefix+'atmosphere', format='%.12g')
        atm_unit = st.selectbox('Atmospheric pressure unit', list(pressure_factors), index=None, key=prefix+'atm_unit')
    st.caption('Absolute suction/source and atmospheric pressures must be strictly positive. Vapor pressure may be zero.')
    pv = st.number_input('Liquid Vapor Pressure — Absolute', value=None, min_value=0.0,
                         key=prefix+'vapor', format='%.12g')
    pv_unit = st.selectbox('Vapor pressure unit', list(pressure_factors), index=None, key=prefix+'vapor_unit')
    fluid_confirmed = st.checkbox('Vapor pressure matches the actual fluid, pumping temperature and composition.', key=prefix+'fluid')
    datum = st.text_input('Common elevation datum — describe it', key=prefix+'datum')
    reference = st.checkbox('Reference point and pump/NPSH datum elevations use this same common datum.', key=prefix+'reference')
    args = {}
    for key, label, nonneg in [
        ('density', 'Liquid density (kg/m³)', True),
        ('velocity', 'Source/surface velocity (m/s)' if source else 'Suction velocity (m/s)', True),
        ('elevation', 'Liquid surface/source elevation (m)' if source else 'Suction measurement elevation (m)', False),
        ('datum_elevation', 'Pump/NPSH reference datum elevation (m)', False),
    ]:
        args[key] = st.number_input(label, value=None, min_value=0.0 if nonneg else None,
                                    key=prefix+key, format='%.12g')
    if source:
        args['suction_loss'] = st.number_input('Total suction-side hydraulic loss (m)', value=None,
                                              min_value=0.0, key=prefix+'suction_loss', format='%.12g')
    if st.button('Calculate NPSHA', key=prefix+'calculate'):
        try:
            if not datum.strip() or not reference:
                raise ValueError('Describe and confirm the common elevation datum.')
            if not fluid_confirmed:
                raise ValueError('Confirm the vapor pressure corresponds to the actual fluid, temperature and composition.')
            p_pa = pressure_to_pa(pressure, unit, pressure_factors)
            atm_pa = pressure_to_pa(atm, atm_unit, pressure_factors) if basis == 'Gauge' else None
            pv_pa = pressure_to_pa(pv, pv_unit, pressure_factors)
            r = (source_npsha if source else flange_npsha)(
                pressure_pa=p_pa, basis=basis, atmospheric_pa=atm_pa, vapor_pressure_pa=pv_pa, **args)
            st.caption(f'Method: {r.mode} | Common datum: {datum.strip()} | Pump/NPSH datum elevation: {args["datum_elevation"]:.12g} m')
            if basis == 'Gauge':
                st.text(f'Explicit conversion: {p_pa:.12g} Pa gauge + {atm_pa:.12g} Pa atmospheric absolute = {r.absolute_pressure_pa:.12g} Pa absolute')
            st.text(f'Absolute suction/source pressure used: {r.absolute_pressure_pa:.12g} Pa\n'
                    f'Liquid vapor pressure — absolute: {r.vapor_pressure_pa:.12g} Pa\n'
                    f'Vapor-pressure head: {r.vapor_head_m:.12g} m\n'
                    f'Pressure-above-vapor head contribution: {r.pressure_above_vapor_head_m:.12g} m\n'
                    f'Velocity-head contribution: {r.velocity_head_m:.12g} m\n'
                    f'Elevation/static contribution: {r.elevation_head_m:.12g} m')
            if source:
                st.text(f'Suction-loss deduction: -{r.suction_loss_m:.12g} m')
            st.text(f'TOTAL NPSHA: {r.total_npsha_m:.12g} m')
            for warning in r.warnings:
                st.warning(warning)
            st.info(COMPARISON)
        except (ValueError, OverflowError, ZeroDivisionError) as exc:
            st.error(str(exc))
