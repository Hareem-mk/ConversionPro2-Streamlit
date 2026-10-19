import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from app import FLOW
from pump_performance.pump_curve import create_pump_curve, interpolate_pump_head, HEAD_FACTORS
from pump_performance.system_curve import SystemModel, model_from_reference, model_from_k
from pump_performance.operating_point import (find_operating_points, head_tolerance,
                                               NO_INTERSECTION, MULTIPLE_INTERSECTIONS)

# Example / test data only, never loaded into production inputs.
BENCHMARK=[(0,50),(50,48),(100,44),(150,38),(200,30)]
UNSORTED=[BENCHMARK[i] for i in (3,0,4,1,2)]
EXPECTED_Q=124.59624833740307
EXPECTED_H=41.04845019951163


def curve(points=BENCHMARK,flow_unit='m³/hr',head_unit='m'):
    return create_pump_curve(points,flow_unit,head_unit,FLOW)


def system(**changes):
    inputs=dict(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,
                flow_unit='m³/hr',flow_factors=FLOW)
    inputs.update(changes)
    return model_from_reference(**inputs)


class OperatingPointTests(unittest.TestCase):
    def test_benchmark_flow_head(self):
        result=find_operating_points(curve(),system())
        self.assertEqual(len(result.points),1)
        self.assertFalse(result.coincident_intervals)
        point=result.points[0]
        self.assertAlmostEqual(point.flow_m3_s*3600,EXPECTED_Q,places=10)
        self.assertAlmostEqual(point.head_m,EXPECTED_H,places=10)

    def test_independent_curve_agreement(self):
        c,m=curve(),system()
        point=find_operating_points(c,m).points[0]
        pump=interpolate_pump_head(c,point.flow_m3_s/c.flow_factor).head_m
        required=m.at_flow(point.flow_m3_s).total_head_m
        self.assertAlmostEqual(point.pump_head_m,pump,places=12)
        self.assertAlmostEqual(point.system_head_m,required,places=12)
        self.assertLessEqual(abs(pump-required),head_tolerance(pump,required))
        self.assertLess(abs(point.residual_m),1e-11)

    def test_bracketed_inside_valid_segment(self):
        point=find_operating_points(curve(),system()).points[0]
        self.assertGreater(point.flow_m3_s,100/3600)
        self.assertLess(point.flow_m3_s,150/3600)

    def test_no_intersection_above(self):
        self.assertFalse(find_operating_points(curve(),SystemModel(60,25920)).points)

    def test_no_intersection_below(self):
        self.assertFalse(find_operating_points(curve(),SystemModel(0,0)).points)

    def test_exact_shared_point_deduplicated(self):
        result=find_operating_points(curve(),SystemModel(10,34/(100/3600)**2))
        self.assertEqual(len(result.points),1)
        self.assertEqual(result.points[0].flow_m3_s,100/3600)
        self.assertEqual(result.points[0].head_m,44)

    def test_range_endpoints(self):
        for static,k,q in [(50,0,0),(10,20/(200/3600)**2,200)]:
            result=find_operating_points(curve(),SystemModel(static,k))
            self.assertEqual(len(result.points),1)
            self.assertEqual(result.points[0].flow_m3_s,q/3600)

    def test_unsorted_data(self):
        self.assertEqual(find_operating_points(curve(UNSORTED),system()),
                         find_operating_points(curve(),system()))

    def test_all_flow_units(self):
        for unit,factor in FLOW.items():
            with self.subTest(unit=unit):
                c=curve([(q/3600/factor,h) for q,h in BENCHMARK],unit)
                m=system(reference_flow=100/3600/factor,flow_unit=unit)
                p=find_operating_points(c,m).points[0]
                self.assertAlmostEqual(p.flow_m3_s,EXPECTED_Q/3600,places=14)
                self.assertAlmostEqual(p.head_m,EXPECTED_H,places=10)

    def test_head_units(self):
        factor=HEAD_FACTORS['ft']
        c=curve([(q,h/factor) for q,h in BENCHMARK],head_unit='ft')
        m=system(static_head=10/factor,reference_friction_head=20/factor,head_unit='ft')
        p=find_operating_points(c,m).points[0]
        self.assertAlmostEqual(p.flow_m3_s,EXPECTED_Q/3600,places=14)
        self.assertAlmostEqual(p.head_m,EXPECTED_H,places=10)

    def test_direct_k_equivalence(self):
        expected=find_operating_points(curve(),system()).points[0]
        actual=find_operating_points(curve(),model_from_k(10,'m',25920)).points[0]
        self.assertAlmostEqual(actual.flow_m3_s,expected.flow_m3_s,places=15)

    def test_multiple_crossing_segments(self):
        c=curve([(0,0),(1,2),(2,0),(3,2),(4,0)],'m³/s')
        result=find_operating_points(c,SystemModel(1,0))
        self.assertEqual([p.flow_m3_s for p in result.points],[.5,1.5,2.5,3.5])
        self.assertTrue(all(p.residual_m==0 for p in result.points))

    def test_two_roots_same_segment_no_endpoint_sign_change(self):
        c=curve([(0,0),(4,16),(5,0)],'m³/s')
        result=find_operating_points(c,SystemModel(1,1))
        self.assertEqual(len(result.points),2)
        for p,q in zip(result.points,[2-math.sqrt(3),2+math.sqrt(3)]):
            self.assertAlmostEqual(p.flow_m3_s,q,places=12)

    def test_exact_tangent(self):
        c=curve([(0,0),(2,4),(3,0)],'m³/s')
        result=find_operating_points(c,SystemModel(1,1))
        self.assertEqual(len(result.points),1)
        self.assertEqual((result.points[0].flow_m3_s,result.points[0].head_m),(1,2))

    def test_shared_point_tangent(self):
        c=curve([(0,0),(1,2),(2,4)],'m³/s')
        result=find_operating_points(c,SystemModel(1,1))
        self.assertEqual(len(result.points),1)
        self.assertEqual(result.points[0].flow_m3_s,1)

    def test_near_touch_two_roots(self):
        c=curve([(0,.000001),(2,4.000001),(3,0)],'m³/s')
        result=find_operating_points(c,SystemModel(1,1))
        self.assertEqual(len(result.points),2)
        self.assertAlmostEqual(result.points[0].flow_m3_s,.999,places=9)
        self.assertAlmostEqual(result.points[1].flow_m3_s,1.001,places=9)

    def test_near_miss_not_false_tangent(self):
        c=curve([(.5,.999999),(2,3.999999),(3,0)],'m³/s')
        self.assertFalse(find_operating_points(c,SystemModel(1,1)).points)

    def test_coincident_intervals(self):
        c=curve([(0,10),(1,10),(2,10)],'m³/s')
        result=find_operating_points(c,SystemModel(10,0))
        self.assertFalse(result.points)
        self.assertEqual(len(result.coincident_intervals),1)
        interval=result.coincident_intervals[0]
        self.assertEqual((interval.minimum_flow_m3_s,interval.maximum_flow_m3_s),(0,2))

    def test_coincident_and_isolated(self):
        c=curve([(0,10),(1,10),(2,20),(3,0)],'m³/s')
        result=find_operating_points(c,SystemModel(10,0))
        self.assertEqual(len(result.coincident_intervals),1)
        self.assertEqual([p.flow_m3_s for p in result.points],[2.5])

    def test_positive_minimum_no_extrapolation(self):
        c=curve(BENCHMARK[1:])
        p=find_operating_points(c,system()).points[0]
        self.assertAlmostEqual(p.flow_m3_s*3600,EXPECTED_Q,places=10)
        # A crossing below this supplied range is not reported.
        c=curve([(10,10),(20,9),(30,8)],'m³/s')
        self.assertFalse(find_operating_points(c,SystemModel(0,1)).points)

    def test_shared_kernel_calls(self):
        from pump_performance import operating_point as module
        original=SystemModel.at_flow
        with patch.object(module,'interpolate_pump_head',wraps=module.interpolate_pump_head) as pump:
            with patch.object(SystemModel,'at_flow',autospec=True,side_effect=original) as required:
                result=module.find_operating_points(curve(),system())
                self.assertEqual(len(result.points),1)
                self.assertGreater(pump.call_count,2)
                self.assertGreater(required.call_count,2)

    def test_invalid_system_reuses_validation(self):
        for model in [SystemModel(-1,1),SystemModel(1,-1),SystemModel(math.inf,1),SystemModel(1,math.nan)]:
            with self.assertRaises(ValueError):find_operating_points(curve(),model)

    def test_duplicate_and_negative_pump_data_rejected(self):
        for points in [[(0,50),(100,44),(100,43)],[(0,-1),(50,48),(100,44)],[(0,50),(-1,48),(100,44)]]:
            with self.assertRaises(ValueError):curve(points)

    def test_small_heads_do_not_create_false_roots(self):
        c=curve([(0,2e-20),(1,2e-20),(2,2e-20)],'m³/s')
        self.assertFalse(find_operating_points(c,SystemModel(1e-20,0)).points)
        c=curve([(0,0),(1,2e-20),(2,0)],'m³/s')
        result=find_operating_points(c,SystemModel(1e-20,0))
        self.assertEqual([p.flow_m3_s for p in result.points],[.5,1.5])

    def test_flat_pump_with_quadratic_system(self):
        c=curve([(0,4),(1,4),(3,4)],'m³/s')
        result=find_operating_points(c,SystemModel(0,1))
        self.assertEqual(len(result.points),1)
        self.assertEqual(result.points[0].flow_m3_s,2)


class OperatingPointAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self,at,points=BENCHMARK,flow_unit='m³/hr',head_unit='m',static=10,reference=100,friction=20):
        at.number_input(key='p3g_count').set_value(len(points)).run()
        at.selectbox(key='p3g_flow_unit').select(flow_unit)
        at.selectbox(key='p3g_head_unit').select(head_unit)
        for index,(q,h) in enumerate(points):
            at.number_input(key=f'p3g_q_{index}').set_value(q)
            at.number_input(key=f'p3g_h_{index}').set_value(h)
        at.number_input(key='p3g_static').set_value(static)
        at.number_input(key='p3g_reference_flow').set_value(reference)
        at.number_input(key='p3g_reference_friction').set_value(friction)
        return at.button(key='p3g_calculate').click().run()

    def texts(self,at):return '\n'.join(w.value for w in at.text if 'Operating Flow:' in w.value)
    def spec(self,at):return json.loads(at.get('vega_lite_chart')[0].proto.spec)

    def test_initial_render_units_and_no_defaults(self):
        at=self.app()
        self.assertTrue(any(w.label=='3G — Pump/System Operating Point' for w in at.expander))
        self.assertIsNone(at.selectbox(key='p3g_flow_unit').value)
        self.assertIsNone(at.selectbox(key='p3g_head_unit').value)
        self.assertIsNone(at.number_input(key='p3g_q_0').value)
        self.assertIsNone(at.number_input(key='p3g_static').value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3g_')])
        self.assertFalse(at.get('vega_lite_chart'))
        self.assertEqual(len(at.tabs),15)
        self.assertFalse(at.exception)
        at.button(key='p3g_calculate').click().run()
        self.assertTrue(at.error)

    def test_benchmark_results_and_plot(self):
        at=self.fill(self.app())
        self.assertFalse(at.error)
        self.assertFalse(at.exception)
        self.assertIn('Operating Flow: 124.596 m³/hr',self.texts(at))
        self.assertIn('Operating Head: 41.0485 m',self.texts(at))
        self.assertIn('Pump Head at Operating Point: 41.0484501995 m',self.texts(at))
        self.assertIn('System Head at Operating Point: 41.0484501995 m',self.texts(at))
        spec=self.spec(at)
        self.assertEqual(spec['title'],'Pump and System Curves')
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/hr)')
        self.assertEqual(spec['encoding']['y']['title'],'Head (m)')
        self.assertEqual(len(spec['layer'][0]['data']['values']),5)
        self.assertEqual(len(spec['layer'][1]['data']['values']),81)
        self.assertEqual(len(spec['layer'][2]['data']['values']),1)
        marker=spec['layer'][2]
        self.assertEqual(marker['mark']['shape'],'diamond')
        self.assertAlmostEqual(marker['data']['values'][0]['flow'],EXPECTED_Q,places=10)
        self.assertEqual(at.number_input(key='p3g_q_0').label,'Pump Point 1 — Flow (m³/hr)')
        self.assertEqual(at.number_input(key='p3g_h_0').label,'Pump Point 1 — Head (m)')
        self.assertTrue(any('Residual check in SI' in w.value for w in at.caption))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox] for w in group]
        self.assertEqual(len(keys),len(set(keys)))

    def test_no_intersection_guidance_and_no_marker(self):
        at=self.fill(self.app(),static=60)
        self.assertTrue(any(w.value==NO_INTERSECTION for w in at.info))
        self.assertFalse(self.texts(at))
        self.assertEqual(len(self.spec(at)['layer']),2)
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_exact_point_no_duplicate_markers(self):
        at=self.fill(self.app(),friction=34)
        self.assertIn('Operating Flow: 100 m³/hr',self.texts(at))
        self.assertIn('Operating Head: 44 m',self.texts(at))
        self.assertEqual(len(self.spec(at)['layer'][2]['data']['values']),1)
        self.assertFalse(any(w.value==MULTIPLE_INTERSECTIONS for w in at.warning))

    def test_unsorted(self):
        at=self.fill(self.app(),points=UNSORTED)
        self.assertIn('Operating Flow: 124.596 m³/hr',self.texts(at))
        self.assertEqual([round(p['flow']) for p in self.spec(at)['layer'][0]['data']['values']],[0,50,100,150,200])

    def test_unit_equivalence(self):
        factor=HEAD_FACTORS['ft']
        at=self.fill(self.app(),points=[(q/3600,h/factor) for q,h in BENCHMARK],flow_unit='m³/s',head_unit='ft',
                     static=10/factor,reference=100/3600,friction=20/factor)
        self.assertIn(f'Operating Flow: {EXPECTED_Q/3600:.6g} m³/s',self.texts(at))
        self.assertIn(f'Operating Head: {EXPECTED_H/factor:.6g} ft',self.texts(at))
        self.assertEqual(self.spec(at)['encoding']['y']['title'],'Head (ft)')
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_direct_k(self):
        at=self.fill(self.app())
        expected=self.texts(at)
        at.selectbox(key='p3g_method').select('From System Resistance Coefficient K').run()
        self.assertFalse(self.texts(at))
        self.assertEqual(at.number_input(key='p3g_k').label,'Operating-Point System K [for Q in m³/s] (s²/m⁵)')
        at.number_input(key='p3g_k').set_value(25920)
        at.button(key='p3g_calculate').click().run()
        self.assertEqual(self.texts(at),expected)
        self.assertFalse(at.exception)

    def test_multiple_all_listed(self):
        at=self.fill(self.app(),points=[(0,0),(1,2),(2,0),(3,2),(4,0)],flow_unit='m³/s',
                     static=1,reference=1,friction=0)
        self.assertTrue(any(w.value==MULTIPLE_INTERSECTIONS for w in at.warning))
        for index,q in enumerate([.5,1.5,2.5,3.5],1):
            self.assertIn(f'Intersection {index}\nOperating Flow: {q} m³/s',self.texts(at))
        self.assertEqual(len(self.spec(at)['layer'][2]['data']['values']),4)
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_tangency(self):
        at=self.fill(self.app(),points=[(0,0),(2,4),(3,0)],flow_unit='m³/s',static=1,reference=1,friction=1)
        self.assertIn('Operating Flow: 1 m³/s',self.texts(at))
        self.assertIn('Operating Head: 2 m',self.texts(at))
        self.assertEqual(len(self.spec(at)['layer'][2]['data']['values']),1)

    def test_coincident_interval_guidance(self):
        at=self.fill(self.app(),points=[(0,10),(1,10),(2,10)],flow_unit='m³/s',static=10,reference=1,friction=0)
        self.assertTrue(any('infinitely many intersections' in w.value for w in at.warning))
        self.assertFalse(self.texts(at))
        self.assertFalse(any(w.value==NO_INTERSECTION for w in at.info))
        self.assertFalse(at.exception)

    def test_invalid_duplicate_and_system(self):
        at=self.fill(self.app())
        at.number_input(key='p3g_q_2').set_value(50)
        at.button(key='p3g_calculate').click().run()
        self.assertIn('Each pump-curve flow value must be unique',at.error[0].value)
        self.assertFalse(self.texts(at))
        self.assertFalse(at.get('vega_lite_chart'))
        at.number_input(key='p3g_q_2').set_value(100)
        at.number_input(key='p3g_reference_flow').set_value(0)
        at.button(key='p3g_calculate').click().run()
        self.assertIn('greater than zero',at.error[0].value)
        self.assertFalse(at.exception)

    def test_stale_results_clear(self):
        at=self.fill(self.app())
        at.number_input(key='p3g_static').set_value(60).run()
        self.assertFalse(self.texts(at))
        self.assertFalse(at.get('vega_lite_chart'))
        at.button(key='p3g_calculate').click().run()
        self.assertTrue(any(w.value==NO_INTERSECTION for w in at.info))
        self.assertFalse(at.exception)
