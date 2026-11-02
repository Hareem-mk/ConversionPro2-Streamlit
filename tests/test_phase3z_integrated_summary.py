"""Integrated orchestration, partial-data isolation, and actual review UI paths."""
import unittest,hashlib,json,inspect
from pathlib import Path
from dataclasses import replace,FrozenInstanceError
from unittest.mock import patch
from contextlib import ExitStack
from app import FLOW
from pump_performance import integrated_summary as core,integrated_summary_ui as ui
ROOT=Path(__file__).resolve().parents[1]
HEAD=((0,50),(50,48),(100,44),(150,38),(200,30))
EFF=((50,65),(100,78),(150,84),(200,80),(250,70))
POWER=((50,6),(100,8.5),(150,11.5),(200,14),(250,16))
NPSHR=((50,2.5),(100,3.2),(150,4.4),(200,6),(250,8))
def curve(points,unit='m'):return core.CurveInput(points,'m³/hr',unit)
def technical(**kw):
    args=dict(pump=curve(HEAD),system=core.SystemInput(10,'m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr'),bep_flow=150,bep_unit='m³/hr',efficiency=curve(EFF,'%'),power=curve(POWER,'kW'),npshr=curve(NPSHR),npsha=12.026359664105,npsha_unit='m',driver_rating=15,driver_unit='kW');args.update(kw);return core.TechnicalInputs(**args)
def economic(**kw):
    args=dict(baseline_capex=0,proposed_capex=120000,analysis_years=5,discount_rate_percent=0,baseline_annual_cost=100000,proposed_annual_cost=70000);args.update(kw);return core.economic_sensitivity.EconomicCase(**args)
def energy():return core.EnergyInputs(tuple(core.annual_energy.DutyPoint(str(i),core.annual_energy.METHODS[2],hours,input_power=power,power_unit='kW',power_basis='Electrical Input Power') for i,(power,hours) in enumerate([(10,2000),(8,3000),(5,1000)])),.12)
def build(data=None,**kw):return core.build_integrated_pump_summary(data or technical(),FLOW,**kw)
def extras(**kw):
    args=dict(reference_speed=1500,new_speed=1200,target_flow=100,target_unit='m³/hr',control_requested=True,density_kg_m3=1000);args.update(kw);return technical(**args)
def full(**kw):
    args=dict(mode=core.MODES[3],optional_energy_inputs=energy(),optional_economic_inputs=economic(),optional_sensitivity_inputs=core.SensitivityInputs('Proposed CAPEX',(90000,120000,150000,180000)),optional_risk_inputs=core.RiskInputs((),1000,42));args.update(kw);return build(extras(),**args)

class IntegratedCoreTests(unittest.TestCase):
    def test_hydraulic_benchmark(self):
        r=build();self.assertAlmostEqual(r.metric('Operating Flow').value/FLOW['m³/hr'],124.59624833740307,10);self.assertAlmostEqual(r.metric('Operating Head').value,41.04845019951163,10);self.assertLess(abs(r.metric('Pump/System Residual').value),1e-9);self.assertEqual(r.metric('Valid Isolated Intersections').value,1)
    def test_all_technical_source_kernels_called(self):
        pairs=[(core.operating_point,'find_operating_points'),(core.bep_operating_range,'compare_bep'),(core.efficiency_curve,'interpolate_efficiency'),(core.power_curve,'interpolate_power'),(core.power_curve,'calculate_driver_margin'),(core.npshr_curve,'interpolate_npshr'),(core.npsh_margin,'calculate_npsh_margin'),(core.curve_characteristics,'analyze_curve_characteristics'),(core.curve_characteristics,'local_curve_slope')]
        with ExitStack() as stack:
            spies=[stack.enter_context(patch.object(module,name,wraps=getattr(module,name))) for module,name in pairs];build()
            for spy in spies:self.assertGreaterEqual(spy.call_count,1)
    def test_bep_si_normalization_and_vendor_only(self):
        r=build(technical(bep_flow=150/3600,bep_unit='m³/s'));self.assertAlmostEqual(r.metric('Percent of BEP').value,83.0641655582687,10)
        r=build(technical(bep_flow=None));self.assertIsNone(r.metric('Percent of BEP').value)
    def test_efficiency_benchmark(self):self.assertAlmostEqual(build().metric('Operating Efficiency').value,80.95154980048837,10)
    def test_shaft_power_and_driver_margin(self):
        r=build();self.assertAlmostEqual(r.metric('Pump Shaft Power').value/1000,9.975774900244185,10);self.assertAlmostEqual(r.metric('Driver Power Margin').value/1000,5.024225099755815,10);self.assertEqual(r.metric('Entered Driver Margin Criterion').status,'Criterion Not Entered')
    def test_npshr_npsh_benchmark(self):
        r=build();self.assertAlmostEqual(r.metric('Vendor NPSHR').value,3.790309960097674,11);self.assertAlmostEqual(r.metric('NPSH Margin').value,8.236049704007325,11);self.assertAlmostEqual(r.metric('NPSHA / NPSHR Ratio').value,3.172922476185849,11)
    def test_curve_characteristics_and_slope(self):
        r=build();self.assertEqual(r.metric('Supplied Shutoff Head').value,50);self.assertAlmostEqual(core.curve_characteristics.display_slope(r.metric('Local Pump Curve Slope').value,'m³/hr','m',FLOW),-.12,12);self.assertEqual(r.metric('Flat Segment Count').value,0);self.assertEqual(r.metric('Rising Segment Count').value,0)
    def test_no_inferred_shutoff(self):self.assertIsNone(build(technical(pump=curve(HEAD[1:]))).metric('Supplied Shutoff Head').value)
    def test_variable_speed_1200_and_1800_reuse(self):
        with patch.object(core.variable_speed,'evaluate_variable_speed_operating_point',wraps=core.variable_speed.evaluate_variable_speed_operating_point) as spy:r=build(extras())
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(r.metric('VSD Operating Flow').value/FLOW['m³/hr'],92.17228585166087,9);self.assertAlmostEqual(r.metric('VSD Operating Head').value,26.99146055824056,9)
        r=build(extras(new_speed=1800));expected=core.variable_speed.evaluate_variable_speed_operating_point(r.technical.pump,1500,1800,r.technical.system);self.assertEqual(r.metric('VSD Operating Flow').value,expected.new.points[0].flow_m3_s)
    def test_target_speed_reuse(self):
        with patch.object(core.target_speed,'solve_speed_for_target_flow',wraps=core.target_speed.solve_speed_for_target_flow) as spy:r=build(extras(control_requested=False))
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(r.metric('Required Speed').value,1270.302598778999,8);self.assertAlmostEqual(r.metric('Verified Target Head').value,30,10)
    def test_control_strategy_reuse_and_hydraulic_label(self):
        with patch.object(core.control_strategy,'compare_throttling_and_vsd',wraps=core.control_strategy.compare_throttling_and_vsd) as spy:r=build(extras())
        self.assertEqual(spy.call_count,1);self.assertEqual(r.metric('Throttling Head').value,44);self.assertEqual(r.metric('Required Throttled K').value,44064);self.assertEqual(r.metric('Resistance Increase').value,70);self.assertAlmostEqual(r.metric('Hydraulic Power Reduction').value,31.818181818181817);self.assertIn('not electrical',r.metric('Hydraulic Power Reduction').note)
    def test_system_sensitivity_reuse(self):
        data=technical(modified_system=core.SystemInput(12,'m','Direct K',k_si=30000))
        with patch.object(core.system_sensitivity,'evaluate_system_sensitivity',wraps=core.system_sensitivity.evaluate_system_sensitivity) as spy:r=build(data)
        self.assertEqual(spy.call_count,1);self.assertEqual(r.metric('Operating Flow Shift').value,r.technical.system_sensitivity.flow_change.difference)
    def test_energy_phase3v_benchmark(self):
        with patch.object(core.annual_energy,'evaluate_duty_profile',wraps=core.annual_energy.evaluate_duty_profile) as spy:r=build(mode=core.MODES[1],optional_energy_inputs=energy())
        self.assertEqual(spy.call_count,1);self.assertEqual(r.metric('Annual Supply Electrical Energy').value,49000);self.assertEqual(r.metric('Annual Supply Electrical Operating Cost').value,5880)
    def test_energy_bases_not_combined(self):
        profile=energy();rows=profile.rows+(core.annual_energy.DutyPoint('Mechanical',core.annual_energy.METHODS[2],1000,input_power=20,power_unit='kW',power_basis='Shaft Power'),);r=build(mode=core.MODES[1],optional_energy_inputs=replace(profile,rows=rows));self.assertEqual(r.metric('Annual Supply Electrical Energy').value,49000);self.assertIsNone(r.energy.rows[-1].cost)
    def test_lifecycle_phase3w_benchmark(self):
        with patch.object(core.economic_sensitivity.lifecycle_cost,'calculate_economic_comparison',wraps=core.economic_sensitivity.lifecycle_cost.calculate_economic_comparison) as spy:r=build(mode=core.MODES[2],optional_economic_inputs=economic())
        self.assertEqual(spy.call_count,1);self.assertEqual((r.metric('Annual Operating Cost Difference').value,r.metric('Simple Payback').value,r.metric('NPV').value),(30000,4,30000))
    def test_sensitivity_phase3x(self):
        with patch.object(core.economic_sensitivity,'run_one_variable_sensitivity',wraps=core.economic_sensitivity.run_one_variable_sensitivity) as spy:r=full(optional_risk_inputs=None)
        self.assertEqual(spy.call_count,1);self.assertEqual([p.result.simple_payback_years for p in r.sensitivity.points],[3,4,5,6]);self.assertEqual([p.result.npv for p in r.sensitivity.points],[60000,30000,0,-30000]);self.assertEqual(r.metric('Break-Even Incremental CAPEX').value,150000)
    def test_monte_carlo_phase3y_fixed(self):
        with patch.object(core.monte_carlo_economics,'run_economic_monte_carlo',wraps=core.monte_carlo_economics.run_economic_monte_carlo) as spy:r=full()
        self.assertEqual(spy.call_count,1);self.assertEqual(r.risk.valid_trials,1000)
        for name in ['Mean NPV','Median NPV','P10 NPV','P50 NPV','P90 NPV']:self.assertEqual(r.metric(name).value,30000)
        self.assertEqual(r.metric('Probability NPV > 0').value,100)
    def test_mode_excludes_unselected_financial_models(self):
        with patch.object(core.monte_carlo_economics,'run_economic_monte_carlo',side_effect=AssertionError('Must not run')):r=build(optional_economic_inputs=economic(),optional_risk_inputs=core.RiskInputs((),1000,42))
        self.assertIsNone(r.economic);self.assertIsNone(r.risk);self.assertFalse(any('independent' in a for a in r.assumptions))
    def test_missing_optional_datasets_are_none(self):
        r=build(technical(bep_flow=None,efficiency=None,power=None,npshr=None,npsha=None,driver_rating=None))
        for name in ['Percent of BEP','Operating Efficiency','Pump Shaft Power','Vendor NPSHR','NPSH Margin','NPV','P10 NPV']:self.assertIsNone(r.metric(name).value);self.assertEqual(r.metric(name).status,core.NOT_EVALUATED)
        self.assertIsNotNone(r.metric('Operating Flow').value)
    def test_optional_error_isolation_no_extrapolation(self):
        bad=curve(((200,70),(250,80),(300,75)),'%');r=build(technical(efficiency=bad,power=core.CurveInput((),'m³/hr','kW','Malformed vendor power data')))
        self.assertEqual(r.metric('Operating Efficiency').status,core.OUTSIDE);self.assertIsNone(r.metric('Pump Shaft Power').value);self.assertIsNotNone(r.metric('NPSH Margin').value)
    def test_bad_economics_and_risk_preserve_technical(self):
        r=build(mode=core.MODES[3],optional_economic_inputs=economic(discount_rate_percent=None));self.assertIsNone(r.economic);self.assertIsNotNone(r.metric('Operating Flow').value)
        r=full(optional_risk_inputs=core.RiskInputs(((core.monte_carlo_economics.CAPEX,core.monte_carlo_economics.DistributionSpec('Normal',mean=1,standard_deviation=-1)),),1000,42));self.assertIsNone(r.risk);self.assertEqual(r.metric('NPV').value,30000)
    def test_multiple_intersections_require_explicit_choice(self):
        data=technical(pump=core.CurveInput(((0,0),(1,4),(2,0)),'m³/s','m'),system=core.SystemInput(1,'m','Direct K',k_si=0))
        r=build(data);self.assertEqual(len(r.technical.operating_points.points),2);self.assertIsNone(r.technical.selected_point);self.assertIsNone(r.metric('Operating Flow').value)
        r=build(replace(data,selected_intersection=1));self.assertEqual(r.metric('Operating Flow').value,1.75);self.assertIn('Explicit intersection index 1',r.metric('Operating Point Selection').value)
    def test_coincident_interval_not_silently_selected(self):
        r=build(technical(pump=core.CurveInput(((0,10),(1,10),(2,20)),'m³/s','m'),system=core.SystemInput(10,'m','Direct K',k_si=0)));self.assertTrue(r.technical.operating_points.coincident_intervals);self.assertIsNone(r.technical.selected_point)
    def test_invalid_selection_no_fallback(self):self.assertIsNone(build(technical(selected_intersection=99)).technical.selected_point)
    def test_no_roots_no_fake_zero_operating_flow(self):
        r=build(technical(system=core.SystemInput(100,'m','Direct K',k_si=0)));self.assertEqual(r.metric('Valid Isolated Intersections').value,0);self.assertIsNone(r.metric('Operating Flow').value)
    def test_completeness_is_presence_not_a_score(self):
        r=build(technical(npshr=None));d={r.dataset:r.status for r in r.completeness};self.assertEqual(d['NPSHR Curve'],'Not Supplied');self.assertEqual(d['Pump Head Curve'],'Available');self.assertEqual(d['Economic Inputs'],'Not Required for Selected Mode');self.assertFalse(any('score' in m.metric.lower() for m in r.items))
    def test_traceability_sources(self):
        r=full();expected={'Operating Flow':'Phase 3G','Percent of BEP':'Phase 3H','Operating Efficiency':'Phase 3M','Pump Shaft Power':'Phase 3N','Vendor NPSHR':'Phase 3O','NPSH Margin':'Phase 3J','Local Pump Curve Slope':'Phase 3Q','Operating Flow Shift':'Phase 3R','VSD Operating Flow':'Phase 3S','Required Speed':'Phase 3T','Hydraulic Power Reduction':'Phase 3U','Annual Supply Electrical Energy':'Phase 3V','NPV':'Phase 3W','Break-Even Incremental CAPEX':'Phase 3X','P10 NPV':'Phase 3Y'}
        for name,source in expected.items():self.assertEqual(r.metric(name).source,source)
    def test_only_explicit_criteria_compared(self):
        r=build(technical(required_npsh_margin_m=9,required_driver_margin_percent=20));self.assertEqual(r.metric('Entered NPSH Margin Criterion').value,'Does not meet entered required margin');self.assertEqual(r.metric('Entered Driver Margin Criterion').value,'Meets entered driver power margin')
    def test_negative_margin_and_signed_display(self):
        r=build(technical(npsha=2));value,unit=ui.display_item(r.metric('NPSH Margin'),'m³/hr','ft','kW','QAR',FLOW);self.assertLess(float(value),0);self.assertEqual(unit,'ft')
    def test_phase2h_object_reused_by_phase3j(self):
        from piping_hydraulics.npsha import source_npsha
        a=source_npsha(pressure_pa=101325,basis='Absolute',vapor_pressure_pa=3000,density=1000,velocity=0,elevation=3,datum_elevation=0,suction_loss=1)
        with patch.object(core.npsh_margin,'margin_from_phase2h',wraps=core.npsh_margin.margin_from_phase2h) as spy:r=build(technical(npsha=a))
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(r.metric('NPSH Margin').value,8.236049704007325,9)
    def test_plot_sources_and_separate_axes(self):
        r=full();spec=ui.technical_plot_spec(r,'m³/hr','m',FLOW);self.assertNotIn('data',spec);self.assertTrue(any(p['series'].startswith('Verified Target') for p in spec['layer'][1]['data']['values']));self.assertEqual(spec['encoding']['y']['title'],'Head (m)')
    def test_no_phase3l_dependency_and_immutable(self):
        self.assertNotIn('series_parallel',inspect.getsource(core));r=build()
        with self.assertRaises(FrozenInstanceError):r.mode='other'
    def test_previous_python_files_unchanged_except_registration(self):
        for path,digest in BASELINE_HASHES.items():
            data=(ROOT/path).read_bytes()
            if path in ('tests/test_phase3w_lifecycle_cost.py','tests/test_phase3x_economic_sensitivity.py','tests/test_phase3y_monte_carlo_economics.py'):data=data.decode().replace('len(at.expander),31','len(at.expander),30').encode()
            self.assertEqual(hashlib.sha256(data).hexdigest(),digest,path)

class IntegratedAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_string('from app import FLOW\nfrom pump_performance.integrated_summary_ui import render_integrated_summary\nrender_integrated_summary(FLOW)').run()
    def fill(self,vendor=True):
        at=self.app();at.selectbox(key='p3z_flow_unit').select('m³/hr');at.selectbox(key='p3z_head_unit').select('m');at.text_area(key='p3z_pump').set_value('\n'.join(f'{q},{h}' for q,h in HEAD))
        for key,value in [('static',10),('reference_flow',100),('friction',20)]:at.number_input(key='p3z_'+key).set_value(value)
        if vendor:at.multiselect(key='p3z_vendor').set_value(list(ui.VENDOR))
        at.run()
        if vendor:
            at.selectbox(key='p3z_power_unit').select('kW');at.number_input(key='p3z_bep').set_value(150);at.number_input(key='p3z_npsha').set_value(12.026359664105);at.number_input(key='p3z_driver').set_value(15)
            for key,points in [('eff',EFF),('power',POWER),('npshr',NPSHR)]:at.text_area(key='p3z_'+key).set_value('\n'.join(f'{q},{v}' for q,v in points))
        return at
    def calc(self,at):at.button(key='p3z_build').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def alltext(self,at):return '\n'.join(w.value for w in list(at.text)+list(at.markdown)+list(at.caption)+list(at.warning))
    def economic_inputs(self,at):
        at.selectbox(key='p3z_mode').select(core.MODES[3]).run()
        for key,value in [('cost_a',100000),('cost_b',70000),('capex_a',0),('capex_b',120000),('years',5),('discount',0)]:at.number_input(key='p3z_econ_'+key).set_value(value)
        return at
    def test_full_app_registers_and_opens_new_panel(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(ROOT/'app.py')).run();self.assertFalse(at.exception);self.assertEqual(len(at.expander),31);self.assertTrue(any(e.label==ui.TITLE for e in at.expander));self.assertFalse([w for w in at.text_area if w.key=='p3z_pump']);at.session_state['p3z_panel']=True;at.run();self.assertFalse(at.exception);self.assertEqual(at.text_area(key='p3z_pump').value,'')
    def test_panel_collapse_preserves_entered_inputs(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(ROOT/'app.py')).run();at.session_state['p3z_panel']=True;at.run();at.text_area(key='p3z_pump').set_value('0,50\n100,40\n200,20').run();at.session_state['p3z_panel']=False;at.run();at.session_state['p3z_panel']=True;at.run();self.assertEqual(at.text_area(key='p3z_pump').value,'0,50\n100,40\n200,20')
    def test_technical_defaults_blank_no_financial_inputs(self):
        at=self.app();self.assertIsNone(at.selectbox(key='p3z_flow_unit').value);self.assertIsNone(at.selectbox(key='p3z_head_unit').value)
        for w in at.number_input:self.assertIsNone(w.value)
        self.assertFalse([w for w in at.number_input if w.key.startswith('p3z_econ_')]);self.assertFalse(at.checkbox)
    def test_mandatory_technical_benchmark_ui(self):
        at=self.calc(self.fill());text=self.text(at)
        for expected in ['Operating Flow: 124.596248337 m³/hr','Operating Head: 41.0484501995 m','Percent of BEP: 83.0641655583 %','Operating Efficiency: 80.9515498005 %','Pump Shaft Power: 9.97577490024 kW','Vendor NPSHR: 3.7903099601 m','NPSH Margin: 8.23604970401 m','Local Pump Curve Slope: -0.12 m per (m³/hr)']:self.assertIn(expected,text)
    def test_real_ui_calls_technical_kernels(self):
        at=self.fill()
        with ExitStack() as stack:
            pairs=[(core.operating_point,'find_operating_points'),(core.bep_operating_range,'compare_bep'),(core.efficiency_curve,'interpolate_efficiency'),(core.power_curve,'interpolate_power'),(core.npshr_curve,'interpolate_npshr'),(core.npsh_margin,'calculate_npsh_margin'),(core.curve_characteristics,'local_curve_slope')];spies=[stack.enter_context(patch.object(m,n,wraps=getattr(m,n))) for m,n in pairs];self.calc(at)
            for spy in spies:self.assertGreaterEqual(spy.call_count,1)
    def test_missing_bep_efficiency_power_npshr_ui(self):
        at=self.calc(self.fill(False));text=self.text(at)
        for name in ['Percent of BEP','Operating Efficiency','Pump Shaft Power','Vendor NPSHR','NPSH Margin']:self.assertIn(name+': N/A',text)
        self.assertIn('Operating Flow: 124.596248337',text)
    def test_multiple_intersections_and_explicit_selection_ui(self):
        at=self.fill(False);at.selectbox(key='p3z_flow_unit').select('m³/s');at.selectbox(key='p3z_system_method').select('Direct K').run();at.number_input(key='p3z_static').set_value(1);at.number_input(key='p3z_k').set_value(0);at.text_area(key='p3z_pump').set_value('0,0\n1,4\n2,0');self.calc(at);self.assertIn('Operating Flow: N/A',self.text(at));self.assertIn('Multiple Valid Intersections',self.alltext(at));self.assertIn('>0.25</td>',self.alltext(at));self.assertIn('>1.75</td>',self.alltext(at));at.number_input(key='p3z_index').set_value(1);self.calc(at);self.assertIn('Operating Flow: 1.75 m³/s',self.text(at));self.assertIn('Explicit intersection index 1',self.text(at))
    def test_malformed_vendor_curve_isolated(self):
        at=self.fill();at.text_area(key='p3z_eff').set_value('not a point');self.calc(at);self.assertIn('Operating Efficiency: N/A',self.text(at));self.assertIn('Pump Shaft Power: 9.97577490024',self.text(at))
    def test_vendor_extrapolation_not_performed(self):
        at=self.fill();at.text_area(key='p3z_eff').set_value('200,70\n250,80\n300,75');self.calc(at);self.assertIn('Outside Supplied Curve Range',self.alltext(at));self.assertIn('Operating Efficiency: N/A',self.text(at))
    def test_optional_vsd_target_control_ui(self):
        at=self.fill();at.multiselect(key='p3z_extensions').set_value(['Variable-Speed Operating Point','Target-Flow Required Speed','Throttling vs VSD']).run()
        for key,value in [('reference_speed',1500),('new_speed',1200),('target',100),('density',1000)]:at.number_input(key='p3z_'+key).set_value(value)
        self.calc(at);text=self.text(at)
        for expected in ['VSD Operating Flow: 92.1722858517','Required Speed: 1270.30259878','Throttling Head: 44','Required Throttled K: 44064','Resistance Increase: 70','Hydraulic Power Reduction: 31.8181818182']:self.assertIn(expected,text)
        self.assertIn('not electrical-energy saving',self.alltext(at))
    def test_modified_system_ui(self):
        at=self.fill();at.multiselect(key='p3z_extensions').set_value(['Modified System']).run();at.number_input(key='p3z_modified_static').set_value(12);at.number_input(key='p3z_modified_k').set_value(30000);self.calc(at);self.assertNotIn('Operating Flow Shift: N/A',self.text(at));self.assertIn('[Phase 3R;',self.text(at))
    def test_technical_energy_49000_ui(self):
        at=self.fill();at.selectbox(key='p3z_mode').select(core.MODES[1]).run();at.number_input(key='p3z_energy_count').set_value(3).run()
        for i,(power,hours) in enumerate([(10,2000),(8,3000),(5,1000)]):at.number_input(key=f'p3z_en{i}_power').set_value(power);at.number_input(key=f'p3z_en{i}_hours').set_value(hours);at.selectbox(key=f'p3z_en{i}_basis').select('Electrical Input Power')
        at.number_input(key='p3z_tariff').set_value(.12);self.calc(at);self.assertIn('Annual Supply Electrical Energy: 49000 kWh/year',self.text(at));self.assertIn('Annual Supply Electrical Operating Cost: 5880',self.text(at))
    def test_full_economic_benchmark_without_risk(self):
        at=self.economic_inputs(self.fill());self.calc(at);text=self.text(at)
        for expected in ['Annual Operating Cost Difference: 30000','Simple Payback: 4 years','NPV: 30000','P10 NPV: N/A','Probability NPV > 0: N/A']:self.assertIn(expected,text)
    def test_full_fixed_monte_carlo_ui_reuses_phase3y(self):
        at=self.economic_inputs(self.fill());at.selectbox(key='p3z_risk_mode').select('All Entered Economic Inputs Fixed').run();at.selectbox(key='p3z_trials').select(1000);at.number_input(key='p3z_seed').set_value(42)
        with patch.object(core.monte_carlo_economics,'run_economic_monte_carlo',wraps=core.monte_carlo_economics.run_economic_monte_carlo) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1)
        for name in ['P10 NPV','P50 NPV','P90 NPV']:self.assertIn(name+': 30000',self.text(at))
        self.assertIn('Probability NPV > 0: 100 %',self.text(at));self.assertIn('Valid Trials: 1000',self.text(at))
    def test_sensitivity_ui(self):
        at=self.economic_inputs(self.fill());at.selectbox(key='p3z_sensitivity_mode').select('One-Variable Phase 3X Analysis').run();at.selectbox(key='p3z_sensitivity_variable').select('Proposed CAPEX');at.text_area(key='p3z_sensitivity_values').set_value('90000\n120000\n150000\n180000');self.calc(at);self.assertIn('Break-Even Incremental CAPEX: 150000',self.text(at));self.assertIn('>-30000</td>',self.alltext(at))
    def test_missing_economics_does_not_break_full_review(self):
        at=self.fill();at.selectbox(key='p3z_mode').select(core.MODES[3]).run();self.calc(at);self.assertIn('Operating Flow: 124.596248337',self.text(at));self.assertIn('NPV: N/A',self.text(at))
    def test_incomplete_economics_isolated(self):
        at=self.economic_inputs(self.fill());at.number_input(key='p3z_econ_discount').set_value(None);self.calc(at);self.assertIn('NPV: N/A',self.text(at));self.assertIn('Operating Flow: 124.596248337',self.text(at))
    def test_missing_mc_no_probability_assumptions(self):
        at=self.economic_inputs(self.fill());self.calc(at);self.assertIn('Monte Carlo simulation not run',self.alltext(at));self.assertNotIn('inputs are statistically independent',self.alltext(at))
    def test_completeness_traceability_and_flags(self):
        at=self.calc(self.fill(False));text=self.alltext(at);self.assertIn('Not Supplied',text);self.assertIn('Not Required for Selected Mode',text);self.assertIn('Phase 3G',text);self.assertIn('Criterion Not Entered',text);self.assertIn('Vendor BEP not entered',text)
    def test_plots_separate_vendor_quantities(self):
        at=self.calc(self.fill());specs=[json.loads(w.proto.spec) for w in at.get('vega_lite_chart')];self.assertEqual(len(specs),4);self.assertEqual(specs[0]['encoding']['y']['title'],'Head (m)');self.assertEqual(specs[1]['encoding']['y']['title'],'Operating Efficiency (%)');self.assertEqual(specs[2]['encoding']['y']['title'],'Pump Shaft Power (kW)')
    def test_case_identification_and_currency_label(self):
        at=self.economic_inputs(self.fill());at.text_input(key='p3z_id_tag').set_value('P-101');at.text_input(key='p3z_currency').set_value('QAR');self.calc(at);self.assertIn('Pump Tag: P-101',self.text(at));self.assertIn('NPV: 30000 QAR',self.text(at))
    def test_previous_review_is_marked_stale_and_not_rebuilt(self):
        at=self.calc(self.fill())
        with patch.object(core,'build_integrated_pump_summary',wraps=core.build_integrated_pump_summary) as spy:at.number_input(key='p3z_static').set_value(12).run()
        self.assertEqual(spy.call_count,0);self.assertTrue(any('previous review' in w.value for w in at.warning))
    def test_no_overall_classification_or_score_widgets(self):
        at=self.calc(self.fill());labels=' '.join(w.label for w in at.number_input).lower();self.assertNotIn('score',labels);self.assertFalse(at.checkbox)
        for item in at.session_state['p3z_last'][1].items:self.assertNotIn(item.metric.lower(),['overall score','overall pass/fail','approval'])
    def test_guidance_and_screen_review_only(self):
        at=self.app();text=self.alltext(at)
        for sentence in ui.GUIDANCE:self.assertIn(sentence,text)
        self.assertFalse(at.get('download_button'));self.assertFalse(at.checkbox)

BASELINE_HASHES = {'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/annual_energy.py': 'f045aa111fb96d38485b8e9b5e270a1a2b798114612173e256dc7dc9401dc108', 'pump_performance/annual_energy_ui.py': '797a0e013a1d0c870de12e8dddfc191d268a8846b8ce042dc274780857eba382', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/control_strategy.py': 'ba639b265ebeaaa6baa878b102591c8f8fa7222b223df1a289fa11ee4a78127e', 'pump_performance/control_strategy_ui.py': '13b63e57b7d58d88127a4643fa524e5e8640577836097447a3348537e480bfca', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/economic_sensitivity.py': 'e7cf8a7d9a95302ce709ea76b28ea1c76fb71dbb075e90bab70100503b9805b4', 'pump_performance/economic_sensitivity_ui.py': 'd1fc037ef2e1369ffd247855ecda10824f4bfab5fc5fabd88ab7a1e690a4149b', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/lifecycle_cost.py': '185a04b2ad59a5a6ed6a8a316c0e98352aea7157c713fa05d0a8085bf871a685', 'pump_performance/lifecycle_cost_ui.py': '3b27a28c06f9c632161d446fec24ba32c0e62bd8e4393f4156156cb736806b6c', 'pump_performance/monte_carlo_economics.py': 'db75e8a3b43bf7dd54cc0c224541f83a096f7e7d8755f26742ec43655c2cb492', 'pump_performance/monte_carlo_economics_ui.py': '97b94f94cc6019912475e19927c2b7dcc1af98416e280b588f52f0053b323981', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase3u_control_strategy.py': 'd07890f6e10820eebbcbd3d268877eb1cb1afda752bb8764f72c2005e07dd4ac', 'tests/test_phase3v_annual_energy.py': '04538377205a188dbf53f2938eacd58960d64b993da0f8b955347630d919b217', 'tests/test_phase3w_lifecycle_cost.py': 'b7cf29bd992947b5bcdc8d69a6e674e1fefcc7d2dfbe513cc1dde87f90584728', 'tests/test_phase3x_economic_sensitivity.py': '56ca25cbcfeb7303dc0652f87134fc33e337379af011e763eabc35f488921bb4', 'tests/test_phase3y_monte_carlo_economics.py': '9b2dfef3b7f2c362a0534514d8a8e5bf52ac6c8962a0fa7e27f3c823d983908c'}
