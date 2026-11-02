"""Phase 3X delegation, deterministic thresholds, scenarios and real UI coverage."""
import unittest,math,hashlib
from pathlib import Path
from dataclasses import replace,FrozenInstanceError
from unittest.mock import patch
from pump_performance import economic_sensitivity as core,economic_sensitivity_ui as ui
ROOT=Path(__file__).resolve().parents[1]
def base(**changes):
    values=dict(baseline_capex=0,proposed_capex=120000,analysis_years=5,discount_rate_percent=0,baseline_annual_cost=100000,proposed_annual_cost=70000);values.update(changes);return core.EconomicCase(**values)
def energy(**changes):
    values=dict(source=core.ENERGY,baseline_energy_kwh=49000,proposed_energy_kwh=40000,tariff=.12);values.update(changes);return base(**values)
def power(**changes):
    values=dict(source=core.POWER,baseline_power_kw=10,proposed_power_kw=8,operating_hours=4000,tariff=.12);values.update(changes);return base(**values)
def series(variable,values,case=None,**kw):return core.run_one_variable_sensitivity(case or base(),variable,values,**kw)

class SensitivityCoreTests(unittest.TestCase):
    def test_base_case_delegates_full_phase3w(self):
        with patch.object(core.lifecycle_cost,'calculate_economic_comparison',wraps=core.lifecycle_cost.calculate_economic_comparison) as spy:r=core.evaluate_economic_scenario(base()).result
        self.assertEqual(spy.call_count,1);self.assertEqual((r.annual_cost_difference,r.incremental_capex,r.simple_payback_years,r.npv),(30000,120000,4,30000))
    def test_capex_payback_sequence(self):self.assertEqual([p.result.simple_payback_years for p in series(core.CAPEX,[90000,120000,150000,180000]).points],[3,4,5,6])
    def test_capex_npv_sequence(self):self.assertEqual([p.result.npv for p in series(core.CAPEX,[90000,120000,150000,180000]).points],[60000,30000,0,-30000])
    def test_oat_keeps_other_inputs(self):
        b=base(baseline_maintenance=123,proposed_residual=456,escalation_percent=2)
        for p in series(core.CAPEX,[90000,150000],b).points:self.assertEqual(replace(p.case,proposed_capex=b.proposed_capex),b)
    def test_percentage_variation(self):self.assertEqual([p.value for p in series(core.CAPEX,[-25,0,25,50],percentage=True).points],[90000,120000,150000,180000])
    def test_zero_base_percentage(self):self.assertEqual([p.value for p in series(core.DISCOUNT,[-20,0,20],percentage=True).points],[0,0,0])
    def test_fractional_period_not_rounded(self):
        p=series(core.PERIOD,[10],percentage=True).points[0];self.assertEqual(p.value,5.5);self.assertIsNone(p.result);self.assertIn('integer',p.error)
    def test_annual_difference_sequence(self):
        r=series(core.DIFFERENCE,[20000,25000,30000,35000,40000]);self.assertEqual([p.result.npv for p in r.points],[-20000,5000,30000,55000,80000]);self.assertEqual([p.result.simple_payback_years for p in r.points],[6,4.8,4,120000/35000,3])
    def test_annual_difference_holds_baseline(self):
        p=series(core.DIFFERENCE,[24000]).points[0];self.assertEqual(p.case.baseline_annual_cost,100000);self.assertEqual(p.case.proposed_annual_cost,76000)
    def test_discount_sequence_phase3w(self):
        r=series(core.DISCOUNT,[0,5,10,15]);npvs=[p.result.npv for p in r.points];self.assertEqual(npvs,sorted(npvs,reverse=True));self.assertAlmostEqual(npvs[2],-6276.396917746559,8)
        for p in r.points:self.assertEqual(p.result,core.evaluate_economic_scenario(p.case).result)
    def test_analysis_period_sequence(self):
        r=series(core.PERIOD,[3,4,5,6,10]);self.assertEqual([p.result.npv for p in r.points],[-30000,0,30000,60000,180000]);self.assertEqual([p.result.simple_payback_years for p in r.points],[4]*5)
    def test_tariff_sequence_reuses_phase3v(self):
        with patch.object(core.annual_energy,'calculate_operating_cost',wraps=core.annual_energy.calculate_operating_cost) as spy:r=series(core.TARIFF,[.08,.10,.12,.15],energy())
        self.assertGreaterEqual(spy.call_count,8);self.assertEqual([p.result.annual_cost_difference for p in r.points],[720,900,1080,1350])
    def test_constant_power_hours_phase3v(self):
        with patch.object(core.annual_energy,'calculate_energy',wraps=core.annual_energy.calculate_energy) as spy:r=series(core.HOURS,[2000,4000,6000],power())
        self.assertGreaterEqual(spy.call_count,6);self.assertEqual([core.electrical_energies(p.case)[0] for p in r.points],[20000,40000,60000]);self.assertEqual([p.result.annual_cost_difference for p in r.points],[480,960,1440])
    def test_variables_only_with_valid_data(self):
        self.assertEqual(set(core.available_variables(base())),{core.CAPEX,core.DIFFERENCE,core.DISCOUNT,core.PERIOD});self.assertNotIn(core.HOURS,core.available_variables(energy()));self.assertIn(core.HOURS,core.available_variables(power()))
        with self.assertRaises(ValueError):series(core.HOURS,[2000],energy())
    def test_invalid_points_preserved_as_na(self):
        r=series(core.CAPEX,[-1,90000]);self.assertIsNone(r.points[0].result);self.assertTrue(r.points[0].error);self.assertEqual(r.points[1].result.npv,60000)
    def test_nonfinite_and_empty_range_rejected(self):
        for values in [[],[None],[True],[math.nan],[math.inf]]:
            with self.assertRaises(ValueError):series(core.CAPEX,values)
    def test_invalid_base_and_source_rejected(self):
        for case in [base(proposed_capex=None),base(analysis_years=0),base(discount_rate_percent=-1),base(source='unknown')]:
            with self.assertRaises(ValueError):core.evaluate_economic_scenario(case)
    def test_undefined_payback_and_negative_npv(self):
        r=series(core.DIFFERENCE,[0,-10000]);self.assertEqual([p.result.simple_payback_years for p in r.points],[None,None]);self.assertEqual([p.result.npv for p in r.points],[-120000,-170000])
    def test_discounted_payback_exact_phase3w(self):
        r=series(core.DISCOUNT,[0,10]);self.assertEqual(r.points[0].result.discounted_payback_year,4);self.assertIsNone(r.points[1].result.discounted_payback_year);self.assertEqual(r.points[1].result.discounted_payback_status,core.lifecycle_cost.NOT_RECOVERED)
    def test_break_even_capex(self):
        r=core.calculate_break_even_capex(base());self.assertEqual(r.value,150000);self.assertEqual(r.npv_at_threshold,0)
    def test_break_even_capex_incremental_not_proposed(self):
        b=base(baseline_capex=10000);r=core.calculate_break_even_capex(b);self.assertEqual(r.value,150000);self.assertEqual(core.evaluate_economic_scenario(replace(b,proposed_capex=160000)).result.npv,0)
    def test_break_even_difference(self):
        r=core.calculate_break_even_annual_cost_difference(base());self.assertEqual(r.value,24000);self.assertEqual(r.npv_at_threshold,0)
    def test_break_even_period_decimal(self):
        self.assertEqual(core.calculate_break_even_analysis_period(base()).value,4);self.assertEqual(core.calculate_break_even_analysis_period(base(proposed_capex=125000)).value,125000/30000)
    def test_period_threshold_restrictions(self):
        for changes in [dict(discount_rate_percent=5),dict(escalation_percent=1),dict(proposed_residual=1),dict(proposed_capex=0),dict(proposed_annual_cost=100000)]:self.assertIsNone(core.calculate_break_even_analysis_period(base(**changes)).value)
    def test_period_threshold_maintenance(self):self.assertEqual(core.calculate_break_even_analysis_period(base(baseline_maintenance=5000,proposed_maintenance=1000)).value,120000/34000)
    def test_break_even_tariff_point_eight(self):
        r=core.calculate_break_even_tariff(energy(baseline_energy_kwh=70000));self.assertEqual(r.value,.8);self.assertEqual(r.npv_at_threshold,0)
    def test_break_even_optional_costs_remain_included(self):
        b=base(discount_rate_percent=8,baseline_maintenance=4000,proposed_maintenance=2000,escalation_percent=3,baseline_residual=5000,proposed_residual=10000)
        for r in [core.calculate_break_even_capex(b),core.calculate_break_even_annual_cost_difference(b)]:self.assertAlmostEqual(r.npv_at_threshold,0,8)
        e=replace(b,source=core.ENERGY,baseline_energy_kwh=49000,proposed_energy_kwh=40000,tariff=.12)
        self.assertAlmostEqual(core.calculate_break_even_tariff(e).npv_at_threshold,0,8)
    def test_break_even_infeasible_no_fake_zero(self):
        self.assertIsNone(core.calculate_break_even_capex(base(proposed_annual_cost=200000)).value)
        self.assertIsNone(core.calculate_break_even_annual_cost_difference(base(baseline_annual_cost=1)).value)
        self.assertIsNone(core.calculate_break_even_tariff(base()).value)
        self.assertIsNone(core.calculate_break_even_tariff(energy(proposed_energy_kwh=50000)).value)
    def test_scenarios_independent_and_invalid_retained(self):
        rows=core.evaluate_scenarios([('A',base()),('B',base(proposed_capex=90000)),('missing',base(discount_rate_percent=None))]);self.assertEqual(rows[0].result.npv,30000);self.assertEqual(rows[1].result.npv,60000);self.assertIsNone(rows[2].result);self.assertTrue(rows[2].error)
    def test_ranking_explicit_and_all_three_metrics(self):
        rows=core.evaluate_scenarios([('A',base()),('B',base(proposed_capex=90000))])
        with self.assertRaises(ValueError):core.rank_scenarios(rows,None)
        for metric in core.RANK_METRICS:self.assertEqual(core.rank_scenarios(rows,metric)[0].name,'B')
    def test_ranking_metrics_can_differ(self):
        rows=core.evaluate_scenarios([('long',base(analysis_years=10)),('short',base(proposed_capex=90000,analysis_years=3))]);self.assertEqual(core.rank_scenarios(rows,core.RANK_METRICS[0])[0].name,'long');self.assertEqual(core.rank_scenarios(rows,core.RANK_METRICS[1])[0].name,'short');self.assertEqual(core.rank_scenarios(rows,core.RANK_METRICS[2])[0].name,'short')
    def test_rank_undefined_last_and_ties_stable(self):
        rows=core.evaluate_scenarios([('undefined',base(proposed_annual_cost=100000)),('A',base()),('B',base())]);self.assertEqual([r.name for r in core.rank_scenarios(rows,core.RANK_METRICS[2])],['A','B','undefined'])
    def test_immutable_and_precision(self):
        r=series(core.CAPEX,[120000.123456789]);self.assertEqual(r.points[0].result.incremental_capex,120000.123456789)
        with self.assertRaises(FrozenInstanceError):r.base_value=0
    def test_plot_markers_zero_reference_and_gaps(self):
        s=series(core.DIFFERENCE,[-1,0,30000]);spec=ui.sensitivity_plot_spec(s,'QAR');self.assertNotIn('data',spec);self.assertTrue(any(layer['mark'].get('shape')=='diamond' for layer in spec['layer']));self.assertTrue(any('zero' in layer['data']['values'][0] for layer in spec['layer']))
        spec=ui.sensitivity_plot_spec(s,'QAR',True);self.assertIsNone(spec['layer'][0]['data']['values'][0]['metric']);self.assertEqual(spec['encoding']['y']['title'],'Simple Payback (years)')
    def test_all_prior_python_files_unchanged(self):
        for path,digest in BASELINE_HASHES.items():
            data=(ROOT/path).read_bytes()
            if path=='tests/test_phase3w_lifecycle_cost.py':
                text=data.decode();self.assertEqual(text.count('len(at.expander),31'),1)
                data=text.replace('len(at.expander),31','len(at.expander),28',1).encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest,path)

class SensitivityAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_string('from pump_performance.economic_sensitivity_ui import render_economic_sensitivity\nrender_economic_sensitivity()').run()
    def fill_case(self,at,prefix='p3x_base_',**changes):
        fields=dict(cost_a=100000,cost_b=70000,capex_a=0,capex_b=120000,years=5,discount=0);fields.update(changes)
        for key,value in fields.items():at.number_input(key=prefix+key).set_value(value)
        return at
    def setup(self,variable=core.CAPEX,values='90000\n120000\n150000\n180000',**changes):
        at=self.fill_case(self.app(),**changes);at.run();at.selectbox(key='p3x_variable').select(variable);at.text_area(key='p3x_values').set_value(values);return at
    def calc(self,at):at.button(key='p3x_evaluate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def md(self,at):return '\n'.join(w.value for w in list(at.markdown)+list(at.caption))
    def test_full_app_registration(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(ROOT/'app.py')).run();self.assertFalse(at.exception);self.assertEqual(len(at.expander),31);self.assertTrue(any(e.label==ui.TITLE for e in at.expander))
    def test_blank_inputs_no_range_no_checkboxes(self):
        at=self.app();self.assertFalse(at.exception)
        for w in at.number_input:self.assertIsNone(w.value,w.label)
        self.assertEqual(at.text_area(key='p3x_values').value,'');self.assertEqual(at.text_input(key='p3x_currency').value,'');self.assertIsNone(at.selectbox(key='p3x_variable').value);self.assertFalse(at.checkbox)
    def test_manual_capex_benchmark_ui(self):
        at=self.calc(self.setup());self.assertIn('Simple Payback: 4 years',self.text(at));self.assertIn('NPV: 30000',self.text(at))
        for val in ['60000','30000','-30000','90000','180000']:self.assertIn('>'+val+'</td>',self.md(at))
        self.assertIn('Break-Even Incremental CAPEX under Entered Assumptions: 150000',self.text(at));self.assertIn('Break-Even Annual Operating Cost Difference under Entered Assumptions: 24000',self.text(at));self.assertIn('Break-Even Analysis Period under Entered Assumptions: 4',self.text(at))
    def test_cost_difference_ui(self):
        at=self.calc(self.setup(core.DIFFERENCE,'20000\n25000\n30000\n35000\n40000'))
        for n in ['-20000','5000','55000','80000']:self.assertIn('>'+n+'</td>',self.md(at))
    def test_discount_ui(self):
        at=self.calc(self.setup(core.DISCOUNT,'0\n5\n10\n15'));self.assertIn('>-6276.39691775</td>',self.md(at));self.assertIn('Not reached within selected analysis period.',self.md(at))
    def test_period_ui(self):
        at=self.calc(self.setup(core.PERIOD,'3\n4\n5\n6\n10'));self.assertIn('>180000</td>',self.md(at));self.assertIn('>60000</td>',self.md(at))
    def test_percentage_ui(self):
        at=self.setup(values='-25\n0\n25\n50');at.selectbox(key='p3x_value_method').select('Percentage Variation (%)');self.calc(at);self.assertIn('>90000</td>',self.md(at));self.assertIn('>180000</td>',self.md(at))
    def test_tariff_ui_calls_existing_kernel(self):
        at=self.app();at.selectbox(key='p3x_base_source').select(core.ENERGY).run()
        for key,value in dict(energy_a=49000,energy_b=40000,tariff=.12,capex_a=0,capex_b=120000,years=5,discount=0).items():at.number_input(key='p3x_base_'+key).set_value(value)
        at.run();at.selectbox(key='p3x_variable').select(core.TARIFF);at.text_area(key='p3x_values').set_value('.08\n.10\n.12\n.15')
        with patch.object(core.annual_energy,'calculate_operating_cost',wraps=core.annual_energy.calculate_operating_cost) as spy:self.calc(at)
        self.assertGreaterEqual(spy.call_count,8)
        for n in ['720','900','1080','1350']:self.assertIn('>'+n+'</td>',self.md(at))
    def test_hours_ui(self):
        at=self.app();at.selectbox(key='p3x_base_source').select(core.POWER).run()
        for key,value in dict(power_a=10,power_b=8,hours=4000,tariff=.12,capex_a=0,capex_b=120000,years=5,discount=0).items():at.number_input(key='p3x_base_'+key).set_value(value)
        at.run();at.selectbox(key='p3x_variable').select(core.HOURS);at.text_area(key='p3x_values').set_value('2000\n4000\n6000');self.calc(at)
        for n in ['480','960','1440']:self.assertIn('>'+n+'</td>',self.md(at))
    def test_undefined_paybacks_not_zero(self):
        at=self.calc(self.setup(core.DIFFERENCE,'0\n-10000'));self.assertIn('>N/A</td>',self.md(at));self.assertIn('>-170000</td>',self.md(at))
    def test_invalid_point_no_clamp(self):
        at=self.calc(self.setup(values='-1\n90000'));self.assertIn('Invalid input:',self.md(at));self.assertIn('>60000</td>',self.md(at))
    def test_missing_range_rejected(self):
        at=self.calc(self.setup(values=''));self.assertTrue(at.error);self.assertNotIn('Base Economic Results',self.md(at))
    def test_invalid_base_rejected(self):
        at=self.calc(self.app());self.assertTrue(at.error)
    def test_fractional_year_variation_invalid(self):
        at=self.setup(core.PERIOD,'10');at.selectbox(key='p3x_value_method').select('Percentage Variation (%)');self.calc(at);self.assertIn('>5.5</td>',self.md(at));self.assertIn('integer',self.md(at))
    def multi(self):
        at=self.app();at.selectbox(key='p3x_analysis').select('Multi-Scenario Comparison').run();self.fill_case(at,'p3x_s0_');self.fill_case(at,'p3x_s1_',capex_b=90000);at.text_input(key='p3x_s0_name').set_value('Entered A');at.text_input(key='p3x_s1_name').set_value('Entered B');return at
    def test_multi_explicit_no_inheritance_defaults(self):
        at=self.app();at.selectbox(key='p3x_analysis').select('Multi-Scenario Comparison').run();self.assertIsNone(at.selectbox(key='p3x_rank').value)
        for w in at.number_input:
            if w.key!='p3x_count':self.assertIsNone(w.value)
        self.assertFalse(at.checkbox)
    def test_multi_comparison_unranked(self):
        at=self.multi();at.button(key='p3x_scenarios').click().run();self.assertFalse(at.exception);md=self.md(at);self.assertIn('Unranked — entry order',md);self.assertIn('>Entered A</td>',md);self.assertIn('>Entered B</td>',md);self.assertLess(md.index('>Entered A</td>'),md.index('>Entered B</td>'));self.assertIn('>60000</td>',md)
    def test_explicit_ranking_ui(self):
        at=self.multi();at.selectbox(key='p3x_rank').select(core.RANK_METRICS[0]);at.button(key='p3x_scenarios').click().run();self.assertTrue(any('Ranked by selected metric.' in w.value for w in at.info));self.assertLess(self.md(at).index('>Entered B</td>'),self.md(at).index('>Entered A</td>'))
    def test_missing_scenario_not_inherited(self):
        at=self.multi();at.number_input(key='p3x_s1_discount').set_value(None);at.button(key='p3x_scenarios').click().run();self.assertIn('Invalid input:',self.md(at));self.assertIn('>30000</td>',self.md(at))
    def test_currency_names_escaped_no_conversion(self):
        at=self.setup();at.text_input(key='p3x_currency').set_value('QAR');self.calc(at);self.assertIn('NPV: 30000 QAR',self.text(at));at.text_input(key='p3x_currency').set_value('USD');self.calc(at);self.assertIn('NPV: 30000 USD',self.text(at))
        at=self.multi();at.text_input(key='p3x_s0_name').set_value('<b>A</b>');at.button(key='p3x_scenarios').click().run();self.assertIn('&lt;b&gt;A&lt;/b&gt;',self.md(at))
    def test_charts_markers_units_scroll(self):
        at=self.calc(self.setup());self.assertEqual(len(at.get('vega_lite_chart')),2);self.assertIn('overflow-x:auto;max-width:100%',self.md(at));self.assertIn('zero-NPV reference',self.md(at));self.assertIn('diamond',self.md(at))
    def test_guidance_scope_no_extra_widgets(self):
        at=self.app();text=self.md(at)
        for sentence in ui.GUIDANCE:self.assertIn(sentence,text)
        for phrase in ['P10','P50','P90','confidence interval','Monte Carlo','guaranteed savings']:self.assertNotIn(phrase,text)
        self.assertFalse(at.checkbox)
    def test_stale_results_removed_on_edit(self):
        at=self.calc(self.setup());at.number_input(key='p3x_base_capex_b').set_value(130000).run();self.assertNotIn('NPV:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))

BASELINE_HASHES = {'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/annual_energy.py': 'f045aa111fb96d38485b8e9b5e270a1a2b798114612173e256dc7dc9401dc108', 'pump_performance/annual_energy_ui.py': '797a0e013a1d0c870de12e8dddfc191d268a8846b8ce042dc274780857eba382', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/control_strategy.py': 'ba639b265ebeaaa6baa878b102591c8f8fa7222b223df1a289fa11ee4a78127e', 'pump_performance/control_strategy_ui.py': '13b63e57b7d58d88127a4643fa524e5e8640577836097447a3348537e480bfca', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/lifecycle_cost.py': '185a04b2ad59a5a6ed6a8a316c0e98352aea7157c713fa05d0a8085bf871a685', 'pump_performance/lifecycle_cost_ui.py': '3b27a28c06f9c632161d446fec24ba32c0e62bd8e4393f4156156cb736806b6c', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase3u_control_strategy.py': 'd07890f6e10820eebbcbd3d268877eb1cb1afda752bb8764f72c2005e07dd4ac', 'tests/test_phase3v_annual_energy.py': '04538377205a188dbf53f2938eacd58960d64b993da0f8b955347630d919b217', 'tests/test_phase3w_lifecycle_cost.py': '59f79d659993da558155a0db2347e5baf3359551b0fd87f1bb96acd2b0ea4a06'}
