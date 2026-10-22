"""Phase 3K benchmarks, shared comparisons, criteria and Streamlit workflows."""
import math
from pathlib import Path
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from app import FLOW
from pump_performance.duty_point_check import (calculate_duty_deviation,calculate_driver_margin,
                                               compare_tolerance,check_duty_point)
from pump_performance.bep_operating_range import compare_bep
from pump_performance.npsh_margin import calculate_npsh_margin
from pump_performance.operating_point import find_operating_points
from pump_performance.hydraulic_power import MECHANICAL_HP_W
from pump_performance.pump_curve import HEAD_FACTORS

Q=124.59624833740307
H=41.04845019951163
POINTS=[(0,50),(50,48),(100,44),(150,38),(200,30)]


def screening(**changes):
    inputs=dict(required_flow_si=125/3600,operating_flow_si=Q/3600,required_head_m=41,
        operating_head_m=H,shaft_power_w=12000,bep_flow_si=150/3600,
        npsha_m=12.026359664105,npshr_m=8,driver_rating_w=15000)
    inputs.update(changes)
    return check_duty_point(**inputs)


class DutyCheckTests(unittest.TestCase):
    def test_mandatory_duty_benchmark(self):
        r=screening().duty
        self.assertAlmostEqual(r.flow_difference_m3_s*3600,-.40375166259693,places=11)
        self.assertAlmostEqual(r.flow_deviation_percent,-.3230013300775,places=11)
        self.assertAlmostEqual(r.head_difference_m,.04845019951163,places=12)
        self.assertAlmostEqual(r.head_deviation_percent,.118171218321,places=11)

    def test_shared_bep_npsh_benchmark(self):
        from pump_performance import duty_point_check as core
        with patch.object(core,'compare_bep',wraps=compare_bep) as bep,patch.object(core,'calculate_npsh_margin',wraps=calculate_npsh_margin) as npsh:
            r=screening()
        self.assertTrue(bep.called);self.assertTrue(npsh.called)
        self.assertAlmostEqual(r.bep.percent_bep,83.06416555826873,places=11)
        self.assertEqual(r.npsh.margin_m,4.026359664105)
        self.assertEqual(r.npsh.ratio,1.503294958013125)
        self.assertEqual(r.npsh.percent_margin,50.3294958013125)

    def test_exact_duty(self):
        r=calculate_duty_deviation(100/3600,100/3600,40,40)
        self.assertEqual((r.flow_difference_m3_s,r.flow_deviation_percent,r.head_difference_m,r.head_deviation_percent),(0,0,0,0))
        self.assertTrue(r.flow_matches and r.head_matches)

    def test_below_duty(self):
        r=calculate_duty_deviation(100/3600,90/3600,40,38)
        for a,b in [(r.flow_difference_m3_s*3600,-10),(r.flow_deviation_percent,-10),(r.head_difference_m,-2),(r.head_deviation_percent,-5)]:
            self.assertAlmostEqual(a,b,places=12)

    def test_above_duty(self):
        r=calculate_duty_deviation(100/3600,110/3600,40,42)
        for a,b in [(r.flow_difference_m3_s*3600,10),(r.flow_deviation_percent,10),(r.head_difference_m,2),(r.head_deviation_percent,5)]:
            self.assertAlmostEqual(a,b,places=12)

    def test_zero_operating(self):
        r=calculate_duty_deviation(1,0,40,0)
        self.assertEqual((r.flow_deviation_percent,r.head_deviation_percent),(-100,-100))

    def test_tiny_required_duty_not_erased_by_absolute_tolerance(self):
        r=calculate_duty_deviation(1e-100,0,1e-100,0)
        self.assertFalse(r.flow_matches or r.head_matches)
        self.assertEqual((r.flow_deviation_percent,r.head_deviation_percent),(-100,-100))

    def test_duty_roundoff_retains_raw_precision(self):
        r=calculate_duty_deviation(.03,.03+1e-16,40,40+1e-10)
        self.assertTrue(r.flow_matches and r.head_matches)
        self.assertNotEqual(r.flow_difference_m3_s,0);self.assertNotEqual(r.head_difference_m,0)

    def test_no_default_criteria(self):
        r=screening()
        for value in [r.flow_tolerance_status,r.head_tolerance_status,r.bep_range_status,r.required_npsh_margin,r.driver_criterion_status]:
            self.assertIsNone(value)

    def test_duty_tolerance_test_only(self):
        self.assertEqual(compare_tolerance(-3,5),'Meets entered duty tolerance')
        self.assertEqual(compare_tolerance(4,5),'Meets entered duty tolerance')
        self.assertEqual(compare_tolerance(-6,5),'Outside entered duty tolerance')
        self.assertEqual(compare_tolerance(-5,5),'Meets entered duty tolerance')

    def test_tolerance_zero_numerical_boundary(self):
        self.assertEqual(compare_tolerance(1e-12,0),'Meets entered duty tolerance')
        self.assertEqual(compare_tolerance(1e-7,0),'Outside entered duty tolerance')

    def test_driver_power_cases(self):
        for shaft,margin,percent in [(12000,3000,25),(15000,0,0),(16000,-1000,-6.25)]:
            r=calculate_driver_margin(shaft,15000)
            self.assertEqual((r.margin_w,r.margin_percent),(margin,percent))
        self.assertEqual(r.relationship_status,'Entered driver rating is below calculated shaft power.')

    def test_zero_shaft_power(self):
        r=calculate_driver_margin(0,15000)
        self.assertEqual(r.margin_w,15000);self.assertIsNone(r.margin_percent)
        self.assertIn('Requires vendor/project review',screening(shaft_power_w=0,required_driver_margin_percent=10).driver_criterion_status)

    def test_driver_criterion_inclusive(self):
        self.assertEqual(screening(required_driver_margin_percent=25).driver_criterion_status,'Meets entered driver power margin')
        self.assertEqual(screening(required_driver_margin_percent=26).driver_criterion_status,'Does not meet entered driver power margin')

    def test_bep_range_shared_logic(self):
        self.assertEqual(screening(bep_min_percent=80,bep_max_percent=110).bep_range_status,'Within entered operating range')
        self.assertEqual(screening(bep_min_percent=90,bep_max_percent=110).bep_range_status,'Below entered operating range')
        self.assertEqual(screening(bep_min_percent=50,bep_max_percent=80).bep_range_status,'Above entered operating range')

    def test_npsh_required_margin_shared_logic(self):
        self.assertEqual(screening(required_npsh_margin_m=4).required_npsh_margin.criterion_status,'Meets entered required margin')
        self.assertEqual(screening(required_npsh_margin_m=5).required_npsh_margin.criterion_status,'Does not meet entered required margin')

    def test_optional_data_omission(self):
        r=screening(bep_flow_si=None,npsha_m=None,npshr_m=None,driver_rating_w=None)
        self.assertIsNone(r.bep);self.assertIsNone(r.npsh);self.assertIsNone(r.driver)

    def test_missing_data_for_criteria(self):
        for changes in [dict(bep_flow_si=None,bep_min_percent=80,bep_max_percent=110),
                        dict(npsha_m=None,npshr_m=None,required_npsh_margin_m=2),
                        dict(driver_rating_w=None,required_driver_margin_percent=10),dict(npsha_m=None),dict(npshr_m=None)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):screening(**changes)

    def test_required_and_operating_validation(self):
        for index,values in enumerate([(0,1,40,40),(1,1,0,40),(-1,1,40,40),(1,-1,40,40),(1,1,40,-1)]):
            with self.subTest(index=index),self.assertRaises(ValueError):calculate_duty_deviation(*values)

    def test_vendor_driver_and_criteria_validation(self):
        for changes in [dict(bep_flow_si=0),dict(npshr_m=0),dict(npsha_m=-1),dict(shaft_power_w=-1),
                        dict(driver_rating_w=0),dict(driver_rating_w=-1),dict(flow_tolerance_percent=-1),
                        dict(head_tolerance_percent=-1),dict(bep_min_percent=110,bep_max_percent=80),
                        dict(bep_min_percent=80),dict(required_npsh_margin_m=-1),dict(required_driver_margin_percent=-1)]:
            with self.subTest(changes=changes),self.assertRaises(ValueError):screening(**changes)

    def test_nonfinite_values(self):
        for key in ['required_flow_si','operating_flow_si','required_head_m','operating_head_m','shaft_power_w',
                    'bep_flow_si','npsha_m','npshr_m','driver_rating_w','flow_tolerance_percent','head_tolerance_percent',
                    'required_driver_margin_percent','required_npsh_margin_m']:
            for invalid in [math.nan,math.inf,True]:
                with self.subTest(key=key,invalid=invalid),self.assertRaises(ValueError):screening(**{key:invalid})

    def test_numeric_range(self):
        with self.assertRaises(ValueError):calculate_duty_deviation(1e-308,1e308,40,40)
        with self.assertRaises(ValueError):calculate_driver_margin(1e-308,1e308)

    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):screening().duty.required_head_m=0
        with self.assertRaises(FrozenInstanceError):calculate_driver_margin(12000,15000).margin_w=0


class DutyCheckAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self,at,rq=125,oq=Q,rh=41,oh=H,shaft=12,rating=15,optional=True,
             rq_unit='m³/hr',oq_unit='m³/hr',rh_unit='m',oh_unit='m',p_unit='kW',d_unit='kW'):
        for key,value in [('p3k_rq_unit',rq_unit),('p3k_rh_unit',rh_unit),('p3k_oq_unit',oq_unit),('p3k_oh_unit',oh_unit),
                          ('p3k_power_unit',p_unit),('p3k_driver_unit',d_unit)]:at.selectbox(key=key).select(value)
        for key,value in [('p3k_rq',rq),('p3k_rh',rh),('p3k_shaft',shaft),('p3k_rating',rating)]:
            at.number_input(key=key).set_value(value)
        if at.selectbox(key='p3k_method_main').value=='Manual Check':
            at.number_input(key='p3k_oq').set_value(oq);at.number_input(key='p3k_oh').set_value(oh)
        if optional:
            for key,value in [('p3k_bep_unit','m³/hr'),('p3k_a_unit','m'),('p3k_n_unit','m')]:at.selectbox(key=key).select(value)
            for key,value in [('p3k_bep',150),('p3k_available',12.026359664105),('p3k_required',8)]:at.number_input(key=key).set_value(value)
        return at.button(key='p3k_calculate').click().run()

    def text(self,at):return '\n'.join(w.value for w in at.text if w.value.startswith('Required Flow:'))
    def summary(self,at):return '\n'.join(w.value for w in at.text if w.value.startswith('Criterion:'))

    def integrate(self,at,points=POINTS,static=10):
        at.selectbox(key='p3k_method_main').select('Integrated Phase 3G Operating Point').run()
        at.number_input(key='p3k_count').set_value(len(points)).run()
        at=self.fill(at)
        for i,(q,h) in enumerate(points):
            at.number_input(key=f'p3k_q_{i}').set_value(q);at.number_input(key=f'p3k_h_{i}').set_value(h)
        for key,value in [('p3k_static',static),('p3k_reference_flow',100),('p3k_reference_friction',20)]:
            at.number_input(key=key).set_value(value)
        return at.button(key='p3k_calculate').click().run()

    def test_render_blank_explicit_units_criteria_no_checkboxes(self):
        at=self.app()
        self.assertTrue(any(w.label=='3K — Pump Duty Point / Selection Check' for w in at.expander))
        for key in ['p3k_rq_unit','p3k_rh_unit','p3k_oq_unit','p3k_oh_unit','p3k_power_unit']:
            self.assertIsNone(at.selectbox(key=key).value)
        for key in ['p3k_flow_tol','p3k_head_tol','p3k_bep_min','p3k_bep_max','p3k_npsh_min','p3k_driver_min']:
            self.assertIsNone(at.number_input(key=key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3k_')])
        self.assertEqual(len(at.tabs),15);self.assertFalse(at.exception)

    def test_mandatory_benchmark(self):
        at=self.fill(self.app())
        self.assertFalse(at.error);self.assertFalse(at.exception)
        for text in ['Duty Flow Difference: -0.403752 m³/hr','Flow Deviation: -0.323001%',
            'Duty Head Difference: +0.0484502 m','Head Deviation: +0.118171%',
            'Percent of BEP: 83.0642%','NPSH Margin: +4.02636 m','Ratio: 1.50329',
            'Driver Power Margin: +3 kW','Driver Power Margin %: +25%']:
            self.assertIn(text,self.text(at))
        self.assertEqual(self.summary(at).count('No criterion entered'),10)

    def test_exact_duty(self):
        at=self.fill(self.app(),rq=100,oq=100,rh=40,oh=40)
        self.assertIn('Duty Flow Difference: +0 m³/hr',self.text(at))
        self.assertIn('Duty Head Difference: +0 m',self.text(at))
        self.assertIn('Flow Deviation: +0%',self.text(at));self.assertIn('Head Deviation: +0%',self.text(at))

    def test_below_duty_no_assumed_acceptance(self):
        at=self.fill(self.app(),rq=100,oq=90,rh=40,oh=38)
        self.assertIn('Flow Deviation: -10%',self.text(at));self.assertIn('Head Deviation: -5%',self.text(at))
        self.assertNotIn('Outside',self.summary(at))

    def test_above_duty(self):
        at=self.fill(self.app(),rq=100,oq=110,rh=40,oh=42)
        self.assertIn('Flow Deviation: +10%',self.text(at));self.assertIn('Head Deviation: +5%',self.text(at))

    def test_entered_flow_and_head_tolerances(self):
        at=self.fill(self.app(),rq=100,oq=97,rh=100,oh=104)
        at.number_input(key='p3k_flow_tol').set_value(5);at.number_input(key='p3k_head_tol').set_value(5)
        at.button(key='p3k_calculate').click().run()
        self.assertEqual(self.summary(at).count('Meets entered duty tolerance'),2)
        at.number_input(key='p3k_oq').set_value(94);at.button(key='p3k_calculate').click().run()
        self.assertIn('Outside entered duty tolerance',self.summary(at))

    def test_entered_bep_npsh_driver_criteria(self):
        at=self.fill(self.app())
        for key,value in [('p3k_bep_min',80),('p3k_bep_max',110),('p3k_npsh_min',2),('p3k_driver_min',10)]:
            at.number_input(key=key).set_value(value)
        at.selectbox(key='p3k_npsh_min_unit').select('m')
        at.button(key='p3k_calculate').click().run()
        for status in ['Within entered operating range','Meets entered required margin','Meets entered driver power margin']:
            self.assertIn(status,self.summary(at))

    def test_shared_3h_3j_called(self):
        from pump_performance import duty_point_check as core
        with patch.object(core,'compare_bep',wraps=compare_bep) as bep,patch.object(core,'calculate_npsh_margin',wraps=calculate_npsh_margin) as npsh:
            at=self.fill(self.app())
        self.assertTrue(bep.called and npsh.called);self.assertFalse(at.error)

    def test_driver_negative_margin_neutral(self):
        at=self.fill(self.app(),shaft=16,rating=15)
        self.assertIn('Driver Power Margin: -1 kW',self.text(at));self.assertIn('-6.25%',self.text(at))
        self.assertIn('Entered driver rating is below calculated shaft power.',self.text(at))

    def test_driver_equal_margin(self):
        at=self.fill(self.app(),shaft=15,rating=15)
        self.assertIn('Driver Power Margin: +0 kW',self.text(at));self.assertIn('Driver Power Margin %: +0%',self.text(at))

    def test_zero_shaft_na(self):
        at=self.fill(self.app(),shaft=0)
        self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('Driver Power Margin: +15 kW',self.text(at));self.assertIn('N/A — shaft power is zero',self.text(at))
        at.number_input(key='p3k_driver_min').set_value(10);at.button(key='p3k_calculate').click().run()
        self.assertIn('Requires vendor/project review',self.summary(at))

    def test_independent_unit_equivalence(self):
        f=HEAD_FACTORS['ft']
        at=self.fill(self.app(),rq=125/3600,oq=Q,rh=41/f,oh=H,shaft=12000/MECHANICAL_HP_W,rating=15000,
                     rq_unit='m³/s',oq_unit='m³/hr',rh_unit='ft',oh_unit='m',p_unit='Mechanical hp',d_unit='W')
        self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('Flow Deviation: -0.323001%',self.text(at));self.assertIn('Head Deviation: +0.118171%',self.text(at))
        self.assertIn('Driver Power Margin %: +25%',self.text(at))

    def test_omitted_optional_data_review(self):
        at=self.fill(self.app(),optional=False,rating=None)
        self.assertFalse(at.error)
        self.assertIn('Percent of BEP: N/A',self.text(at));self.assertIn('NPSH Margin: N/A',self.text(at))
        self.assertIn('Requires vendor/project review',self.summary(at))

    def test_validation_required_zero_driver_negative(self):
        at=self.app()
        for changes in [dict(rq=0),dict(rh=0),dict(oq=-1),dict(oh=-1),dict(shaft=-1),dict(rating=0)]:
            at=self.fill(at,**changes)
            self.assertTrue(at.error);self.assertFalse(self.text(at));self.assertFalse(at.exception)

    def test_criteria_validation(self):
        at=self.fill(self.app())
        at.number_input(key='p3k_bep_min').set_value(110);at.number_input(key='p3k_bep_max').set_value(80)
        at.button(key='p3k_calculate').click().run();self.assertTrue(at.error)
        at.number_input(key='p3k_bep_min').set_value(None);at.number_input(key='p3k_bep_max').set_value(None)
        at.number_input(key='p3k_flow_tol').set_value(-1);at.button(key='p3k_calculate').click().run()
        self.assertTrue(at.error)

    def test_guidance_no_overall_approval(self):
        at=self.fill(self.app())
        captions='\n'.join(w.value for w in at.caption)
        self.assertIn('NPSHR must come from manufacturer/vendor data',captions)
        self.assertIn('no universal motor margin',captions)
        self.assertTrue(any('does not replace manufacturer/vendor pump selection review' in w.value for w in at.info))
        content=self.text(at)+'\n'+self.summary(at)
        for prohibited in ['Pump approved','Pump safe','Automatically suitable','API compliant','PASS','FAIL']:
            self.assertNotIn(prohibited,content)

    def test_integrated_3g_benchmark(self):
        from pump_performance import duty_point_check_ui as ui
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as roots:
            at=self.integrate(self.app())
        self.assertTrue(roots.called);self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('Operating Flow: 124.596 m³/hr',self.text(at))
        self.assertIn('Operating Head: 41.0485 m',self.text(at))
        self.assertIn('Flow Deviation: -0.323001%',self.text(at))

    def test_integrated_unsorted_and_direct_k(self):
        at=self.integrate(self.app(),points=list(reversed(POINTS)))
        self.assertIn('Operating Flow: 124.596 m³/hr',self.text(at))
        at.selectbox(key='p3k_method').select('From System Resistance Coefficient K').run()
        at.number_input(key='p3k_k').set_value(25920);at.button(key='p3k_calculate').click().run()
        self.assertFalse(at.error);self.assertIn('Operating Flow: 124.596 m³/hr',self.text(at))

    def test_integrated_no_root(self):
        at=self.integrate(self.app(),static=60)
        self.assertTrue(any('No pump/system intersection' in w.value for w in at.info))
        self.assertFalse(self.text(at))

    def test_integrated_multiple_roots(self):
        at=self.integrate(self.app(),points=[(0,0),(50,2),(100,0),(150,2),(200,0)],static=1)
        at.number_input(key='p3k_reference_friction').set_value(0);at.button(key='p3k_calculate').click().run()
        self.assertTrue(any('Multiple pump/system intersections' in w.value for w in at.warning))
        self.assertEqual(self.text(at).count('Required Flow:'),4)

    def test_integrated_coincident(self):
        at=self.integrate(self.app(),points=[(0,10),(100,10),(200,10)],static=10)
        at.number_input(key='p3k_reference_friction').set_value(0);at.button(key='p3k_calculate').click().run()
        self.assertTrue(any('no unique operating point' in w.value for w in at.warning))
        self.assertFalse(self.text(at))

    def test_unit_requirement_and_stale_result(self):
        at=self.app().button(key='p3k_calculate').click().run()
        self.assertTrue(at.error);self.assertFalse(at.exception)
        at=self.fill(at);at.number_input(key='p3k_rq').set_value(100).run()
        self.assertFalse(self.text(at))

if __name__=='__main__':unittest.main()
