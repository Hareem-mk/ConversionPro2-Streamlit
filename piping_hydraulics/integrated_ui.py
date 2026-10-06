"""Manual single-section input; no hidden cross-module state."""
from .integrated import integrated_section


def render_integrated(flow_factors):
    import streamlit as st
    st.divider()
    st.subheader('Stage 2F — Integrated Piping Hydraulics')
    st.write('One uniform-INTERNAL-diameter, full circular pipe section. Steady, single-phase, '
             'incompressible Newtonian liquid; defined roughness; fully developed-flow friction correlations.')
    st.info('FRICTIONAL PRESSURE LOSS only. Excludes static elevation, vessel pressure differences, '
            'pump head, equipment pressure losses not represented by K, acceleration effects and transient effects.')
    st.latex(r'A=\pi D^2/4,\quad V=Q/A,\quad Re=\rho VD/\mu,\quad\varepsilon_r=\varepsilon/D')
    st.latex(r'h_f=f_D(L/D)V^2/(2g),\quad h_m=KV^2/(2g),\quad h_t=h_f+h_m,\quad\Delta P=\rho gh')
    st.caption('Darcy factor only (f_Darcy = 4 × f_Fanning); g = 9.80665 m/s². '
               'Re=0: no flow; 0<Re<2300: laminar; 2300≤Re<4000: transitional; Re≥4000: turbulent. '
               'Phase 1 domain: ε/D ≤ 0.05. Swamee–Jain only for 5000≤Re≤10⁸ and 10⁻⁶≤ε/D≤10⁻².')
    inputs={}
    for name,label in [('flow','Volumetric flow rate'),('diameter','INTERNAL pipe diameter (m)'),
                       ('length','Straight pipe length (m)'),('density','Density (kg/m³)'),
                       ('viscosity','Dynamic viscosity (Pa·s)'),('roughness','Absolute roughness ε (m)'),
                       ('k_total','Total K-factor (dimensionless)')]:
        inputs[name]=st.number_input(label,value=None,min_value=0.0,format='%.12g',key='p2f_'+name)
    inputs['flow_unit']=st.selectbox('Volumetric flow unit',list(flow_factors),index=None,key='p2f_unit')
    confirmed=st.checkbox('K_total uses this section’s calculated velocity, uniform diameter and single flow path.',key='p2f_basis')
    duplicate=st.checkbox('Entered length includes equivalent lengths for fittings',key='p2f_equivalent')
    st.warning('Enter actual straight pipe length only. Use K_total for fittings; do not also add their Stage 2E equivalent lengths. '
               'No inputs are transferred from other modules. Enter reviewed values explicitly.')
    if st.button('Calculate section frictional loss',key='p2f_calculate'):
        try:
            r=integrated_section(**inputs,flow_factors=flow_factors,common_k_basis=confirmed,
                                 length_contains_equivalent_fittings=duplicate)
            st.text(f"SI flow: {r['flow_m3_s']:.12g} m³/s\nArea: {r['area_m2']:.12g} m²\n"
                    f"Velocity: {r['velocity_m_s']:.12g} m/s\nReynolds number: {r['reynolds']:.12g}\n"
                    f"Flow regime: {r['regime']}\nAbsolute roughness: {r['roughness_m']:.12g} m\n"
                    f"Relative roughness ε/D: {r['relative_roughness']:.12g}\nMethod: {r['method']}")
            f=r['friction']
            st.text('Darcy friction factor: '+('Unavailable / not applicable' if f['darcy'] is None else f"{f['darcy']:.12g}"))
            if f['residual'] is not None:
                st.caption(f"Colebrook final residual: {f['residual']:.6g}; iterations: {f['iterations']}")
            if f['swamee_jain'] is not None:
                st.text(f"Swamee–Jain: {f['swamee_jain']:.12g}; difference from Colebrook: {f['comparison_percent']:+.8g}%")
            if f['note']:st.info(f['note'])
            if not r['complete']:
                st.warning('INCOMPLETE: transitional flow. Automatic major and total friction losses are unavailable, not zero. '
                           'Minor loss is shown separately and is not the total.')
            st.write('**FRICTIONAL PRESSURE LOSS**')
            for key,label in [('major','Major'),('minor','Minor'),('total','Total')]:
                loss=r[key]
                if loss is None:st.text(f'{label} head loss and ΔP: UNAVAILABLE')
                else:st.text(f'{label} head loss: {loss.head_m:.12g} m\n{label} ΔP: {loss.pressure_pa:.12g} Pa | '
                             f'{loss.pressure_kpa:.12g} kPa | {loss.pressure_bar:.12g} bar')
        except (ValueError,OverflowError,ZeroDivisionError) as exc:st.error(str(exc))
