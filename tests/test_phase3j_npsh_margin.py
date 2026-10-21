"""Phase 3J supplied-NPSHR comparisons and unchanged Phase 2H integration."""
import math
from pathlib import Path
from dataclasses import FrozenInstanceError
import unittest
from unittest.mock import patch

from app import PRESSURE
from pump_performance.npsh_margin import calculate_npsh_margin, margin_from_phase2h, compare_required_margin
from pump_performance.system_curve import head_to_metres
from pump_performance.pump_curve import HEAD_FACTORS
from piping_hydraulics.npsha import source_npsha, flange_npsha

A=12.026359664105


def source(**updates):
    args=dict(pressure_pa=101325,basis='Absolute',vapor_pressure_pa=3000,density=1000,
              velocity=0,elevation=3,datum_elevation=0,suction_loss=1)
    args.update(updates)
    return source_npsha(**args)


def flange(**updates):
    args=dict(pressure_pa=150000,basis='Absolute',vapor_pressure_pa=3000,density=1000,
              velocity=2,elevation=0,datum_elevation=0)
    args.update(updates)
    return flange_npsha(**args)


class NPSHMarginTests(unittest.TestCase):
    def test_mandatory_benchmark(self):
        r=calculate_npsh_margin(A,8)
        self.assertAlmostEqual(r.margin_m,4.026359664105,places=12)
        self.assertAlmostEqual(r.ratio,1.503294958013125,places=13)
        self.assertAlmostEqual(r.percent_margin,50.3294958013125,places=11)
        self.assertEqual(r.relationship_status,'NPSHA is above entered NPSHR.')

    def test_small_positive_margin(self):
        r=calculate_npsh_margin(10,9)
        self.assertEqual(r.margin_m,1)
        self.assertAlmostEqual(r.ratio,1.1111111111111112,places=13)
        self.assertAlmostEqual(r.percent_margin,11.11111111111111,places=12)

    def test_equality(self):
        r=calculate_npsh_margin(8,8)
        self.assertEqual((r.margin_m,r.ratio,r.percent_margin),(0,1,0))
        self.assertEqual(r.relationship_status,'NPSHA equals entered NPSHR.')

    def test_negative_margin(self):
        r=calculate_npsh_margin(7,8)
        self.assertEqual((r.margin_m,r.ratio,r.percent_margin),(-1,.875,-12.5))
        self.assertEqual(r.relationship_status,'NPSHA is below entered NPSHR.')

    def test_zero_available(self):
        r=calculate_npsh_margin(0,8)
        self.assertEqual((r.margin_m,r.ratio,r.percent_margin),(-8,0,-100))

    def test_zero_required_before_division(self):
        with self.assertRaisesRegex(ValueError,'Vendor NPSHR.*greater than zero'):calculate_npsh_margin(10,0)

    def test_negative_required(self):
        with self.assertRaisesRegex(ValueError,'Vendor NPSHR'):calculate_npsh_margin(10,-8)

    def test_negative_manual_available(self):
        with self.assertRaisesRegex(ValueError,'Manual NPSHA'):calculate_npsh_margin(-1,8)

    def test_nonfinite_missing_boolean(self):
        for bad in [None,True,'bad',math.nan,math.inf,-math.inf]:
            for pair in [(bad,8),(10,bad)]:
                with self.subTest(pair=pair),self.assertRaises(ValueError):calculate_npsh_margin(*pair)

    def test_overflow_underflow(self):
        for pair in [(1e308,1e-308),(1e-308,1e308)]:
            with self.subTest(pair=pair),self.assertRaisesRegex(ValueError,'numeric range'):
                calculate_npsh_margin(*pair)

    def test_status_tolerance_retains_margin(self):
        for delta in [-5e-10,5e-10]:
            r=calculate_npsh_margin(8+delta,8)
            self.assertEqual(r.relationship_status,'NPSHA equals entered NPSHR.')
            self.assertNotEqual(r.margin_m,0)
        self.assertEqual(calculate_npsh_margin(8+2e-9,8).relationship_status,'NPSHA is above entered NPSHR.')
        self.assertEqual(calculate_npsh_margin(8-2e-9,8).relationship_status,'NPSHA is below entered NPSHR.')

    def test_relative_status_tolerance(self):
        self.assertEqual(calculate_npsh_margin(1e6+5e-5,1e6).relationship_status,'NPSHA equals entered NPSHR.')
        self.assertEqual(calculate_npsh_margin(1e6+.001,1e6).relationship_status,'NPSHA is above entered NPSHR.')

    def test_required_margin_statuses_inclusive(self):
        for actual,required,status in [(4,3,'Meets'),(3,3,'Meets'),(2,3,'Does not meet'),(-1,0,'Does not meet')]:
            r=compare_required_margin(actual,required)
            self.assertEqual(r.excess_margin_m,actual-required)
            self.assertEqual(r.criterion_status,status+' entered required margin')

    def test_criterion_does_not_use_relationship_tolerance(self):
        self.assertEqual(compare_required_margin(3-1e-12,3).criterion_status,'Does not meet entered required margin')

    def test_required_margin_validation(self):
        for bad in [-1,True,None,math.nan,math.inf]:
            with self.assertRaises(ValueError):compare_required_margin(4,bad)
        with self.assertRaises(ValueError):compare_required_margin(-1e308,1e308)

    def test_mixed_head_unit_equivalence(self):
        f=HEAD_FACTORS['ft']
        r=calculate_npsh_margin(head_to_metres(A/f,'ft','NPSHA'),head_to_metres(8,'m','NPSHR'))
        self.assertAlmostEqual(r.ratio,1.503294958013125,places=13)
        c=compare_required_margin(r.margin_m,head_to_metres(3/f,'ft','Required margin'))
        self.assertAlmostEqual(c.excess_margin_m,1.026359664105,places=11)

    def test_source_integration(self):
        a=source();r=margin_from_phase2h(a,8)
        self.assertAlmostEqual(a.total_npsha_m,A,places=11)
        self.assertAlmostEqual(r.margin_m,4.026359664105,places=11)
        self.assertAlmostEqual(r.ratio,1.503294958013125,places=12)
        self.assertAlmostEqual(r.percent_margin,50.3294958013125,places=10)

    def test_flange_integration(self):
        a=flange();r=margin_from_phase2h(a,10)
        self.assertAlmostEqual(a.total_npsha_m,15.193771573371,places=11)
        self.assertAlmostEqual(r.margin_m,5.193771573371,places=11)
        self.assertAlmostEqual(r.ratio,1.5193771573371,places=12)
        self.assertAlmostEqual(r.percent_margin,51.93771573371,places=10)

    def test_gauge_absolute_equivalence(self):
        self.assertEqual(source(),source(pressure_pa=0,basis='Gauge',atmospheric_pa=101325))
        self.assertEqual(flange(),flange(pressure_pa=48675,basis='Gauge',atmospheric_pa=101325))
        with self.assertRaises(ValueError):source(pressure_pa=0,basis='Gauge')

    def test_negative_integrated_available_preserved(self):
        a=source(elevation=-20)
        self.assertLess(a.total_npsha_m,0)
        r=margin_from_phase2h(a,8)
        self.assertEqual(r.npsha_m,a.total_npsha_m)
        self.assertLess(r.ratio,0)
        self.assertLess(r.percent_margin,-100)
        self.assertTrue(a.warnings)

    def test_phase2h_adapter_type(self):
        with self.assertRaisesRegex(ValueError,'Phase 2H'):margin_from_phase2h(-1,8)

    def test_immutable_results(self):
        with self.assertRaises(FrozenInstanceError):calculate_npsh_margin(A,8).ratio=2
        with self.assertRaises(FrozenInstanceError):compare_required_margin(4,3).excess_margin_m=0


class NPSHMarginAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def manual(self,at,a=A,r=8,unit='m',r_unit='m',criterion=None,c_unit=None):
        at.selectbox(key='p3j_unit').select(unit)
        at.selectbox(key='p3j_required_unit').select(r_unit)
        at.number_input(key='p3j_available').set_value(a)
        at.number_input(key='p3j_required').set_value(r)
        if criterion is not None:
            at.number_input(key='p3j_criterion').set_value(criterion)
        if c_unit is not None:at.selectbox(key='p3j_criterion_unit').select(c_unit)
        return at.button(key='p3j_calculate').click().run()

    def integrate(self,at,source_mode=True,gauge=False,negative=False):
        at.selectbox(key='p3j_method').select('Calculate NPSHA from Phase 2H').run()
        mode='Vessel/Source Method' if source_mode else 'Suction-Flange Method'
        at.selectbox(key='p3j_npsha_method').select(mode).run()
        prefix='p3j_source_' if source_mode else 'p3j_flange_'
        at.selectbox(key=prefix+'basis').select('Gauge' if gauge else 'Absolute').run()
        at.selectbox(key='p3j_unit').select('m')
        at.selectbox(key='p3j_required_unit').select('m')
        at.number_input(key='p3j_required').set_value(8 if source_mode else 10)
        at.selectbox(key=prefix+'unit').select('Kilopascal (kPa)')
        at.selectbox(key=prefix+'vapor_unit').select('Kilopascal (kPa)')
        at.number_input(key=prefix+'pressure').set_value((0 if source_mode else 48.675) if gauge else (101.325 if source_mode else 150))
        if gauge:
            at.number_input(key=prefix+'atmosphere').set_value(101.325)
            at.selectbox(key=prefix+'atm_unit').select('Kilopascal (kPa)')
        for key,value in [('vapor',3),('density',1000),('velocity',0 if source_mode else 2),
                          ('elevation',-20 if negative else (3 if source_mode else 0)),('datum_elevation',0)]:
            at.number_input(key=prefix+key).set_value(value)
        if source_mode:at.number_input(key=prefix+'suction_loss').set_value(1)
        at.text_input(key=prefix+'datum').set_value('Pump datum elevation zero')
        return at.button(key='p3j_calculate').click().run()

    def text(self,at):return '\n'.join(w.value for w in at.text if 'NPSH' in w.value or 'Margin Status' in w.value)

    def test_render_explicit_blank_units_and_criteria(self):
        at=self.app()
        self.assertTrue(any(w.label=='3J — NPSHR / NPSH Margin' for w in at.expander))
        self.assertEqual(at.selectbox(key='p3j_method').options,['Manual NPSHA','Calculate NPSHA from Phase 2H'])
        for key in ['p3j_unit','p3j_required_unit','p3j_criterion_unit']:
            self.assertIsNone(at.selectbox(key=key).value)
        for key in ['p3j_available','p3j_required','p3j_criterion']:
            self.assertIsNone(at.number_input(key=key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3j_')])
        self.assertEqual(len(at.tabs),15);self.assertFalse(at.exception)

    def test_mandatory_manual_benchmark(self):
        at=self.manual(self.app())
        self.assertFalse(at.error);self.assertFalse(at.exception)
        for text in ['NPSHA: 12.0264 m','Vendor NPSHR: 8 m','NPSH Margin: +4.02636 m',
                     'Ratio: 1.50329','Percent Margin relative to NPSHR: +50.3295%',
                     'NPSHA is above entered NPSHR.']:self.assertIn(text,self.text(at))
        self.assertNotIn('Required Margin Status',self.text(at))

    def test_small_positive(self):
        at=self.manual(self.app(),a=10,r=9)
        self.assertIn('NPSH Margin: +1 m',self.text(at));self.assertIn('Ratio: 1.11111',self.text(at))

    def test_equality(self):
        at=self.manual(self.app(),a=8)
        self.assertIn('NPSHA equals entered NPSHR.',self.text(at));self.assertIn('NPSH Margin: +0 m',self.text(at))

    def test_negative_margin(self):
        at=self.manual(self.app(),a=7)
        for text in ['NPSH Margin: -1 m','Ratio: 0.875','-12.5%','NPSHA is below entered NPSHR.']:
            self.assertIn(text,self.text(at))

    def test_zero_negative_required_rejected(self):
        at=self.app()
        for r in [0,-8]:
            at=self.manual(at,r=r)
            self.assertTrue(any('Vendor NPSHR' in w.value for w in at.error))
            self.assertNotIn('Relationship Status',self.text(at));self.assertFalse(at.exception)

    def test_negative_manual_rejected(self):
        at=self.manual(self.app(),a=-1)
        self.assertTrue(any('Manual NPSHA' in w.value for w in at.error))
        self.assertNotIn('Relationship Status',self.text(at))

    def test_zero_manual_available(self):
        at=self.manual(self.app(),a=0)
        self.assertIn('NPSHA: 0 m',self.text(at));self.assertIn('Ratio: 0',self.text(at))
        self.assertIn('-100%',self.text(at))

    def test_mixed_m_ft(self):
        factor=HEAD_FACTORS['ft']
        at=self.manual(self.app(),a=A/factor,r=8,unit='ft',r_unit='m',criterion=3/factor,c_unit='ft')
        self.assertFalse(at.error)
        self.assertIn('Ratio: 1.50329',self.text(at))
        self.assertIn('NPSH Margin: +13.2098 ft',self.text(at))
        self.assertIn('Meets entered required margin',self.text(at))

    def test_required_margin_inclusive_and_unmet(self):
        at=self.app()
        for criterion,status in [(1,'Meets'),(2,'Does not meet')]:
            at=self.manual(at,a=10,r=9,criterion=criterion,c_unit='m')
            self.assertIn(status+' entered required margin',self.text(at))
        self.assertIn('NPSHA is above entered NPSHR.',self.text(at))
        self.assertIn('Excess Above Required Margin: -1 m',self.text(at))

    def test_required_margin_validation_and_blank(self):
        at=self.manual(self.app(),criterion=-1,c_unit='m')
        self.assertTrue(at.error);self.assertNotIn('Relationship Status',self.text(at))
        at.number_input(key='p3j_criterion').set_value(1)
        at.selectbox(key='p3j_criterion_unit').set_value(None)
        at.button(key='p3j_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p3j_criterion').set_value(None)
        at.button(key='p3j_calculate').click().run()
        self.assertFalse(at.error);self.assertNotIn('Required Margin Status',self.text(at))

    def test_integrated_source_reuses_phase2h(self):
        from pump_performance import npsh_margin_ui as ui
        with patch.object(ui,'source_npsha',wraps=source_npsha) as kernel:
            at=self.integrate(self.app())
        self.assertTrue(kernel.called);self.assertFalse(at.error);self.assertFalse(at.exception)
        line=next(line for line in self.text(at).splitlines() if line.startswith('Phase 2H NPSHA (SI):'))
        self.assertAlmostEqual(float(line.split(': ')[1].split()[0]),A,places=11)
        self.assertIn('Ratio: 1.50329',self.text(at))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3j_')])

    def test_integrated_flange_reuses_phase2h(self):
        from pump_performance import npsh_margin_ui as ui
        with patch.object(ui,'flange_npsha',wraps=flange_npsha) as kernel:
            at=self.integrate(self.app(),source_mode=False)
        self.assertTrue(kernel.called);self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertIn('NPSH Margin: +5.19377 m',self.text(at));self.assertIn('Ratio: 1.51938',self.text(at))
        self.assertFalse([w for w in at.number_input if w.key=='p3j_flange_suction_loss'])

    def test_integrated_gauge_pressure(self):
        at=self.integrate(self.app(),gauge=True)
        self.assertFalse(at.error)
        self.assertIn('Ratio: 1.50329',self.text(at))
        self.assertTrue(any('0 Pa gauge + 101325 Pa' in w.value for w in at.text))
        at.number_input(key='p3j_source_atmosphere').set_value(None)
        at.button(key='p3j_calculate').click().run()
        self.assertTrue(at.error);self.assertNotIn('Relationship Status',self.text(at))

    def test_negative_calculated_available_retained(self):
        at=self.integrate(self.app(),negative=True)
        self.assertFalse(at.error)
        self.assertIn('NPSHA: -10.9736 m',self.text(at))
        self.assertIn('NPSHA is below entered NPSHR.',self.text(at))
        self.assertTrue(any('calculated value is retained' in w.value for w in at.warning))

    def test_vendor_and_engineering_guidance(self):
        at=self.manual(self.app())
        self.assertTrue(any('relevant operating flow, speed and impeller diameter' in w.value for w in at.info))
        captions='\n'.join(w.value for w in at.caption)
        self.assertIn('does not calculate or estimate NPSHR',captions)
        self.assertIn('NPSHR normally varies with pump flow',captions)
        self.assertIn('rather than assuming Phase 3I affinity-law scaling',captions)
        self.assertIn('Positive NPSH margin alone does not establish',captions)
        self.assertNotIn('safe',self.text(at).lower())
        self.assertNotIn('guaranteed',self.text(at).lower())
        self.assertNotIn('p3j_required_ratio',[w.key for w in at.number_input])

    def test_missing_inputs_and_unit_validation(self):
        at=self.app().button(key='p3j_calculate').click().run()
        self.assertTrue(at.error);self.assertFalse(at.exception)
        at=self.manual(at)
        at.selectbox(key='p3j_required_unit').set_value(None)
        at.button(key='p3j_calculate').click().run()
        self.assertTrue(at.error)

    def test_input_change_clears_results(self):
        at=self.manual(self.app())
        at.number_input(key='p3j_required').set_value(9).run()
        self.assertNotIn('Relationship Status',self.text(at))

if __name__=='__main__':unittest.main()
