"""Editable duty rows and explicitly separated energy boundaries; no pandas."""
from .annual_energy import (DutyPoint,evaluate_duty_profile,compare_control_alternatives,METHODS,BASES,ENERGY_LABELS,SUPPLY_BASES)
from .pump_curve import create_pump_curve,curve_flow_to_si,HEAD_FACTORS
from .power_curve import create_power_curve
from .shaft_power import POWER_FACTORS
from .system_curve import model_from_k,model_from_reference
from .variable_speed_ui import _points

GUIDANCE=(
    'Annual energy depends on both applicable operating power and operating duration. Hydraulic, shaft/brake, motor input and VFD electrical input power are different quantities. Totals retain each explicitly selected basis.',
    'Electrical energy and cost require valid electrical input power. Motor-terminal energy excludes unspecified upstream VFD losses and is kept separate from comparable supply electrical energy. Only one selected energy basis per duty row contributes to totals; intermediate power stages are not counted twice.',
    'Pump and motor efficiency may vary with operating point; VFD efficiency may vary with speed and load. No efficiency, tariff or hours are assumed. Affinity-scaled power is an engineering estimate; check manufacturer/vendor data.',
    'Operating profiles should represent realistic annual duty. Invalid or ambiguous modeled operating points produce no energy result. No pump or power curve is extrapolated, and no VSD speed is selected from multiple solutions automatically.',
    'Calculated difference under the supplied operating profile, efficiency assumptions, and power data. Results are not guaranteed savings. Final lifecycle decisions should consider reliability, maintenance, CAPEX, process-control requirements and vendor limits. Emissions, demand charges and automatic payback are not calculated.'
)
PRESERVE='Preserve Selected Input Basis'


def energy_display(value,unit):
    # Reuse the existing 1000 metric prefix factor; internal energy stays kWh.
    return value/(POWER_FACTORS['kW'] if unit=='MWh' else 1)


def profile_chart_spec(summary,energy_unit,hours=False):
    rows=[]
    for i,r in enumerate(summary.rows,1):
        value=r.hours if hours else (energy_display(r.energy_kwh,energy_unit) if r.energy_kwh is not None else None)
        if value is not None:rows.append({'case':f'{i}. {r.case}','value':value,'basis':'Entered Operating Hours' if hours else ENERGY_LABELS[r.energy_basis]})
    return {'title':'Operating Hours by Duty Point' if hours else 'Annual Energy by Duty Point — Labeled Bases',
        'layer':[{'data':{'values':rows},'mark':{'type':'bar'}}],'encoding':{
        'x':{'field':'case','type':'nominal','sort':None,'title':'Duty Period','axis':{'labelAngle':-30,'labelLimit':140}},
        'y':{'field':'value','type':'quantitative','title':'Operating Hours (h/year)' if hours else f'Annual Energy ({energy_unit}/year)'},
        'color':{'field':'basis','type':'nominal','title':'Basis','legend':{'orient':'bottom','columns':1,'labelLimit':500}},
        'tooltip':[{'field':'case'},{'field':'basis'},{'field':'value','type':'quantitative'}]},'height':340}


def render_annual_energy(flow_factors):
    import streamlit as st
    st.subheader('3V — Pump Annual Energy / Duty-Cycle Operating Cost Analysis')
    st.info('Enter 1–20 duty periods. Select each power/energy basis explicitly. Profile totals include every entered period; use the optional comparison only to inspect selected alternatives, not to remove rows from totals.')
    mode=st.selectbox('Annual Analysis Data',('Direct Power Rows Only','Include Pump / System Models'),key='p3v_analysis')
    fu=st.selectbox('Annual Duty Flow Unit',list(flow_factors),index=None,key='p3v_flow_unit')
    hu=st.selectbox('Annual Duty Head Unit',list(HEAD_FACTORS),index=None,key='p3v_head_unit')
    pu=st.selectbox('Annual Result Power Unit',list(POWER_FACTORS),index=1,key='p3v_display_power_unit')
    eu=st.selectbox('Annual Result Energy Unit',('kWh','MWh'),key='p3v_energy_unit')
    st.caption('Changing input units reinterprets entered numbers; it does not rewrite them. Direct-row flow is optional/informational. Modeled target flow is required. Speed is rpm and density kg/m³.')
    head_rows=power_rows=[];speed=static=k=reference=friction=density=None;pm=pfu=ppu=None
    if mode!='Direct Power Rows Only':
        st.markdown('**Pump / System Data**')
        head_rows=_points(st,'Annual Reference Head Curve','p3v_head',fu,hu)
        speed=st.number_input('Annual Reference Pump Speed (rpm)',value=None,format='%.12g',key='p3v_speed')
        density=st.number_input('Annual Fluid Density (kg/m³)',value=None,format='%.12g',key='p3v_density')
        method=st.selectbox('Annual System Method',('Direct K','Reference Flow / Friction Head'),key='p3v_system_method')
        static=st.number_input(f'Annual Static Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3v_static')
        if method=='Direct K':k=st.number_input('Annual System K — SI (s²/m⁵)',value=None,format='%.12g',key='p3v_k')
        else:
            reference=st.number_input(f'Annual Reference Flow ({fu or "select unit above"})',value=None,format='%.12g',key='p3v_reference_flow')
            friction=st.number_input(f'Annual Reference Friction Head ({hu or "select unit above"})',value=None,format='%.12g',key='p3v_friction')
        pm=st.selectbox('Annual Shaft Power Source',('No Vendor Power Curve — Hydraulic Basis Only','Reference-Speed Vendor Power Curve'),key='p3v_power_mode')
        if pm=='Reference-Speed Vendor Power Curve':
            pfu=st.selectbox('Annual Vendor Power Flow Unit',list(flow_factors),index=None,key='p3v_power_flow_unit')
            ppu=st.selectbox('Annual Vendor Power Value Unit',list(POWER_FACTORS),index=None,key='p3v_power_value_unit')
            power_rows=_points(st,'Annual Vendor Power Curve','p3v_power',pfu,ppu)
    st.markdown('**Duty Profile — Editable Rows**')
    count=st.number_input('Number of Annual Duty Periods',min_value=1,max_value=20,value=1,step=1,key='p3v_count')
    raw=[]
    for i in range(count):
        st.markdown(f'**Duty Period {i+1}**')
        a,b=st.columns(2)
        with a:name=st.text_input(f'Period {i+1} Case / Name',value='',key=f'p3v_name_{i}')
        with b:control=st.selectbox(f'Period {i+1} Control Method',METHODS,index=2,key=f'p3v_method_{i}')
        a,b=st.columns(2)
        with a:flow=st.number_input(f'Period {i+1} Target Flow ({fu or "select flow unit"})',value=None,format='%.12g',key=f'p3v_flow_{i}')
        with b:hours=st.number_input(f'Period {i+1} Operating Hours per Year',value=None,format='%.12g',key=f'p3v_hours_{i}')
        value=unit=basis=output=None;em=ev=None
        if control==METHODS[2]:
            a,b=st.columns(2)
            with a:value=st.number_input(f'Period {i+1} User-Supplied Power',value=None,format='%.12g',key=f'p3v_power_{i}')
            with b:unit=st.selectbox(f'Period {i+1} Power Unit',list(POWER_FACTORS),index=None,key=f'p3v_unit_{i}')
            basis=st.selectbox(f'Period {i+1} Supplied Power Basis',BASES[:4],index=None,key=f'p3v_basis_{i}')
            options=[PRESERVE]
            if basis=='Shaft Power':options+=['Motor Input Power','VFD Electrical Input Power']
            if basis=='Motor Input Power':options+=['VFD Electrical Input Power']
            conversion=st.selectbox(f'Period {i+1} Energy Conversion',options,key=f'p3v_conversion_{i}')
            output=None if conversion==PRESERVE else conversion
            if output in ('Motor Input Power','VFD Electrical Input Power') and basis=='Shaft Power':em=st.number_input(f'Period {i+1} Motor Efficiency (%)',value=None,format='%.12g',key=f'p3v_motor_{i}')
            if output=='VFD Electrical Input Power':ev=st.number_input(f'Period {i+1} VFD Efficiency (%)',value=None,format='%.12g',key=f'p3v_vfd_{i}')
        else:
            outputs=BASES[1:] if control==METHODS[1] else BASES[1:4]
            output=st.selectbox(f'Period {i+1} Applicable Energy Basis',outputs,index=None,key=f'p3v_output_{i}')
            if output in ('Motor Input Power','VFD Electrical Input Power'):em=st.number_input(f'Period {i+1} Motor Efficiency (%)',value=None,format='%.12g',key=f'p3v_motor_{i}')
            if output=='VFD Electrical Input Power':ev=st.number_input(f'Period {i+1} VFD Efficiency (%)',value=None,format='%.12g',key=f'p3v_vfd_{i}')
        notes=st.text_input(f'Period {i+1} Notes (optional)',value='',key=f'p3v_notes_{i}')
        raw.append((name,control,flow,hours,value,unit,basis,output,em,ev,notes))
    st.markdown('**Optional Electricity Cost**')
    tariff=st.number_input('Annual Electricity Cost per kWh (optional)',value=None,format='%.12g',key='p3v_tariff')
    currency=st.text_input('Annual Currency Label (optional)',value='',key='p3v_currency')
    st.caption('No tariff, hours or efficiencies are prefilled. Cost uses only explicitly selected electrical bases. Motor-terminal costs and supply-input costs remain separately labeled. Unknown/invalid periods are excluded from energy totals and remain visible.')
    st.markdown('**Optional Comparison of Selected Control Alternatives**')
    labels=[f'{i+1}. {row[0] or "Duty Period "+str(i+1)}' for i,row in enumerate(raw)]
    first=st.selectbox('Constant-Speed Alternative Row',labels,index=None,key='p3v_compare_constant')
    second=st.selectbox('VSD Alternative Row',labels,index=None,key='p3v_compare_vsd')
    st.caption('Alternatives must have the same target flow and hours. Constant-speed motor electrical input is compared with VSD supply electrical input including entered drive losses. All entered rows still contribute to their labeled profile totals; do not treat alternative rows as one asset schedule without reviewing overlap.')
    if st.button('Evaluate Annual Duty Profile',key='p3v_evaluate'):
        curve=system=power_curve=None
        if mode!='Direct Power Rows Only':
            try:
                curve=create_pump_curve(head_rows,fu,hu,flow_factors)
                system=model_from_k(static,hu,k) if method=='Direct K' else model_from_reference(static_head=static,head_unit=hu,reference_flow=reference,reference_friction_head=friction,flow_unit=fu,flow_factors=flow_factors)
            except (ValueError,OverflowError) as exc:st.error('Pump/system data: '+str(exc))
            if pm=='Reference-Speed Vendor Power Curve':
                try:power_curve=create_power_curve(power_rows,pfu,ppu,flow_factors)
                except (ValueError,OverflowError) as exc:st.error('Vendor power data: '+str(exc))
        rows=[]
        for i,(name,control,flow,hours,value,unit,basis,output,em,ev,notes) in enumerate(raw):
            q=None;error=None
            if flow is not None:
                try:q=curve_flow_to_si(flow,fu,flow_factors)
                except (ValueError,OverflowError) as exc:error=str(exc)
            rows.append(DutyPoint(name or f'Duty Period {i+1}',control,hours,q,value,unit,basis,output,em,ev,notes,error))
        try:
            result=evaluate_duty_profile(rows,curve=curve,reference_speed=speed,system=system,density=density,power_curve=power_curve,tariff=tariff)
            if result.warning:st.warning(result.warning)
            if not result.hours_complete:st.warning('Total hours include only validated hour entries. Correct invalid hours to obtain a complete profile total.')
            st.markdown('**Annual Duty Results**')
            def fmt(value,factor=1):return 'N/A' if value is None else f'{value/factor:.10g}'
            table='| Case | Control Method | Target Flow | Hours | Speed rpm | Head | Hydraulic Power | Shaft Power | Motor Input | VFD Input | Energy Basis | Annual Energy | Annual Cost | Status |\n|'+ '|'.join(['---']*14)+'|\n'
            for row in result.rows:
                values=[row.case,row.method,fmt(row.target_flow_si,flow_factors.get(fu,1)),fmt(row.hours),fmt(row.speed_rpm),fmt(row.head_m,HEAD_FACTORS.get(hu,1)),fmt(row.hydraulic_w,POWER_FACTORS[pu]),fmt(row.shaft_w,POWER_FACTORS[pu]),fmt(row.motor_w,POWER_FACTORS[pu]),fmt(row.vfd_w,POWER_FACTORS[pu]),ENERGY_LABELS.get(row.energy_basis,'N/A'),fmt(energy_display(row.energy_kwh,eu) if row.energy_kwh is not None else None),fmt(row.cost) if currency.strip() else 'N/A',row.status]
                table+='| '+' | '.join(str(v).replace('|',' / ').replace('\n',' ') for v in values)+' |\n'
            st.caption(f'Table units: flow {fu or "N/A"}; head {hu or "N/A"}; power {pu}; energy {eu}/year; cost {currency.strip() or "currency label not entered"}/year. Scroll the table horizontally; all fields are also listed per period below.')
            st.markdown(table)
            for i,row in enumerate(result.rows,1):
                st.text(f'Period {i}: {row.case}\nControl Method: {row.method}\nTarget Flow: {fmt(row.target_flow_si,flow_factors.get(fu,1))} {fu or "N/A"}\nOperating Hours: {fmt(row.hours)} h/year\nOperating Speed: {fmt(row.speed_rpm)} rpm\nOperating Head: {fmt(row.head_m,HEAD_FACTORS.get(hu,1))} {hu or "N/A"}\nHydraulic Power: {fmt(row.hydraulic_w,POWER_FACTORS[pu])} {pu}\nShaft Power: {fmt(row.shaft_w,POWER_FACTORS[pu])} {pu}\nMotor Input Power: {fmt(row.motor_w,POWER_FACTORS[pu])} {pu}\nCalculated VFD Electrical Input Power: {fmt(row.vfd_w,POWER_FACTORS[pu])} {pu}\nApplicable Energy Basis: {ENERGY_LABELS.get(row.energy_basis,"N/A")}\nApplicable Power: {fmt(row.applicable_w,POWER_FACTORS[pu])} {pu}\nAnnual Energy: {fmt(energy_display(row.energy_kwh,eu) if row.energy_kwh is not None else None)} {eu}/year\nTime Fraction: {fmt(row.time_fraction_percent)}%\nComparable Supply Electrical Energy Share: {fmt(row.electrical_share_percent)}%\nAnnual Cost: {fmt(row.cost) if currency.strip() else "N/A"} {currency.strip() or "currency not entered"}/year\nStatus: {row.status}\nNotes: {row.notes}')
            st.markdown('**Annual Summary — Selected Bases Only**')
            st.text(f'Total Operating Hours: {result.total_hours:.12g} h/year')
            totals=dict(result.energy_by_basis);costs=dict(result.cost_by_basis)
            for basis in BASES:
                value=totals.get(basis)
                st.text(f'Total {ENERGY_LABELS[basis]}: {fmt(energy_display(value,eu) if value is not None else None)} {eu}/year')
                if basis in costs and currency.strip():st.text(f'Annual Cost — {ENERGY_LABELS[basis]}: {fmt(costs[basis])} {currency.strip()}/year')
            st.text(f'Total Comparable Supply Electrical Energy: {fmt(energy_display(result.comparable_supply_kwh,eu) if result.comparable_supply_kwh is not None else None)} {eu}/year')
            if result.comparable_supply_cost is not None and currency.strip():st.text(f'Annual Comparable Supply Electrical Cost: {fmt(result.comparable_supply_cost)} {currency.strip()}/year')
            if tariff is not None and not currency.strip():st.info('Enter a currency label to display calculated electrical operating costs.')
            if any(r.energy_kwh is None for r in result.rows):st.info('Energy totals are partial: invalid or unavailable periods are listed with N/A energy and are not replaced by zero.')
            if first is not None and second is not None:
                try:
                    comparison=compare_control_alternatives(result.rows[labels.index(first)],result.rows[labels.index(second)])
                    st.text(f'Annual Electrical Energy Difference: {energy_display(comparison.difference_kwh,eu):+.10g} {eu}/year\nAnnual Electrical Energy Reduction: {fmt(comparison.reduction_percent)}%')
                    if comparison.difference_cost is not None and currency.strip():st.text(f'Annual Operating Cost Difference: {comparison.difference_cost:+.10g} {currency.strip()}/year')
                    st.caption('Calculated difference under the supplied operating profile, efficiency assumptions, and power data.')
                except ValueError as exc:st.info('Alternative comparison unavailable: '+str(exc))
            st.vega_lite_chart(spec=profile_chart_spec(result,eu),width='stretch')
            st.vega_lite_chart(spec=profile_chart_spec(result,eu,hours=True),width='stretch')
        except (ValueError,OverflowError) as exc:st.error(str(exc))
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.caption(text)
