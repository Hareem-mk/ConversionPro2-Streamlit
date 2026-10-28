"""Shared affinity and bounded operating-point integration, including UI paths."""
import hashlib,json,math,unittest
from pathlib import Path
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from app import FLOW
from pump_performance import variable_speed as core,variable_speed_ui as ui
from pump_performance.pump_curve import create_pump_curve,HEAD_FACTORS
from pump_performance.system_curve import model_from_reference,SystemModel
from pump_performance.affinity_laws import calculate_speed_affinity

ROOT=Path(__file__).resolve().parents[1]
HEAD=[(0,50),(50,48),(100,44),(150,38),(200,30)]
def curve(points=HEAD,unit='m³/hr',hu='m'):return create_pump_curve(points,unit,hu,FLOW)
def system(static=10):return model_from_reference(static_head=static,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)
def evaluate(n=1200,static=10):return core.evaluate_variable_speed_operating_point(curve(),1500,n,system(static))

class VariableSpeedCoreTests(unittest.TestCase):
    def test_ratio_reduction_and_all_points(self):
        r=evaluate();self.assertEqual(r.scaling.ratio,.8);self.assertEqual(r.scaling.speed_change_percent,-20)
        for p,(q,h) in zip(r.scaling.scaled_curve.points,[(0,32),(40,30.72),(80,28.16),(120,24.32),(160,19.2)]):
            self.assertAlmostEqual(p.flow_m3_s*3600,q,12);self.assertAlmostEqual(p.head_m,h,12)
    def test_ratio_increase_and_all_points(self):
        r=evaluate(1800);self.assertEqual(r.scaling.ratio,1.2);self.assertEqual(r.scaling.speed_change_percent,20)
        for p,(q,h) in zip(r.scaling.scaled_curve.points,[(0,72),(60,69.12),(120,63.36),(180,54.72),(240,43.2)]):
            self.assertAlmostEqual(p.flow_m3_s*3600,q,12);self.assertAlmostEqual(p.head_m,h,12)
    def test_base_and_reduction_intersection(self):
        r=evaluate();self.assertAlmostEqual(r.base.points[0].flow_m3_s*3600,124.59624833740307,10);self.assertAlmostEqual(r.base.points[0].head_m,41.04845019951163,11)
        self.assertAlmostEqual(r.new.points[0].flow_m3_s*3600,92.17228585166086,10);self.assertAlmostEqual(r.new.points[0].head_m,26.99146055824056,11)
    def test_increase_intersection(self):
        r=evaluate(1800);self.assertAlmostEqual(r.new.points[0].flow_m3_s*3600,155.35307679783985,10);self.assertAlmostEqual(r.new.points[0].head_m,58.269156941111056,11)
    def test_not_direct_old_point_scaling(self):
        r=evaluate();b=r.base.points[0];direct=calculate_speed_affinity(b.flow_m3_s,b.head_m,0,1500,1200)
        self.assertGreater(abs(r.new.points[0].flow_m3_s-direct.estimated_flow_m3_s),.001);self.assertGreater(abs(r.new.points[0].head_m-direct.estimated_head_m),.1)
    def test_shared_affinity_for_every_point_and_ratio(self):
        with patch.object(core,'calculate_speed_affinity',wraps=core.calculate_speed_affinity) as spy:r=evaluate()
        self.assertEqual(spy.call_count,6);self.assertEqual(spy.call_args_list[2].args,(50/3600,48,0,1500,1200))
    def test_shared_solver_and_same_static_system(self):
        s=system()
        with patch.object(core,'find_operating_points',wraps=core.find_operating_points) as spy:r=core.evaluate_variable_speed_operating_point(curve(),1500,1200,s)
        self.assertEqual(spy.call_count,2);self.assertIs(spy.call_args_list[0].args[1],s);self.assertIs(spy.call_args_list[1].args[1],s);self.assertEqual(s.static_head_m,10);self.assertEqual(s.k_si,25920)
    def test_signed_shifts_and_percentages(self):
        for speed in [1200,1800]:
            r=evaluate(speed);b,n=r.base.points[0],r.new.points[0]
            self.assertEqual(r.flow_change.difference,n.flow_m3_s-b.flow_m3_s);self.assertEqual(r.head_change.difference,n.head_m-b.head_m)
            self.assertAlmostEqual(r.flow_change.percent,(n.flow_m3_s-b.flow_m3_s)/b.flow_m3_s*100,12);self.assertAlmostEqual(r.head_change.percent,(n.head_m-b.head_m)/b.head_m*100,12)
    def test_zero_static_explicit_solver(self):
        with patch.object(core,'find_operating_points',wraps=core.find_operating_points) as spy:r=evaluate(static=0)
        self.assertEqual(spy.call_count,2);self.assertAlmostEqual(r.new.points[0].flow_m3_s,r.base.points[0].flow_m3_s*.8,13)
    def test_no_intersection_no_endpoint(self):
        r=evaluate(static=40);self.assertTrue(r.base.points);self.assertFalse(r.new.points);self.assertIsNone(r.flow_change)
    def test_multiple_intersections_preserved(self):
        c=curve([(0,0),(1,2),(2,0),(3,2),(4,0)],'m³/s');r=core.evaluate_variable_speed_operating_point(c,1500,1500,SystemModel(1,0))
        self.assertEqual([p.flow_m3_s for p in r.new.points],[.5,1.5,2.5,3.5]);self.assertEqual(len(r.base.points),4);self.assertIsNone(r.flow_change)
    def test_tangency(self):
        c=curve([(0,0),(2,4),(3,0)],'m³/s');r=core.evaluate_variable_speed_operating_point(c,1,1,SystemModel(1,1));self.assertEqual(len(r.new.points),1);self.assertEqual(r.new.points[0].flow_m3_s,1);self.assertEqual(r.new.points[0].head_m,2)
    def test_coincident_intervals(self):
        r=core.evaluate_variable_speed_operating_point(curve([(0,10),(1,10),(2,10)],'m³/s'),1,1,SystemModel(10,0));self.assertTrue(r.new.coincident_intervals);self.assertIsNone(r.head_change)
    def test_invalid_speed_each_position(self):
        for bad in [0,-1,None,True,math.nan,math.inf,-math.inf]:
            for pair in [(bad,1200),(1500,bad)]:
                with self.assertRaises(ValueError):core.scale_head_curve_by_speed(curve(),*pair)
    def test_no_arbitrary_speed_bounds_and_numeric_overflow(self):
        for n in [1e-12,1e12]:self.assertEqual(core.scale_head_curve_by_speed(curve(),n,n).ratio,1)
        with self.assertRaises(ValueError):core.scale_head_curve_by_speed(curve(),1e-300,1e300)
    def test_phase3e_validation_sort_and_duplicates(self):
        c=curve(list(reversed(HEAD)));r=core.scale_head_curve_by_speed(c,1500,1200);self.assertEqual(r.scaled_curve.points[0].flow_m3_s,0)
        with self.assertRaises(ValueError):curve([(0,50),(0,40),(1,30)])
        with self.assertRaises(ValueError):curve(HEAD[:2])
    def test_all_equivalent_flow_head_units(self):
        expected=evaluate()
        for fu,ff in FLOW.items():
            for hu,hf in HEAD_FACTORS.items():
                c=curve([(q/3600/ff,h/hf) for q,h in HEAD],fu,hu)
                s=model_from_reference(static_head=10/hf,head_unit=hu,reference_flow=100/3600/ff,reference_friction_head=20/hf,flow_unit=fu,flow_factors=FLOW)
                r=core.evaluate_variable_speed_operating_point(c,1500,1200,s);self.assertAlmostEqual(r.new.points[0].flow_m3_s,expected.new.points[0].flow_m3_s,13);self.assertAlmostEqual(r.new.points[0].head_m,expected.new.points[0].head_m,10)
    def test_plot_separate_bounded_domains_all_markers(self):
        for n,last in [(1200,160),(1800,240)]:
            r=evaluate(n);s=ui.variable_speed_plot_spec(curve(),r,system(),FLOW['m³/hr'],'m³/hr','m')
            self.assertEqual(len(s['layer']),5);self.assertEqual(s['layer'][0]['data']['values'][-1]['flow'],200);self.assertAlmostEqual(s['layer'][1]['data']['values'][-1]['flow'],last,11)
            self.assertEqual(len(s['layer'][3]['data']['values']),1);self.assertEqual(len(s['layer'][4]['data']['values']),1)
    def test_immutable_and_zero_baseline(self):
        r=evaluate()
        with self.assertRaises(FrozenInstanceError):r.scaling.ratio=2
        r=core.evaluate_variable_speed_operating_point(curve(),1500,1500,SystemModel(50,0));self.assertEqual(r.base.points[0].flow_m3_s,0);self.assertIsNone(r.flow_change.percent)

class VariableSpeedAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,*,n1=1500,n2=1200,static=10,k=25920,direct=False,points=HEAD,fu='m³/hr',hu='m',ref=100,friction=20):
        at=self.app();at.number_input(key='p3s_head_count').set_value(len(points));at.selectbox(key='p3s_method').select(ui.METHODS[0 if direct else 1]).run()
        at.selectbox(key='p3s_flow_unit').select(fu);at.selectbox(key='p3s_head_unit').select(hu)
        for i,(q,h) in enumerate(points):at.number_input(key=f'p3s_head_q_{i}').set_value(q);at.number_input(key=f'p3s_head_v_{i}').set_value(h)
        at.number_input(key='p3s_n1').set_value(n1);at.number_input(key='p3s_n2').set_value(n2);at.number_input(key='p3s_static').set_value(static)
        if direct:at.number_input(key='p3s_k').set_value(k)
        else:at.number_input(key='p3s_reference_flow').set_value(ref);at.number_input(key='p3s_friction').set_value(friction)
        return at
    def calc(self,at):at.button(key='p3s_evaluate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def test_initial_render_blank_units_speeds_and_optionals(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3S — Variable-Speed Pump Operating Point / VSD Analysis' for e in at.expander))
        for w in at.number_input:
            if w.key.startswith('p3s_') and w.key!='p3s_head_count':self.assertIsNone(w.value)
        for key in ['flow_unit','head_unit','bep_unit','power_unit']:self.assertIsNone(at.selectbox(key='p3s_'+key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3s_')])
    def test_reference_method_reduction_summary_and_points(self):
        at=self.calc(self.fill());self.assertFalse(at.error);text=self.text(at)
        for v in ['Reference Speed: 1500 rpm','New Speed: 1200 rpm','Speed Ratio: 0.8','Speed Change: -20%','Unchanged Static Head: 10 m','Unchanged K: 25920 s²/m⁵','Operating Flow: 124.596248337 m³/hr','Operating Flow: 92.1722858517 m³/hr','Operating Head: 26.9914605582 m']:self.assertIn(v,text)
        table='\n'.join(w.value for w in at.markdown)
        for v in ['| 0 | 32 |','| 40 | 30.72 |','| 80 | 28.16 |','| 120 | 24.32 |','| 160 | 19.2 |']:self.assertIn(v,table)
    def test_increase_summary_and_scaled_points(self):
        at=self.calc(self.fill(n2=1800));self.assertIn('Speed Ratio: 1.2',self.text(at));self.assertIn('Operating Flow: 155.353076798 m³/hr',self.text(at));self.assertIn('Operating Head: 58.2691569411 m',self.text(at))
        table='\n'.join(w.value for w in at.markdown)
        for v in ['| 0 | 72 |','| 120 | 63.36 |','| 240 | 43.2 |']:self.assertIn(v,table)
    def test_direct_k(self):
        at=self.calc(self.fill(direct=True));self.assertIn('Operating Flow: 92.1722858517 m³/hr',self.text(at));self.assertFalse(at.error)
    def test_all_signed_shifts_percentages(self):
        for n in [1200,1800]:
            at=self.calc(self.fill(n2=n));r=evaluate(n)
            for v in [f'Flow Shift: {r.flow_change.difference*3600:+.12g} m³/hr',f'Flow Change: {r.flow_change.percent:+.12g}%',f'Head Shift: {r.head_change.difference:+.12g} m',f'Head Change: {r.head_change.percent:+.12g}%']:self.assertIn(v,self.text(at))
    def test_not_direct_scaled_old_point_and_solver_reuse(self):
        with patch.object(core,'find_operating_points',wraps=core.find_operating_points) as spy:at=self.calc(self.fill())
        self.assertEqual(spy.call_count,2);self.assertNotIn('99.6769986699',self.text(at));self.assertNotIn('26.2710081277',self.text(at));self.assertEqual(spy.call_args_list[0].args[1].static_head_m,10);self.assertIs(spy.call_args_list[0].args[1],spy.call_args_list[1].args[1])
    def test_zero_speed_rejected(self):
        for key in ['p3s_n1','p3s_n2']:
            at=self.fill();at.number_input(key=key).set_value(0);self.calc(at);self.assertTrue(at.error);self.assertNotIn('New Intersection 1',self.text(at))
    def test_negative_speed_rejected(self):
        at=self.fill(n2=-1);self.calc(at);self.assertTrue(at.error)
    def test_no_intersection(self):
        at=self.calc(self.fill(static=40));self.assertTrue(any(core.NO_SCALED_POINT==w.value for w in at.info));self.assertIn('Base Intersection 1',self.text(at));self.assertNotIn('New Intersection 1',self.text(at));self.assertNotIn('Flow Shift:',self.text(at))
    def test_multiple_all_preserved(self):
        at=self.calc(self.fill(n2=1500,direct=True,points=[(0,0),(1,2),(2,0),(3,2),(4,0)],fu='m³/s',static=1,k=0));self.assertEqual(sum('Multiple intersections' in w.value for w in at.warning),2)
        for name in ['Base','New']:
            for i,q in enumerate([.5,1.5,2.5,3.5],1):self.assertIn(f'{name} Intersection {i}\nOperating Flow: {q} m³/s',self.text(at))
        self.assertNotIn('Flow Shift:',self.text(at))
    def test_tangent(self):
        at=self.calc(self.fill(n2=1500,direct=True,points=[(0,0),(2,4),(3,0)],fu='m³/s',static=1,k=1));self.assertIn('New Intersection 1\nOperating Flow: 1 m³/s\nOperating Head: 2 m',self.text(at));self.assertIn('Flow Shift: +0 m³/s',self.text(at))
    def test_coincident(self):
        at=self.calc(self.fill(n2=1500,direct=True,points=[(0,10),(1,10),(2,10)],fu='m³/s',static=10,k=0));self.assertIn('New Coincident Flow Interval: 0 to 2 m³/s',self.text(at));self.assertNotIn('Flow Shift:',self.text(at))
    def test_mixed_units(self):
        ff=FLOW['Gallon/min (US GPM)'];hf=HEAD_FACTORS['ft'];at=self.calc(self.fill(points=[(q/3600/ff,h/hf) for q,h in HEAD],fu='Gallon/min (US GPM)',hu='ft',static=10/hf,ref=100/3600/ff,friction=20/hf))
        r=evaluate();self.assertIn(f'Operating Flow: {r.new.points[0].flow_m3_s/ff:.12g} Gallon/min (US GPM)',self.text(at));self.assertIn(f'Operating Head: {r.new.points[0].head_m/hf:.12g} ft',self.text(at));self.assertFalse(at.error)
    def test_optional_bep_shared_affinity_and_comparison(self):
        at=self.fill();at.number_input(key='p3s_bep').set_value(150/3600);at.selectbox(key='p3s_bep_unit').select('m³/s')
        with patch.object(ui,'calculate_speed_affinity',wraps=ui.calculate_speed_affinity) as a,patch.object(ui,'compare_bep',wraps=ui.compare_bep) as b:self.calc(at)
        self.assertEqual(a.call_count,1);self.assertGreaterEqual(b.call_count,2);self.assertIn('Affinity-Law Scaled BEP Flow: 120 m³/hr',self.text(at));self.assertIn(f'{evaluate().new.points[0].flow_m3_s/(120/3600)*100:.12g}%',self.text(at));self.assertFalse(at.error)
    def test_optional_power_cubic_and_unit_equivalence(self):
        from pump_performance.shaft_power import POWER_FACTORS
        for unit,factor in POWER_FACTORS.items():
            at=self.fill();at.number_input(key='p3s_power').set_value(12000/factor);at.selectbox(key='p3s_power_unit').select(unit)
            with patch.object(ui,'calculate_speed_affinity',wraps=ui.calculate_speed_affinity) as spy:self.calc(at)
            self.assertEqual(spy.call_count,1);self.assertIn(f'Affinity-Law Scaled Power: {6144/factor:.12g} {unit}',self.text(at));self.assertFalse(at.error)
    def enable_npshr(self,at,points=None):
        pts=points or [(0,2),(100,4),(200,6)];at.selectbox(key='p3s_npsh_mode').select('Separate Vendor NPSHR Curve for the New Speed').run()
        at.selectbox(key='p3s_npshr_flow_unit').select('m³/hr');at.selectbox(key='p3s_npshr_head_unit').select('m')
        for i,(q,h) in enumerate(pts):at.number_input(key=f'p3s_npshr_q_{i}').set_value(q);at.number_input(key=f'p3s_npshr_v_{i}').set_value(h)
        return at
    def test_new_speed_vendor_npshr_and_margin_shared(self):
        at=self.enable_npshr(self.fill());at.number_input(key='p3s_npsha').set_value(12);at.selectbox(key='p3s_npsha_unit').select('m')
        with patch.object(ui,'interpolate_npshr',wraps=ui.interpolate_npshr) as r,patch.object(ui,'calculate_npsh_margin',wraps=ui.calculate_npsh_margin) as m:self.calc(at)
        self.assertEqual(r.call_count,1);self.assertEqual(m.call_count,1);expected=2+evaluate().new.points[0].flow_m3_s*3600*.02
        self.assertIn(f'Vendor NPSHR at N2: {expected:.12g} m',self.text(at));self.assertIn(f'New-Speed NPSH Margin: {12-expected:+.12g} m',self.text(at));self.assertFalse(at.error)
    def test_new_vendor_npshr_without_npsha(self):
        at=self.calc(self.enable_npshr(self.fill()));self.assertIn('Vendor NPSHR at N2:',self.text(at));self.assertNotIn('New-Speed NPSH Margin:',self.text(at));self.assertFalse(at.error)
    def test_npshr_no_auto_scaling(self):
        at=self.calc(self.fill());self.assertNotIn('Vendor NPSHR at N2:',self.text(at));self.assertNotIn('New-Speed NPSH Margin:',self.text(at));self.assertTrue(any(ui.GUIDANCE[3]==w.value for w in at.caption))
    def test_npshr_outside_range_local(self):
        at=self.calc(self.enable_npshr(self.fill(),[(100,2),(150,3),(200,4)]));self.assertTrue(any('not extrapolated' in w.value for w in at.info));self.assertIn('New Intersection 1',self.text(at));self.assertTrue(at.get('vega_lite_chart'))
    def test_bad_optional_keeps_results(self):
        at=self.fill();at.number_input(key='p3s_bep').set_value(0);at.selectbox(key='p3s_bep_unit').select('m³/hr');self.calc(at);self.assertTrue(at.error);self.assertIn('New Intersection 1',self.text(at));self.assertTrue(at.get('vega_lite_chart'))
    def test_guidance_no_efficiency_guarantee_no_approval(self):
        at=self.calc(self.fill());captions='\n'.join(w.value for w in at.caption)
        for text in ui.GUIDANCE:self.assertIn(text,captions)
        self.assertNotIn('improvement',self.text(at));self.assertNotIn('deterioration',self.text(at));self.assertNotIn('APPROVED',self.text(at));self.assertFalse([w for w in at.checkbox if w.key.startswith('p3s_')])
    def test_plot_bounded_curves_and_markers(self):
        at=self.calc(self.fill());p=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(len(p['layer']),5);self.assertEqual(p['layer'][0]['data']['values'][-1]['flow'],200);self.assertEqual(p['layer'][1]['data']['values'][-1]['flow'],160);self.assertEqual(len(p['layer'][3]['data']['values']),1);self.assertEqual(len(p['layer'][4]['data']['values']),1)
    def test_stale_results_clear_after_input_change(self):
        at=self.calc(self.fill());at.number_input(key='p3s_n2').set_value(1800).run();self.assertNotIn('New Intersection 1',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
    def test_previous_engineering_files_unchanged(self):
        expected={'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
