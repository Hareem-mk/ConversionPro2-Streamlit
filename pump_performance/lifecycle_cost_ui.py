"""Explicit financial assumptions and label-only currency, separate from the core."""
from .lifecycle_cost import (calculate_economic_comparison, annual_costs_from_energy, initial_cost, LOWER_INITIAL)

GUIDANCE=(
    'Lifecycle economics depend on initial cost and future operating costs. Simple payback ignores the time value of money; NPV accounts for the selected discount rate and analysis period.',
    'Use realistic annual duty-cycle energy and operating costs. Maintenance differences should be user/vendor/project supplied.',
    'Discount rate and escalation assumptions should be applied consistently on either a nominal or real basis.',
    'Positive NPV indicates lower discounted lifecycle cost under the entered assumptions, not automatic project approval. Final investment decisions should consider uncertainty, reliability, process requirements, project risk and company economic criteria.'
)

def cash_flow_chart_spec(rows, currency, discounted=False):
    field='cumulative_discounted' if discounted else 'cumulative_undiscounted'
    title='Cumulative Discounted Cash Flow by Year' if discounted else 'Cumulative Undiscounted Cash Flow by Year'
    return {'title':title,'layer':[{'data':{'values':[{'year':r.year,'cash':getattr(r,field)} for r in rows]},'mark':{'type':'line','point':True}}],
        'encoding':{'x':{'field':'year','type':'quantitative','title':'Year','axis':{'tickMinStep':1}},
        'y':{'field':'cash','type':'quantitative','title':currency or 'Currency (label not entered)'},
        'tooltip':[{'field':'year'},{'field':'cash','type':'quantitative','format':'.12g'}]},'height':280}


def render_lifecycle_cost():
    import streamlit as st
    st.subheader('3W — Pump Lifecycle Cost / VSD Economic Evaluation')
    st.caption('Compare two user-defined alternatives. Currency is a label only; no exchange-rate conversion. No financial assumption is prepopulated.')
    def number(label,key):return st.number_input(label,value=None,format='%.12g',key='p3w_'+key)
    left,right=st.columns(2)
    with left:name_a=st.text_input('Baseline Alternative Name',value='',key='p3w_name_a')
    with right:name_b=st.text_input('Proposed Alternative Name',value='',key='p3w_name_b')
    currency=st.text_input('Currency Label',value='',key='p3w_currency').strip()
    unit=currency or 'currency (label not entered)'
    source=st.selectbox('Annual Operating-Cost Source',('Manual Annual Operating Costs','Phase 3V Electrical Energy / Cost Kernel'),key='p3w_source')
    st.caption('Phase 3V source: enter annual electrical-energy totals from Phase 3V or verified duty data on the same electrical boundary for both alternatives. Pricing calls the existing Phase 3V kernel; no annual-energy model is duplicated.')
    a=b=None; energy_a=energy_b=tariff=None
    if source=='Manual Annual Operating Costs':
        a=number(f'Baseline Annual Operating Cost ({unit}/year)','cost_a')
        b=number(f'Proposed Annual Operating Cost ({unit}/year)','cost_b')
    else:
        energy_a=number('Baseline Annual Electrical Energy (kWh/year)','energy_a')
        energy_b=number('Proposed Annual Electrical Energy (kWh/year)','energy_b')
        tariff=number(f'Electricity Tariff ({unit}/kWh)','tariff')
    st.markdown('**Initial CAPEX**')
    mode=st.selectbox('Initial Cost Method',('Simple CAPEX — All-In Initial Costs','Detailed Proposed CAPEX Breakdown'),key='p3w_capex_mode')
    ia=number(f'Baseline CAPEX — All-In Initial Cost ({unit})','capex_a')
    ib=number(f'Proposed CAPEX — All-In Initial Cost ({unit})' if mode.startswith('Simple') else f'Proposed Equipment CAPEX Only ({unit})','capex_b' if mode.startswith('Simple') else 'equipment')
    details={}
    if mode.startswith('Detailed'):
        st.caption('Proposed equipment CAPEX plus entered one-time costs replaces the simple all-in proposed CAPEX. Do not include these costs twice. Baseline CAPEX remains all-in.')
        for key,label in [('installation','Installation'),('engineering','Engineering'),('commissioning','Commissioning'),('other','Other One-Time')]:
            details[key]=number(f'Proposed {label} Cost ({unit})',key)
    st.markdown('**Optional Maintenance Costs**')
    ma=number(f'Baseline Annual Maintenance Cost ({unit}/year)','maintenance_a')
    mb=number(f'Proposed Annual Maintenance Cost ({unit}/year)','maintenance_b')
    st.caption('Manual annual operating costs must exclude maintenance entered separately above. Blank optional costs are excluded, not inferred.')
    st.markdown('**Analysis Period and Discount Rate**')
    years=st.number_input('Analysis Period (integer years)',value=None,step=1,key='p3w_years')
    rate=number('Annual Discount Rate (%)','discount')
    st.markdown('**Optional Escalation / Residual Value**')
    escalation=number('Annual Operating / Energy-Cost Escalation (%)','escalation')
    ra=number(f'Baseline Residual Value at End of Analysis ({unit})','residual_a')
    rb=number(f'Proposed Residual Value at End of Analysis ({unit})','residual_b')
    st.caption('Year 0 contains initial costs; future cash flows occur at each year end. Year 1 uses entered operating costs; escalation starts in Year 2 and applies only to operating/energy costs. Maintenance is constant. Residual value is a terminal benefit. Blank escalation means no escalation contribution is applied. Entered escalation must exceed −100%.')
    if st.button('Calculate Lifecycle Economics',key='p3w_calculate'):
        try:
            if not source.startswith('Manual'):a,b=annual_costs_from_energy(energy_a,energy_b,tariff)
            total_b=initial_cost(ib,**details)
            result=calculate_economic_comparison(a,b,ia,total_b,years,rate,baseline_maintenance=ma,proposed_maintenance=mb,escalation_percent=escalation,baseline_residual=ra,proposed_residual=rb)
            def money(value):return f'{value:.12g} {unit}'
            st.markdown('**Economic Results**')
            st.text(f'Baseline Alternative: {name_a or "Baseline"}\nProposed Alternative: {name_b or "Proposed"}\nAnnual Cost Source: {source}\nCurrency Label: {currency or "not entered"}\nBaseline Annual Operating Cost: {money(a)}/year\nProposed Annual Operating Cost: {money(b)}/year\nCalculated Annual Operating Cost Difference: {money(result.annual_cost_difference)}/year\nBaseline Initial Cost: {money(result.baseline.initial_cost)}\nProposed Initial Cost: {money(result.proposed.initial_cost)}\nIncremental CAPEX: {money(result.incremental_capex)}\nSimple Payback: {str(result.simple_payback_years)+" years" if result.simple_payback_years is not None else "not defined"}\nAnalysis Period: {years} years\nAnnual Discount Rate: {rate:.12g}%\nNet Present Value — Proposed vs Baseline: {money(result.npv)}\nDiscounted Payback: {str(result.discounted_payback_year)+" years (first year-end crossing)" if result.discounted_payback_year is not None else "not reached / not applicable"}\nBaseline Lifecycle Cost: {money(result.baseline.lifecycle_cost)}\nProposed Lifecycle Cost: {money(result.proposed.lifecycle_cost)}\nLifecycle Cost Difference — Baseline minus Proposed: {money(result.lifecycle_cost_difference)}')
            st.info(result.simple_payback_status)
            if result.incremental_capex<0:st.info(LOWER_INITIAL)
            st.info(result.discounted_payback_status)
            st.caption('Simple payback uses entered annual operating-cost difference only, without maintenance, escalation or terminal residual. NPV and discounted payback include those separately entered contributions. All calculations retain full internal precision.')
            st.markdown('**Lifecycle Cost Components**')
            for label,cost in [('Baseline',result.baseline),('Proposed',result.proposed)]:
                st.text(f'{label}: Initial Cost {money(cost.initial_cost)}; PV Operating Costs {money(cost.pv_operating_cost)}; PV Maintenance {money(cost.pv_maintenance_cost)}; less PV Residual {money(cost.pv_residual_value)}; Lifecycle Cost {money(cost.lifecycle_cost)}')
            if details:
                st.text('Proposed Equipment CAPEX: '+money(ib)+'\n'+'\n'.join(f'{key.title()}: '+(money(value) if value is not None else 'not entered; excluded') for key,value in details.items()))
            st.markdown('**Annual Cash-Flow Table**')
            st.caption('All monetary columns use '+unit+'. Annual operating-cost difference = baseline minus proposed; maintenance difference uses the same sign. Terminal residual difference = proposed minus baseline. Year 0 net cash flow = negative incremental CAPEX. Tables may scroll horizontally on narrow screens.')
            headers=['Year','Baseline Operating Cost','Proposed Operating Cost','Annual Cost Difference','Maintenance Difference','Terminal Residual Difference','Net Incremental Cash Flow','Discount Factor','Discounted Cash Flow','Cumulative Undiscounted','Cumulative Discounted']
            lines=['<div role="region" aria-label="Scrollable Annual Cash-Flow Table" tabindex="0" style="overflow-x:auto;max-width:100%"><table style="border-collapse:collapse;min-width:100%"><thead><tr>'+''.join('<th style="padding:8px;border:1px solid #666;text-align:left;min-width:85px">'+h+'</th>' for h in headers)+'</tr></thead><tbody>']
            for row in result.rows:
                vals=[row.year,row.baseline_operating_cost,row.proposed_operating_cost,row.annual_cost_difference,row.maintenance_difference,row.terminal_residual_difference,row.net_cash_flow,row.discount_factor,row.discounted_cash_flow,row.cumulative_undiscounted,row.cumulative_discounted]
                lines.append('<tr>'+''.join(f'<td style="padding:8px;border:1px solid #666;white-space:nowrap">{v:.12g}</td>' for v in vals)+'</tr>')
            st.markdown(''.join(lines)+'</tbody></table></div>',unsafe_allow_html=True)
            for discounted in (False,True):st.vega_lite_chart(cash_flow_chart_spec(result.rows,currency,discounted),use_container_width=True)
        except (ValueError,OverflowError) as error:st.error(str(error))
    st.markdown('**Engineering Guidance**')
    for text in GUIDANCE:st.write(text)
