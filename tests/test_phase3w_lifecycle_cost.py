"""Phase 3W financial timing, Phase 3V delegation, and real Streamlit UI paths."""
import math, unittest, hashlib, json
from pathlib import Path
from unittest.mock import patch
from dataclasses import FrozenInstanceError
from pump_performance import lifecycle_cost as core, lifecycle_cost_ui as ui
ROOT=Path(__file__).resolve().parents[1]

def benchmark(**kwargs):
    args=dict(baseline_annual_cost=100000,proposed_annual_cost=70000,baseline_initial_cost=0,proposed_initial_cost=120000,analysis_years=5,discount_rate_percent=0)
    args.update(kwargs);return core.calculate_economic_comparison(**args)

class EconomicCoreTests(unittest.TestCase):
    def test_annual_difference(self):self.assertEqual(benchmark().annual_cost_difference,30000)
    def test_incremental_capex(self):self.assertEqual(benchmark().incremental_capex,120000)
    def test_simple_payback(self):self.assertEqual(benchmark().simple_payback_years,4)
    def test_zero_discount_npv(self):self.assertEqual(benchmark().npv,30000)
    def test_ten_percent_npv(self):
        expected=math.fsum([-120000]+[30000/1.1**i for i in range(1,6)])
        self.assertAlmostEqual(benchmark(discount_rate_percent=10).npv,expected,8)
    def test_year_zero_and_end_year_cash(self):
        r=benchmark();self.assertEqual([x.net_cash_flow for x in r.rows],[-120000]+[30000]*5);self.assertEqual([x.year for x in r.rows],list(range(6)))
        self.assertEqual(core.discount_cash_flow(110,10,1),100)
    def test_npv_general_signed_flows(self):self.assertAlmostEqual(core.calculate_npv(10,[20,-10,30],10),-10+20/1.1-10/1.1**2+30/1.1**3)
    def test_discounted_recovery(self):self.assertEqual(benchmark().discounted_payback_year,4)
    def test_discounted_not_reached(self):
        r=benchmark(discount_rate_percent=10);self.assertIsNone(r.discounted_payback_year);self.assertEqual(r.discounted_payback_status,core.NOT_RECOVERED)
    def test_lifecycle_components(self):
        r=benchmark();self.assertEqual(r.baseline.lifecycle_cost,500000);self.assertEqual(r.proposed.lifecycle_cost,470000);self.assertEqual(r.baseline.pv_operating_cost,500000);self.assertEqual(r.proposed.initial_cost,120000);self.assertEqual(r.lifecycle_cost_difference,r.npv)
    def test_maintenance_difference(self):
        r=benchmark(baseline_maintenance=5000,proposed_maintenance=2000);self.assertEqual(r.rows[1].maintenance_difference,3000);self.assertEqual(r.npv,45000);self.assertEqual(r.simple_payback_years,4);self.assertEqual(r.baseline.pv_maintenance_cost,25000)
    def test_escalation_after_year_one_not_maintenance(self):
        r=benchmark(analysis_years=3,escalation_percent=10,baseline_maintenance=5000,proposed_maintenance=2000)
        for row,expected in zip(r.rows[1:],[100000,110000,121000]):self.assertAlmostEqual(row.baseline_operating_cost,expected,8);self.assertEqual(row.maintenance_difference,3000)
        self.assertAlmostEqual(r.npv,-120000+30000+33000+36300+9000,8)
    def test_explicit_negative_escalation(self):self.assertEqual(benchmark(escalation_percent=-10).rows[2].baseline_operating_cost,90000)
    def test_residual_terminal_timing(self):
        r=benchmark(discount_rate_percent=10,baseline_residual=10000,proposed_residual=25000)
        self.assertEqual([x.terminal_residual_difference for x in r.rows],[0,0,0,0,0,15000]);self.assertAlmostEqual(r.proposed.pv_residual_value,25000/1.1**5,9)
        self.assertAlmostEqual(r.npv,benchmark(discount_rate_percent=10).npv+15000/1.1**5,8)
    def test_lifecycle_reconciles_full_optional(self):
        r=benchmark(discount_rate_percent=8,escalation_percent=3,baseline_maintenance=4000,proposed_maintenance=6000,baseline_residual=9000,proposed_residual=18000);self.assertAlmostEqual(r.npv,r.lifecycle_cost_difference,8)
    def test_zero_difference(self):
        r=benchmark(proposed_annual_cost=100000);self.assertIsNone(r.simple_payback_years);self.assertEqual(r.npv,-120000);self.assertEqual(r.simple_payback_status,core.NO_PAYBACK)
    def test_negative_difference(self):
        r=benchmark(proposed_annual_cost=110000);self.assertEqual(r.annual_cost_difference,-10000);self.assertIsNone(r.simple_payback_years);self.assertEqual(r.npv,-170000)
    def test_negative_incremental(self):
        r=benchmark(baseline_initial_cost=150000);self.assertEqual(r.incremental_capex,-30000);self.assertEqual(r.simple_payback_status,core.LOWER_INITIAL);self.assertIsNone(r.simple_payback_years);self.assertIsNone(r.discounted_payback_year)
    def test_zero_incremental(self):self.assertIsNone(benchmark(proposed_initial_cost=0).simple_payback_years)
    def test_phase3v_cost_delegation(self):
        with patch.object(core.annual_energy,'calculate_operating_cost',wraps=core.annual_energy.calculate_operating_cost) as spy:
            a,b=core.annual_costs_from_energy(49000,40000,.12)
        self.assertEqual(spy.call_count,2);self.assertEqual((a,b,a-b),(5880,4800,1080))
    def test_detail_initial_cost(self):self.assertEqual(core.initial_cost(100000,installation=10000,engineering=5000,commissioning=3000,other=2000),120000)
    def test_required_numeric_validation(self):
        for key in ['baseline_annual_cost','proposed_annual_cost','baseline_initial_cost','proposed_initial_cost','discount_rate_percent']:
            for bad in [None,-1,True,math.nan,math.inf]:
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):benchmark(**{key:bad})
    def test_year_validation(self):
        for bad in [None,0,-1,1.5,True,math.nan,math.inf]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):benchmark(analysis_years=bad)
    def test_optional_validation(self):
        for key in ['baseline_maintenance','proposed_maintenance','baseline_residual','proposed_residual']:
            for bad in [-1,True,math.nan,math.inf]:
                with self.subTest(key=key,bad=bad),self.assertRaises(ValueError):benchmark(**{key:bad})
        for bad in [-100,-101,True,math.nan,math.inf]:
            with self.assertRaises(ValueError):benchmark(escalation_percent=bad)
    def test_numeric_overflow_rejected(self):
        with self.assertRaises(ValueError):benchmark(baseline_annual_cost=1e308,escalation_percent=100)
        with self.assertRaises(ValueError):core.initial_cost(1e308,installation=1e308)
    def test_precision_and_immutable(self):
        r=benchmark(baseline_annual_cost=100000.123456789,discount_rate_percent=7.123456789)
        self.assertEqual(r.rows[1].annual_cost_difference,100000.123456789-70000)
        with self.assertRaises(FrozenInstanceError):r.npv=0
    def test_charts_separate_currency_axes_inline_layers(self):
        for discounted in [False,True]:
            spec=ui.cash_flow_chart_spec(benchmark().rows,'QAR',discounted);self.assertNotIn('data',spec);self.assertEqual(spec['encoding']['y']['title'],'QAR');self.assertEqual(len(spec['layer'][0]['data']['values']),6)
    def test_all_previous_source_unchanged(self):
        expected=BASELINE_HASHES
        for path,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)

class EconomicAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_string('from pump_performance.lifecycle_cost_ui import render_lifecycle_cost\nrender_lifecycle_cost()').run()
    def fill(self,**changes):
        at=self.app();values=dict(cost_a=100000,cost_b=70000,capex_a=0,capex_b=120000,years=5,discount=0);values.update(changes)
        for key,value in values.items():at.number_input(key='p3w_'+key).set_value(value)
        at.text_input(key='p3w_currency').set_value('QAR');return at
    def calc(self,at):at.button(key='p3w_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def infos(self,at):return '\n'.join(w.value for w in at.info)
    def test_full_app_registration(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(ROOT/'app.py')).run();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3W — Pump Lifecycle Cost / VSD Economic Evaluation' for e in at.expander));self.assertEqual(len(at.expander),28)
    def test_blank_required_and_optional_no_checkboxes(self):
        at=self.app();self.assertFalse(at.exception)
        for field in at.number_input:self.assertIsNone(field.value,field.label)
        self.assertEqual(at.text_input(key='p3w_currency').value,'');self.assertFalse(at.checkbox)
    def test_benchmark_summary(self):
        at=self.calc(self.fill());text=self.text(at)
        for expected in ['Calculated Annual Operating Cost Difference: 30000 QAR/year','Incremental CAPEX: 120000 QAR','Simple Payback: 4.0 years','Net Present Value — Proposed vs Baseline: 30000 QAR','Baseline Lifecycle Cost: 500000 QAR','Proposed Lifecycle Cost: 470000 QAR','Discounted Payback: 4 years']:self.assertIn(expected,text)
    def test_ten_percent(self):
        at=self.calc(self.fill(discount=10));self.assertIn(f'{benchmark(discount_rate_percent=10).npv:.12g} QAR',self.text(at));self.assertIn(core.NOT_RECOVERED,self.infos(at))
    def test_phase3v_ui_integration(self):
        at=self.fill();at.selectbox(key='p3w_source').select('Phase 3V Electrical Energy / Cost Kernel').run()
        for key,value in [('energy_a',49000),('energy_b',40000),('tariff',.12)]:at.number_input(key='p3w_'+key).set_value(value)
        with patch.object(core.annual_energy,'calculate_operating_cost',wraps=core.annual_energy.calculate_operating_cost) as spy:self.calc(at)
        self.assertEqual(spy.call_count,2)
        for expected in ['Baseline Annual Operating Cost: 5880 QAR/year','Proposed Annual Operating Cost: 4800 QAR/year','Difference: 1080 QAR/year']:self.assertIn(expected,self.text(at))
    def test_alternative_names_and_currency_label(self):
        at=self.fill();at.text_input(key='p3w_name_a').set_value('Existing | A');at.text_input(key='p3w_name_b').set_value('Modified B');at.text_input(key='p3w_currency').set_value('Custom');self.calc(at)
        self.assertIn('Existing | A',self.text(at));self.assertIn('Modified B',self.text(at));self.assertIn('30000 Custom',self.text(at))
    def test_currency_change_no_conversion(self):
        at=self.fill();at.text_input(key='p3w_currency').set_value('USD');self.calc(at);self.assertIn('30000 USD',self.text(at));at.text_input(key='p3w_currency').set_value('PKR');self.calc(at);self.assertIn('30000 PKR',self.text(at))
    def test_required_missing_no_result(self):
        at=self.calc(self.app());self.assertTrue(at.error);self.assertNotIn('Net Present Value',self.text(at))
    def test_invalid_negative_discount(self):
        at=self.calc(self.fill(discount=-1));self.assertTrue(at.error)
    def test_zero_annual_difference_ui(self):
        at=self.calc(self.fill(cost_b=100000));self.assertIn(core.NO_PAYBACK,self.infos(at));self.assertIn('Simple Payback: not defined',self.text(at))
    def test_negative_annual_difference_ui(self):
        at=self.calc(self.fill(cost_b=110000));self.assertIn('Difference: -10000 QAR/year',self.text(at));self.assertIn(core.NO_PAYBACK,self.infos(at))
    def test_lower_initial_cost_ui(self):
        at=self.calc(self.fill(capex_a=150000));self.assertIn(core.LOWER_INITIAL,self.infos(at));self.assertIn('Incremental CAPEX: -30000 QAR',self.text(at))
    def test_optional_maintenance_ui(self):
        at=self.calc(self.fill(maintenance_a=5000,maintenance_b=2000));self.assertIn('45000 QAR',self.text(at));self.assertIn('PV Maintenance 25000 QAR',self.text(at))
    def test_escalation_ui(self):
        at=self.calc(self.fill(escalation=10,years=3));self.assertIn('>110000</td>','\n'.join(w.value for w in at.markdown));self.assertIn('>77000</td>','\n'.join(w.value for w in at.markdown))
    def test_residual_ui(self):
        at=self.calc(self.fill(residual_b=10000));self.assertIn('40000 QAR',self.text(at));self.assertIn('PV Residual 10000 QAR',self.text(at))
    def test_detail_mode_blank_and_no_double_count(self):
        at=self.fill();at.selectbox(key='p3w_capex_mode').select('Detailed Proposed CAPEX Breakdown').run()
        for key in ['equipment','installation','engineering','commissioning','other']:self.assertIsNone(at.number_input(key='p3w_'+key).value)
        for key,value in [('equipment',100000),('installation',10000),('engineering',5000),('commissioning',3000),('other',2000)]:at.number_input(key='p3w_'+key).set_value(value)
        self.calc(at);self.assertIn('Proposed Initial Cost: 120000 QAR',self.text(at));self.assertIn('Simple Payback: 4.0 years',self.text(at))
    def test_cash_table_and_charts(self):
        at=self.calc(self.fill());md='\n'.join(w.value for w in at.markdown);self.assertIn('>-120000</td>',md);self.assertIn('overflow-x:auto;max-width:100%',md);self.assertIn('Discount Factor',md);self.assertEqual(len(at.get('vega_lite_chart')),2)
    def test_guidance_scope_and_no_added_finance_widgets(self):
        at=self.app();text='\n'.join(w.value for w in at.markdown)+ui.__doc__
        for sentence in ui.GUIDANCE:self.assertIn(sentence,text)
        labels=' '.join(w.label for w in at.number_input).lower()
        for excluded in ['tax','depreciation','irr','loan','exchange']:self.assertNotIn(excluded,labels)
        self.assertNotIn('guaranteed',text.lower());self.assertFalse(at.checkbox)
    def test_input_edit_removes_stale_result(self):
        at=self.calc(self.fill());at.number_input(key='p3w_cost_b').set_value(80000).run();self.assertNotIn('Net Present Value',self.text(at))

# Fixed accepted-source hashes are embedded during construction, not runtime-derived.
BASELINE_HASHES = {'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/annual_energy.py': 'f045aa111fb96d38485b8e9b5e270a1a2b798114612173e256dc7dc9401dc108', 'pump_performance/annual_energy_ui.py': '797a0e013a1d0c870de12e8dddfc191d268a8846b8ce042dc274780857eba382', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/control_strategy.py': 'ba639b265ebeaaa6baa878b102591c8f8fa7222b223df1a289fa11ee4a78127e', 'pump_performance/control_strategy_ui.py': '13b63e57b7d58d88127a4643fa524e5e8640577836097447a3348537e480bfca', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase3u_control_strategy.py': 'd07890f6e10820eebbcbd3d268877eb1cb1afda752bb8764f72c2005e07dd4ac', 'tests/test_phase3v_annual_energy.py': '04538377205a188dbf53f2938eacd58960d64b993da0f8b955347630d919b217'}
