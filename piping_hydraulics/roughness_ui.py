"""Stage 2C only. No roughness is transferred to other calculators."""
from .roughness import RECORDS, CAUTION, roughness_to_si, roughness_displays, roughness_ratio


def render_roughness():
    import streamlit as st
    st.divider()
    st.subheader('Stage 2C — Pipe Roughness Database')
    st.warning(CAUTION)
    st.write('ABSOLUTE ROUGHNESS ε is a length. It is not Hazen-Williams C, Manning n, '
             'or dimensionless relative roughness ε/D. No selection is transferred to another calculator.')
    labels = {f'{r.material} — {r.condition}': r for r in RECORDS}
    selection = st.selectbox('Roughness source', ['Manual Roughness', *labels], index=None,
                             placeholder='Select material or Manual Roughness', key='p2c_source')
    epsilon = None
    if selection == 'Manual Roughness':
        st.caption('Enter an engineering value with a known basis. Explicit zero represents a hydraulically smooth assumption.')
        raw = st.number_input('Manual absolute roughness ε', value=None, min_value=0.0,
                              format='%.12g', key='p2c_manual')
        unit = st.selectbox('Manual roughness unit', ['m','mm','µm'], index=None, key='p2c_unit')
        st.text_input('Manual basis/source or condition note (optional)', key='p2c_basis')
    elif selection in labels:
        record = labels[selection]
        epsilon = record.epsilon_m
        st.write(f'**Material:** {record.material} — **Condition:** {record.condition}')
        st.write(f'**Original absolute roughness:** {record.original_value:g} {record.original_units}')
        st.write(f'**Source:** [{record.source}]({record.url})')
        st.caption(record.edition + ' | ' + record.location)
        st.caption(record.notes)
    diameter = st.number_input('Optional INTERNAL diameter D (m) for ε/D', value=None,
                               min_value=0.0, format='%.12g', key='p2c_diameter')
    st.latex(r'\text{Relative roughness}=\varepsilon/D')
    if st.button('Show roughness / calculate ε/D', key='p2c_calculate'):
        try:
            if selection is None:
                raise ValueError('Select a roughness source; no material value is assumed.')
            if selection == 'Manual Roughness':
                epsilon = roughness_to_si(raw, unit)
            displays = roughness_displays(epsilon)
            st.text('Absolute roughness ε\n' + '\n'.join(f'{v:.12g} {u}' for u,v in displays.items()))
            if epsilon == 0:
                st.info('Explicit ε = 0: hydraulically smooth assumption; not a universal material property.')
            if diameter is not None:
                ratio = roughness_ratio(epsilon, diameter)
                st.text(f'Relative roughness ε/D: {ratio:.12g} (dimensionless)')
                if ratio > .05:
                    st.warning('This ratio exceeds the validated Phase 1 friction calculator limit ε/D ≤ 0.05. No friction factor calculated.')
            else:
                st.caption('No diameter entered; relative roughness not calculated.')
        except ValueError as exc:
            st.error(str(exc))
    st.caption('Included: four new-pipe EPA records. Concrete/concrete-lined has a published range '
               'and no fixed value is selected here; vitrified clay has no epsilon entry in that table. '
               'Use Manual Roughness for other conditions/products with a defensible basis.')
