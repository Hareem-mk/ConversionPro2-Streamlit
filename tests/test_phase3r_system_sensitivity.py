"""Shared system/solver orchestration, signed shifts and retained root sets."""
import hashlib,json,math
from pathlib import Path
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch
from app import FLOW,DENSITY
from pump_performance import system_sensitivity as core,system_sensitivity_ui as ui
from pump_performance.pump_curve import create_pump_curve,HEAD_FACTORS
from pump_performance.system_curve import model_from_reference,model_from_k,SystemModel
from pump_performance.power_curve import create_power_curve
from pump_performance.npshr_curve import create_npshr_curve

HEAD=[(0,50),(50,48),(100,44),(150,38),(200,30)]
POWER=[(50,6),(100,8.5),(150,11.5),(200,14),(250,16)]
NPSHR=[(50,2.5),(100,3.2),(150,4.4),(200,6),(250,8)]
ROOT=Path(__file__).resolve().parents[1]

def curve(points=HEAD,unit='m³/hr',hu='m'):return create_pump_curve(points,unit,hu,FLOW)
def system(static=10,friction=20):return model_from_reference(static_head=static,head_unit='m',reference_flow=100,reference_friction_head=friction,flow_unit='m³/hr',flow_factors=FLOW)
def evaluate(static=10,friction=30):return core.evaluate_system_sensitivity(curve(),system(),system(static,friction))

class SensitivityCoreTests(unittest.TestCase):
    def test_base_benchmark(self):
        r=evaluate();p=r.base.points[0];self.assertEqual(r.base_k_si,25920);self.assertEqual(r.modified_k_si,38880)
        self.assertAlmostEqual(p.flow_m3_s*3600,124.59624833740307,10);self.assertAlmostEqual(p.head_m,41.04845019951163,11)
    def test_higher_lower_resistance(self):
        for friction,direction in [(30,-1),(10,1)]:
            r=evaluate(friction=friction);self.assertEqual(math.copysign(1,r.flow_change.difference),direction);self.assertEqual(math.copysign(1,r.head_change.difference),-direction)
    def test_higher_lower_static(self):
        for static,direction in [(20,-1),(5,1)]:
            r=evaluate(static,20);self.assertEqual(math.copysign(1,r.flow_change.difference),direction)
    def test_signed_absolute_and_percent_changes(self):
        r=evaluate();a,b=r.base.points[0],r.modified.points[0]
        self.assertEqual(r.flow_change.difference,b.flow_m3_s-a.flow_m3_s);self.assertAlmostEqual(r.flow_change.percent,(b.flow_m3_s-a.flow_m3_s)/a.flow_m3_s*100,12)
        self.assertEqual(r.head_change.difference,b.head_m-a.head_m);self.assertAlmostEqual(r.head_change.percent,(b.head_m-a.head_m)/a.head_m*100,12)
    def test_percent_resistance_and_no_mutation(self):
        base=system()
        for percent,k in [(25,32400),(-20,20736),(-100,0),(0,25920)]:
            r=core.modified_resistance_model(base,10,percent);self.assertEqual(r.k_si,k);self.assertEqual(base.k_si,25920)
        for bad in [None,True,math.nan,math.inf,-math.inf,-101]:
            with self.assertRaises(ValueError):core.modified_resistance_model(base,10,bad)
    def test_shared_root_solver_twice(self):
        with patch.object(core,'find_operating_points',wraps=core.find_operating_points) as spy:r=evaluate()
        self.assertEqual(spy.call_count,2);self.assertIs(spy.call_args_list[0].args[0],spy.call_args_list[1].args[0]);self.assertEqual(len(r.base.points),1)
    def test_no_intersection_preserves_other_case(self):
        r=evaluate(static=100,friction=20);self.assertEqual(len(r.base.points),1);self.assertFalse(r.modified.points);self.assertIsNone(r.flow_change);self.assertIsNone(r.head_change)
    def test_multiple_roots_preserved_no_pairing(self):
        c=curve([(0,0),(1,2),(2,0),(3,2),(4,0)],'m³/s');r=core.evaluate_system_sensitivity(c,SystemModel(1,0),SystemModel(1,0))
        self.assertEqual([p.flow_m3_s for p in r.base.points],[.5,1.5,2.5,3.5]);self.assertEqual(len(r.modified.points),4);self.assertIsNone(r.flow_change)
    def test_tangent_shared_behavior(self):
        c=curve([(0,0),(2,4),(3,0)],'m³/s');r=core.evaluate_system_sensitivity(c,SystemModel(1,1),SystemModel(1,1))
        self.assertEqual(len(r.base.points),1);self.assertEqual(r.base.points[0].flow_m3_s,1);self.assertEqual(r.flow_change.difference,0)
    def test_coincident_intervals_preserved(self):
        r=core.evaluate_system_sensitivity(curve([(0,10),(1,10),(2,10)],'m³/s'),SystemModel(10,0),SystemModel(10,0))
        self.assertEqual(len(r.base.coincident_intervals),1);self.assertEqual(len(r.modified.coincident_intervals),1);self.assertIsNone(r.flow_change)
    def test_zero_baseline_denominators(self):
        self.assertIsNone(core.numeric_change(0,1).percent)
        r=core.evaluate_system_sensitivity(curve(),SystemModel(50,0),system())
        self.assertEqual(r.base.points[0].flow_m3_s,0);self.assertIsNone(r.flow_change.percent)
    def test_invalid_differences(self):
        for bad in [None,True,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):core.numeric_change(bad,1)
        with self.assertRaises(ValueError):core.numeric_change(1e-308,1e308)
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):evaluate().flow_change=None
    def test_all_flow_and_head_units(self):
        expected=evaluate()
        for u,ff in FLOW.items():
            for hu,hf in HEAD_FACTORS.items():
                c=curve([(q/3600/ff,h/hf) for q,h in HEAD],u,hu)
                def model(f):return model_from_reference(static_head=10/hf,head_unit=hu,reference_flow=100/3600/ff,reference_friction_head=f/hf,flow_unit=u,flow_factors=FLOW)
                r=core.evaluate_system_sensitivity(c,model(20),model(30));self.assertAlmostEqual(r.modified.points[0].flow_m3_s,expected.modified.points[0].flow_m3_s,13);self.assertAlmostEqual(r.modified.points[0].head_m,expected.modified.points[0].head_m,10)
    def context(self,p=None,**kw):
        args=dict(density=1000,density_unit='kg/m³',density_factors=DENSITY,bep_flow_si=150/3600,
                  vendor_power_curve=create_power_curve(POWER,'m³/hr','kW',FLOW),npshr_curve=create_npshr_curve(NPSHR,'m³/hr','m',FLOW),npsha_m=12.026359664105)
        args.update(kw);return core.evaluate_point_context(p or evaluate().base.points[0],FLOW,**args)
    def test_optional_shared_kernels(self):
        from contextlib import ExitStack
        with ExitStack() as stack:
            spies=[stack.enter_context(patch.object(core,n,wraps=getattr(core,n))) for n in ['hydraulic_power','interpolate_power','compare_bep','interpolate_npshr','calculate_npsh_margin']];r=self.context()
        for s in spies:self.assertEqual(s.call_count,1)
        self.assertFalse(r.errors);self.assertAlmostEqual(r.percent_bep,83.06416555826873,10);self.assertAlmostEqual(r.npsh_margin_m,8.236049704007325,10)
    def test_optional_range_errors_are_local(self):
        from pump_performance.operating_point import OperatingPoint
        r=self.context(OperatingPoint(25/3600,49,49,49,0));self.assertEqual(len(r.errors),2);self.assertIsNone(r.vendor_shaft_w);self.assertIsNone(r.npshr_m);self.assertIsNotNone(r.hydraulic_w);self.assertIsNotNone(r.percent_bep)
    def test_plot_bounded_pump_and_all_markers(self):
        r=evaluate();p=ui.sensitivity_plot_spec(curve(),system(),system(friction=30),r,FLOW['m³/hr'],'m³/hr','m')
        self.assertEqual(len(p['layer']),5);self.assertEqual(len(p['layer'][0]['data']['values']),5)
        self.assertEqual(p['encoding']['color']['legend']['columns'],2)
        self.assertEqual(p['layer'][0]['data']['values'][-1]['flow'],200)
        self.assertEqual(sum(len(l['data']['values']) for l in p['layer'] if l['mark']['type']=='point'),2)

class SensitivityAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,*,direct=False,friction=30,static=10,points=HEAD,unit='m³/hr',hu='m',base_static=10,base_k=25920,modified_k=38880,reference=100,base_friction=20):
        at=at or self.app();at.selectbox(key='p3r_method').select(ui.METHODS_3R[0 if direct else 1]).run();at.number_input(key='p3r_count').set_value(len(points)).run()
        at.selectbox(key='p3r_flow_unit').select(unit);at.selectbox(key='p3r_head_unit').select(hu)
        for i,(q,h) in enumerate(points):at.number_input(key=f'p3r_q_{i}').set_value(q);at.number_input(key=f'p3r_h_{i}').set_value(h)
        at.number_input(key='p3r_base_static').set_value(base_static);at.number_input(key='p3r_modified_static').set_value(static)
        if direct:at.number_input(key='p3r_base_k').set_value(base_k);at.number_input(key='p3r_modified_k').set_value(modified_k)
        else:
            for key,value in [('base_ref',reference),('modified_ref',reference),('base_friction',base_friction),('modified_friction',friction)]:at.number_input(key='p3r_'+key).set_value(value)
        return at
    def calc(self,at):
        at.button(key='p3r_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def test_initial_render_explicit_units_blank_inputs(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3R — System Curve Sensitivity / Operating Point Shift Analysis' for e in at.expander))
        for w in at.number_input:
            if w.key.startswith('p3r_') and w.key!='p3r_count':self.assertIsNone(w.value)
        for key in ['flow_unit','head_unit','density_unit','bep_unit']:self.assertIsNone(at.selectbox(key='p3r_'+key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3r_')]);self.assertTrue(any(ui.GUIDANCE in w.value for w in at.caption))
    def test_reference_higher_resistance_and_all_shifts(self):
        at=self.calc(self.fill());self.assertFalse(at.error);text=self.text(at);r=evaluate()
        for expected in ['Base K: 25920 s²/m⁵','Modified K: 38880 s²/m⁵','Operating Flow: 124.596248337 m³/hr','Operating Head: 41.0484501995 m',f'Flow Shift: {r.flow_change.difference*3600:+.12g} m³/hr',f'Head Shift: {r.head_change.difference:+.12g} m',f'Percent Flow Change: {r.flow_change.percent:.12g}%',f'Percent Head Change: {r.head_change.percent:.12g}%']:self.assertIn(expected,text)
        self.assertTrue(any(w.value=='Operating flow decreased.' for w in at.markdown));self.assertTrue(any(w.value=='Operating head increased.' for w in at.markdown))
    def test_direct_k_equivalence(self):
        at=self.calc(self.fill(direct=True));self.assertIn(f'Operating Flow: {evaluate().modified.points[0].flow_m3_s*3600:.12g} m³/hr',self.text(at));self.assertFalse(at.error)
    def test_lower_resistance(self):
        at=self.calc(self.fill(friction=10));self.assertIn('Modified K: 12960 s²/m⁵',self.text(at));self.assertTrue(any(w.value=='Operating flow increased.' for w in at.markdown))
    def test_higher_static(self):
        at=self.calc(self.fill(static=20,friction=20));self.assertTrue(any(w.value=='Static head increased.' for w in at.markdown));self.assertTrue(any(w.value=='Operating flow decreased.' for w in at.markdown))
    def test_lower_static(self):
        at=self.calc(self.fill(static=5,friction=20));self.assertTrue(any(w.value=='Static head decreased.' for w in at.markdown));self.assertTrue(any(w.value=='Operating flow increased.' for w in at.markdown))
    def test_percent_resistance_active_no_hidden_override(self):
        at=self.fill(direct=True,modified_k=123);at.selectbox(key='p3r_modified_method').select(ui.MODIFIED_METHODS[1]).run()
        self.assertNotIn('p3r_modified_k',[w.key for w in at.number_input]);self.assertIsNone(at.number_input(key='p3r_percent').value)
        for change,k in [(25,32400),(-20,20736)]:
            at.number_input(key='p3r_percent').set_value(change);self.calc(at);self.assertIn(f'Modified K: {k} s²/m⁵',self.text(at))
        at.number_input(key='p3r_percent').set_value(-101);self.calc(at);self.assertTrue(at.error)
    def test_no_intersection_no_endpoint_substitution(self):
        at=self.calc(self.fill(static=100,friction=20));self.assertTrue(any(ui.NO_VALID_POINT in i.value for i in at.info));self.assertIn('Base Intersection 1',self.text(at));self.assertNotIn('Modified Intersection 1',self.text(at));self.assertNotIn('Flow Shift:',self.text(at))
        p=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(sum(len(l['data']['values']) for l in p['layer'] if l['mark']['type']=='point'),1)
    def test_multiple_real_intersections_all_preserved(self):
        pts=[(0,0),(1,2),(2,0),(3,2),(4,0)];at=self.calc(self.fill(direct=True,points=pts,unit='m³/s',base_static=1,static=1,base_k=0,modified_k=0))
        text=self.text(at)
        for name in ['Base','Modified']:
            for i,q in enumerate([.5,1.5,2.5,3.5],1):self.assertIn(f'{name} Intersection {i}\nOperating Flow: {q} m³/s',text)
        self.assertNotIn('Flow Shift:',text);self.assertTrue(any('Multiple intersections exist.' in w.value for w in at.warning))
        p=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(sum(len(l['data']['values']) for l in p['layer'] if l['mark']['type']=='point'),8)
    def test_real_tangency(self):
        at=self.calc(self.fill(direct=True,points=[(0,0),(2,4),(3,0)],unit='m³/s',base_static=1,static=1,base_k=1,modified_k=1));self.assertIn('Operating Flow: 1 m³/s',self.text(at));self.assertIn('Operating Head: 2 m',self.text(at));self.assertIn('Flow Shift: +0 m³/s',self.text(at));self.assertFalse(at.error)
    def test_coincident_interval_display(self):
        at=self.calc(self.fill(direct=True,points=[(0,10),(1,10),(2,10)],unit='m³/s',base_static=10,static=10,base_k=0,modified_k=0));self.assertIn('Base Coincident Flow Interval: 0 to 2 m³/s',self.text(at));self.assertIn('Modified Coincident Flow Interval: 0 to 2 m³/s',self.text(at));self.assertNotIn('Flow Shift:',self.text(at))
    def test_mixed_units_reference(self):
        f=FLOW['Gallon/min (US GPM)'];h=HEAD_FACTORS['ft'];at=self.calc(self.fill(points=[(q/3600/f,v/h) for q,v in HEAD],unit='Gallon/min (US GPM)',hu='ft',base_static=10/h,static=10/h,reference=100/3600/f,base_friction=20/h,friction=30/h))
        self.assertIn(f'Operating Flow: {evaluate().base.points[0].flow_m3_s/f:.12g} Gallon/min (US GPM)',self.text(at));self.assertIn(f'Operating Head: {evaluate().modified.points[0].head_m/h:.12g} ft',self.text(at));self.assertFalse(at.error)
    def test_zero_base_flow_percent_na(self):
        at=self.calc(self.fill(direct=True,base_static=50,base_k=0,static=10,modified_k=25920));self.assertIn('Percent Flow Change: N/A — base flow is zero',self.text(at))
    def test_optional_hydraulic_and_bep_reused(self):
        at=self.fill();at.number_input(key='p3r_density').set_value(1000);at.selectbox(key='p3r_density_unit').select('kg/m³');at.number_input(key='p3r_bep').set_value(150/3600);at.selectbox(key='p3r_bep_unit').select('m³/s')
        with patch.object(core,'hydraulic_power',wraps=core.hydraulic_power) as power,patch.object(core,'compare_bep',wraps=core.compare_bep) as bep:self.calc(at)
        self.assertEqual(power.call_count,2);self.assertEqual(bep.call_count,2);self.assertIn('Percent of BEP: 83.0641655583 %',self.text(at));self.assertIn('Hydraulic Power Change:',self.text(at));self.assertIn('BEP Change:',self.text(at))
    def enable_curve(self,at,key,label,points,value_unit):
        if key=='power':at.selectbox(key='p3r_power_mode').select('Use Vendor Shaft/Brake Power Curve').run()
        else:at.selectbox(key='p3r_npsh_mode').select('Use Vendor NPSHR Curve and Entered NPSHA').run()
        at.number_input(key=f'p3r_{key}_count').set_value(len(points)).run();at.selectbox(key=f'p3r_{key}_flow_unit').select('m³/hr');at.selectbox(key=f'p3r_{key}_value_unit').select(value_unit)
        for i,(q,v) in enumerate(points):at.number_input(key=f'p3r_{key}_q_{i}').set_value(q);at.number_input(key=f'p3r_{key}_v_{i}').set_value(v)
        return at
    def test_optional_vendor_power(self):
        at=self.enable_curve(self.fill(),'power','Sensitivity Vendor Shaft Power',POWER,'kW')
        with patch.object(core,'interpolate_power',wraps=core.interpolate_power) as spy:self.calc(at)
        self.assertEqual(spy.call_count,2);self.assertIn('Vendor Interpolated Shaft Power: 9.97577490024 kW',self.text(at));self.assertIn('Vendor Shaft Power Change:',self.text(at))
    def test_optional_npsh_reuses3o3j_constant_npsha(self):
        at=self.enable_curve(self.fill(),'npshr','Sensitivity Vendor NPSHR',NPSHR,'m');at.number_input(key='p3r_npsha').set_value(12.026359664105);at.selectbox(key='p3r_npsha_unit').select('m')
        with patch.object(core,'interpolate_npshr',wraps=core.interpolate_npshr) as r,patch.object(core,'calculate_npsh_margin',wraps=core.calculate_npsh_margin) as m:self.calc(at)
        self.assertEqual(r.call_count,2);self.assertEqual(m.call_count,2);self.assertEqual(m.call_args_list[0].args[0],m.call_args_list[1].args[0]);self.assertIn('NPSH Margin: 8.23604970401 m',self.text(at));self.assertIn('NPSH Margin Change:',self.text(at))
    def test_optional_outside_curve_preserves_operating_points(self):
        at=self.enable_curve(self.fill(friction=1000),'npshr','Sensitivity Vendor NPSHR',NPSHR,'m');at.number_input(key='p3r_npsha').set_value(12.026359664105);at.selectbox(key='p3r_npsha_unit').select('m');self.calc(at)
        self.assertIn('Modified Intersection 1',self.text(at));self.assertTrue(any('NPSHR is not extrapolated' in i.value for i in at.info));self.assertIn('Base Intersection 1 Context',self.text(at));self.assertFalse(at.error)
    def test_optional_bad_setup_keeps_primary_results(self):
        at=self.fill();at.number_input(key='p3r_bep').set_value(150);self.calc(at);self.assertTrue(at.error);self.assertIn('Modified Intersection 1',self.text(at));self.assertTrue(at.get('vega_lite_chart'))
    def test_plot_and_neutral_wording(self):
        at=self.calc(self.fill());s=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(s['layer'][0]['data']['values'][0]['flow'],0);self.assertEqual(s['layer'][0]['data']['values'][-1]['flow'],200)
        text=self.text(at);self.assertNotIn('improvement',text);self.assertNotIn('deterioration',text);self.assertNotIn('PASS',text);self.assertNotIn('APPROVED',text)
    def test_invalid_inputs_and_stale_results(self):
        at=self.calc(self.fill());at.number_input(key='p3r_modified_friction').set_value(10).run();self.assertNotIn('Flow Shift:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
        at.number_input(key='p3r_modified_friction').set_value(-1);self.calc(at);self.assertTrue(at.error)
    def test_previous_modules_unchanged(self):
        expected={'pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
