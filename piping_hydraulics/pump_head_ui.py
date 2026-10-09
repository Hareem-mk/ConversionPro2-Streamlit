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
        st.write('Choose one upstream reference point and one downstream reference point. Pressure, elevation, and velocity must all correspond to those same two physical locations.')
        st.caption('Examples of valid reference points include tank liquid surfaces, pipeline boundaries, or other defined hydraulic locations. Use the same physical upstream and downstream locations consistently for pressure, elevation, and velocity.')
        st.latex(r'H_{required}=\frac{P_2-P_1}{\rho g}+(z_2-z_1)+\frac{V_2^2-V_1^2}{2g}+h_s+h_d+\frac{\Delta P_{equipment}}{\rho g}')
    else:
        st.write('Point 1: defined suction flange/reference point. Point 2: defined discharge flange/reference point. '
                 'Measured pressures and velocities define the pump differential head directly. External suction/discharge '
                 'piping losses are not added in this mode.')
        st.latex(r'H_{pump}=\frac{P_d-P_s}{\rho g}+(z_d-z_s)+\frac{V_d^2-V_s^2}{2g}')
    st.caption('Flow is positive from point 1 to point 2. Elevation is positive upward. '+
               ('Higher downstream pressure/elevation contributes positively. Loss magnitudes are nonnegative and added. ' if system else 'Higher destination pressure/elevation contributes positively. Loss magnitudes are nonnegative and added. ')+
               'Negative calculated head is retained. Gauge pressures may be signed; absolute pressures cannot be negative.')
    if system:
        names={'p1':'Upstream Reference Pressure','p2':'Downstream Reference Pressure',
               'z1':'Upstream Reference Elevation','z2':'Downstream Reference Elevation',
               'v1':'Upstream Reference Velocity','v2':'Downstream Reference Velocity'}
        pressure_help='Pressure at the defined upstream/downstream system reference point. Negative gauge pressure is allowed.'
    else:
        names={'p1':'Pump Suction-Flange Pressure','p2':'Pump Discharge-Flange Pressure',
               'z1':'Pump Suction-Flange Elevation','z2':'Pump Discharge-Flange Elevation',
               'v1':'Pump Suction Velocity','v2':'Pump Discharge Velocity'}
        pressure_help='Pressure measured at the defined pump flange/reference point. Negative gauge pressure is allowed.'
        st.caption('External suction/discharge piping losses are not added in this mode.')
    args={}
    labels={}
    def numeric(key,label,nonneg=False,help_text=None):
        labels[key]=label
        args[key]=st.number_input(label,value=None,min_value=0.0 if nonneg else None,
                                  format='%.12g',key=prefix+key,help=help_text)
    st.caption('STEP 1 — FLUID')
    st.markdown('#### Fluid Properties')
    numeric('density','Density (kg/m³)',True)
    st.caption('STEP 2 — PRESSURE')
    st.markdown('#### Pressure')
    st.write('Select a pressure reference and unit, then enter both numeric pressures. '
             'Enter explicit zero where applicable; blank inputs are not treated as zero.')
    basis=st.selectbox('Pressure Reference',['Gauge','Absolute'],index=None,key=prefix+'basis',
        format_func=lambda value: value+' Pressure',
        help='Use the same pressure reference for both Point 1 and Point 2. Gauge pressure is commonly used for plant hydraulic calculations. Absolute pressure may also be used when both points use the same basis.')
    st.caption('Use the same pressure reference for both Point 1 and Point 2. '
               'Gauge pressure is commonly used for plant hydraulic calculations. '
               'Absolute pressure may also be used when both points use the same basis. '
               'Gauge pressures must use the same atmospheric reference.')
    unit=st.selectbox('Pressure Unit',list(pressure_factors),index=None,key=prefix+'unit',
        help='Select the unit used for both pressure entries below.')
    pressure_suffix=unit if unit is not None else 'select Pressure Unit above'
    for key in ['p1','p2']:
        numeric(key,f'{names[key]} ({pressure_suffix})',help_text=pressure_help)
    st.caption('STEP 3 — ELEVATION')
    st.markdown('#### Elevation')
    st.write('**Elevation Reference:** Enter both elevations relative to the same reference level, such as '
             'plant grade, sea level, or the project datum. Only the elevation difference between Point 1 and Point 2 affects pump head.')
    datum=st.text_input('Reference level — describe it',key=prefix+'datum',
                       help='For example: plant grade, sea level, or the project datum. Describe the level used for both elevations.')
    confirmed=st.checkbox('I confirm that Point 1 and Point 2 use consistent pressure and elevation references.',
        key=prefix+'reference',
        help='Both elevations must use the same datum/reference level. Both pressures must use the same pressure reference. If gauge pressure is selected, use the same atmospheric reference for both points.')
    for key in ['z1','z2']:
        numeric(key,f'{names[key]} (m)',help_text='Signed elevation relative to the same reference level; positive upward.')
    st.caption('STEP 4 — VELOCITY')
    st.markdown('#### Velocity')
    for key in ['v1','v2']:
        numeric(key,f'{names[key]} (m/s)',True)
    loss_args={}
    if system:
        st.caption('STEP 5 — SYSTEM LOSSES')
        st.markdown('#### System Hydraulic Losses')
        loss_help='Enter only losses that are not already represented by the selected Point 1 and Point 2 pressure measurements. Avoid double-counting.'
        st.caption('Suction/discharge totals include their major and minor losses. Enter explicit zero when absent. '
                   'Equipment loss must not already be included in these totals or reference pressures. No automatic Stage 2F transfer.')
        st.info('Important — Avoid double-counting losses: Enter suction-side, discharge-side, and equipment losses only when those losses are NOT already represented in the Point 1 and Point 2 pressure values.')
        st.caption('If the selected reference pressures already include the pressure drop through a pipe, valve, fitting, or equipment item, do not enter that same loss again separately.')
        eq_unit=st.selectbox('Equipment Pressure Loss Unit',list(pressure_factors),index=None,key=prefix+'equipment_unit')
        eq_suffix=eq_unit if eq_unit is not None else 'select Equipment Pressure Loss Unit above'
        loss_labels={'suction_loss':'Suction-Side Hydraulic Loss (m)',
                     'discharge_loss':'Discharge-Side Hydraulic Loss (m)',
                     'equipment_dp':f'Equipment Pressure Loss ({eq_suffix})'}
        for key,label in loss_labels.items():
            loss_args[key]=st.number_input(label,value=None,min_value=0.0,format='%.12g',key=prefix+key,help=loss_help)
    if st.button('Calculate pump head',key=prefix+'calculate'):
        try:
            if not confirmed:
                st.warning('Please confirm that Point 1 and Point 2 use consistent pressure and elevation references.')
                return
            if basis is None:raise ValueError('Select Pressure Reference: Gauge Pressure or Absolute Pressure.')
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
                r=system_required_head(**args,**loss_args,losses_already_in_reference_pressures=False)
            else:r=flange_differential_head(**args)
            st.subheader('Total Pump Head' if system else 'Pump-Flange Differential Head')
            st.text(('TOTAL PUMP HEAD' if system else 'TOTAL PUMP DIFFERENTIAL HEAD')+f': {r.total_head_m:.12g} m')
            st.caption(f'Mode: {r.mode} | Pressure reference: {r.pressure_basis} Pressure | Reference level: {r.datum} | α = 1')
            st.markdown('**Component breakdown**')
            st.text(f'Pressure-head contribution: {r.pressure_head_m:.12g} m\n'
                    f'Static/elevation-head contribution: {r.elevation_head_m:.12g} m\n'
                    f'Velocity-head contribution: {r.velocity_head_m:.12g} m')
            if system:
                st.text(f'Suction loss: {r.suction_loss_m:.12g} m\nDischarge loss: {r.discharge_loss_m:.12g} m\nEquipment-loss head: {r.equipment_head_m:.12g} m')
            if r.total_head_m<0:
                st.warning('Negative head retained: the specified boundary/reference conditions provide a net head surplus '
                           'relative to the included losses. This is not positive pump head demand or a pump selection; '
                           'verify the assumed flow and whether energy dissipation/control is required.')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))

