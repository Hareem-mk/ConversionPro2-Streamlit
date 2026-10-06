"""Stage 2E: manual K to equivalent length using a supplied Darcy factor."""
from dataclasses import dataclass
import math
from .pipe_geometry import positive
from .pipe_capacity import nonnegative


@dataclass(frozen=True)
class EquivalentLength:
    le_over_d: float
    length_m: float
    length_ft: float


def equivalent_length(k, diameter_m, darcy_factor, *, also_counted_as_k=False):
    k=nonnegative(k,'K-factor')
    d=positive(diameter_m,'INTERNAL pipe diameter')
    f=positive(darcy_factor,'Darcy Friction Factor')
    if also_counted_as_k:
        raise ValueError('Double counting: use either K-based loss OR equivalent length for the same fitting, not both.')
    ratio=k/f
    length=ratio*d
    feet=length/.3048
    if any(not math.isfinite(x) or (k>0 and x==0) for x in (ratio,length,feet)):
        raise ValueError('Equivalent length exceeds the supported numeric range.')
    return EquivalentLength(ratio,length,feet)


def render_equivalent_length():
    import streamlit as st
    st.divider()
    st.subheader('Stage 2E — Equivalent Length')
    st.latex(r'L_e/D=K/f_D,\qquad L_e=KD/f_D')
    st.info('Darcy friction factor only: f_Darcy = 4 × f_Fanning. '
            'Convert a Fanning factor explicitly before entering it; no automatic conversion is performed.')
    st.caption('Equivalent length depends on the selected Darcy factor and can change with Reynolds number, '
               'pipe roughness and operating condition. Use INTERNAL diameter and a factor for that pipe/condition.')
    st.warning('Use either K-based loss OR equivalent-length representation for the same fitting, not both.')
    mode=st.selectbox('K input basis',['Individual fitting K','Total K — manual entry'],index=None,key='p2e_basis')
    st.caption('Total K must refer to the same pipe reference velocity, diameter and flow path. '
               'No Stage 2D result is transferred automatically; enter a reviewed value explicitly.')
    k=st.number_input('K-factor (dimensionless)',min_value=0.0,value=None,format='%.12g',key='p2e_k')
    d=st.number_input('INTERNAL pipe diameter (m)',min_value=0.0,value=None,format='%.12g',key='p2e_diameter')
    f=st.number_input('Darcy Friction Factor',min_value=0.0,value=None,format='%.12g',key='p2e_darcy')
    basis_ok=st.checkbox('I confirm the entered factor is Darcy and K uses this pipe’s reference velocity basis.',key='p2e_confirm')
    duplicate=st.checkbox('These fittings are also included as K-based minor losses in the same total calculation',key='p2e_duplicate')
    if st.button('Calculate equivalent length',key='p2e_calculate'):
        try:
            if mode is None:raise ValueError('Select individual or total K input basis.')
            if not basis_ok:raise ValueError('Confirm the Darcy factor and K reference basis.')
            result=equivalent_length(k,d,f,also_counted_as_k=duplicate)
            st.text(f'Input basis: {mode}\nLe/D: {result.le_over_d:.12g} (dimensionless)\n'
                    f'Equivalent length Le: {result.length_m:.12g} m | {result.length_ft:.12g} ft')
        except ValueError as exc:st.error(str(exc))
