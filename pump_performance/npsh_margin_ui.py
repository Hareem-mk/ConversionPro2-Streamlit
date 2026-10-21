"""Manual/vendor NPSH margin and explicit, unchanged Phase 2H kernel integration."""
import math
from piping_hydraulics.pipe_geometry import positive
from piping_hydraulics.pump_head import pressure_to_pa
from piping_hydraulics.npsha import flange_npsha, source_npsha
from .pump_curve import HEAD_FACTORS
from .system_curve import head_to_metres
from .npsh_margin import calculate_npsh_margin, margin_from_phase2h, compare_required_margin

METHODS = ('Manual NPSHA', 'Calculate NPSHA from Phase 2H')
NPSHA_METHODS = ('Suction-Flange Method', 'Vessel/Source Method')
VENDOR_GUIDANCE = ('NPSHR must be obtained from the applicable manufacturer/vendor pump performance curve at the relevant operating flow, speed and impeller diameter.')


def _phase2h_inputs(st, pressure_factors):
    method = st.selectbox('Integrated NPSHA Method', NPSHA_METHODS, index=None, key='p3j_npsha_method')
    if method is None:
        return None
    source = method == NPSHA_METHODS[1]
    prefix = 'p3j_source_' if source else 'p3j_flange_'
    if source:
        st.caption('Reference: vessel liquid surface/source. Enter pressure above the liquid surface and source-to-pump suction losses once. Do not enter flange pressure and subtract those upstream losses again. Enter surface velocity explicitly, including zero for a large vessel when justified.')
    else:
        st.caption('Reference: pump suction pressure measurement point. Measured flange pressure already reflects upstream suction losses; do not add or subtract those losses again. No suction-loss input applies to this method.')
    basis = st.selectbox('Integrated Suction/Source Pressure Basis', ['Absolute','Gauge'], index=None, key=prefix+'basis')
    unit = st.selectbox('Integrated Suction/Source Pressure Unit', list(pressure_factors), index=None, key=prefix+'unit')
    pressure = st.number_input('Source Surface Pressure' if source else 'Suction Measurement Pressure', value=None, format='%.12g', key=prefix+'pressure')
    atm = atm_unit = None
    if basis == 'Gauge':
        st.caption('Gauge pressure requires explicit local atmospheric absolute pressure; no standard-atmosphere default. Phase 2H converts gauge + atmospheric pressure to absolute.')
        atm = st.number_input('Integrated Local Atmospheric Pressure — Absolute', value=None,format='%.12g',key=prefix+'atmosphere')
        atm_unit = st.selectbox('Integrated Atmospheric Pressure Unit',list(pressure_factors),index=None,key=prefix+'atm_unit')
    vapor = st.number_input('Integrated Liquid Vapor Pressure — Absolute',value=None,format='%.12g',key=prefix+'vapor')
    vapor_unit = st.selectbox('Integrated Vapor Pressure Unit',list(pressure_factors),index=None,key=prefix+'vapor_unit')
    st.caption('Enter vapor pressure for the actual liquid, pumping temperature and composition, using appropriate process/property data. No vapor-pressure database or water assumption is used.')
    datum = st.text_input('Integrated Common Elevation Datum — Describe It',key=prefix+'datum')
    st.caption('Enter both elevations relative to this same common datum, positive upward. Density is in kg/m³; velocity in m/s; elevations and suction loss in m.')
    args = {}
    for key,label in [('density','Integrated Liquid Density (kg/m³)'),
                      ('velocity','Source Surface Velocity (m/s)' if source else 'Integrated Suction Velocity (m/s)'),
                      ('elevation','Source Surface Elevation (m)' if source else 'Suction Measurement Elevation (m)'),
                      ('datum_elevation','Integrated Pump/NPSH Datum Elevation (m)')]:
        args[key] = st.number_input(label,value=None,format='%.12g',key=prefix+key)
    if source:
        args['suction_loss'] = st.number_input('Integrated Total Suction Loss (m)',value=None,format='%.12g',key=prefix+'suction_loss')
    st.caption('Phase 2H assumptions: steady-state single-phase incompressible liquid; kinetic-energy correction α=1; g=9.80665 m/s². Calculated negative NPSHA and kernel warnings are retained.')
    return source, basis, unit, pressure, atm, atm_unit, vapor, vapor_unit, datum, args


def _display_head(metres, unit):
    # Reuse the existing head factor table; unlike the nonnegative head display
    # adapter, margins and calculated Phase 2H NPSHA can legitimately be signed.
    value = metres / HEAD_FACTORS[unit]
    if not math.isfinite(value) or (metres != 0 and value == 0):
        raise ValueError('Displayed NPSH head exceeds the supported numeric range.')
    return value


def render_npsh_margin(pressure_factors):
    import streamlit as st
    st.subheader('3J — NPSHR / NPSH Margin')
    st.write('Compare Net Positive Suction Head Available (NPSHA) with manufacturer/vendor supplied Net Positive Suction Head Required (NPSHR).')
    st.info(VENDOR_GUIDANCE)
    st.caption('ConversionPro does not calculate or estimate NPSHR.')
    method = st.selectbox('NPSH Margin Calculation Method',METHODS,key='p3j_method')
    unit = st.selectbox('NPSHA / Result Head Unit',list(HEAD_FACTORS),index=None,placeholder='Select head unit',key='p3j_unit')
    if method == METHODS[0]:
        available = st.number_input(f'Manual NPSHA ({unit or "select unit above"})',value=None,format='%.12g',key='p3j_available')
    else:
        integrated = _phase2h_inputs(st,pressure_factors)
    st.markdown('**Vendor NPSHR**')
    r_unit = st.selectbox('Vendor NPSHR Unit',list(HEAD_FACTORS),index=None,placeholder='Select head unit',key='p3j_required_unit')
    required = st.number_input(f'Vendor NPSHR ({r_unit or "select unit above"})',value=None,format='%.12g',key='p3j_required')
    st.caption('NPSHR normally varies with pump flow. Use the NPSHR corresponding to the relevant operating point on the applicable manufacturer/vendor curve.')
    st.markdown('**Optional User/Vendor/Project Criterion**')
    criterion = st.number_input('User/Vendor/Project Required NPSH Margin',value=None,format='%.12g',key='p3j_criterion')
    criterion_unit = st.selectbox('Required NPSH Margin Unit',list(HEAD_FACTORS),index=None,placeholder='Select head unit if entering a margin',key='p3j_criterion_unit')
    st.caption('Required NPSH margin is pump-, service-, and project-specific. Enter the applicable vendor/project criterion if available. Leave the margin blank for numerical comparison only. An entered margin must be nonnegative.')
    st.caption('Head units are independent. Signed margin and excess are displayed in the NPSHA / Result Head Unit. Changing units reinterprets entered numbers; it does not rewrite them. No other module inputs are transferred automatically.')
    if st.button('Calculate NPSH Margin',key='p3j_calculate'):
        try:
            if unit not in HEAD_FACTORS:
                raise ValueError('Select a supported NPSHA / result head unit: m or ft.')
            positive(required,'Vendor NPSHR')
            r_m = positive(head_to_metres(required,r_unit,'Vendor NPSHR'),'Converted Vendor NPSHR')
            c_m = None if criterion is None else head_to_metres(criterion,criterion_unit,'User/Vendor/Project Required NPSH Margin')
            phase2h = None
            if method == METHODS[0]:
                a_m = head_to_metres(available,unit,'Manual NPSHA')
                result = calculate_npsh_margin(a_m,r_m)
            else:
                if integrated is None:
                    raise ValueError('Select an integrated Phase 2H NPSHA method.')
                source,basis,p_unit,pressure,atm,atm_unit,vapor,vapor_unit,datum,args = integrated
                if not datum.strip():
                    raise ValueError('Describe the common elevation datum and use it for both elevations.')
                p_pa = pressure_to_pa(pressure,p_unit,pressure_factors)
                atm_pa = pressure_to_pa(atm,atm_unit,pressure_factors) if basis == 'Gauge' else None
                pv_pa = pressure_to_pa(vapor,vapor_unit,pressure_factors)
                phase2h = (source_npsha if source else flange_npsha)(pressure_pa=p_pa,basis=basis,
                           atmospheric_pa=atm_pa,vapor_pressure_pa=pv_pa,**args)
                result = margin_from_phase2h(phase2h,r_m)
            comparison = None if c_m is None else compare_required_margin(result.margin_m,c_m)
            a_display = _display_head(result.npsha_m,unit)
            margin_display = _display_head(result.margin_m,unit)
            excess_display = None if comparison is None else _display_head(comparison.excess_margin_m,unit)
            st.markdown('**NPSH Margin Results**')
            st.text(f'NPSHA: {a_display:.6g} {unit}\n'
                    f'Vendor NPSHR: {required:.6g} {r_unit}\n'
                    f'NPSH Margin: {margin_display:+.6g} {unit}\n'
                    f'NPSHA / NPSHR Ratio: {result.ratio:.6g}\n'
                    f'Percent Margin relative to NPSHR: {result.percent_margin:+.6g}%\n'
                    f'Relationship Status: {result.relationship_status}')
            if comparison is not None:
                st.text(f'User/Vendor/Project Required NPSH Margin: {criterion:.6g} {criterion_unit}\n'
                        f'Excess Above Required Margin: {excess_display:+.6g} {unit}\n'
                        f'Required Margin Status: {comparison.criterion_status}')
            if phase2h is not None:
                st.caption(f'Calculated by unchanged Phase 2H kernel: {phase2h.mode}. Common datum: {datum.strip()}.')
                st.text(f'Phase 2H NPSHA (SI): {phase2h.total_npsha_m:.17g} m\n'
                        f'Absolute suction/source pressure used: {phase2h.absolute_pressure_pa:.12g} Pa\n'
                        f'Liquid vapor pressure — absolute: {phase2h.vapor_pressure_pa:.12g} Pa')
                if basis == 'Gauge':
                    st.text(f'Explicit pressure conversion: {p_pa:.12g} Pa gauge + {atm_pa:.12g} Pa atmospheric absolute = {phase2h.absolute_pressure_pa:.12g} Pa absolute')
                for warning in phase2h.warnings:
                    st.warning(warning)
        except (ValueError,OverflowError,ZeroDivisionError) as exc:
            st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.caption('NPSHA represents suction-system conditions available to the pump. NPSHR is manufacturer/vendor performance data determined under defined test criteria. The entered NPSHR should use the same basis as the manufacturer/vendor performance data applicable to the pump.')
    st.caption('If pump speed or impeller diameter changes, verify the applicable NPSHR from manufacturer/vendor data rather than assuming Phase 3I affinity-law scaling applies to NPSHR.')
    st.caption('Positive NPSH margin alone does not establish that all vendor/project cavitation or reliability criteria are satisfied. Apply user/vendor/project margin criteria where available. Final pump suitability requires manufacturer/vendor performance and project requirements.')
    st.caption('Relationship equality uses math.isclose in metres: relative tolerance 1e-10, absolute tolerance 1e-9 m. Raw margins retain full precision. Entered required-margin criteria use the inclusive numeric comparison actual margin ≥ required margin without this status tolerance.')
