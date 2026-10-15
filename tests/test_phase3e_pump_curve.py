import json
import math
from pathlib import Path
import unittest
from app import FLOW
from pump_performance.pump_curve import (create_pump_curve, interpolate_pump_head, HEAD_FACTORS,
                                          OUT_OF_RANGE, RISING_HEAD_WARNING)
from pump_performance.pump_curve_ui import curve_plot_spec

# Example / test data only. Never loaded into production inputs.
BENCHMARK = [(0, 50), (50, 48), (100, 44), (150, 38), (200, 30)]
UNSORTED = [BENCHMARK[i] for i in (3, 0, 4, 1, 2)]


def curve(points=BENCHMARK, unit='m³/hr', head_unit='m', factors=FLOW):
    return create_pump_curve(points, unit, head_unit, factors)


class PumpCurveTests(unittest.TestCase):
    def test_benchmark_sorted_data(self):
        r = curve()
        self.assertEqual(len(r.points), 5)
        self.assertEqual([p.head_m for p in r.points], [50,48,44,38,30])
        for (q,h), (expected_q,expected_h) in zip(r.display_points(),BENCHMARK):
            self.assertAlmostEqual(q,expected_q,places=12)
            self.assertEqual(h,expected_h)
        self.assertFalse(r.has_rising_head)
        self.assertEqual(r.shutoff_head_m,50)

    def test_125_interpolation(self):
        r = interpolate_pump_head(curve(),125)
        self.assertAlmostEqual(r.head_m,41,places=12)
        self.assertEqual((r.lower.head_m,r.upper.head_m),(44,38))
        self.assertFalse(r.exact_point)

    def test_175_interpolation(self):
        self.assertAlmostEqual(interpolate_pump_head(curve(),175).head_m,34,places=12)

    def test_exact_points_and_endpoints(self):
        c = curve()
        for point, (q,h) in zip(c.points,BENCHMARK):
            r = interpolate_pump_head(c,q)
            self.assertEqual(r.head_m,h)
            self.assertIs(r.lower,point)
            self.assertIs(r.upper,point)
            self.assertTrue(r.exact_point)

    def test_no_extrapolation(self):
        for c,q in [(curve(),250), (curve(BENCHMARK[1:]),0)]:
            with self.subTest(q=q), self.assertRaisesRegex(ValueError,'Extrapolation is not performed'):
                interpolate_pump_head(c,q)
        with self.assertRaisesRegex(ValueError,'nonnegative'):
            interpolate_pump_head(curve(),-10)

    def test_invalid_target(self):
        for value in (None,'','bad',True,math.nan,math.inf,-math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                interpolate_pump_head(curve(),value)

    def test_unsorted(self):
        original = list(UNSORTED)
        c = curve(UNSORTED)
        self.assertEqual(c.points,curve().points)
        self.assertEqual(UNSORTED,original)
        self.assertAlmostEqual(interpolate_pump_head(c,125).head_m,41,places=12)

    def test_duplicate_flow(self):
        for points in [[(0,50),(100,44),(100,43)],[(0,50),(100,44),(100,44)]]:
            with self.subTest(points=points), self.assertRaisesRegex(ValueError,'Each pump-curve flow value must be unique'):
                curve(points)

    def test_minimum_points(self):
        for points in [[],[(0,50)],[(0,50),(50,48)]]:
            with self.subTest(points=points), self.assertRaisesRegex(ValueError,'at least 3 valid unique'):
                curve(points)

    def test_negative_and_invalid_coordinates(self):
        for bad in (None,'','bad',True,-1,math.nan,math.inf,-math.inf):
            for points in [[(bad,50),(50,48),(100,44)],[(0,bad),(50,48),(100,44)]]:
                with self.subTest(bad=bad,points=points), self.assertRaises(ValueError):
                    curve(points)

    def test_incomplete_pair(self):
        for pair in [(1,), (1,2,3), None, 'bad']:
            with self.subTest(pair=pair), self.assertRaisesRegex(ValueError,'both flow and head'):
                curve([pair,(50,48),(100,44)])

    def test_flat_and_rising_allowed(self):
        self.assertFalse(curve([(0,50),(50,50),(100,44)]).has_rising_head)
        c = curve([(0,40),(50,50),(100,44)])
        self.assertTrue(c.has_rising_head)
        self.assertAlmostEqual(interpolate_pump_head(c,25).head_m,45,places=12)
        self.assertEqual(c.points[0].head_m,40)

    def test_optional_shutoff(self):
        self.assertIsNone(curve(BENCHMARK[1:]).shutoff_head_m)
        self.assertEqual(curve().shutoff_head_m,50)

    def test_flow_equivalence(self):
        self.assertAlmostEqual(curve().points[2].flow_m3_s,.0277777777777778,places=15)
        for unit,factor in FLOW.items():
            converted = [(q*FLOW['m³/hr']/factor,h) for q,h in BENCHMARK]
            c = curve(converted,unit)
            self.assertAlmostEqual(interpolate_pump_head(c,125*FLOW['m³/hr']/factor).head_m,41,places=12)
            for actual,expected in zip(c.points,curve().points):
                self.assertAlmostEqual(actual.flow_m3_s,expected.flow_m3_s,places=15)

    def test_head_equivalence(self):
        self.assertAlmostEqual(50/HEAD_FACTORS['ft'],164.041994750656,places=10)
        c = curve([(q,h/HEAD_FACTORS['ft']) for q,h in BENCHMARK],head_unit='ft')
        for actual,expected in zip(c.points,curve().points):
            self.assertAlmostEqual(actual.head_m,expected.head_m,places=12)
        self.assertAlmostEqual(interpolate_pump_head(c,125).head_m,41,places=12)

    def test_missing_units_and_bad_factor(self):
        for unit in (None,'','bad'):
            with self.assertRaises(ValueError):curve(unit=unit)
            with self.assertRaises(ValueError):curve(head_unit=unit)
        for factor in (0,-1,True,math.nan,math.inf):
            with self.subTest(factor=factor), self.assertRaises(ValueError):
                curve(factors={'m³/hr':factor})

    def test_numeric_range(self):
        with self.assertRaises(ValueError):curve([(0,50),(1e308,40),(2,30)],unit='m³/s',factors={'m³/s':1000})
        with self.assertRaises(ValueError):curve([(0,5e-324),(1,40),(2,30)],head_unit='ft')
        with self.assertRaises(ValueError):curve([(5e-324,50),(1,40),(2,30)],unit='L/min')

    def test_ten_and_twenty_points(self):
        for count in (10,20):
            c = curve([(q,50-q) for q in range(count)])
            self.assertEqual(len(c.points),count)
            self.assertAlmostEqual(interpolate_pump_head(c,5.5).head_m,44.5,places=12)

    def test_chart_spec(self):
        s = curve_plot_spec('m³/hr','ft')
        self.assertEqual(s['title'],'Pump Q–H Curve')
        self.assertEqual(s['layer'][0]['mark']['type'],'line')
        self.assertTrue(s['layer'][0]['mark']['point']['filled'])
        self.assertEqual(s['encoding']['x']['title'],'Flow Rate (m³/hr)')
        self.assertEqual(s['encoding']['y']['title'],'Pump Head (ft)')
        self.assertNotIn('transform',s)


class PumpCurveAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self,at,points=BENCHMARK,flow_unit='m³/hr',head_unit='m'):
        at.number_input(key='p3e_count').set_value(len(points)).run()
        at.selectbox(key='p3e_flow_unit').select(flow_unit)
        at.selectbox(key='p3e_head_unit').select(head_unit)
        for index,(q,h) in enumerate(points):
            at.number_input(key=f'p3e_q_{index}').set_value(q)
            at.number_input(key=f'p3e_h_{index}').set_value(h)
        return at.button(key='p3e_plot').click().run()

    def interpolate(self,at,q):
        at.number_input(key='p3e_target').set_value(q)
        return at.button(key='p3e_interpolate').click().run()

    def result(self,at):
        return '\n'.join(w.value for w in at.text if 'Requested Flow:' in w.value)

    def charts(self,at):
        return at.get('vega_lite_chart')

    def test_empty_render_no_fictional_defaults(self):
        at = self.app()
        self.assertFalse(at.exception)
        self.assertTrue(any(w.label=='3E — Pump Curve' for w in at.expander))
        self.assertEqual(len(at.tabs),15)
        self.assertIsNone(at.selectbox(key='p3e_flow_unit').value)
        self.assertIsNone(at.selectbox(key='p3e_head_unit').value)
        self.assertEqual(at.number_input(key='p3e_count').value,3)
        self.assertIsNone(at.number_input(key='p3e_q_0').value)
        self.assertIsNone(at.number_input(key='p3e_h_0').value)
        self.assertFalse(self.charts(at))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3e_')])
        self.assertTrue(any('does not generate or assume pump performance data' in w.value for w in at.info))
        at.button(key='p3e_plot').click().run()
        self.assertTrue(at.error)

    def test_points_plot_axes_and_labels(self):
        at = self.fill(self.app())
        self.assertFalse(at.error)
        self.assertFalse(at.exception)
        self.assertEqual(len(self.charts(at)),1)
        spec=json.loads(self.charts(at)[0].proto.spec)
        self.assertEqual(spec['title'],'Pump Q–H Curve')
        values=spec['layer'][0]['data']['values']
        self.assertEqual(len(values),5)
        for point,(q,h) in zip(values,BENCHMARK):
            self.assertAlmostEqual(point['flow'],q,places=12)
            self.assertEqual(point['head'],h)
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/hr)')
        self.assertEqual(spec['encoding']['y']['title'],'Pump Head (m)')
        self.assertEqual(at.number_input(key='p3e_q_0').label,'Point 1 — Flow (m³/hr)')
        self.assertEqual(at.number_input(key='p3e_h_0').label,'Point 1 — Head (m)')
        self.assertEqual(at.number_input(key='p3e_target').label,'Flow for Interpolation (m³/hr)')
        self.assertTrue(any('Shutoff / zero-flow head: 50 m' in w.value for w in at.text))
        self.assertTrue(any('| 0 | 50 |\n| 50 | 48 |\n| 100 | 44 |\n| 150 | 38 |\n| 200 | 30 |' in w.value for w in at.markdown))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox] for w in group]
        self.assertEqual(len(keys),len(set(keys)))

    def test_interpolation_benchmarks(self):
        at=self.fill(self.app())
        for q,h in [(125,41),(175,34)]:
            self.interpolate(at,q)
            self.assertIn(f'Interpolated Pump Head: {h} m',self.result(at))
            self.assertIn('Bounding Data Points:',self.result(at))
            self.assertIn(f'Requested Flow: {q} m³/hr',self.result(at))
            self.assertFalse(at.error)
        self.interpolate(at,125)
        self.assertIn('100 m³/hr → 44 m\n150 m³/hr → 38 m',self.result(at))

    def test_exact_point(self):
        at=self.fill(self.app())
        self.interpolate(at,100)
        self.assertIn('Exact Supplied Point: 100 m³/hr → 44 m',self.result(at))
        self.assertIn('Pump Head (exact supplied point): 44 m',self.result(at))
        self.assertFalse(at.exception)

    def test_out_of_range_and_stale_result(self):
        at=self.fill(self.app())
        self.interpolate(at,125)
        at.number_input(key='p3e_target').set_value(175).run()
        self.assertFalse(self.result(at))
        self.assertEqual(len(self.charts(at)),1)
        self.interpolate(at,250)
        self.assertEqual(at.error[0].value,OUT_OF_RANGE)
        self.assertFalse(self.result(at))
        self.assertEqual(len(self.charts(at)),1)
        self.assertFalse(at.exception)

    def test_unsorted_input(self):
        at=self.fill(self.app(),UNSORTED)
        self.assertTrue(any('| 0 | 50 |\n| 50 | 48 |\n| 100 | 44 |\n| 150 | 38 |\n| 200 | 30 |' in w.value for w in at.markdown))
        self.interpolate(at,125)
        self.assertIn('Interpolated Pump Head: 41 m',self.result(at))
        self.assertFalse(at.exception)

    def test_duplicate_rejected_plot_removed(self):
        at=self.fill(self.app())
        self.interpolate(at,125)
        at.number_input(key='p3e_q_2').set_value(50)
        at.button(key='p3e_plot').click().run()
        self.assertEqual(at.error[0].value,'Each pump-curve flow value must be unique.')
        self.assertFalse(self.charts(at))
        self.assertFalse(self.result(at))
        at.button(key='p3e_interpolate').click().run()
        self.assertTrue(at.error)
        self.assertFalse(at.exception)

    def test_incomplete_points(self):
        at=self.fill(self.app())
        at.number_input(key='p3e_h_2').set_value(None)
        at.button(key='p3e_plot').click().run()
        self.assertIn('Point 3:',at.error[0].value)
        self.assertFalse(self.charts(at))
        self.assertFalse(at.exception)

    def test_nonmonotonic_warning_only(self):
        at=self.fill(self.app(),[(0,40),(50,50),(100,44)])
        self.assertTrue(any(w.value==RISING_HEAD_WARNING for w in at.warning))
        self.assertFalse(at.error)
        self.assertEqual(len(self.charts(at)),1)
        self.interpolate(at,25)
        self.assertIn('Interpolated Pump Head: 45 m',self.result(at))

    def test_units_equivalence_and_no_assumed_shutoff(self):
        points=[(q*FLOW['m³/hr'],h/HEAD_FACTORS['ft']) for q,h in BENCHMARK[1:]]
        at=self.fill(self.app(),points,'m³/s','ft')
        self.assertFalse(any('Shutoff / zero-flow head:' in w.value for w in at.text))
        self.interpolate(at,125*FLOW['m³/hr'])
        self.assertIn(f'Interpolated Pump Head: {41/HEAD_FACTORS["ft"]:.12g} ft',self.result(at))
        spec=json.loads(self.charts(at)[0].proto.spec)
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/s)')
        self.assertEqual(spec['encoding']['y']['title'],'Pump Head (ft)')
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_twenty_rows_supported(self):
        at=self.fill(self.app(),[(q,50-q) for q in range(20)])
        self.assertIsNotNone(at.number_input(key='p3e_q_19'))
        self.assertEqual(len(self.charts(at)),1)
        self.assertFalse(at.error)
        self.assertFalse(at.exception)
