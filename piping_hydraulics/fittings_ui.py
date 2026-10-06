"""Fittings table, with explicit source suitability and velocity-basis gates."""
from .fittings import K_RECORDS, CAUTION, Component, calculate_fittings


def render_fittings():
    import streamlit as st
    st.divider()
    st.subheader('Stage 2D — Fittings / K-Factor Calculator')
    st.warning(CAUTION)
    st.latex(r'K_{total}=\sum n_iK_i,\quad h_m=K_{total}\frac{V^2}{2g},\quad\Delta P_m=\rho gh_m')
    st.caption('g = 9.80665 m/s². Steady single-phase incompressible liquid flow. '
               'K is dimensionless. Enter explicit zero if applicable. Do not enter the same '
               'physical fitting more than once or add its equivalent-length loss elsewhere.')
    mode=st.selectbox('Velocity basis', ['Common reference velocity','Separate row reference velocities'],
                       key='p2d_mode')
    common=mode=='Common reference velocity'
    confirmed=st.checkbox('All rows represent losses along one flow path; K values share the same reference velocity.'
                          if common else 'All rows represent losses along one flow path, each with its stated local reference velocity.',
                          key='p2d_basis_'+('common' if common else 'separate'))
    count=st.number_input('Number of component rows',min_value=1,max_value=20,value=2,step=1,key='p2d_count')
    records={r.component:r for r in K_RECORDS}
    rows=[];approved=True
    for i in range(count):
        st.write(f'**Component row {i+1}**')
        choice=st.selectbox('Component / source', ['Manual K',*records], index=None,key=f'p2d_source_{i}')
        n=st.number_input('Quantity',min_value=0,value=None,step=1,key=f'p2d_qty_{i}')
        if choice=='Manual K':
            k=st.number_input('Manual K (dimensionless)',min_value=0.0,value=None,format='%.10g',key=f'p2d_k_{i}')
            st.text_input('Manual geometry / condition / reference-velocity basis',key=f'p2d_note_{i}')
        elif choice in records:
            r=records[choice];k=r.k
            st.write(f'K = {k:g} | {r.configuration} | {r.condition}')
            st.caption(f'{r.source}; {r.edition}; {r.location}')
            st.markdown(f'[Source table]({r.url})')
            st.caption(r.velocity_basis+' '+r.limitations)
            approved &= st.checkbox('I verified this representative configuration and velocity basis are suitable for this row.',
                                    key=f'p2d_approve_{i}_{r.id}')
        else:k=None;approved=False
        duplicate=st.checkbox('This row is already included as an equivalent-length loss elsewhere',key=f'p2d_duplicate_{i}')
        v=None if common else st.number_input('This row’s reference velocity (m/s)',min_value=0.0,value=None,
                                              format='%.10g',key=f'p2d_velocity_{i}')
        rows.append(Component(n,k,v,duplicate))
    velocity=st.number_input('Common reference velocity (m/s) — optional for K total only',min_value=0.0,
                             value=None,format='%.10g',key='p2d_velocity') if common else None
    if not common:
        st.caption('Each row uses h_i = n_i K_i V_i²/(2g); sum the head losses, not K. No combined K is reported.')
    density=st.number_input('Density (kg/m³) — optional, needed only for pressure loss',min_value=0.0,
                            value=None,format='%.10g',key='p2d_density')
    if st.button('Calculate fittings losses',key='p2d_calculate'):
        try:
            if not approved:raise ValueError('Select every row source and verify database configuration applicability.')
            if not confirmed:raise ValueError('Confirm the flow path and velocity basis before combining rows.')
            result=calculate_fittings(rows,mode='common' if common else 'separate',
                    common_basis_confirmed=confirmed,velocity=velocity,density=density)
            st.text('K total: '+f"{result['k_total']:.12g}" if common else 'No combined K: separate velocity bases.')
            if result['head_m'] is not None:
                st.text(f"Minor head loss: {result['head_m']:.12g} m")
                for i,h in enumerate(result['rows']):st.caption(f'Row {i+1} head loss: {h:.12g} m')
            else:st.caption('Velocity not entered; head loss not calculated.')
            if result['pressure_pa'] is not None:
                st.text(f"Minor pressure loss: {result['pressure_pa']:.12g} Pa | {result['pressure_kpa']:.12g} kPa | {result['pressure_bar']:.12g} bar")
            else:st.caption('No density assumed; pressure loss not calculated.')
        except ValueError as exc:st.error(str(exc))
