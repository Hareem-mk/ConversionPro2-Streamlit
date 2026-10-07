"""Explicitly separate endpoints and losses for the two pump-head modes."""
from .pump_head import pressure_to_pa,system_required_head,flange_differential_head


def render_pump_head(pressure_factors):
    import streamlit as st
    st.divider()
    st.subheader('2G — Total Pump Head Calculation')
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
        st.write('Point 1 = source/upstream system reference point. '
                 'Point 2 = destination/downstream system reference point. '
                 'Pump head is calculated from Point 1 to Point 2. '
                 'Do not use already adjusted flange pressures while also re-adding external piping losses.')
        st.latex(r'H_{required}=\frac{P_2-P_1}{\rho g}+(z_2-z_1)+\frac{V_2^2-V_1^2}{2g}+h_s+h_d+\frac{\Delta P_{equipment}}{\rho g}')
    else:
        st.write('Point 1: defined suction flange/reference point. Point 2: defined discharge flange/reference point. '
                 'Measured pressures and velocities define the pump differential head directly. External suction/discharge '
                 'piping losses are not added in this mode.')
        st.latex(r'H_{pump}=\frac{P_d-P_s}{\rho g}+(z_d-z_s)+\frac{V_d^2-V_s^2}{2g}')
    st.caption('Flow is positive from point 1 to point 2. Elevation is positive upward. '
               'Higher destination pressure/elevation contributes positively. Loss magnitudes are nonnegative and added. '
               'Negative calculated head is retained. Gauge pressures may be signed; absolute pressures cannot be negative.')
    st.write('Select Pressure Basis and Pressure Unit, then enter a numeric pressure at each reference point. '
             'Enter explicit zero where applicable; blank inputs are not treated as zero.')
    basis=st.selectbox('Pressure Basis',['Gauge','Absolute'],index=None,key=prefix+'basis',
        help='Use the same pressure basis for Point 1 and Point 2. Gauge pressures are valid for this differential-head calculation when both use the same atmospheric reference.')
    unit=st.selectbox('Pressure Unit',list(pressure_factors),index=None,key=prefix+'unit',
        help='Select the unit used for both pressure entries below.')
    st.caption('Use the same pressure basis for Point 1 and Point 2. Gauge pressures are valid for this '
               'differential-head calculation when both use the same atmospheric reference.')
    pressure_suffix=unit if unit is not None else 'select Pressure Unit above'
    st.write('**Common Elevation Datum**')
    st.caption('Enter both elevations relative to the same reference datum. Only the difference z2 − z1 affects the calculated pump head.')
    datum=st.text_input('Common Elevation Datum — describe the reference',key=prefix+'datum',
                       help='For example: site survey datum or pump centreline. This describes the reference, not a numeric elevation.')
    confirmed=st.checkbox('Both points use this datum and consistent pressure references; if gauge, the same atmospheric reference.',key=prefix+'reference')
    if system:
        names={'p1':'Point 1 — Source Pressure','p2':'Point 2 — Destination Pressure',
               'z1':'Point 1 — Source Elevation','z2':'Point 2 — Destination Elevation',
               'v1':'Point 1 — Source Velocity','v2':'Point 2 — Destination Velocity'}
        pressure_help='Pressure at the defined source/destination system reference point. Negative gauge pressure is allowed.'
    else:
        names={'p1':'Pump Suction-Flange Pressure','p2':'Pump Discharge-Flange Pressure',
               'z1':'Pump Suction-Flange Elevation','z2':'Pump Discharge-Flange Elevation',
               'v1':'Pump Suction Velocity','v2':'Pump Discharge Velocity'}
        pressure_help='Pressure measured at the defined pump flange/reference point. Negative gauge pressure is allowed.'
        st.caption('External suction/discharge piping losses are not added in this mode.')
    args={}
    labels={'density':'Density (kg/m³)'}
    for key in ['p1','p2','z1','z2','v1','v2']:
        suffix=pressure_suffix if key.startswith('p') else 'm' if key.startswith('z') else 'm/s'
        labels[key]=f'{names[key]} ({suffix})'
    for key,label in labels.items():
        nonneg=key in ('density','v1','v2')
        help_text=pressure_help if key.startswith('p') else ('Signed elevation relative to the common datum; positive upward.' if key.startswith('z') else None)
        args[key]=st.number_input(label,value=None,min_value=0.0 if nonneg else None,format='%.12g',key=prefix+key,help=help_text)
    loss_args={}
    if system:
        loss_help='Do not enter losses already represented between the selected pressure reference points again. Include each loss once.'
        st.caption('Suction/discharge totals include their major and minor losses. Enter explicit zero when absent. '
                   'Equipment loss must not already be included in these totals or reference pressures. No automatic Stage 2F transfer.')
        st.caption(loss_help)
        eq_unit=st.selectbox('Equipment Pressure Loss Unit',list(pressure_factors),index=None,key=prefix+'equipment_unit')
        eq_suffix=eq_unit if eq_unit is not None else 'select Equipment Pressure Loss Unit above'
        loss_labels={'suction_loss':'Suction-Side Hydraulic Loss (m)',
                     'discharge_loss':'Discharge-Side Hydraulic Loss (m)',
                     'equipment_dp':f'Equipment Pressure Loss ({eq_suffix})'}
        for key,label in loss_labels.items():
            loss_args[key]=st.number_input(label,value=None,min_value=0.0,format='%.12g',key=prefix+key,help=loss_help)
        already=st.checkbox('Entered losses are already represented in the supplied reference pressures',key=prefix+'duplicate')
    if st.button('Calculate pump head',key=prefix+'calculate'):
        try:
            if basis is None:raise ValueError('Select Pressure Basis: Gauge or Absolute.')
            if unit is None:raise ValueError('Select Pressure Unit for both pressure entries.')
            missing=[label for key,label in labels.items() if args[key] is None]
            if system:
                if eq_unit is None:raise ValueError('Select Equipment Pressure Loss Unit, including when the loss is zero.')
                missing += [label for key,label in loss_labels.items() if loss_args[key] is None]
            if missing:raise ValueError('Enter a numeric value for: '+ '; '.join(missing)+'. Enter explicit zero where applicable.')
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

