"""Explicitly separate endpoints and losses for the two pump-head modes."""
from .pump_head import pressure_to_pa,system_required_head,flange_differential_head


def render_pump_head(pressure_factors):
    import streamlit as st
    st.divider()
    st.subheader('Total Pump Head Calculation')
    st.caption('Steady-state, single-phase incompressible liquid; g = 9.80665 m/s²; kinetic-energy correction α = 1. '
               'A common elevation datum and consistent pressure reference are required.')
    st.info('Calculates hydraulic head requirement or measured differential head only. '
            'Does NOT calculate efficiency, shaft power, pump curve, BEP, operating point, NPSHR or pump selection.')
    mode=st.selectbox('Calculation mode',['SYSTEM REQUIRED PUMP HEAD','PUMP-FLANGE DIFFERENTIAL HEAD'],
                      index=None,key='p2g_mode')
    if mode is None:return
    system=mode=='SYSTEM REQUIRED PUMP HEAD'
    prefix='p2g_system_' if system else 'p2g_flange_'
    if system:
        st.write('Point 1: source boundary. Point 2: destination boundary. Add the losses between these boundaries once. '
                 'Do not use already adjusted flange pressures while also re-adding external piping losses.')
        st.latex(r'H_{required}=\frac{P_2-P_1}{\rho g}+(z_2-z_1)+\frac{V_2^2-V_1^2}{2g}+h_s+h_d+\frac{\Delta P_{equipment}}{\rho g}')
    else:
        st.write('Point 1: defined suction flange/reference point. Point 2: defined discharge flange/reference point. '
                 'Measured pressures and velocities define the pump differential head directly. External suction/discharge '
                 'piping losses must NOT be added again; there are no external-loss inputs in this mode.')
        st.latex(r'H_{pump}=\frac{P_d-P_s}{\rho g}+(z_d-z_s)+\frac{V_d^2-V_s^2}{2g}')
    st.caption('Flow is positive from point 1 to point 2. Elevation is positive upward. '
               'Higher destination pressure/elevation contributes positively. Loss magnitudes are nonnegative and added. '
               'Negative calculated head is retained. Gauge pressures may be signed; absolute pressures cannot be negative.')
    basis=st.selectbox('Pressure basis — applies to BOTH points',['Gauge','Absolute'],index=None,key=prefix+'basis')
    unit=st.selectbox('Pressure unit — both points',list(pressure_factors),index=None,key=prefix+'unit')
    datum=st.text_input('Common elevation datum — describe it',key=prefix+'datum')
    confirmed=st.checkbox('Both points use this datum and consistent pressure references; if gauge, the same atmospheric reference.',key=prefix+'reference')
    args={}
    for key,label,nonneg in [('density','Density (kg/m³)',True),('p1','Point 1 pressure',False),
                            ('p2','Point 2 pressure',False),('z1','Point 1 elevation (m)',False),
                            ('z2','Point 2 elevation (m)',False),('v1','Point 1 velocity (m/s)',True),
                            ('v2','Point 2 velocity (m/s)',True)]:
        args[key]=st.number_input(label,value=None,min_value=0.0 if nonneg else None,format='%.12g',key=prefix+key)
    loss_args={}
    if system:
        st.caption('Suction/discharge totals include their major and minor losses. Enter explicit zero when absent. '
                   'Equipment loss must not already be included in these totals or reference pressures. No automatic Stage 2F transfer.')
        for key,label in [('suction_loss','Suction major/minor loss total (m)'),('discharge_loss','Discharge major/minor loss total (m)'),
                          ('equipment_dp','Equipment pressure loss')]:
            loss_args[key]=st.number_input(label,value=None,min_value=0.0,format='%.12g',key=prefix+key)
        eq_unit=st.selectbox('Equipment pressure-loss unit',list(pressure_factors),index=None,key=prefix+'equipment_unit')
        already=st.checkbox('Entered losses are already represented in the supplied reference pressures',key=prefix+'duplicate')
    if st.button('Calculate pump head',key=prefix+'calculate'):
        try:
            args['p1_pa']=pressure_to_pa(args.pop('p1'),unit,pressure_factors)
            args['p2_pa']=pressure_to_pa(args.pop('p2'),unit,pressure_factors)
            args.update(basis1=basis,basis2=basis,datum=datum,reference_confirmed=confirmed)
            if system:
                loss_args['equipment_dp_pa']=pressure_to_pa(loss_args.pop('equipment_dp'),eq_unit,pressure_factors)
                r=system_required_head(**args,**loss_args,losses_already_in_reference_pressures=already)
            else:r=flange_differential_head(**args)
            st.caption(f'Mode: {r.mode} | Pressure basis: {r.pressure_basis} | Datum: {r.datum} | α = 1')
            st.text(f'Pressure-head contribution: {r.pressure_head_m:.12g} m\n'
                    f'Static/elevation-head contribution: {r.elevation_head_m:.12g} m\n'
                    f'Velocity-head contribution: {r.velocity_head_m:.12g} m')
            if system:
                st.text(f'Suction loss: {r.suction_loss_m:.12g} m\nDischarge loss: {r.discharge_loss_m:.12g} m\nEquipment-loss head: {r.equipment_head_m:.12g} m')
            st.text(('TOTAL PUMP HEAD' if system else 'TOTAL PUMP DIFFERENTIAL HEAD')+f': {r.total_head_m:.12g} m')
            if r.total_head_m<0:
                st.warning('Negative head retained: the specified boundary/reference conditions provide a net head surplus '
                           'relative to the included losses. This is not positive pump head demand or a pump selection; '
                           'verify the assumed flow and whether energy dissipation/control is required.')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))
