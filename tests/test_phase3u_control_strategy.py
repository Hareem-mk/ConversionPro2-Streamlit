"""Same-target strategy, shaft/input boundaries and Streamlit integration."""
import unittest,math,json,hashlib
from pathlib import Path
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from app import FLOW
from pump_performance import control_strategy as core,control_strategy_ui as ui
from pump_performance.pump_curve import create_pump_curve,HEAD_FACTORS
from pump_performance.system_curve import model_from_reference,SystemModel
from pump_performance.power_curve import create_power_curve

ROOT=Path(__file__).resolve().parents[1]
HEAD=[(0,50),(50,48),(100,44),(150,38),(200,30)]
POWER=[(50,6),(100,8.5),(150,11.5),(200,14),(250,16)]
def curve(points=HEAD,fu='m³/hr',hu='m'):return create_pump_curve(points,fu,hu,FLOW)
def system(static=10):return model_from_reference(static_head=static,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)
def evaluate(q=100,static=10):return core.compare_throttling_and_vsd(curve(),1500,system(static),q/3600,1000)
def power():return create_power_curve(POWER,'m³/hr','kW',FLOW)
def shaft():return core.compare_shaft_power(power(),1500,evaluate().vsd.solutions[0].required_speed_rpm,100/3600)

class ControlCoreTests(unittest.TestCase):
    def test_constant_benchmark_head_k_resistance(self):
        r=evaluate();self.assertIsNone(r.constant_speed_error);self.assertEqual(r.constant_speed.head_m,44);self.assertEqual(r.constant_speed.friction_head_m,34);self.assertEqual(r.constant_speed.system.k_si,44064);self.assertEqual(r.resistance_change.difference,18144);self.assertEqual(r.resistance_change.percent,70)
    def test_constant_forward_same_target(self):
        p=evaluate().constant_speed.verified_point;self.assertAlmostEqual(p.flow_m3_s*3600,100,10);self.assertEqual(p.head_m,44);self.assertLess(abs(p.residual_m),1e-9)
    def test_vsd_reuses3t_and_same_target(self):
        with patch.object(core,'solve_speed_for_target_flow',wraps=core.solve_speed_for_target_flow) as spy:r=evaluate()
        self.assertEqual(spy.call_count,1);s=r.vsd.solutions[0];self.assertAlmostEqual(s.required_speed_rpm,1270.302598778999,8);self.assertAlmostEqual(s.verified_flow_m3_s*3600,100,10);self.assertAlmostEqual(s.verified_head_m,30,10)
    def test_head_hydraulic_differences(self):
        r=evaluate();d=core.difference_relative_to_first(r.constant_speed.head_m,r.vsd.target_system_head_m);self.assertEqual(d.difference,14);self.assertAlmostEqual(d.percent,31.818181818181817,12)
        self.assertAlmostEqual(r.constant_hydraulic_w,11985.905555555555,8);self.assertAlmostEqual(r.vsd_hydraulic_w[0],8172.208333333333,8);d=core.difference_relative_to_first(r.constant_hydraulic_w,r.vsd_hydraulic_w[0]);self.assertAlmostEqual(d.difference,3813.697222222222,8);self.assertAlmostEqual(d.percent,31.818181818181817,11)
    def test_shared_interpolation_system_solver_hydraulic(self):
        with patch.object(core,'interpolate_pump_head',wraps=core.interpolate_pump_head) as e,patch.object(core,'model_from_reference',wraps=core.model_from_reference) as f,patch.object(core,'find_operating_points',wraps=core.find_operating_points) as g,patch.object(core,'hydraulic_power',wraps=core.hydraulic_power) as a:r=evaluate()
        self.assertEqual(e.call_count,1);self.assertEqual(f.call_count,1);self.assertEqual(g.call_count,1);self.assertEqual([x.kwargs['head_m'] for x in a.call_args_list],[0,44,30])
    def test_positive_target_speed_density(self):
        for bad in [0,-1,None,True,math.inf,math.nan,-math.inf]:
            for args in [(1500,bad,1000),(bad,100/3600,1000),(1500,100/3600,bad)]:
                with self.assertRaises(ValueError):core.compare_throttling_and_vsd(curve(),args[0],system(),args[1],args[2])
    def test_negative_and_zero_required_friction_rejected(self):
        for static in [44,50]:
            with self.assertRaisesRegex(ValueError,'nonnegative quadratic'):core.solve_constant_speed_system_for_target_flow(curve(),static,100/3600)
    def test_constant_unavailable_vsd_preserved(self):
        for q,static in [(250,10),(100,50)]:
            r=evaluate(q,static);self.assertIsNone(r.constant_speed);self.assertTrue(r.constant_speed_error);self.assertTrue(r.vsd.solutions);self.assertTrue(r.vsd_hydraulic_w)
    def test_vsd_unavailable_constant_preserved(self):
        c=curve([(1,10),(2,10),(3,10)],'m³/s');r=core.compare_throttling_and_vsd(c,1500,SystemModel(0,100),1,1000);self.assertIsNotNone(r.constant_speed);self.assertFalse(r.vsd.solutions)
    def test_above_base_reduced_resistance(self):
        r=evaluate(150);self.assertEqual(r.constant_speed.system.k_si,16128);self.assertLess(r.resistance_change.percent,0);self.assertGreater(r.vsd.solutions[0].required_speed_rpm,1500)
    def test_zero_base_k_no_percent(self):
        r=core.compare_throttling_and_vsd(curve(),1500,SystemModel(10,0),100/3600,1000);self.assertIsNone(r.resistance_change.percent)
    def test_scaled_full_vendor_power_curve(self):
        s=shaft();self.assertEqual(s.constant_w,8500);self.assertAlmostEqual(s.vsd_w,5821.5220936881715,8);self.assertAlmostEqual(s.difference.difference,2678.4779063118285,8);self.assertAlmostEqual(s.difference.percent,31.51150478013916,10)
        ratio=evaluate().vsd.solutions[0].ratio
        for p,(q,w) in zip(s.scaled_curve.points,POWER):self.assertAlmostEqual(p.flow_m3_s,q/3600*ratio,13);self.assertAlmostEqual(p.shaft_power_w,w*1000*ratio**3,8)
    def test_power_interpolation_after_scaling(self):
        reference=power()
        with patch.object(core,'interpolate_power',wraps=core.interpolate_power) as n,patch.object(core,'calculate_speed_affinity',wraps=core.calculate_speed_affinity) as i:s=core.compare_shaft_power(reference,1500,evaluate().vsd.solutions[0].required_speed_rpm,100/3600)
        self.assertEqual(n.call_count,2);self.assertIs(n.call_args_list[0].args[0],reference);self.assertIs(n.call_args_list[1].args[0],s.scaled_curve);self.assertIsNot(n.call_args_list[1].args[0],reference);self.assertEqual(i.call_count,6) # includes reference-speed validation in evaluate()
    def test_power_out_of_range_no_extrapolation(self):
        with self.assertRaises(ValueError):core.compare_shaft_power(power(),1500,1200,1)
    def test_motor_and_vfd_separate_explicit(self):
        s=shaft();v=core.compare_input_power(s,90,88,97);self.assertAlmostEqual(v.constant_motor_input_w,9444.444444444443,8);self.assertAlmostEqual(v.vsd_motor_input_w,6615.36601555474,8);self.assertAlmostEqual(v.vsd_drive_input_w,6819.964964489423,8)
        self.assertIsNone(core.compare_input_power(s,90,88).vsd_drive_input_w)
        for values in [(None,88,97),(90,None,97),(0,88,97),(90,105,97),(90,88,0),(90,88,101)]:
            with self.assertRaises(ValueError):core.compare_input_power(s,*values)
    def test_annual_requires_comparable_supply_power(self):
        for p in [None,core.compare_input_power(shaft(),90,88)]:
            with self.assertRaises(ValueError):core.annual_energy(p,4000,.12)
    def test_annual_explicit_benchmark(self):
        p=core.compare_input_power(shaft(),90,88,97);a=core.annual_energy(p,4000,.12);self.assertAlmostEqual(a.constant_kwh,37777.777777777774,8);self.assertAlmostEqual(a.vsd_kwh,27279.859857957694,8);self.assertAlmostEqual(a.difference_kwh,10497.91791982008,8);self.assertAlmostEqual(a.difference_cost,1259.7501503784094,8)
        self.assertEqual(core.annual_energy(p,0,0).difference_kwh,0);self.assertIsNone(core.annual_energy(p,100).difference_cost)
    def test_shaft_below_hydraulic_basis_rejected(self):
        r=evaluate()
        with self.assertRaisesRegex(ValueError,'below calculated hydraulic'):core.validate_shaft_hydraulic_basis(shaft(),r.constant_hydraulic_w,r.vsd_hydraulic_w[0])
        p=core.compare_shaft_power(create_power_curve([(q,p*2) for q,p in POWER],'m³/hr','kW',FLOW),1500,r.vsd.solutions[0].required_speed_rpm,100/3600)
        core.validate_shaft_hydraulic_basis(p,r.constant_hydraulic_w,r.vsd_hydraulic_w[0])
    def test_annual_validation(self):
        p=core.compare_input_power(shaft(),90,88,97)
        for bad in [-1,True,math.inf,math.nan]:
            with self.assertRaises(ValueError):core.annual_energy(p,bad,.12)
            with self.assertRaises(ValueError):core.annual_energy(p,4000,bad)
    def test_all_equivalent_flow_head_units(self):
        for fu,ff in FLOW.items():
            for hu,hf in HEAD_FACTORS.items():
                c=curve([(q/3600/ff,h/hf) for q,h in HEAD],fu,hu);s=model_from_reference(static_head=10/hf,head_unit=hu,reference_flow=100/3600/ff,reference_friction_head=20/hf,flow_unit=fu,flow_factors=FLOW);r=core.compare_throttling_and_vsd(c,1500,s,100/3600,1000);self.assertAlmostEqual(r.constant_speed.system.k_si,44064,7);self.assertAlmostEqual(r.vsd.solutions[0].required_speed_rpm,1270.302598778999,8)
    def test_plot_same_target_bounded_domains(self):
        r=evaluate();s=r.vsd.solutions[0];p=ui.comparison_plot_spec(curve(),r,s,FLOW['m³/hr'],'m³/hr','m');self.assertEqual(len(p['layer']),6);markers=[x['data']['values'][0] for x in p['layer'] if x['mark']['type']=='point'];self.assertEqual([x['flow'] for x in markers],[100,100]);self.assertEqual([x['head'] for x in markers],[44,30]);self.assertEqual(p['layer'][0]['data']['values'][-1]['flow'],200)
    def test_immutable_and_zero_power_percent(self):
        r=evaluate()
        with self.assertRaises(FrozenInstanceError):r.constant_hydraulic_w=1
        self.assertIsNone(core.difference_relative_to_first(0,0).percent)

class ControlAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,*,q=100,static=10,direct=False,k=25920,points=HEAD,fu='m³/hr',hu='m',ref=100,friction=20):
        at=self.app();at.number_input(key='p3u_head_count').set_value(len(points));at.selectbox(key='p3u_method').select(ui.METHODS[0 if direct else 1]).run();at.selectbox(key='p3u_flow_unit').select(fu);at.selectbox(key='p3u_head_unit').select(hu);at.selectbox(key='p3u_display_power_unit').select('kW')
        for i,(flow,head) in enumerate(points):at.number_input(key=f'p3u_head_q_{i}').set_value(flow);at.number_input(key=f'p3u_head_v_{i}').set_value(head)
        at.number_input(key='p3u_speed').set_value(1500);at.number_input(key='p3u_target').set_value(q);at.number_input(key='p3u_static').set_value(static);at.number_input(key='p3u_density').set_value(1000)
        if direct:at.number_input(key='p3u_k').set_value(k)
        else:at.number_input(key='p3u_reference_flow').set_value(ref);at.number_input(key='p3u_friction').set_value(friction)
        return at
    def calc(self,at):at.button(key='p3u_compare').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def enable_power(self,at,fu='m³/hr',pu='kW',multiplier=1):
        at.selectbox(key='p3u_power_mode').select('Reference-Speed Vendor Power Curve').run();at.number_input(key='p3u_power_count').set_value(5).run();at.selectbox(key='p3u_power_flow_unit').select(fu);at.selectbox(key='p3u_power_value_unit').select(pu)
        for i,(q,p) in enumerate(POWER):at.number_input(key=f'p3u_power_q_{i}').set_value(q/3600/FLOW[fu]);at.number_input(key=f'p3u_power_v_{i}').set_value(p*1000*multiplier/ui.POWER_FACTORS[pu])
        return at
    def test_render_blank_numeric_economics_units(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3U — Throttling vs VSD Control Comparison / Energy Impact Analysis' for e in at.expander))
        for w in at.number_input:
            if w.key.startswith('p3u_') and w.key!='p3u_head_count':self.assertIsNone(w.value)
        self.assertEqual(at.text_input(key='p3u_currency').value,'');self.assertFalse([w for w in at.checkbox if w.key.startswith('p3u_')])
    def test_mandatory_constant_benchmark(self):
        at=self.calc(self.fill());self.assertFalse(at.error)
        for text in ['Reference Pump Head at Target: 44 m','Required Friction Head at Target: 34 m','Required Constant-Speed System K: 44064 s²/m⁵','Resistance Change: +18144 s²/m⁵','Resistance Change Percent: +70%','Constant-Speed Verified Flow: 100 m³/hr','Constant-Speed Verified Head: 44 m']:self.assertIn(text,self.text(at))
    def test_mandatory_vsd_head_power_differences(self):
        at=self.calc(self.fill());text=self.text(at)
        for v in ['VSD Required Speed: 1270.30259878 rpm','VSD Verified Flow: 100 m³/hr','VSD Verified Head: 30 m','Head Difference (Constant-Speed minus VSD): +14 m','Head Difference Percent: +31.8181818182%','Constant-Speed Hydraulic Power: 11.9859055556 kW','VSD Hydraulic Power: 8.17220833333 kW','Hydraulic Power Difference: +3.81369722222 kW']:self.assertIn(v,text)
    def test_shared3a3t_ui(self):
        with patch.object(core,'solve_speed_for_target_flow',wraps=core.solve_speed_for_target_flow) as t,patch.object(core,'hydraulic_power',wraps=core.hydraulic_power) as a:at=self.calc(self.fill())
        self.assertEqual(t.call_count,1);self.assertEqual([c.kwargs['head_m'] for c in a.call_args_list],[0,44,30])
    def test_direct_k_equivalence(self):
        at=self.calc(self.fill(direct=True));self.assertIn('Required Constant-Speed System K: 44064',self.text(at));self.assertFalse(at.error)
    def test_above_base_neutral_constant_speed(self):
        at=self.calc(self.fill(q=150));self.assertIn('Required Constant-Speed System K: 16128',self.text(at));self.assertTrue(any(w.value=='**Required Constant-Speed System Resistance**' for w in at.markdown));self.assertFalse(any(w.value=='**Constant-Speed Throttling Case**' for w in at.markdown));self.assertTrue(any('not a throttling-only' in w.value for w in at.info))
    def test_zero_negative_k_boundary_unavailable_vsd_valid(self):
        for static in [44,50]:
            at=self.calc(self.fill(static=static));self.assertTrue(any(core.INVALID_RESISTANCE in w.value for w in at.info));self.assertIn('VSD Required Speed:',self.text(at));self.assertNotIn('Required Constant-Speed System K:',self.text(at))
    def test_target_outside_reference_retains_vsd(self):
        at=self.calc(self.fill(q=250));self.assertTrue(any('Constant-Speed Strategy Unavailable' in w.value for w in at.info));self.assertIn('VSD Verified Flow: 250 m³/hr',self.text(at))
    def test_vsd_unavailable_retains_constant(self):
        at=self.calc(self.fill(q=1,points=[(1,10),(2,10),(3,10)],fu='m³/s',static=0,k=100,direct=True));self.assertIn('Constant-Speed Verified Flow: 1 m³/s',self.text(at));self.assertNotIn('VSD Required Speed:',self.text(at));self.assertTrue(any('VSD Strategy Unavailable' in w.value for w in at.info))
    def test_invalid_required_inputs(self):
        for key in ['p3u_target','p3u_density','p3u_speed']:
            at=self.fill();at.number_input(key=key).set_value(0);self.calc(at);self.assertTrue(at.error)
    def test_vendor_power_scaled_before_interpolation(self):
        at=self.enable_power(self.fill())
        with patch.object(core,'interpolate_power',wraps=core.interpolate_power) as n,patch.object(core,'scale_vendor_power_curve',wraps=core.scale_vendor_power_curve) as scale:self.calc(at)
        self.assertEqual(n.call_count,2);self.assertEqual(scale.call_count,1);self.assertIsNot(n.call_args_list[0].args[0],n.call_args_list[1].args[0]);self.assertIn('Vendor-Interpolated Throttling Shaft Power: 8.5 kW',self.text(at));self.assertIn('Affinity-Law Scaled VSD Shaft Power: 5.82152209369 kW',self.text(at));self.assertFalse(at.error);self.assertEqual(len(at.get('vega_lite_chart')),2)
    def test_inconsistent_benchmark_blocks_electrical_annual(self):
        at=self.enable_power(self.fill())
        for key,v in [('motor_constant',90),('motor_vsd',88),('vfd_efficiency',97),('hours',4000)]:at.number_input(key='p3u_'+key).set_value(v)
        at.number_input(key='p3u_driver').set_value(10);at.selectbox(key='p3u_driver_unit').select('kW')
        self.calc(at);self.assertNotIn('Driver Margin:',self.text(at));self.assertIn('Affinity-Law Scaled VSD Shaft Power: 5.82152209369 kW',self.text(at));self.assertNotIn('Motor Input Power:',self.text(at));self.assertNotIn('Annual Electrical Energy:',self.text(at));self.assertTrue(any('below calculated hydraulic power' in w.value for w in at.info))
    def test_optional_efficiencies_blank(self):
        at=self.enable_power(self.fill())
        for key in ['motor_constant','motor_vsd','vfd_efficiency','driver']:self.assertIsNone(at.number_input(key='p3u_'+key).value)
    def test_annual_not_from_hydraulic(self):
        at=self.fill();at.number_input(key='p3u_hours').set_value(4000);self.calc(at);self.assertNotIn('Annual Electrical Energy:',self.text(at));self.assertTrue(any('Annual Electrical Energy Unavailable' in w.value for w in at.info))
    def test_annual_requires_explicit_vfd_efficiency(self):
        at=self.enable_power(self.fill(),multiplier=2);at.number_input(key='p3u_motor_constant').set_value(90);at.number_input(key='p3u_motor_vsd').set_value(88);at.number_input(key='p3u_hours').set_value(4000);self.calc(at);self.assertIn('Motor Input Power:',self.text(at));self.assertNotIn('Annual Electrical Energy:',self.text(at));self.assertTrue(any('Annual Electrical Energy Unavailable' in w.value for w in at.info))
    def test_electrical_annual_explicit_user_inputs(self):
        at=self.enable_power(self.fill(),multiplier=2)
        for key,v in [('motor_constant',90),('motor_vsd',88),('vfd_efficiency',97),('hours',4000),('tariff',.12)]:at.number_input(key='p3u_'+key).set_value(v)
        at.text_input(key='p3u_currency').set_value('QAR');self.calc(at);self.assertFalse(at.error)
        for t in ['Constant-Speed Motor Input Power: 18.8888888889 kW','VFD Supply Input Power: 13.639929929 kW','Constant-Speed Annual Electrical Energy: 75555.5555556 kWh','VSD Annual Electrical Energy: 54559.7197159 kWh','Annual Cost Difference: +2519.50030076 QAR']:self.assertIn(t,self.text(at))
    def test_bad_efficiency_local_primary_kept(self):
        at=self.enable_power(self.fill(),multiplier=2);at.number_input(key='p3u_motor_constant').set_value(0);at.number_input(key='p3u_motor_vsd').set_value(90);self.calc(at);self.assertTrue(at.error);self.assertIn('VSD Required Speed:',self.text(at));self.assertTrue(at.get('vega_lite_chart'))
    def test_driver_shared_margin(self):
        at=self.enable_power(self.fill(),multiplier=2);at.number_input(key='p3u_driver').set_value(20);at.selectbox(key='p3u_driver_unit').select('kW')
        with patch.object(ui,'calculate_driver_margin',wraps=ui.calculate_driver_margin) as spy:self.calc(at)
        self.assertEqual(spy.call_count,2);self.assertIn('Constant-Speed Driver Margin: +3 kW',self.text(at));self.assertFalse(at.error)
    def test_bep_shared3h3i(self):
        at=self.fill();at.number_input(key='p3u_bep').set_value(150/3600);at.selectbox(key='p3u_bep_unit').select('m³/s')
        with patch.object(ui,'compare_bep',wraps=ui.compare_bep) as h,patch.object(ui,'calculate_speed_affinity',wraps=ui.calculate_speed_affinity) as i:self.calc(at)
        self.assertEqual(h.call_count,2);self.assertEqual(i.call_count,1);self.assertIn('Constant-Speed Percent of Vendor BEP: 66.6666666667%',self.text(at));self.assertIn('VSD Percent of Affinity-Scaled BEP: 78.7214007876%',self.text(at))
    def test_mixed_units_and_mechanical_hp_power_curve(self):
        ff=FLOW['Gallon/min (US GPM)'];hf=HEAD_FACTORS['ft'];at=self.fill(q=100/3600/ff,points=[(q/3600/ff,h/hf) for q,h in HEAD],fu='Gallon/min (US GPM)',hu='ft',static=10/hf,ref=100/3600/ff,friction=20/hf);self.enable_power(at,'m³/s','Mechanical hp');self.calc(at);self.assertIn('VSD Required Speed: 1270.30259878 rpm',self.text(at));self.assertIn('Vendor-Interpolated Throttling Shaft Power: 8.5 kW',self.text(at));self.assertFalse(at.error)
    def test_head_plot_both_points_same_target(self):
        at=self.calc(self.fill());p=json.loads(at.get('vega_lite_chart')[0].proto.spec);markers=[l['data']['values'][0] for l in p['layer'] if l['mark']['type']=='point'];self.assertEqual([r['flow'] for r in markers],[100,100]);self.assertEqual([r['head'] for r in markers],[44,30])
    def test_power_plot_separate_axis(self):
        at=self.calc(self.enable_power(self.fill()));specs=[json.loads(c.proto.spec) for c in at.get('vega_lite_chart')];self.assertEqual(specs[0]['encoding']['y']['title'],'Shaft Power (kW)');self.assertEqual(specs[1]['encoding']['y']['title'],'Head (m)');self.assertEqual(specs[0]['encoding']['tooltip'][-1]['title'],'Shaft Power (kW)')
    def test_no_npshr_scaling_or_overall_best(self):
        at=self.calc(self.fill());cap='\n'.join(w.value for w in at.caption)
        for g in ui.GUIDANCE:self.assertIn(g,cap)
        self.assertNotIn('Annual Electrical Energy:',self.text(at));self.assertNotIn('electrical savings',self.text(at).lower());self.assertFalse([w for w in at.checkbox if w.key.startswith('p3u_')])
    def test_zero_base_k_percent_unavailable(self):
        at=self.calc(self.fill(direct=True,k=0));self.assertIn('Resistance Change Percent: N/A — base K is zero',self.text(at))
    def test_stale_results_clear(self):
        at=self.calc(self.fill());at.number_input(key='p3u_target').set_value(80).run();self.assertNotIn('VSD Required Speed:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
    def test_previous_files_unchanged(self):
        expected={'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
