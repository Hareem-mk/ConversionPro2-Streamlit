"""Vendor interpolation, SI integration and real Streamlit UI regressions."""
import json
import math
from pathlib import Path
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from app import FLOW
from pump_performance.efficiency_curve import (create_efficiency_curve,interpolate_efficiency,find_peak_supplied_efficiency,OUT_OF_RANGE)
from pump_performance import efficiency_curve_ui as ui
from pump_performance.pump_curve import create_pump_curve
from pump_performance.system_curve import model_from_reference
from pump_performance.operating_point import find_operating_points

POINTS=[(50,65),(100,78),(150,84),(200,80),(250,70)]
PUMP=[(0,50),(50,48),(100,44),(150,38),(200,30)]
ROOT=Path(__file__).resolve().parents[1]

def curve(points=POINTS,unit='m³/hr'):
    return create_efficiency_curve(points,unit,FLOW)

class EfficiencyCoreTests(unittest.TestCase):
    def test_benchmarks_and_endpoints(self):
        c=curve()
        for q,e in [(125,81),(175,82),(150,84),(50,65),(250,70)]:
            with self.subTest(q=q):self.assertAlmostEqual(interpolate_efficiency(c,q/3600).efficiency_percent,e,12)
    def test_exact_point_returns_stored_value(self):
        c=curve()
        for p in c.points:
            r=interpolate_efficiency(c,p.flow_m3_s)
            self.assertTrue(r.exact_point);self.assertEqual(r.efficiency_percent,p.efficiency_percent)
    def test_bounds_roundoff_only(self):
        c=curve()
        for p,direction in [(c.points[0],-math.inf),(c.points[-1],math.inf)]:
            q=math.nextafter(p.flow_m3_s,direction)
            self.assertEqual(interpolate_efficiency(c,q).efficiency_percent,p.efficiency_percent)
            with self.assertRaisesRegex(ValueError,'not extrapolated'):interpolate_efficiency(c,p.flow_m3_s+(-1 if direction<0 else 1)*1e-10)
    def test_outside_range(self):
        for q in [25,275]:
            with self.assertRaisesRegex(ValueError,'not extrapolated'):interpolate_efficiency(curve(),q/3600)
    def test_sort_and_nonmonotonic(self):
        self.assertEqual(curve(list(reversed(POINTS))),curve())
    def test_peak(self):
        p=find_peak_supplied_efficiency(curve());self.assertEqual(p.efficiency_percent,84);self.assertEqual(p.flows_m3_s,(150/3600,))
    def test_tied_peaks(self):
        p=find_peak_supplied_efficiency(curve([(50,65),(125,84),(150,84),(250,70)]))
        self.assertEqual(p.flows_m3_s,(125/3600,150/3600))
    def test_duplicate_flows(self):
        with self.assertRaisesRegex(ValueError,'unique'):curve([(50,60),(50,70),(100,80)])
    def test_minimum_points_and_malformed(self):
        for pts in [POINTS[:2],[(1,50),(2,60),(3,)],[(1,50),None,(3,70)]]:
            with self.assertRaises(ValueError):curve(pts)
    def test_invalid_flow(self):
        for bad in [None,True,-1,math.nan,math.inf,-math.inf,'bad']:
            with self.subTest(bad=bad),self.assertRaises(ValueError):curve([(bad,65),(100,78),(150,84)])
    def test_invalid_efficiency(self):
        for bad in [None,True,0,-1,101,math.nan,math.inf,-math.inf,'bad',5e-324]:
            with self.subTest(bad=bad),self.assertRaises(ValueError):curve([(50,bad),(100,78),(150,84)])
    def test_invalid_operating_flow(self):
        for bad in [None,True,-1,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):interpolate_efficiency(curve(),bad)
    def test_zero_flow_and_100_percent(self):
        self.assertEqual(interpolate_efficiency(curve([(0,50),(1,100),(2,80)],'m³/s'),0).efficiency_percent,50)
    def test_all_supported_units(self):
        for unit,factor in FLOW.items():
            c=curve([(q/3600/factor,e) for q,e in POINTS],unit)
            self.assertAlmostEqual(interpolate_efficiency(c,125/3600).efficiency_percent,81,11)
    def test_unsupported_units_and_overflow(self):
        with self.assertRaises(ValueError):curve(unit=None)
        with self.assertRaises(ValueError):create_efficiency_curve(POINTS,'huge',{'huge':1e308})
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):curve().points=()
    def test_shared_3g_benchmark(self):
        p=create_pump_curve(PUMP,'m³/hr','m',FLOW)
        m=model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)
        q=find_operating_points(p,m).points[0].flow_m3_s
        self.assertAlmostEqual(q*3600,124.59624833740307,11)
        self.assertAlmostEqual(interpolate_efficiency(curve(),q).efficiency_percent,80.95154980048837,11)
    def test_plot_domain_and_markers(self):
        c=curve();spec=ui.efficiency_plot_spec(c,FLOW['m³/hr'],'m³/hr',interpolate_efficiency(c,125/3600))
        self.assertEqual(len(spec['layer']),3)
        self.assertEqual([r['flow'] for r in spec['layer'][0]['data']['values']],[50,100,150,200,250])
        self.assertEqual(spec['layer'][1]['data']['values'][0]['efficiency'],84)
        self.assertEqual(spec['layer'][2]['data']['values'][0]['efficiency'],81)

class EfficiencyAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,points=POINTS,q=125,unit='m³/hr',op_unit='m³/hr'):
        at=at or self.app()
        at.number_input(key='p3m_count').set_value(len(points)).run()
        at.selectbox(key='p3m_curve_unit').select(unit)
        at.selectbox(key='p3m_op_unit').select(op_unit)
        for i,(flow,e) in enumerate(points):
            at.number_input(key=f'p3m_q_{i}').set_value(flow)
            at.number_input(key=f'p3m_e_{i}').set_value(e)
        at.number_input(key='p3m_operating').set_value(q)
        return at
    def calculate(self,at):
        at.button(key='p3m_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def integrated(self):
        at=self.app();at.selectbox(key='p3m_method').select(ui.METHODS_3M[1]).run()
        at.number_input(key='p3m_count').set_value(5)
        at.number_input(key='p3m_qh_count').set_value(5).run()
        at.selectbox(key='p3m_curve_unit').select('m³/hr');at.selectbox(key='p3m_op_unit').select('m³/hr');at.selectbox(key='p3m_head_unit').select('m')
        for i,((q,e),(pq,h)) in enumerate(zip(POINTS,PUMP)):
            at.number_input(key=f'p3m_q_{i}').set_value(q);at.number_input(key=f'p3m_e_{i}').set_value(e)
            at.number_input(key=f'p3m_pq_{i}').set_value(pq);at.number_input(key=f'p3m_ph_{i}').set_value(h)
        for key,val in [('static',10),('reference',100),('friction',20)]:at.number_input(key='p3m_'+key).set_value(val)
        return at
    def test_render_defaults_guidance(self):
        at=self.app();self.assertFalse(at.exception)
        self.assertTrue(any(e.label=='3M — Pump Efficiency Curve / Operating Efficiency' for e in at.expander))
        self.assertEqual(at.selectbox(key='p3m_method').options,list(ui.METHODS_3M))
        self.assertIsNone(at.number_input(key='p3m_bep').value)
        self.assertIsNone(at.selectbox(key='p3m_curve_unit').value)
        self.assertTrue(all(w.value is None for w in at.number_input if w.key.startswith('p3m_') and w.key!='p3m_count'))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3m_')])
        self.assertTrue(any(ui.GUIDANCE in w.value for w in at.info))
        self.assertTrue(any('not automatically the official vendor BEP' in w.value for w in at.caption))
    def test_manual_125_benchmark_peak_and_plot(self):
        at=self.calculate(self.fill());text=self.text(at)
        self.assertIn('Interpolated Vendor Efficiency: 81%',text)
        self.assertIn('Peak Supplied Efficiency: 84%',text);self.assertIn('Flow(s): 150 m³/hr',text)
        self.assertIn('Operating Flow Minus Peak Supplied Flow(s): -25 m³/hr',text)
        self.assertNotIn('Percent of BEP:',text)
        spec=json.loads(at.get('vega_lite_chart')[0].proto.spec)
        self.assertEqual(len(spec['layer']),3);self.assertFalse(at.error)
    def test_manual_175(self):self.assertIn('Efficiency: 82%',self.text(self.calculate(self.fill(q=175))))
    def test_exact_150(self):self.assertIn('Efficiency: 84%',self.text(self.calculate(self.fill(q=150))))
    def test_lower_endpoint(self):self.assertIn('Efficiency: 65%',self.text(self.calculate(self.fill(q=50))))
    def test_upper_endpoint(self):self.assertIn('Efficiency: 70%',self.text(self.calculate(self.fill(q=250))))
    def test_below_range(self):
        at=self.calculate(self.fill(q=25));self.assertIn(OUT_OF_RANGE,at.error[0].value);self.assertFalse(at.get('vega_lite_chart'));self.assertNotIn('Interpolated Vendor Efficiency:',self.text(at))
    def test_above_range(self):
        at=self.calculate(self.fill(q=275));self.assertIn(OUT_OF_RANGE,at.error[0].value);self.assertFalse(at.get('vega_lite_chart'))
    def test_duplicate_rejected(self):
        at=self.calculate(self.fill(points=[(50,65),(50,78),(150,84)]));self.assertIn('unique',at.error[0].value)
    def test_zero_efficiency_rejected(self):
        at=self.calculate(self.fill(points=[(50,0),(100,78),(150,84)]));self.assertTrue(at.error)
    def test_above100_rejected(self):
        at=self.calculate(self.fill(points=[(50,101),(100,78),(150,84)]));self.assertTrue(at.error)
    def test_negative_flow_rejected(self):
        at=self.calculate(self.fill(q=-1));self.assertTrue(at.error)
    def test_multiple_peaks(self):
        at=self.calculate(self.fill(points=[(50,65),(125,84),(150,84),(250,70)]))
        self.assertIn('Flow(s): 125, 150 m³/hr',self.text(at))
        spec=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual(len(spec['layer'][1]['data']['values']),2)
    def test_mixed_units(self):
        for unit in ['m³/s','L/s','L/min','Gallon/min (US GPM)']:
            at=self.calculate(self.fill(q=125/3600/FLOW[unit],op_unit=unit));self.assertIn('Efficiency: 81%',self.text(at))
    def test_mixed_bep_uses_shared_si_kernel(self):
        at=self.fill();at.number_input(key='p3m_bep').set_value(150/3600);at.selectbox(key='p3m_bep_unit').select('m³/s')
        with patch.object(ui,'compare_bep',wraps=ui.compare_bep) as spy:self.calculate(at)
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(spy.call_args.args[0],125/3600);self.assertAlmostEqual(spy.call_args.args[1],150/3600)
        self.assertIn('Percent of BEP: 83.3333333333%',self.text(at))
    def test_integrated_3g_reused(self):
        at=self.integrated()
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as spy:self.calculate(at)
        self.assertEqual(spy.call_count,1)
        self.assertIn('Operating Flow: 124.596248337',self.text(at));self.assertIn('Efficiency: 80.9515498005%',self.text(at))
        self.assertIn('Phase 3G Operating Head: 41.0484501995 m',self.text(at));self.assertFalse(at.error)
    def test_integrated_no_root(self):
        at=self.integrated();at.number_input(key='p3m_static').set_value(100);self.calculate(at)
        self.assertTrue(at.error);self.assertNotIn('Interpolated Vendor Efficiency:',self.text(at))
    def test_integrated_multiple_roots_no_silent_selection(self):
        at=self.integrated()
        from types import SimpleNamespace
        with patch.object(ui,'find_operating_points',return_value=SimpleNamespace(coincident_intervals=(),points=(1,2))):self.calculate(at)
        self.assertIn('No operating flow is selected',at.error[0].value)
    def test_integrated_coincident_no_silent_selection(self):
        at=self.integrated()
        from types import SimpleNamespace
        with patch.object(ui,'find_operating_points',return_value=SimpleNamespace(coincident_intervals=(1,),points=())):self.calculate(at)
        self.assertIn('coincide',at.error[0].value)
    def test_power_shared_kernels(self):
        at=self.fill();at.selectbox(key='p3m_power').select('Calculate hydraulic and shaft power').run()
        at.number_input(key='p3m_density').set_value(1000);at.selectbox(key='p3m_density_unit').select('kg/m³')
        at.number_input(key='p3m_power_head').set_value(40);at.selectbox(key='p3m_power_head_unit').select('m')
        with patch.object(ui,'hydraulic_power',wraps=ui.hydraulic_power) as hp,patch.object(ui,'shaft_power',wraps=ui.shaft_power) as sp:self.calculate(at)
        self.assertEqual(hp.call_count,1);self.assertEqual(sp.call_count,1)
        self.assertIn('Hydraulic Power: 13620.3472222 W',self.text(at));self.assertIn('16815.2434842 W',self.text(at))
    def test_previous_production_sources_unchanged(self):
        import hashlib
        hashes={'series_parallel.py':'0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc',
                'series_parallel_ui.py':'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de'}
        for name,digest in hashes.items():
            self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)
        self.assertNotIn('series_parallel',(ROOT/'pump_performance/efficiency_curve_ui.py').read_text())

if __name__=='__main__':unittest.main(verbosity=2)
