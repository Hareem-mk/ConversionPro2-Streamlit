"""Speed-change affinity point estimates; no curve generation or system solving."""
import math

from piping_hydraulics.pipe_capacity import nonnegative
from .pump_curve import curve_flow_to_si, HEAD_FACTORS
from .system_curve import head_to_metres, head_from_metres
from .shaft_power import POWER_FACTORS
from .affinity_laws import calculate_speed_affinity

EFFICIENCY_GUIDANCE = ('The cubic power relationship is an affinity-law estimate. Actual shaft power may differ if pump efficiency changes.')
SYSTEM_GUIDANCE = ('Affinity laws describe how the pump performance characteristic changes. The actual operating point also depends on the connected system curve.')


def _percent_text(value):
    return 'N/A — original value is zero' if value is None else f'{value:+.6g}%'


def render_affinity_laws(flow_factors):
    import streamlit as st
    st.subheader('3I — Pump Affinity Laws')
    st.write('Estimate a corresponding centrifugal-pump performance point after a rotational-speed change, for the same pump and impeller diameter.')
    st.selectbox('Affinity Calculation Method', ['Speed Change'], key='p3i_method')
    st.caption('Scalar speed-change estimates only. Diameter-change approximation and full-curve scaling are not included in this module.')
    st.markdown('**Original Pump Condition**')
    flow_unit = st.selectbox('Affinity Flow Unit', list(flow_factors), index=None,
                             placeholder='Select flow unit', key='p3i_flow_unit')
    head_unit = st.selectbox('Affinity Head Unit', list(HEAD_FACTORS), index=None,
                             placeholder='Select head unit', key='p3i_head_unit')
    power_unit = st.selectbox('Affinity Shaft Power Unit', list(POWER_FACTORS), index=None,
                              placeholder='Select shaft power unit', key='p3i_power_unit')
    st.caption('Selected units apply to original inputs and estimated results. Changing units reinterprets entered numbers; it does not convert them automatically. No data are transferred from other modules.')
    flow = st.number_input(f'Original Flow ({flow_unit or "select unit above"})',value=None,
                           format='%.12g',key='p3i_flow')
    head = st.number_input(f'Original Head ({head_unit or "select unit above"})',value=None,
                           format='%.12g',key='p3i_head')
    power = st.number_input(f'Original Pump Shaft/Brake Power ({power_unit or "select unit above"})',value=None,
                            format='%.12g',key='p3i_power')
    st.caption('Power means mechanical pump shaft/brake power, excluding motor efficiency losses; it is not motor electrical input power.')
    st.markdown('**Changed Rotational Speed**')
    st.caption('Both rotational speeds use rpm. Only their ratio N2/N1 is used; no speed-unit conversion is required.')
    n1 = st.number_input('Original Rotational Speed (rpm)',value=None,format='%.12g',key='p3i_n1')
    n2 = st.number_input('New Rotational Speed (rpm)',value=None,format='%.12g',key='p3i_n2')
    if st.button('Calculate Affinity-Law Estimates',key='p3i_calculate'):
        try:
            q = curve_flow_to_si(flow, flow_unit, flow_factors)
            h = head_to_metres(head, head_unit, 'Original Head')
            watts = nonnegative(power, 'Original Pump Shaft/Brake Power')
            if power_unit not in POWER_FACTORS:
                raise ValueError('Select a supported shaft power unit: W, kW or Mechanical hp.')
            # Reuse the existing power-unit factor table, including the exact
            # Phase 3A mechanical horsepower constant; no second definition.
            p = watts * POWER_FACTORS[power_unit]
            if not math.isfinite(p) or (watts > 0 and p == 0):
                raise ValueError('Original shaft power exceeds the supported numeric range.')
            result = calculate_speed_affinity(q, h, p, n1, n2)
            q2 = result.estimated_flow_m3_s / flow_factors[flow_unit]
            h2 = head_from_metres(result.estimated_head_m, head_unit)
            p2 = result.estimated_power_w / POWER_FACTORS[power_unit]
            if any(not math.isfinite(v) or (original > 0 and v == 0)
                   for v, original in [(q2,q),(h2,h),(p2,p)]):
                raise ValueError('Displayed affinity-law estimate exceeds the supported numeric range.')
            st.markdown('**Affinity-Law Results**')
            st.text(f'Original Speed: {n1:.6g} rpm\n'
                    f'New Speed: {n2:.6g} rpm\n'
                    f'Speed Ratio: {result.ratio:.6g}\n'
                    f'Original Flow: {flow:.6g} {flow_unit}\n'
                    f'Affinity-Law Estimated Flow: {q2:.6g} {flow_unit}\n'
                    f'Original Head: {head:.6g} {head_unit}\n'
                    f'Affinity-Law Estimated Head: {h2:.6g} {head_unit}\n'
                    f'Original Shaft Power: {power:.6g} {power_unit}\n'
                    f'Affinity-Law Estimated Shaft Power: {p2:.6g} {power_unit}\n'
                    f'Flow Change: {_percent_text(result.flow_change_percent)}\n'
                    f'Head Change: {_percent_text(result.head_change_percent)}\n'
                    f'Power Change: {_percent_text(result.power_change_percent)}')
        except ValueError as exc:
            st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    st.info(SYSTEM_GUIDANCE)
    st.caption('Speed affinity laws apply to the same centrifugal pump with the same impeller diameter. Flow changes approximately in direct proportion to speed; head with speed squared; shaft power with speed cubed.')
    st.caption(EFFICIENCY_GUIDANCE + ' Sufficiently similar pump efficiency is assumed; efficiency is not automatically changed.')
    st.caption('These are affinity-law-scaled pump performance points, not a calculated installed-system operating point. Manufacturer/vendor pump curves remain the primary basis for final engineering decisions.')
    st.caption('A calculated speed increase is not automatically acceptable. Verify actual efficiency, driver power and motor/VFD capability, NPSHR and cavitation margin, maximum pump speed, mechanical design limits, bearing/seal loading and vibration against manufacturer limits. These checks are not calculated here.')
