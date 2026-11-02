"""Explicit sampling, Phase 3W delegation, statistics, and persistent Streamlit runs."""
import unittest,math,hashlib,json
from pathlib import Path
from dataclasses import replace,FrozenInstanceError
from unittest.mock import patch
import numpy as np
from pump_performance import monte_carlo_economics as core,monte_carlo_economics_ui as ui
ROOT=Path(__file__).resolve().parents[1]
def base(**kw):
    args=dict(baseline_capex=0,proposed_capex=120000,analysis_years=5,discount_rate_percent=0,baseline_annual_cost=100000,proposed_annual_cost=70000);args.update(kw);return core.economics.EconomicCase(**args)
def fixed(value):return core.DistributionSpec('Fixed',value=value)
def uniform(lo=90000,hi=150000):return core.DistributionSpec('Uniform',minimum=lo,maximum=hi)
def simulate(specs=None,n=1000,seed=42,case=None,**kw):return core.run_economic_monte_carlo(case or base(),{} if specs is None else specs,n,seed,**kw)
def all_fixed():return {core.CAPEX:fixed(120000),core.BASELINE_CAPEX:fixed(0),core.BASELINE_COST:fixed(100000),core.PROPOSED_COST:fixed(70000),core.PERIOD:fixed(5),core.DISCOUNT:fixed(0)}
def trial(value):return core.MonteCarloTrialResult(1,(),value,4,4,value,500000,470000)

class MonteCarloCoreTests(unittest.TestCase):
    def test_fixed_distribution(self):self.assertEqual(core.sample_distribution(fixed(12),100,np.random.default_rng(1)).values,(12,)*100)
    def test_uniform_distribution_bounds(self):
        b=core.sample_distribution(uniform(1,3),1000,np.random.default_rng(42));self.assertTrue(all(1<=x<=3 for x in b.values));self.assertEqual(b.rejected_draws,0)
    def test_triangular_distribution(self):
        s=core.DistributionSpec('Triangular',minimum=1,most_likely=2,maximum=5);b=core.sample_distribution(s,1000,np.random.default_rng(42));self.assertTrue(all(1<=x<=5 for x in b.values))
    def test_normal_finite_and_reproducible(self):
        s=core.DistributionSpec('Normal',mean=120000,standard_deviation=10000);a=simulate({core.CAPEX:s});b=simulate({core.CAPEX:s});self.assertEqual(a,b);self.assertTrue(all(math.isfinite(dict(t.sampled_inputs)[core.CAPEX]) for t in a.trials))
    def test_normal_negative_draws_resampled_not_clamped(self):
        s=core.DistributionSpec('Normal',mean=0,standard_deviation=1);b=core.sample_distribution(s,1000,np.random.default_rng(42),lower=0);self.assertGreater(b.rejected_draws,0);self.assertTrue(all(x>0 for x in b.values));self.assertEqual(b,core.sample_distribution(s,1000,np.random.default_rng(42),lower=0))
    def test_normal_attempt_limit_configuration_invalid(self):
        with self.assertRaisesRegex(ValueError,'100 attempts'):core.sample_distribution(core.DistributionSpec('Normal',mean=-1e9,standard_deviation=1),10,np.random.default_rng(42),lower=0)
    def test_degenerate_distributions(self):
        for s in [uniform(7,7),core.DistributionSpec('Triangular',minimum=7,most_likely=7,maximum=7),core.DistributionSpec('Normal',mean=7,standard_deviation=0)]:self.assertEqual(core.sample_distribution(s,100,np.random.default_rng(42)).values,(7,)*100)
    def test_distribution_validation(self):
        bad=[core.DistributionSpec(None),core.DistributionSpec('Uniform',minimum=2,maximum=1),core.DistributionSpec('Triangular',minimum=0,most_likely=4,maximum=3),core.DistributionSpec('Normal',mean=1,standard_deviation=-1),core.DistributionSpec('Fixed'),core.DistributionSpec('Normal',mean=0),fixed(math.inf),uniform(0,math.nan),fixed(True)]
        for spec in bad:
            with self.subTest(spec=spec),self.assertRaises(ValueError):core.sample_distribution(spec,10,np.random.default_rng(42))
    def test_physical_bounded_support_rejected(self):
        for spec in [fixed(-1),uniform(-1,1),core.DistributionSpec('Triangular',minimum=-1,most_likely=0,maximum=1),core.DistributionSpec('Normal',mean=-1,standard_deviation=0)]:
            with self.assertRaises(ValueError):simulate({core.CAPEX:spec})
    def test_discrete_period_fixed_and_inclusive_integer_uniform(self):
        s=core.DistributionSpec('Integer Uniform',minimum=3,maximum=6);r=simulate({core.PERIOD:s});values=[dict(t.sampled_inputs)[core.PERIOD] for t in r.trials];self.assertEqual(set(values),{3,4,5,6});self.assertEqual(r.valid_trials,1000)
    def test_continuous_period_and_fractional_years_rejected(self):
        for spec in [uniform(3,6),fixed(3.5),core.DistributionSpec('Integer Uniform',minimum=3.1,maximum=6),fixed(0)]:
            with self.assertRaises(ValueError):simulate({core.PERIOD:spec})
    def test_fixed_1000_every_trial_exact(self):
        r=simulate(all_fixed());self.assertEqual((r.requested_trials,r.valid_trials,r.invalid_trials),(1000,1000,0));self.assertTrue(all(t.npv==30000 for t in r.trials));self.assertEqual(r.summary.npv.mean,30000);self.assertEqual(r.summary.npv.median,30000);self.assertEqual(r.summary.npv.minimum,30000);self.assertEqual(r.summary.npv.maximum,30000);self.assertEqual(r.summary.npv.standard_deviation,0);self.assertTrue(all(v==30000 for _,v in r.summary.npv.percentiles))
    def test_fixed_probabilities_and_paybacks(self):
        s=simulate(all_fixed()).summary;self.assertEqual((s.probability_positive_npv_percent,s.probability_negative_npv_percent,s.probability_zero_npv_percent),(100,0,0));self.assertEqual(s.simple_payback_defined_percent,100);self.assertEqual(s.simple_payback.median,4);self.assertEqual(s.discounted_payback_reached_percent,100);self.assertEqual(s.probability_proposed_lifecycle_cost_lower_percent,100)
    def test_uniform_capex_range_and_statistical_mean(self):
        r=simulate({core.CAPEX:uniform()},n=20000);self.assertTrue(all(0<=t.npv<=60000 for t in r.trials));self.assertAlmostEqual(r.summary.npv.mean,30000,delta=500)
    def test_triangular_capex_statistical_mean(self):
        r=simulate({core.CAPEX:core.DistributionSpec('Triangular',minimum=90000,most_likely=120000,maximum=180000)},n=20000);self.assertAlmostEqual(r.summary.npv.mean,20000,delta=600)
    def test_same_seed_identical_different_seed_changes(self):
        a=simulate({core.CAPEX:uniform()},seed=1);self.assertEqual(a,simulate({core.CAPEX:uniform()},seed=1));self.assertNotEqual(a.trials,simulate({core.CAPEX:uniform()},seed=2).trials)
    def test_mapping_order_does_not_change_sequence(self):
        a={core.CAPEX:uniform(),core.DISCOUNT:uniform(0,10)};self.assertEqual(simulate(a),simulate(dict(reversed(list(a.items())))))
    def test_seed_and_count_validation(self):
        for seed in [-1,True,1.5,'42',math.nan]:
            with self.assertRaises(ValueError):simulate(seed=seed)
        for count in [0,-1,True,1.5,50001,math.inf]:
            with self.assertRaises(ValueError):simulate(n=count)
    def test_optional_seed_not_fabricated(self):self.assertIsNone(simulate(seed=None).seed)
    def test_every_trial_calls_phase3w(self):
        with patch.object(core.economics.lifecycle_cost,'calculate_economic_comparison',wraps=core.economics.lifecycle_cost.calculate_economic_comparison) as spy:r=simulate(all_fixed())
        self.assertGreaterEqual(spy.call_count,1000);self.assertEqual(r.base_result.npv,30000)
    def test_sampled_case_optional_costs_match_phase3w(self):
        b=base(discount_rate_percent=7,baseline_maintenance=5000,proposed_maintenance=2000,escalation_percent=3,baseline_residual=10000,proposed_residual=20000);r=simulate({core.CAPEX:uniform()},case=b)
        for t in r.trials[:12]:
            expected=core.economics.evaluate_economic_scenario(replace(b,proposed_capex=dict(t.sampled_inputs)[core.CAPEX])).result
            self.assertEqual((t.npv,t.simple_payback_years,t.discounted_payback_year,t.lifecycle_cost_difference),(expected.npv,expected.simple_payback_years,expected.discounted_payback_year,expected.lifecycle_cost_difference))
    def test_cost_modes_mutually_exclusive(self):
        with self.assertRaises(ValueError):simulate({core.DIFFERENCE:fixed(30000),core.BASELINE_COST:fixed(100000)},cost_basis=core.COST_DIFFERENCE)
        with self.assertRaises(ValueError):simulate({core.DIFFERENCE:fixed(30000)})
        with self.assertRaises(ValueError):simulate({core.TARIFF:fixed(.12)})
        r=simulate({core.DIFFERENCE:fixed(30000)},cost_basis=core.COST_DIFFERENCE);self.assertEqual(r.summary.npv.mean,30000)
    def test_difference_domain_upper_bound(self):
        with self.assertRaises(ValueError):simulate({core.DIFFERENCE:uniform(0,100001)},cost_basis=core.COST_DIFFERENCE)
    def test_phase3v_energy_pricing_reused(self):
        b=base(source=core.economics.ENERGY,baseline_energy_kwh=49000,proposed_energy_kwh=40000,tariff=.12)
        with patch.object(core.economics.annual_energy,'calculate_operating_cost',wraps=core.economics.annual_energy.calculate_operating_cost) as spy:r=simulate({core.TARIFF:fixed(.12)},case=b)
        self.assertGreaterEqual(spy.call_count,2000);self.assertEqual(r.base_result.annual_cost_difference,1080);self.assertEqual(r.summary.npv.mean,-114600)
        with self.assertRaises(ValueError):simulate({core.PROPOSED_COST:fixed(4800)},case=b)
    def test_phase3v_constant_power_hours_reused(self):
        b=base(source=core.economics.POWER,baseline_power_kw=10,proposed_power_kw=8,operating_hours=4000,tariff=.12)
        with patch.object(core.economics.annual_energy,'calculate_energy',wraps=core.economics.annual_energy.calculate_energy) as spy:r=simulate({core.HOURS:fixed(2000)},case=b)
        self.assertGreaterEqual(spy.call_count,2000);self.assertEqual(r.summary.npv.mean,-117600)
    def test_invalid_trial_counts_and_minimum_threshold(self):
        b=base(baseline_annual_cost=1e308,proposed_annual_cost=0,analysis_years=1)
        r=simulate({core.PERIOD:core.DistributionSpec('Integer Uniform',minimum=1,maximum=3)},case=b)
        self.assertEqual(r.valid_trials+r.invalid_trials,1000);self.assertGreater(r.invalid_trials,0);self.assertEqual(r.valid_trials,sum(t.error is None for t in r.trials));self.assertIsNotNone(r.summary);self.assertTrue(r.warning)
        r=simulate({core.PERIOD:fixed(2)},case=b);self.assertEqual(r.invalid_trials,1000);self.assertIsNone(r.summary);self.assertEqual(r.warning,core.INSUFFICIENT)
    def test_fewer_than_100_no_statistics(self):
        r=simulate(n=99);self.assertEqual(r.valid_trials,99);self.assertIsNone(r.summary);self.assertEqual(r.warning,core.INSUFFICIENT)
    def test_undefined_paybacks_not_zero(self):
        for proposed in [100000,110000]:
            r=simulate(case=base(proposed_annual_cost=proposed));self.assertTrue(all(t.simple_payback_years is None for t in r.trials));self.assertEqual(r.summary.simple_payback_defined_percent,0);self.assertIsNone(r.summary.simple_payback);self.assertEqual(r.summary.discounted_payback_reached_percent,0)
    def test_conditional_payback_denominators(self):
        r=simulate({core.DIFFERENCE:uniform(-30000,60000)},cost_basis=core.COST_DIFFERENCE);defined=sum(t.simple_payback_years is not None for t in r.trials);reached=sum(t.discounted_payback_year is not None for t in r.trials);self.assertEqual(r.summary.simple_payback_defined_count,defined);self.assertEqual(r.summary.simple_payback_defined_percent,defined/1000*100);self.assertEqual(r.summary.simple_payback.count,defined);self.assertEqual(r.summary.discounted_payback_reached_percent,reached/1000*100)
    def test_zero_npv_neither_positive_nor_negative(self):
        s=simulate(case=base(proposed_capex=150000)).summary;self.assertEqual((s.probability_positive_npv_percent,s.probability_negative_npv_percent,s.probability_zero_npv_percent),(0,0,100))
    def test_strict_sign_and_approximate_zero_are_explicit_diagnostics(self):
        s=core.calculate_monte_carlo_summary([trial(1e-10)]*100);self.assertEqual(s.probability_positive_npv_percent,100);self.assertEqual(s.probability_negative_npv_percent,0);self.assertEqual(s.probability_zero_npv_percent,100)
    def test_lifecycle_sign_and_statistics(self):
        r=simulate({core.CAPEX:uniform(90000,180000)});s=r.summary;self.assertAlmostEqual(s.lifecycle_cost_difference.mean,s.npv.mean,8);self.assertEqual(s.probability_proposed_lifecycle_cost_lower_percent,sum(t.lifecycle_cost_difference>0 for t in r.trials)/1000*100)
    def test_percentile_convention_and_order(self):
        s=core.distribution_statistics([0,10,20,30]);q=dict(s.percentiles);self.assertAlmostEqual(q[10],3);self.assertEqual(q[50],15);self.assertAlmostEqual(q[90],27);self.assertEqual(s.mean,15);self.assertAlmostEqual(s.standard_deviation,math.sqrt(125))
    def test_spearman_perfect_negative_and_zero_variance(self):
        r=simulate({core.CAPEX:uniform(),core.DISCOUNT:fixed(0)});rows={c.variable:c for c in r.correlations};self.assertAlmostEqual(rows[core.CAPEX].rho,-1);self.assertIsNone(rows[core.DISCOUNT].rho)
        self.assertTrue(all(c.rho is None for c in simulate(all_fixed()).correlations))
    def test_spearman_ties_and_pair_validation(self):
        r=core.calculate_rank_correlations({'x':[1,1,2]},[1,2,3])[0];self.assertAlmostEqual(r.rho,math.sqrt(.75));self.assertIsNone(core.calculate_rank_correlations({'x':[1,2]},[3,3])[0].rho)
        with self.assertRaises(ValueError):core.calculate_rank_correlations({'x':[1]},[1,2])
    def test_full_precision_and_immutable(self):
        value=120000.123456789;r=simulate({core.CAPEX:fixed(value)});self.assertEqual(dict(r.trials[0].sampled_inputs)[core.CAPEX],value)
        with self.assertRaises(FrozenInstanceError):r.valid_trials=0
    def test_plot_inline_layers_zero_line_counts(self):
        r=simulate();spec=ui.histogram_spec(r,'QAR');self.assertNotIn('data',spec);self.assertEqual(sum(v['trials'] for v in spec['layer'][0]['data']['values']),1000);self.assertEqual(spec['layer'][1]['data']['values'],[{'zero':0}]);self.assertIn('QAR',spec['layer'][0]['encoding']['x']['title'])
    def test_prior_python_sources_guarded(self):
        for path,digest in BASELINE_HASHES.items():
            data=(ROOT/path).read_bytes()
            if path in ('tests/test_phase3w_lifecycle_cost.py','tests/test_phase3x_economic_sensitivity.py'):
                data=data.decode().replace('len(at.expander),31','len(at.expander),29').encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest,path)

class MonteCarloAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_string('from pump_performance.monte_carlo_economics_ui import render_monte_carlo_economics\nrender_monte_carlo_economics()').run()
    def fill(self,**changes):
        at=self.app();values=dict(cost_a=100000,cost_b=70000,capex_a=0,capex_b=120000,years=5,discount=0);values.update(changes)
        for key,value in values.items():at.number_input(key='p3y_base_'+key).set_value(value)
        at.selectbox(key='p3y_trials').select(1000);at.number_input(key='p3y_seed').set_value(42);return at.run()
    def run_sim(self,at):at.button(key='p3y_run').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def all_text(self,at):return '\n'.join(w.value for w in list(at.markdown)+list(at.caption)+list(at.warning)+list(at.text))
    def configure(self,at,variable,kind,**values):
        at.multiselect(key='p3y_variables').set_value([variable]).run();prefix='p3y_d'+str(core.ORDER.index(variable))+'_';at.selectbox(key=prefix+'kind').select(kind).run()
        for key,value in values.items():at.number_input(key=prefix+key).set_value(value)
        return at
    def test_full_app_registration(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(ROOT/'app.py')).run();self.assertFalse(at.exception);self.assertEqual(len(at.expander),31);self.assertTrue(any(e.label==ui.TITLE for e in at.expander))
    def test_blank_financial_and_distribution_defaults(self):
        at=self.app();self.assertFalse(at.exception)
        for w in at.number_input:self.assertIsNone(w.value,w.label)
        self.assertEqual(at.multiselect(key='p3y_variables').value,[]);self.assertEqual(at.selectbox(key='p3y_trials').value,5000);self.assertEqual(at.text_input(key='p3y_currency').value,'');self.assertFalse(at.checkbox)
    def test_deterministic_base_visible_before_simulation(self):
        at=self.fill();self.assertIn('Base NPV: 30000',self.text(at));self.assertIn('Simple Payback: 4.0 years',self.text(at));self.assertNotIn('Requested Trials:',self.text(at))
    def test_selected_distribution_and_parameters_start_blank(self):
        at=self.fill();at.multiselect(key='p3y_variables').set_value([core.CAPEX]).run();self.assertIsNone(at.selectbox(key='p3y_d0_kind').value)
        at.selectbox(key='p3y_d0_kind').select('Normal').run();self.assertIsNone(at.number_input(key='p3y_d0_mean').value);self.assertIsNone(at.number_input(key='p3y_d0_std').value)
        at.selectbox(key='p3y_d0_kind').select('Uniform').run();self.assertIsNone(at.number_input(key='p3y_d0_minimum').value);self.assertIsNone(at.number_input(key='p3y_d0_maximum').value)
    def test_explicit_all_fixed_1000_benchmark_ui(self):
        at=self.fill();specs=all_fixed();at.multiselect(key='p3y_variables').set_value(list(specs)).run()
        for variable in specs:at.selectbox(key='p3y_d'+str(core.ORDER.index(variable))+'_kind').select('Fixed')
        at.run()
        for variable,spec in specs.items():at.number_input(key='p3y_d'+str(core.ORDER.index(variable))+'_value').set_value(int(spec.value) if variable==core.PERIOD else spec.value)
        self.run_sim(at);text=self.text(at);self.assertNotIn('DistributionSpec(',self.all_text(at));self.assertIn('Value: 120000',self.all_text(at))
        for expected in ['Requested Trials: 1000','Valid Trials: 1000','Invalid Trials: 0','NPV Mean: 30000','NPV Median: 30000','NPV P10: 30000','NPV P50: 30000','NPV P90: 30000','Probability NPV > 0: 100%','Probability NPV < 0: 0%','Probability NPV ≈ 0: 0%']:self.assertIn(expected,text)
    def test_uniform_ui_and_correlation(self):
        at=self.configure(self.fill(),core.CAPEX,'Uniform',minimum=90000,maximum=150000);self.run_sim(at);self.assertIn('Spearman rho vs NPV',self.all_text(at));self.assertIn('>-1</td>',self.all_text(at));self.assertEqual(len(at.get('vega_lite_chart')),2)
    def test_triangular_ui(self):
        at=self.configure(self.fill(),core.CAPEX,'Triangular',minimum=90000,most_likely=120000,maximum=180000);self.run_sim(at);self.assertIn('Valid Trials: 1000',self.text(at));self.assertFalse(at.error)
    def test_normal_ui_rejected_draw_count(self):
        at=self.configure(self.fill(),core.CAPEX,'Normal',mean=0,std=1);self.run_sim(at);self.assertIn('Valid Trials: 1000',self.text(at));self.assertNotIn('Rejected Normal Draws (resampled, not invalid trials): 0',self.text(at))
    def test_same_seed_repeated_ui_run(self):
        at=self.configure(self.fill(),core.CAPEX,'Uniform',minimum=90000,maximum=150000);self.run_sim(at);old=at.session_state['p3y_last']['result'];self.run_sim(at);self.assertEqual(old,at.session_state['p3y_last']['result'])
    def test_edits_do_not_automatically_rerun_and_stale_warning(self):
        at=self.run_sim(self.fill());old=at.session_state['p3y_last']['result']
        with patch.object(core,'run_economic_monte_carlo',wraps=core.run_economic_monte_carlo) as spy:at.number_input(key='p3y_base_capex_b').set_value(130000).run()
        self.assertEqual(spy.call_count,0);self.assertEqual(old,at.session_state['p3y_last']['result']);self.assertTrue(any('Inputs have changed.' in w.value for w in at.warning));self.assertIn('NPV Mean: 30000',self.text(at));self.assertIn('Base NPV: 20000',self.text(at))
    def test_explicit_rerun_updates_and_clears_stale(self):
        at=self.run_sim(self.fill());at.number_input(key='p3y_base_capex_b').set_value(130000).run();self.run_sim(at);self.assertIn('NPV Mean: 20000',self.text(at));self.assertFalse(any('Inputs have changed.' in w.value for w in at.warning))
    def test_invalid_distribution_no_summary_created(self):
        at=self.configure(self.fill(),core.CAPEX,'Uniform',minimum=150000,maximum=90000);self.run_sim(at);self.assertTrue(at.error);self.assertNotIn('NPV Mean:',self.text(at))
    def test_unselected_distribution_not_assumed(self):
        at=self.fill();at.multiselect(key='p3y_variables').set_value([core.CAPEX]).run();self.run_sim(at);self.assertTrue(at.error)
    def test_invalid_base_error(self):
        at=self.run_sim(self.app());self.assertTrue(at.error)
    def test_normal_sampling_failure_preserves_previous_with_warning(self):
        at=self.run_sim(self.fill());self.configure(at,core.CAPEX,'Normal',mean=-1e9,std=1);self.run_sim(at);self.assertTrue(at.error);self.assertIn('NPV Mean: 30000',self.text(at));self.assertTrue(any('previous simulation' in w.value for w in at.warning))
    def test_cost_difference_basis_excludes_individual_costs(self):
        at=self.fill();at.selectbox(key='p3y_cost_basis').select(core.COST_DIFFERENCE).run();options=at.multiselect(key='p3y_variables').options;self.assertIn(core.DIFFERENCE,options);self.assertNotIn(core.BASELINE_COST,options);self.assertNotIn(core.PROPOSED_COST,options)
    def test_integer_life_distributions_only(self):
        at=self.fill();at.multiselect(key='p3y_variables').set_value([core.PERIOD]).run();self.assertEqual(at.selectbox(key='p3y_d8_kind').options,['Fixed','Integer Uniform'])
    def test_seed_blank_and_explicit_display(self):
        at=self.fill();at.number_input(key='p3y_seed').set_value(None);self.run_sim(at);self.assertIn('Random Seed: not supplied',self.text(at));at.number_input(key='p3y_seed').set_value(42);self.run_sim(at);self.assertIn('Random Seed: 42',self.text(at))
    def test_undefined_payback_and_unrecovered_ui(self):
        at=self.run_sim(self.fill(cost_b=100000));self.assertIn('Simple-Payback Defined: 0 / 1000 valid trials (0%)',self.text(at));self.assertIn('Discounted-Payback Reached Within Analysis Period: 0 / 1000',self.text(at));self.assertIn('N/A — no defined paybacks',self.all_text(at))
    def test_zero_variance_no_misleading_correlation(self):
        at=self.run_sim(self.configure(self.fill(),core.CAPEX,'Fixed',value=120000));self.assertIn('Rank correlations are undefined',self.all_text(at));self.assertEqual(len(at.get('vega_lite_chart')),1)
    def test_currency_label_changes_no_conversion(self):
        at=self.fill();at.text_input(key='p3y_currency').set_value('QAR');self.run_sim(at);self.assertIn('NPV Mean: 30000 QAR',self.text(at));at.text_input(key='p3y_currency').set_value('USD');self.run_sim(at);self.assertIn('NPV Mean: 30000 USD',self.text(at))
    def test_histogram_zero_reference_and_percentile_labels(self):
        at=self.run_sim(self.fill());spec=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(spec['layer'][1]['data']['values'],[{'zero':0}]);self.assertIn('Neutral gray vertical rule',self.all_text(at));self.assertIn('NPV P90:',self.text(at))
    def test_guidance_independence_and_no_decision_widgets(self):
        at=self.app();text=self.all_text(at)
        for sentence in ui.GUIDANCE:self.assertIn(sentence,text)
        self.assertIn('Phase 3Y assumes uncertain inputs are statistically independent unless otherwise stated.',text);self.assertNotIn('project should proceed',text);self.assertNotIn('economically acceptable',text);self.assertFalse(at.checkbox)
    def test_insufficient_valid_trials_counts_only_ui(self):
        at=self.fill(cost_a=1e308,cost_b=0,years=1);self.configure(at,core.PERIOD,'Fixed',value=2);self.run_sim(at);self.assertIn('Invalid Trials: 1000',self.text(at));self.assertTrue(any(w.value==core.INSUFFICIENT for w in at.warning));self.assertNotIn('NPV Mean:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))

BASELINE_HASHES = {'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/annual_energy.py': 'f045aa111fb96d38485b8e9b5e270a1a2b798114612173e256dc7dc9401dc108', 'pump_performance/annual_energy_ui.py': '797a0e013a1d0c870de12e8dddfc191d268a8846b8ce042dc274780857eba382', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/control_strategy.py': 'ba639b265ebeaaa6baa878b102591c8f8fa7222b223df1a289fa11ee4a78127e', 'pump_performance/control_strategy_ui.py': '13b63e57b7d58d88127a4643fa524e5e8640577836097447a3348537e480bfca', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/economic_sensitivity.py': 'e7cf8a7d9a95302ce709ea76b28ea1c76fb71dbb075e90bab70100503b9805b4', 'pump_performance/economic_sensitivity_ui.py': 'd1fc037ef2e1369ffd247855ecda10824f4bfab5fc5fabd88ab7a1e690a4149b', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/lifecycle_cost.py': '185a04b2ad59a5a6ed6a8a316c0e98352aea7157c713fa05d0a8085bf871a685', 'pump_performance/lifecycle_cost_ui.py': '3b27a28c06f9c632161d446fec24ba32c0e62bd8e4393f4156156cb736806b6c', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase3u_control_strategy.py': 'd07890f6e10820eebbcbd3d268877eb1cb1afda752bb8764f72c2005e07dd4ac', 'tests/test_phase3v_annual_energy.py': '04538377205a188dbf53f2938eacd58960d64b993da0f8b955347630d919b217', 'tests/test_phase3w_lifecycle_cost.py': '2929b6f1355b2278c370c8fc5207abaea8db525f713a164f04492bc7c9e011d7', 'tests/test_phase3x_economic_sensitivity.py': '83492632dfa9337d6654a9fd88d7c2d296666cfe2ae96151e796bc022469c1a4'}
