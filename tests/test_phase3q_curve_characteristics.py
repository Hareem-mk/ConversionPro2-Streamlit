"""Supplied shutoff, dimensional slopes, neutral diagnostics and shared kernels."""
import hashlib,json,math
from pathlib import Path
from types import SimpleNamespace
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch
from app import FLOW
from pump_performance import curve_characteristics as core,curve_characteristics_ui as ui
from pump_performance.pump_curve import create_pump_curve,HEAD_FACTORS

POINTS=[(0,50),(50,48),(100,44),(150,38),(200,30)]
RISING=[(0,50),(50,48),(100,49),(150,43),(200,35)]
FLAT=[(0,50),(50,48),(100,48),(150,40)]
ROOT=Path(__file__).resolve().parents[1]

def curve(points=POINTS,unit='m³/hr',head_unit='m'):
    return create_pump_curve(points,unit,head_unit,FLOW)

def slope(s):return core.display_slope(s.slope_si,'m³/hr','m',FLOW)

class CharacteristicsCoreTests(unittest.TestCase):
    def test_ranges_shutoff_maximum(self):
        a=core.analyze_curve_characteristics(curve());self.assertEqual(a.minimum_flow_m3_s,0);self.assertEqual(a.maximum_flow_m3_s,200/3600)
        self.assertEqual((a.minimum_head_m,a.maximum_head_m,a.shutoff_head_m),(30,50,50));self.assertEqual(a.maximum_flow_point.head_m,30)
    def test_all_segment_slopes(self):
        for s,expected in zip(core.segment_slopes(curve()),[-.04,-.08,-.12,-.16]):self.assertAlmostEqual(slope(s),expected,13)
    def test_operating_head_and_local_slope_shared3e(self):
        with patch.object(core,'interpolate_pump_head',wraps=core.interpolate_pump_head) as spy:r=core.local_curve_slope(curve(),125/3600)
        self.assertEqual(spy.call_count,1);self.assertEqual(spy.call_args.args[0].flow_factor,1);self.assertEqual(r.operating_head_m,41);self.assertAlmostEqual(slope(r.local_segments[0]),-.12)
    def test_head_rise(self):
        r=core.calculate_shutoff_head_rise(50,41);self.assertEqual(r.rise_m,9);self.assertAlmostEqual(r.percent_of_operating_head,21.951219512195124,12);self.assertEqual(r.percent_of_shutoff_head,18)
    def test_exact_internal_point_both_slopes(self):
        r=core.local_curve_slope(curve(),100/3600);self.assertTrue(r.exact_point);self.assertEqual(r.operating_head_m,44);self.assertEqual(len(r.local_segments),2)
        for s,e in zip(r.local_segments,[-.08,-.12]):self.assertAlmostEqual(slope(s),e,12)
    def test_endpoints_one_adjacent_slope(self):
        for q,h,s in [(0,50,-.04),(200,30,-.16)]:
            r=core.local_curve_slope(curve(),q/3600);self.assertEqual(r.operating_head_m,h);self.assertEqual(len(r.local_segments),1);self.assertAlmostEqual(slope(r.local_segments[0]),s)
    def test_exact_point_roundoff_only(self):
        c=curve();r=core.local_curve_slope(c,math.nextafter(200/3600,math.inf));self.assertEqual(r.operating_head_m,30)
        with self.assertRaises(ValueError):core.local_curve_slope(c,200/3600+1e-10)
    def test_monotonicity(self):
        a=core.analyze_curve_characteristics(curve());self.assertEqual(a.monotonicity_status,'Supplied head curve is monotonically decreasing.');self.assertEqual(a.flat_segment_count,0);self.assertEqual(a.rising_segment_count,0)
    def test_rising_curve_preserved(self):
        c=curve(RISING);a=core.analyze_curve_characteristics(c);self.assertEqual(a.rising_segment_count,1);self.assertEqual(a.segments[1].classification,'Rising');self.assertIn('not monotonically decreasing',a.monotonicity_status)
        self.assertEqual([p.head_m for p in c.points],[50,48,49,43,35])
    def test_flat_segment(self):
        a=core.analyze_curve_characteristics(curve(FLAT));self.assertEqual(a.flat_segment_count,1);self.assertEqual(a.segments[1].slope_si,0);self.assertIn('non-increasing',a.monotonicity_status)
    def test_tiny_head_noise_flat_with_raw_slope_retained(self):
        c=curve([(0,50),(50,48),(100,48+1e-10),(150,40)]);a=core.analyze_curve_characteristics(c)
        self.assertEqual(a.flat_segment_count,1);self.assertEqual(a.rising_segment_count,0);self.assertGreater(a.segments[1].slope_si,0);self.assertEqual(c.points[2].head_m,48+1e-10)
    def test_no_shutoff_and_no_near_zero_inference(self):
        for pts in [POINTS[1:],[(1e-20,50),(50,48),(100,44)]]:
            self.assertIsNone(core.analyze_curve_characteristics(curve(pts)).shutoff_head_m)
    def test_all_flat_zero_denominators(self):
        c=curve([(0,0),(50,0),(100,0)]);a=core.analyze_curve_characteristics(c);self.assertEqual(a.flat_segment_count,2)
        r=core.calculate_shutoff_head_rise(0,0);self.assertIsNone(r.percent_of_operating_head);self.assertIsNone(r.percent_of_shutoff_head)
    def test_signed_head_rise_preserved(self):
        r=core.calculate_shutoff_head_rise(40,50);self.assertEqual(r.rise_m,-10);self.assertEqual(r.percent_of_operating_head,-20)
    def test_no_extrapolation(self):
        for q in [-1,201,250]:
            with self.assertRaises(ValueError):core.local_curve_slope(curve(),q/3600)
        with self.assertRaises(ValueError):core.local_curve_slope(curve(POINTS[1:]),0)
    def test_invalid_inputs_and_overflow(self):
        for bad in [None,True,math.nan,math.inf,-math.inf,-1]:
            with self.assertRaises(ValueError):core.local_curve_slope(curve(),bad)
            with self.assertRaises(ValueError):core.calculate_shutoff_head_rise(50,bad)
        with self.assertRaises(ValueError):core.calculate_shutoff_head_rise(1e308,1e-308)
        with self.assertRaises(ValueError):core.segment_slopes(curve([(0,0),(1e-308,1e308),(2e-308,0)],'m³/s'))
    def test_unit_equivalence_all_units(self):
        hf=HEAD_FACTORS['ft']
        for unit,f in FLOW.items():
            c=curve([(q/3600/f,h/hf) for q,h in POINTS],unit,'ft');r=core.local_curve_slope(c,125/3600)
            self.assertAlmostEqual(r.operating_head_m,41,11);self.assertAlmostEqual(slope(r.local_segments[0]),-.12,12)
    def test_slope_display_dimensions(self):
        s=core.local_curve_slope(curve(),125/3600).local_segments[0]
        for fu,ff in FLOW.items():
            for hu,hf in HEAD_FACTORS.items():self.assertAlmostEqual(core.display_slope(s.slope_si,fu,hu,FLOW),s.slope_si*ff/hf,11)
        with self.assertRaises(ValueError):core.display_slope(s.slope_si,None,'m',FLOW)
    def test_minimum_status(self):
        for q,status in [(125,'Equals'),(126,'Above'),(124,'Below')]:self.assertEqual(core.compare_minimum_flow(q/3600,125/3600),status+' entered minimum flow')
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):core.analyze_curve_characteristics(curve()).shutoff_head_m=0
    def test_plot_labels_and_no_inferred_shutoff_marker(self):
        for pts,count in [(POINTS,4),(POINTS[1:],3)]:
            c=curve(pts);a=core.analyze_curve_characteristics(c);r=core.local_curve_slope(c,125/3600)
            p=ui.characteristics_plot_spec(c,a,r,FLOW['m³/hr'],'m³/hr','m');self.assertEqual(len(p['layer']),count)
            labels=[l['data']['values'][0]['label'] for l in p['layer'][1:]];self.assertIn('Maximum Supplied Flow Point',labels)
            self.assertEqual('Supplied Shutoff Head' in labels,len(pts)==5)

class CharacteristicsAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,points=POINTS,q=125,mixed=False):
        at=at or self.app();at.number_input(key='p3q_count').set_value(len(points)).run()
        cu='m³/s' if mixed else 'm³/hr';hu='ft' if mixed else 'm'
        for key,value in [('curve_unit',cu),('curve_head_unit',hu),('display_flow_unit','m³/hr'),('display_head_unit','m')]:at.selectbox(key='p3q_'+key).select(value)
        if at.selectbox(key='p3q_method').value==ui.METHODS_3Q[0]:at.selectbox(key='p3q_operating_unit').select('L/s' if mixed else 'm³/hr');at.number_input(key='p3q_operating').set_value(q/3600/.001 if mixed else q)
        for i,(flow,head) in enumerate(points):at.number_input(key=f'p3q_q_{i}').set_value(flow/3600 if mixed else flow);at.number_input(key=f'p3q_h_{i}').set_value(head/HEAD_FACTORS['ft'] if mixed else head)
        return at
    def calc(self,at):
        at.button(key='p3q_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def integrated(self):
        at=self.app();at.selectbox(key='p3q_method').select(ui.METHODS_3Q[1]).run();self.fill(at)
        for key,value in [('static',10),('reference',100),('friction',20)]:at.number_input(key='p3q_'+key).set_value(value)
        return at
    def test_render_blank_inputs_and_limits(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3Q — Pump Curve Characteristics / Shutoff & Slope Analysis' for e in at.expander))
        for w in at.selectbox:
            if w.key.startswith('p3q_') and w.key!='p3q_method':self.assertIsNone(w.value)
        for w in at.number_input:
            if w.key.startswith('p3q_') and w.key!='p3q_count':self.assertIsNone(w.value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3q_')]);self.assertTrue(any(ui.GUIDANCE in w.value for w in at.info))
        self.assertTrue(any('does not determine hydraulic stability' in w.value for w in at.caption))
    def test_manual_benchmark_all_summary_values(self):
        at=self.calc(self.fill());text=self.text(at);self.assertFalse(at.error)
        for expected in ['Supplied Flow Range: 0 to 200 m³/hr','Supplied Head Range: 30 to 50 m','Supplied Shutoff Head: 50 m','Operating Head: 41 m','Head Rise to Shutoff: 9 m','Percent Head Rise relative to Operating Head: 21.9512195122%','Percent Head Rise relative to Shutoff Head: 18%','Local Pump-Curve Slope — Adjacent Segment: -0.12 m per (m³/hr)','Flat Segment Count: 0','Rising Segment Count: 0','Supplied head curve is monotonically decreasing.']:self.assertIn(expected,text)
    def test_segment_table_benchmarks(self):
        at=self.calc(self.fill());table='\n'.join(w.value for w in at.markdown if '| Segment |' in w.value)
        for row in ['| 1 | 0 | 50 | -0.04 | Falling |','| 2 | 50 | 100 | -0.08 | Falling |','| 3 | 100 | 150 | -0.12 | Falling |','| 4 | 150 | 200 | -0.16 | Falling |']:self.assertIn(row,table)
    def test_internal_exact_operating_point(self):
        text=self.text(self.calc(self.fill(q=100)));self.assertIn('Operating Head: 44 m',text);self.assertIn('Left Segment: -0.08',text);self.assertIn('Right Segment: -0.12',text)
    def test_endpoint_operating_flows(self):
        for q,h,s in [(0,50,-.04),(200,30,-.16)]:
            at=self.calc(self.fill(q=q));self.assertIn(f'Operating Head: {h} m',self.text(at));self.assertIn(f'Adjacent Segment: {s}',self.text(at));self.assertNotIn('Left Segment',self.text(at))
    def test_flat_segment_accepted(self):
        at=self.calc(self.fill(points=FLAT,q=75));self.assertFalse(at.error);self.assertIn('Flat Segment Count: 1',self.text(at));self.assertTrue(any('Flat head segment detected. Segment 2: 50 to 100' in w.value for w in at.info))
        self.assertTrue(any('| 2 | 50 | 100 | 0 | Flat |' in w.value for w in at.markdown))
    def test_rising_nonmonotonic_preserved(self):
        at=self.calc(self.fill(points=RISING,q=75));self.assertFalse(at.error);self.assertIn('Rising Segment Count: 1',self.text(at));self.assertIn('not monotonically decreasing',self.text(at));self.assertTrue(any('Rising-head segment detected in supplied curve. Segment 2: 50 to 100' in w.value for w in at.info))
        spec=json.loads(at.get('vega_lite_chart')[0].proto.spec);self.assertEqual([p['head'] for p in spec['layer'][0]['data']['values']],[50,48,49,43,35])
    def test_no_zero_no_shutoff_or_marker(self):
        at=self.calc(self.fill(points=POINTS[1:]));self.assertIn(core.NO_SHUTOFF,self.text(at));self.assertNotIn('Head Rise to Shutoff:',self.text(at));self.assertEqual(len(json.loads(at.get('vega_lite_chart')[0].proto.spec)['layer']),3)
    def test_maximum_supplied_not_runout(self):
        at=self.calc(self.fill());text=self.text(at);self.assertIn('Maximum Supplied Flow Point: 200 m³/hr at 30 m',text);self.assertNotIn('Runout',text)
        labels=[l['data']['values'][0].get('label') for l in json.loads(at.get('vega_lite_chart')[0].proto.spec)['layer'][1:]];self.assertIn('Maximum Supplied Flow Point',labels)
    def test_no_extrapolation_low_high(self):
        for points,q in [(POINTS,-1),(POINTS,201),(POINTS[1:],0)]:
            at=self.calc(self.fill(points=points,q=q));self.assertTrue(at.error);self.assertFalse(at.get('vega_lite_chart'));self.assertNotIn('Operating Head:',self.text(at))
    def test_mixed_inputs_equivalence(self):
        at=self.calc(self.fill(mixed=True));self.assertIn('Operating Head: 41 m',self.text(at));self.assertIn('Adjacent Segment: -0.12 m per (m³/hr)',self.text(at));self.assertFalse(at.error)
    def test_ft_us_gpm_slope_display(self):
        at=self.fill();fu='Gallon/min (US GPM)';at.selectbox(key='p3q_display_flow_unit').select(fu);at.selectbox(key='p3q_display_head_unit').select('ft');self.calc(at)
        expected=core.display_slope(core.local_curve_slope(curve(),125/3600).local_segments[0].slope_si,fu,'ft',FLOW)
        self.assertIn(f'{expected:.12g} ft per ({fu})',self.text(at));self.assertIn(f'Operating Head: {41/HEAD_FACTORS["ft"]:.12g} ft',self.text(at))
    def test_integrated_3g_shared(self):
        at=self.integrated()
        with patch.object(ui,'find_operating_points',wraps=ui.find_operating_points) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1)
        for expected in ['Operating Flow: 124.596248337 m³/hr','Operating Head: 41.0484501995 m','Head Rise to Shutoff: 8.95154980049 m','Adjacent Segment: -0.12 m per (m³/hr)']:self.assertIn(expected,self.text(at))
        self.assertFalse(at.error)
    def test_integrated_direct_k(self):
        at=self.integrated();at.selectbox(key='p3q_sys_method').select('From System Resistance Coefficient K').run();at.number_input(key='p3q_k').set_value(20/(100/3600)**2);self.calc(at);self.assertIn('Operating Head: 41.0484501995 m',self.text(at))
    def test_ambiguous_or_missing_root_withheld(self):
        for roots in [SimpleNamespace(coincident_intervals=(),points=()),SimpleNamespace(coincident_intervals=(),points=(1,2)),SimpleNamespace(coincident_intervals=(1,),points=())]:
            at=self.integrated()
            with patch.object(ui,'find_operating_points',return_value=roots):self.calc(at)
            self.assertTrue(at.error);self.assertFalse(at.get('vega_lite_chart'))
    def test_optional_runout_is_explicit_ratio_only(self):
        at=self.fill();at.number_input(key='p3q_runout').set_value(250);at.selectbox(key='p3q_runout_unit').select('m³/hr');self.calc(at)
        self.assertIn('Operating Flow / Vendor Runout Flow %: 50%',self.text(at));self.assertIn('Maximum Supplied Flow Point: 200 m³/hr',self.text(at))
    def test_optional_minimum_neutral_relationships(self):
        for entered,status in [(100,'Above'),(125,'Equals'),(150,'Below')]:
            at=self.fill();at.number_input(key='p3q_minimum').set_value(entered);at.selectbox(key='p3q_minimum_unit').select('m³/hr');self.calc(at);self.assertIn(status+' entered minimum flow',self.text(at))
    def test_optional_bep_reuses3h_and_mixed_units(self):
        at=self.integrated();at.number_input(key='p3q_bep').set_value(150/3600);at.selectbox(key='p3q_bep_unit').select('m³/s')
        with patch.object(ui,'compare_bep',wraps=ui.compare_bep) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Percent of BEP: 83.0641655583%',self.text(at))
    def test_zero_head_percent_na(self):
        at=self.calc(self.fill(points=[(0,0),(50,0),(100,0)],q=50));self.assertFalse(at.error);self.assertIn('N/A — operating head is zero',self.text(at));self.assertIn('N/A — shutoff head is zero',self.text(at))
    def test_validation_and_stale_results(self):
        at=self.calc(self.fill());at.number_input(key='p3q_operating').set_value(75).run();self.assertNotIn('Operating Head:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
        at.number_input(key='p3q_q_1').set_value(0);self.calc(at);self.assertTrue(at.error)
    def test_previous_modules_unchanged(self):
        expected={'pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
