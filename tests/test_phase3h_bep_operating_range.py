"""Phase 3H benchmarks, limits, unit equivalence and complete Streamlit flows."""
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from app import FLOW
from pump_performance.bep_operating_range import compare_bep, classify_user_range, validate_user_range
from pump_performance.pump_curve import curve_flow_to_si, create_pump_curve
from pump_performance.system_curve import model_from_reference
from pump_performance.operating_point import find_operating_points

Q = 124.59624833740307
POINTS = [(0,50),(50,48),(100,44),(150,38),(200,30)]

class BEPTests(unittest.TestCase):
    def test_benchmark(self):
        r=compare_bep(Q/3600,150/3600)
        self.assertAlmostEqual(r.percent_bep,83.06416555826871,places=11)
        self.assertAlmostEqual(r.deviation_m3_s*3600,-25.40375166259693,places=11)
        self.assertAlmostEqual(r.percent_deviation,-16.935834441731288,places=11)

    def test_exact_bep(self):
        r=compare_bep(150/3600,150/3600)
        self.assertEqual((r.percent_bep,r.deviation_m3_s,r.percent_deviation),(100,0,0))

    def test_eighty_percent(self):
        r=compare_bep(120/3600,150/3600)
        self.assertAlmostEqual(r.percent_bep,80)
        self.assertAlmostEqual(r.deviation_m3_s*3600,-30)
        self.assertAlmostEqual(r.percent_deviation,-20)

    def test_one_twenty_percent(self):
        r=compare_bep(180/3600,150/3600)
        self.assertAlmostEqual(r.percent_bep,120)
        self.assertAlmostEqual(r.deviation_m3_s*3600,30)
        self.assertAlmostEqual(r.percent_deviation,20)

    def test_zero_operating(self):
        r=compare_bep(0,150/3600)
        self.assertEqual((r.percent_bep,r.percent_deviation),(0,-100))
        self.assertEqual(r.deviation_m3_s,-150/3600)

    def test_zero_bep_before_division(self):
        with self.assertRaisesRegex(ValueError,'Vendor BEP Flow.*greater than zero'):
            compare_bep(1,0)

    def test_negative_flows(self):
        for a,b in [(-1,1),(1,-1)]:
            with self.subTest(a=a,b=b),self.assertRaises(ValueError):compare_bep(a,b)

    def test_nonfinite_missing_boolean(self):
        for invalid in [None,True,'bad',math.nan,math.inf,-math.inf]:
            for pair in [(invalid,1),(1,invalid)]:
                with self.subTest(pair=pair),self.assertRaises(ValueError):compare_bep(*pair)

    def test_overflow_rejected(self):
        with self.assertRaisesRegex(ValueError,'numeric range'):compare_bep(1e308,1e-308)

    def test_underflow_rejected(self):
        with self.assertRaisesRegex(ValueError,'numeric range'):compare_bep(1e-308,1e308)

    def test_all_units_and_mixed_units(self):
        for unit,factor in FLOW.items():
            with self.subTest(unit=unit):
                r=compare_bep(curve_flow_to_si(Q/3600/factor,unit,FLOW),
                              curve_flow_to_si(150,'m³/hr',FLOW))
                self.assertAlmostEqual(r.percent_bep,Q/150*100,places=11)
                self.assertAlmostEqual(r.deviation_m3_s*3600,Q-150,places=11)

    def test_range_boundaries_inclusive(self):
        for value,status in [(79,'Below'),(80,'Within'),(100,'Within'),(110,'Within'),(111,'Above')]:
            self.assertEqual(classify_user_range(value,80,110),status+' entered operating range')

    def test_range_validation(self):
        for limits in [(0,110),(-1,110),(110,80),(80,80),(None,110),(80,None),(80,math.inf)]:
            with self.subTest(limits=limits),self.assertRaises(ValueError):validate_user_range(*limits)

    def test_range_not_universally_capped(self):
        self.assertEqual(classify_user_range(250,200,300),'Within entered operating range')

    def test_phase3g_integration(self):
        c=create_pump_curve(POINTS,'m³/hr','m',FLOW)
        m=model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,
                               flow_unit='m³/hr',flow_factors=FLOW)
        roots=find_operating_points(c,m)
        self.assertEqual(len(roots.points),1)
        self.assertAlmostEqual(compare_bep(roots.points[0].flow_m3_s,150/3600).percent_bep,Q/150*100,places=11)

class BEPAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def manual(self,at,q=Q,bep=150,unit='m³/hr',bep_unit='m³/hr',limits=None):
        at.selectbox(key='p3h_flow_unit').select(unit)
        at.selectbox(key='p3h_bep_unit').select(bep_unit)
        at.number_input(key='p3h_operating').set_value(q)
        at.number_input(key='p3h_bep').set_value(bep)
        if limits:
            at.number_input(key='p3h_minimum').set_value(limits[0])
            at.number_input(key='p3h_maximum').set_value(limits[1])
        return at.button(key='p3h_calculate').click().run()

    def integrated(self,at,points=POINTS,static=10,friction=20):
        at.selectbox(key='p3h_method_main').select('From Phase 3G Operating Point').run()
        at.number_input(key='p3h_count').set_value(len(points)).run()
        at.selectbox(key='p3h_flow_unit').select('m³/hr')
        at.selectbox(key='p3h_bep_unit').select('m³/hr')
        at.selectbox(key='p3h_head_unit').select('m')
        for i,(q,h) in enumerate(points):
            at.number_input(key=f'p3h_q_{i}').set_value(q)
            at.number_input(key=f'p3h_h_{i}').set_value(h)
        at.number_input(key='p3h_static').set_value(static)
        at.number_input(key='p3h_reference_flow').set_value(100)
        at.number_input(key='p3h_reference_friction').set_value(friction)
        at.number_input(key='p3h_bep').set_value(150)
        return at.button(key='p3h_calculate').click().run()

    def text(self,at):return '\n'.join(w.value for w in at.text if 'BEP' in w.value or 'Operating Range Status' in w.value)

    def test_render_blank_units_range_no_checkboxes(self):
        at=self.app()
        self.assertTrue(any(w.label=='3H — BEP / Operating Range' for w in at.expander))
        for key in ['p3h_flow_unit','p3h_bep_unit']:
            self.assertIsNone(at.selectbox(key=key).value)
        for key in ['p3h_operating','p3h_bep','p3h_minimum','p3h_maximum']:
            self.assertIsNone(at.number_input(key=key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3h_')])
        self.assertEqual(len(at.tabs),15)
        self.assertFalse(at.exception)
        self.assertTrue(any('does not estimate or generate BEP' in w.value for w in at.caption))

    def test_manual_benchmark_and_no_assumed_range(self):
        at=self.manual(self.app())
        self.assertFalse(at.error);self.assertFalse(at.exception)
        for expected in ['Operating Flow: 124.596 m³/hr','Vendor BEP Flow: 150 m³/hr','Percent of BEP: 83.0642%',
                         'Flow Deviation from BEP: -25.4038 m³/hr','Percent Deviation from BEP: -16.9358%']:
            self.assertIn(expected,self.text(at))
        self.assertNotIn('Operating Range Status',self.text(at))

    def test_exact_bep(self):
        at=self.manual(self.app(),q=150)
        self.assertIn('Percent of BEP: 100%',self.text(at))
        self.assertIn('Flow Deviation from BEP: +0',self.text(at))

    def test_eighty_percent(self):
        at=self.manual(self.app(),q=120)
        self.assertIn('Percent of BEP: 80%',self.text(at));self.assertIn('-30 m³/hr',self.text(at))

    def test_one_twenty_percent(self):
        at=self.manual(self.app(),q=180)
        self.assertIn('Percent of BEP: 120%',self.text(at));self.assertIn('+30 m³/hr',self.text(at))

    def test_zero_operating(self):
        at=self.manual(self.app(),q=0)
        self.assertIn('Percent of BEP: 0%',self.text(at));self.assertIn('-100%',self.text(at))

    def test_zero_bep(self):
        at=self.manual(self.app(),bep=0)
        self.assertTrue(any('Vendor BEP Flow' in w.value and 'greater than zero' in w.value for w in at.error))
        self.assertNotIn('Percent of BEP:',self.text(at));self.assertFalse(at.exception)

    def test_negative_and_missing_inputs(self):
        at=self.manual(self.app(),q=-1)
        self.assertTrue(at.error)
        at=self.app().button(key='p3h_calculate').click().run()
        self.assertTrue(at.error);self.assertFalse(at.exception)

    def test_range_all_statuses(self):
        at=self.app()
        for q,status in [(100,'Below'),(Q,'Within'),(180,'Above')]:
            at=self.manual(at,q=q,limits=(80,110))
            self.assertIn(status+' entered operating range',self.text(at))

    def test_range_reversed_and_partial(self):
        at=self.manual(self.app(),limits=(110,80))
        self.assertTrue(any('greater than Minimum' in w.value for w in at.error))
        self.assertNotIn('Percent of BEP:',self.text(at))
        at.number_input(key='p3h_maximum').set_value(None)
        at.button(key='p3h_calculate').click().run()
        self.assertTrue(at.error)

    def test_mixed_units(self):
        at=self.manual(self.app(),q=Q/3600,unit='m³/s')
        self.assertIn('Percent of BEP: 83.0642%',self.text(at))
        self.assertIn('Operating Flow: 0.0346101 m³/s',self.text(at))
        self.assertIn('Vendor BEP Flow: 150 m³/hr',self.text(at))

    def test_integrated_benchmark_reuses_kernel(self):
        from pump_performance import bep_operating_range_ui as ui
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as kernel:
            at=self.integrated(self.app())
        self.assertTrue(kernel.called)
        self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('Percent of BEP: 83.0642%',self.text(at))
        self.assertIn('Operating Flow: 124.596 m³/hr',self.text(at))

    def test_integrated_k_and_unsorted(self):
        at=self.integrated(self.app(),points=list(reversed(POINTS)))
        self.assertIn('Percent of BEP: 83.0642%',self.text(at))
        at.selectbox(key='p3h_method').select('From System Resistance Coefficient K').run()
        at.number_input(key='p3h_k').set_value(25920)
        at.button(key='p3h_calculate').click().run()
        self.assertFalse(at.error);self.assertIn('Percent of BEP: 83.0642%',self.text(at))

    def test_integrated_no_root(self):
        at=self.integrated(self.app(),static=60)
        self.assertTrue(any('No pump/system intersection' in w.value for w in at.info))
        self.assertNotIn('Percent of BEP:',self.text(at))

    def test_integrated_multiple_roots(self):
        at=self.integrated(self.app(),points=[(0,0),(50,2),(100,0),(150,2),(200,0)],static=1,friction=0)
        self.assertTrue(any('Multiple pump/system intersections' in w.value for w in at.warning))
        self.assertEqual(self.text(at).count('Percent of BEP:'),4)
        self.assertIn('Intersection 4',self.text(at))

    def test_integrated_coincident(self):
        at=self.integrated(self.app(),points=[(0,10),(100,10),(200,10)],static=10,friction=0)
        self.assertTrue(any('no unique operating flow' in w.value for w in at.warning))
        self.assertNotIn('Percent of BEP:',self.text(at))

    def test_input_change_clears_result(self):
        at=self.manual(self.app())
        at.number_input(key='p3h_operating').set_value(150).run()
        self.assertNotIn('Percent of BEP:',self.text(at))

if __name__=='__main__':unittest.main()
