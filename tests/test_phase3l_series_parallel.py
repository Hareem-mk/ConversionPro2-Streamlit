"""Exact piecewise composition, bounded domains and shared-kernel UI workflows."""
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch
from dataclasses import FrozenInstanceError

from app import FLOW
from pump_performance.pump_curve import create_pump_curve,interpolate_pump_head,HEAD_FACTORS
from pump_performance.series_parallel import (combine_series_curves,combine_parallel_curves,
    combine_identical_series,combine_identical_parallel)
from pump_performance.system_curve import model_from_reference,SystemModel
from pump_performance.operating_point import find_operating_points,head_tolerance

BENCHMARK=[(0,50),(50,48),(100,44),(150,38),(200,30)]
A=[(0,50),(50,48),(100,44),(150,38)]
B=[(0,40),(50,38),(100,34),(150,28)]
PAR_A=[(0,50),(50,45),(100,40)]
PAR_B=[(0,45),(50,40),(100,35)]


def curve(points=BENCHMARK,unit='m³/hr',head_unit='m'):
    return create_pump_curve(points,unit,head_unit,FLOW)


def system():
    return model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)


class CombinedCurveTests(unittest.TestCase):
    def test_identical_series_preserves_all_points(self):
        c=curve();r=combine_identical_series(c)
        self.assertEqual(len(r.combined.points),5)
        self.assertEqual([(p.flow_m3_s,p.head_m) for p in r.combined.points],[(p.flow_m3_s,2*p.head_m) for p in c.points])
        self.assertEqual(r.combined.shutoff_head_m,100)

    def test_identical_series_selected_flow(self):
        r=combine_identical_series(curve())
        self.assertAlmostEqual(interpolate_pump_head(r.combined,125/3600).head_m,82,places=12)

    def test_identical_parallel_preserves_all_points(self):
        c=curve();r=combine_identical_parallel(c)
        self.assertEqual([(p.flow_m3_s,p.head_m) for p in r.combined.points],[(2*p.flow_m3_s,p.head_m) for p in c.points])
        self.assertEqual(r.combined.shutoff_head_m,50)

    def test_identical_parallel_selected_flow(self):
        r=combine_identical_parallel(curve())
        self.assertAlmostEqual(interpolate_pump_head(r.combined,250/3600).head_m,41,places=12)

    def test_different_series_benchmark(self):
        r=combine_series_curves(curve(A),curve(B))
        self.assertEqual([p.head_m for p in r.combined.points],[90,86,78,66])
        self.assertAlmostEqual(interpolate_pump_head(r.combined,125/3600).head_m,72,places=12)

    def test_different_parallel_hand_check(self):
        r=combine_parallel_curves(curve(PAR_A),curve(PAR_B))
        self.assertEqual(r.overlap_minimum,40);self.assertEqual(r.overlap_maximum,45)
        # At head 42 m: A supplies 80 m³/h, B supplies 30 m³/h.
        self.assertAlmostEqual(interpolate_pump_head(r.combined,110/3600).head_m,42,places=12)
        self.assertAlmostEqual(r.combined.points[0].flow_m3_s*3600,50,places=12)
        self.assertAlmostEqual(r.combined.points[-1].flow_m3_s*3600,150,places=12)
        self.assertIsNone(r.combined.shutoff_head_m)

    def test_series_breakpoint_union(self):
        a=curve([(0,10),(1,8),(2,6)],'m³/s')
        b=curve([(.5,12),(1.5,10),(2.5,8)],'m³/s')
        r=combine_series_curves(a,b)
        self.assertEqual([p.flow_m3_s for p in r.combined.points],[.5,1,1.5,2])
        self.assertEqual([p.head_m for p in r.combined.points],[21,19,17,15])

    def test_parallel_breakpoint_union(self):
        a=curve([(0,10),(1,8),(2,4)],'m³/s')
        b=curve([(0,9),(1,7),(3,3)],'m³/s')
        r=combine_parallel_curves(a,b)
        self.assertEqual([p.head_m for p in r.combined.points],[9,8,7,4])
        self.assertTrue(all(x.flow_m3_s<y.flow_m3_s for x,y in zip(r.combined.points,r.combined.points[1:])))

    def test_narrow_series_overlap_midpoint(self):
        a=curve([(0,10),(1,8),(2,6)],'m³/s')
        b=curve([(1.5,12),(3,10),(4,8)],'m³/s')
        r=combine_series_curves(a,b)
        self.assertEqual([p.flow_m3_s for p in r.combined.points],[1.5,1.75,2])
        self.assertEqual(len(find_operating_points(r.combined,SystemModel(0,0)).points),0)

    def test_nonoverlap_series_and_single_contact(self):
        for points in [[(201,30),(250,20),(300,10)],[(200,30),(250,20),(300,10)]]:
            with self.assertRaisesRegex(ValueError,'overlapping flow domain'):combine_series_curves(curve(),curve(points))

    def test_nonoverlap_parallel_and_single_contact(self):
        for points in [[(0,20),(50,10),(100,0)],[(0,30),(50,20),(100,10)]]:
            with self.assertRaisesRegex(ValueError,'overlapping head domain'):combine_parallel_curves(curve(),curve(points))

    def test_parallel_rejects_rising_and_flat(self):
        for points in [[(0,20),(1,30),(2,10)],[(0,30),(1,30),(2,10)]]:
            c=curve(points,'m³/s')
            with self.assertRaisesRegex(ValueError,'unique head-to-flow inversion'):combine_parallel_curves(c,curve())
            with self.assertRaisesRegex(ValueError,'strictly decreasing'):combine_identical_parallel(c)

    def test_series_accepts_nonmonotonic(self):
        c=curve([(0,0),(1,2),(2,0)],'m³/s')
        self.assertEqual([p.head_m for p in combine_identical_series(c).combined.points],[0,4,0])

    def test_no_zero_flow_required(self):
        c=curve([(50,48),(100,44),(150,38)])
        for fn in [combine_identical_series,combine_identical_parallel]:
            r=fn(c);self.assertGreater(r.combined.points[0].flow_m3_s,0)
            self.assertIsNone(r.combined.shutoff_head_m)

    def test_combined_extrapolation_rejected(self):
        for r in [combine_identical_series(curve()),combine_identical_parallel(curve()),combine_parallel_curves(curve(PAR_A),curve(PAR_B))]:
            with self.assertRaisesRegex(ValueError,'outside the supplied'):interpolate_pump_head(r.combined,r.combined.points[-1].flow_m3_s+1)
        r=combine_parallel_curves(curve(PAR_A),curve(PAR_B))
        with self.assertRaises(ValueError):interpolate_pump_head(r.combined,0)

    def test_original_interpolation_reused(self):
        from pump_performance import series_parallel as core
        with patch.object(core,'interpolate_pump_head',wraps=interpolate_pump_head) as forward:
            combine_series_curves(curve(A),curve(B))
            self.assertTrue(forward.called)
        with patch.object(core,'interpolate_pump_head',wraps=interpolate_pump_head) as inverse_check:
            combine_parallel_curves(curve(PAR_A),curve(PAR_B))
            self.assertTrue(inverse_check.called)

    def test_si_and_all_flow_units_and_ft(self):
        reference=combine_series_curves(curve(A),curve(B)).combined
        reference_parallel=combine_parallel_curves(curve(PAR_A),curve(PAR_B)).combined
        for unit,f in FLOW.items():
            for head_unit,hf in HEAD_FACTORS.items():
                def converted(points):return curve([(q/3600/f,h/hf) for q,h in points],unit,head_unit)
                for r,expected in [(combine_series_curves(converted(A),converted(B)).combined,reference),
                                   (combine_parallel_curves(converted(PAR_A),converted(PAR_B)).combined,reference_parallel)]:
                    with self.subTest(unit=unit,head=head_unit):
                        self.assertEqual(len(r.points),len(expected.points))
                        for p,e in zip(r.points,expected.points):
                            self.assertAlmostEqual(p.flow_m3_s,e.flow_m3_s,places=14)
                            self.assertAlmostEqual(p.head_m,e.head_m,places=11)

    def test_independent_input_curve_units(self):
        f=HEAD_FACTORS['ft']
        b=curve([(q/3600,h/f) for q,h in B],'m³/s','ft')
        r=combine_series_curves(curve(A),b)
        self.assertAlmostEqual(interpolate_pump_head(r.combined,125/3600).head_m,72,places=11)

    def test_series_system_benchmark(self):
        c=combine_identical_series(curve()).combined
        p=find_operating_points(c,system()).points[0]
        self.assertAlmostEqual(p.flow_m3_s*3600,171.7935662402834,places=10)
        self.assertAlmostEqual(p.head_m,69.02605880310931,places=10)
        self.assertLessEqual(abs(p.residual_m),head_tolerance(p.pump_head_m,p.system_head_m))
        self.assertLessEqual(p.flow_m3_s,c.points[-1].flow_m3_s)

    def test_parallel_system_benchmark(self):
        c=combine_identical_parallel(curve()).combined
        p=find_operating_points(c,system()).points[0]
        self.assertAlmostEqual(p.flow_m3_s*3600,135.2583904633395,places=10)
        self.assertAlmostEqual(p.head_m,46.58966438146642,places=10)
        self.assertLessEqual(abs(p.residual_m),head_tolerance(p.pump_head_m,p.system_head_m))

    def test_no_multiple_and_coincident_intersections(self):
        c=combine_identical_series(curve([(0,0),(1,2),(2,0),(3,2),(4,0)],'m³/s')).combined
        self.assertEqual([p.flow_m3_s for p in find_operating_points(c,SystemModel(2,0)).points],[.5,1.5,2.5,3.5])
        self.assertFalse(find_operating_points(c,SystemModel(10,0)).points)
        c=combine_identical_series(curve([(0,1),(1,1),(2,1)],'m³/s')).combined
        self.assertEqual(len(find_operating_points(c,SystemModel(2,0)).coincident_intervals),1)

    def test_unsorted_and_invalid_curve_input(self):
        self.assertEqual(combine_identical_series(curve(list(reversed(BENCHMARK)))),combine_identical_series(curve()))
        for points in [[(0,50),(0,48),(100,44)],[(0,50),(-1,48),(100,44)],[(0,50),(50,-1),(100,44)],[(0,50),(math.inf,48),(100,44)],[(0,50),(100,44)]]:
            with self.assertRaises(ValueError):curve(points)
        with self.assertRaises(ValueError):curve(unit='unsupported')

    def test_immutable_and_overflow(self):
        r=combine_identical_series(curve())
        with self.assertRaises(FrozenInstanceError):r.configuration='Parallel'
        c=curve([(0,1e308),(1,8e307),(2,6e307)],'m³/s')
        with self.assertRaises(ValueError):combine_identical_series(c)


class CombinedCurveAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self,at,configuration='Pumps in Series',first=BENCHMARK,second=None,selected=125,system_enabled=False):
        at.selectbox(key='p3l_configuration').select(configuration)
        if second is not None:at.selectbox(key='p3l_mode').select('Different Pump Curves')
        at.run()
        for number,points in [(1,first)]+([(2,second)] if second is not None else []):
            at.number_input(key=f'p3l_count_{number}').set_value(len(points)).run()
        at.selectbox(key='p3l_flow_unit').select('m³/hr')
        at.selectbox(key='p3l_head_unit').select('m')
        for number,points in [(1,first)]+([(2,second)] if second is not None else []):
            for i,(q,h) in enumerate(points):
                at.number_input(key=f'p3l_q_{number}_{i}').set_value(q)
                at.number_input(key=f'p3l_h_{number}_{i}').set_value(h)
        at.number_input(key='p3l_selected').set_value(selected)
        if system_enabled:
            at.selectbox(key='p3l_comparison').select('Compare with System Curve').run()
            for key,val in [('p3l_static',10),('p3l_reference',100),('p3l_friction',20)]:at.number_input(key=key).set_value(val)
        return at.button(key='p3l_calculate').click().run()

    def text(self,at):return '\n'.join(w.value for w in at.text)
    def spec(self,at):return json.loads(at.get('vega_lite_chart')[0].proto.spec)

    def test_initial_render_explicit_units_no_defaults(self):
        at=self.app()
        self.assertTrue(any(w.label=='3L — Pumps in Series / Parallel' for w in at.expander))
        self.assertEqual(at.selectbox(key='p3l_configuration').options,['Pumps in Series','Pumps in Parallel'])
        self.assertEqual(at.selectbox(key='p3l_mode').options,['Identical Pumps','Different Pump Curves'])
        self.assertIsNone(at.selectbox(key='p3l_flow_unit').value);self.assertIsNone(at.selectbox(key='p3l_head_unit').value)
        self.assertIsNone(at.number_input(key='p3l_q_1_0').value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3l_')])
        self.assertEqual(len(at.tabs),15);self.assertFalse(at.exception)

    def test_identical_series_benchmark(self):
        at=self.fill(self.app())
        self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('Combined Head: 82 m',self.text(at))
        self.assertIn('0 | 100\n50 | 96\n100 | 88\n150 | 76\n200 | 60',self.text(at))
        self.assertEqual(len(self.spec(at)['layer']),2)

    def test_identical_parallel_benchmark(self):
        at=self.fill(self.app(),configuration='Pumps in Parallel',selected=250)
        self.assertFalse(at.error)
        self.assertIn('Combined Head: 41 m',self.text(at))
        self.assertIn('0 | 50\n100 | 48\n200 | 44\n300 | 38\n400 | 30',self.text(at))

    def test_different_series_benchmark(self):
        at=self.fill(self.app(),first=A,second=B)
        self.assertFalse(at.error);self.assertIn('Combined Head: 72 m',self.text(at))
        self.assertEqual(len(self.spec(at)['layer']),3)

    def test_different_parallel_hand_check(self):
        at=self.fill(self.app(),configuration='Pumps in Parallel',first=PAR_A,second=PAR_B,selected=110)
        self.assertFalse(at.error);self.assertIn('Combined Head: 42 m',self.text(at))
        self.assertIn('Combined Valid Flow Range: 50 to 150 m³/hr',self.text(at))
        self.assertIn('Common Head: 40 to 45 m',self.text(at))

    def test_extrapolation_rejected(self):
        at=self.fill(self.app(),selected=201)
        self.assertTrue(any('outside the supplied' in w.value for w in at.error))
        self.assertFalse(at.get('vega_lite_chart'))

    def test_nonoverlap_series(self):
        at=self.fill(self.app(),second=[(201,30),(250,20),(300,10)],selected=None)
        self.assertTrue(any('overlapping flow domain' in w.value for w in at.error))

    def test_nonoverlap_parallel(self):
        at=self.fill(self.app(),configuration='Pumps in Parallel',second=[(0,20),(50,10),(100,0)],selected=None)
        self.assertTrue(any('overlapping head domain' in w.value for w in at.error))

    def test_parallel_flat_and_nonmonotonic(self):
        for first in [[(0,20),(50,30),(100,10)],[(0,30),(50,30),(100,10)]]:
            at=self.fill(self.app(),configuration='Pumps in Parallel',first=first,selected=None)
            self.assertTrue(any('unique head-to-flow inversion' in w.value for w in at.error))
            self.assertFalse(at.exception)

    def test_series_system_shared_kernels_and_plot(self):
        from pump_performance import series_parallel_ui as ui
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as roots,patch.object(ui,'model_from_reference',wraps=model_from_reference) as model:
            at=self.fill(self.app(),system_enabled=True)
        self.assertTrue(roots.called and model.called);self.assertFalse(at.error)
        self.assertIn('Operating Flow: 171.79356624 m³/hr',self.text(at))
        spec=self.spec(at)
        self.assertEqual(len(spec['layer']),4)
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/hr)')
        self.assertEqual(spec['layer'][-1]['mark']['shape'],'diamond')
        combined=spec['layer'][1]['data']['values']
        system_rows=spec['layer'][2]['data']['values']
        self.assertEqual(system_rows[0]['flow'],combined[0]['flow'])
        self.assertEqual(system_rows[-1]['flow'],combined[-1]['flow'])

    def test_parallel_system_and_direct_k(self):
        at=self.fill(self.app(),configuration='Pumps in Parallel',selected=250,system_enabled=True)
        self.assertIn('Operating Flow: 135.258390463 m³/hr',self.text(at))
        at.selectbox(key='p3l_system_method').select('From System Resistance Coefficient K').run()
        at.number_input(key='p3l_k').set_value(25920);at.button(key='p3l_calculate').click().run()
        self.assertFalse(at.error);self.assertIn('Operating Head: 46.5896643815 m',self.text(at))

    def test_no_intersection(self):
        at=self.fill(self.app(),system_enabled=True)
        at.number_input(key='p3l_static').set_value(200);at.button(key='p3l_calculate').click().run()
        self.assertTrue(any('No pump/system intersection' in w.value for w in at.info))
        self.assertEqual(len(self.spec(at)['layer']),3)

    def test_multiple_intersections_preserved(self):
        at=self.fill(self.app(),first=[(0,0),(50,2),(100,0),(150,2),(200,0)],selected=None,system_enabled=True)
        at.number_input(key='p3l_static').set_value(2);at.number_input(key='p3l_friction').set_value(0)
        at.button(key='p3l_calculate').click().run()
        self.assertTrue(any('Multiple pump/system intersections' in w.value for w in at.warning))
        self.assertEqual(self.text(at).count('Operating Flow:'),4)
        self.assertEqual(len(self.spec(at)['layer'][-1]['data']['values']),4)

    def test_coincident_intervals_preserved(self):
        at=self.fill(self.app(),first=[(0,1),(50,1),(100,1)],selected=None,system_enabled=True)
        at.number_input(key='p3l_static').set_value(2);at.number_input(key='p3l_friction').set_value(0)
        at.button(key='p3l_calculate').click().run()
        self.assertTrue(any('infinitely many intersections' in w.value for w in at.warning))
        self.assertIn('Coincident Flow Interval: 0 to 100 m³/hr',self.text(at))
        self.assertNotIn('Operating Flow:',self.text(at))

    def test_unit_equivalence_si_ft(self):
        at=self.fill(self.app())
        at.selectbox(key='p3l_flow_unit').select('m³/s');at.selectbox(key='p3l_head_unit').select('ft')
        for i,(q,h) in enumerate(BENCHMARK):
            at.number_input(key=f'p3l_q_1_{i}').set_value(q/3600)
            at.number_input(key=f'p3l_h_1_{i}').set_value(h/HEAD_FACTORS['ft'])
        at.number_input(key='p3l_selected').set_value(125/3600)
        at.button(key='p3l_calculate').click().run()
        self.assertFalse(at.error)
        self.assertIn(f'Combined Head: {82/HEAD_FACTORS["ft"]:.12g} ft',self.text(at))
        self.assertEqual(self.spec(at)['encoding']['x']['title'],'Flow Rate (m³/s)')

    def test_vendor_guidance_no_dissimilar_equal_flow_claim(self):
        at=self.fill(self.app(),configuration='Pumps in Parallel',first=PAR_A,second=PAR_B,selected=110)
        captions='\n'.join(w.value for w in at.caption)
        self.assertIn('Equal flow sharing is assumed only for identical pumps',captions)
        self.assertIn('Check BEP, NPSHR, power and driver loading for each operating pump',captions)
        self.assertTrue(any('manufacturer/vendor pump curves applicable' in w.value for w in at.info))
        self.assertNotIn('Stable parallel operation',self.text(at))

    def test_invalid_data_and_missing_units(self):
        at=self.app().button(key='p3l_calculate').click().run()
        self.assertTrue(at.error);self.assertFalse(at.exception)
        at=self.fill(self.app(),first=[(0,50),(0,48),(100,44)],selected=None)
        self.assertTrue(any('unique' in w.value for w in at.error))

    def test_input_change_clears_results(self):
        at=self.fill(self.app())
        at.number_input(key='p3l_h_1_0').set_value(51).run()
        self.assertFalse(at.get('vega_lite_chart'))
        self.assertNotIn('Combined Head:',self.text(at))

if __name__=='__main__':unittest.main()
