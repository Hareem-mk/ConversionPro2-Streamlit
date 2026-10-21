"""Phase 3I speed benchmarks, validation, conversions and Streamlit integration."""
import math
import sys
from pathlib import Path
import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch

from app import FLOW
from pump_performance.affinity_laws import calculate_speed_affinity
from pump_performance.pump_curve import curve_flow_to_si, HEAD_FACTORS
from pump_performance.system_curve import head_to_metres
from pump_performance.shaft_power import POWER_FACTORS
from pump_performance.hydraulic_power import MECHANICAL_HP_W


class AffinityTests(unittest.TestCase):
    def benchmark(self):return calculate_speed_affinity(100/3600,40,10000,1450,1750)

    def test_increase_benchmark(self):
        r=self.benchmark()
        self.assertAlmostEqual(r.ratio,1.206896551724138,places=14)
        self.assertAlmostEqual(r.estimated_flow_m3_s*3600,120.6896551724138,places=11)
        self.assertAlmostEqual(r.estimated_head_m,58.26397146254459,places=11)
        self.assertAlmostEqual(r.estimated_power_w/1000,17.57964656197466,places=11)

    def test_increase_percent_changes(self):
        r=self.benchmark()
        self.assertAlmostEqual(r.flow_change_percent,20.689655172413794,places=11)
        self.assertAlmostEqual(r.head_change_percent,45.65992865636147,places=11)
        self.assertAlmostEqual(r.power_change_percent,75.7964656197466,places=11)

    def test_speed_reduction(self):
        r=calculate_speed_affinity(100/3600,40,10000,1500,1200)
        self.assertEqual(r.ratio,.8)
        for value,expected in [(r.estimated_flow_m3_s*3600,80),(r.estimated_head_m,25.6),
                               (r.estimated_power_w/1000,5.12),(r.flow_change_percent,-20),
                               (r.head_change_percent,-36),(r.power_change_percent,-48.8)]:
            self.assertAlmostEqual(value,expected,places=11)

    def test_identity_exact(self):
        r=calculate_speed_affinity(.03,40,10000,1450,1450)
        self.assertEqual((r.ratio,r.estimated_flow_m3_s,r.estimated_head_m,r.estimated_power_w),(1,.03,40,10000))
        self.assertEqual((r.flow_change_percent,r.head_change_percent,r.power_change_percent),(0,0,0))

    def test_zero_originals(self):
        r=calculate_speed_affinity(0,0,0,1450,1750)
        self.assertEqual((r.estimated_flow_m3_s,r.estimated_head_m,r.estimated_power_w),(0,0,0))
        self.assertEqual((r.flow_change_percent,r.head_change_percent,r.power_change_percent),(None,None,None))

    def test_individually_zero_originals(self):
        for index in range(3):
            inputs=[1,40,10000];inputs[index]=0
            r=calculate_speed_affinity(*inputs,1450,1750)
            percentages=(r.flow_change_percent,r.head_change_percent,r.power_change_percent)
            self.assertIsNone(percentages[index])
            self.assertTrue(all(v is not None for i,v in enumerate(percentages) if i!=index))

    def test_zero_original_speed(self):
        with self.assertRaisesRegex(ValueError,'Original Rotational Speed.*greater than zero'):
            calculate_speed_affinity(1,1,1,0,1750)

    def test_zero_new_speed(self):
        with self.assertRaisesRegex(ValueError,'New Rotational Speed.*greater than zero'):
            calculate_speed_affinity(1,1,1,1450,0)

    def test_negative_speeds(self):
        for speeds in [(-1,1750),(1450,-1)]:
            with self.subTest(speeds=speeds),self.assertRaises(ValueError):
                calculate_speed_affinity(1,1,1,*speeds)

    def test_negative_performance(self):
        for index in range(3):
            values=[1,1,1,1450,1750];values[index]=-1
            with self.subTest(index=index),self.assertRaises(ValueError):calculate_speed_affinity(*values)

    def test_all_inputs_reject_nonfinite_missing_boolean(self):
        for index in range(5):
            for invalid in [None,True,'bad',math.nan,math.inf,-math.inf]:
                values=[1,40,10000,1450,1750];values[index]=invalid
                with self.subTest(index=index,value=invalid),self.assertRaises(ValueError):
                    calculate_speed_affinity(*values)

    def test_ratio_overflow_underflow(self):
        for n1,n2 in [(1e-308,1e308),(1e308,1e-308)]:
            with self.assertRaisesRegex(ValueError,'Speed Ratio.*numeric range'):
                calculate_speed_affinity(1,1,1,n1,n2)

    def test_output_overflow(self):
        with self.assertRaisesRegex(ValueError,'numeric range'):
            calculate_speed_affinity(1,1e308,1,1,2)

    def test_output_underflow(self):
        with self.assertRaisesRegex(ValueError,'numeric range'):
            calculate_speed_affinity(1,1,1e-320,1,1e-10)

    def test_zero_with_large_ratio(self):
        r=calculate_speed_affinity(0,0,0,1,1e200)
        self.assertEqual(r.estimated_power_w,0)
        self.assertIsNone(r.power_change_percent)

    def test_si_units_all_flow_and_head_power_units(self):
        expected=self.benchmark()
        for unit,factor in FLOW.items():
            q=curve_flow_to_si((100/3600)/factor,unit,FLOW)
            for head_unit,hfactor in HEAD_FACTORS.items():
                for power_unit,pfactor in POWER_FACTORS.items():
                    with self.subTest(unit=unit,head=head_unit,power=power_unit):
                        r=calculate_speed_affinity(q,head_to_metres(40/hfactor,head_unit,'Original Head'),
                                                   (10000/pfactor)*pfactor,1450,1750)
                        self.assertAlmostEqual(r.estimated_flow_m3_s,expected.estimated_flow_m3_s,places=14)
                        self.assertAlmostEqual(r.estimated_head_m,expected.estimated_head_m,places=11)
                        self.assertAlmostEqual(r.estimated_power_w,expected.estimated_power_w,places=9)

    def test_mechanical_hp_single_constant(self):
        self.assertEqual(POWER_FACTORS['Mechanical hp'],745.6998715822702)
        self.assertIs(POWER_FACTORS['Mechanical hp'],MECHANICAL_HP_W)
        self.assertAlmostEqual(self.benchmark().estimated_power_w/MECHANICAL_HP_W,23.574694366881307,places=10)

    def test_immutable_result_preserves_originals(self):
        r=self.benchmark()
        self.assertEqual((r.original_flow_m3_s,r.original_head_m,r.original_power_w),(100/3600,40,10000))
        with self.assertRaises(FrozenInstanceError):r.ratio=2


class AffinityAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def calculate(self,at,q=100,h=40,p=10,n1=1450,n2=1750,flow_unit='m³/hr',head_unit='m',power_unit='kW'):
        for key,unit in [('p3i_flow_unit',flow_unit),('p3i_head_unit',head_unit),('p3i_power_unit',power_unit)]:
            at.selectbox(key=key).select(unit)
        for key,value in [('p3i_flow',q),('p3i_head',h),('p3i_power',p),('p3i_n1',n1),('p3i_n2',n2)]:
            at.number_input(key=key).set_value(value)
        return at.button(key='p3i_calculate').click().run()

    def text(self,at):return '\n'.join(w.value for w in at.text if 'Affinity-Law Estimated' in w.value)

    def test_render_units_blank_no_checkboxes(self):
        at=self.app()
        self.assertTrue(any(w.label=='3I — Pump Affinity Laws' for w in at.expander))
        self.assertEqual(at.selectbox(key='p3i_method').value,'Speed Change')
        for key in ['p3i_flow_unit','p3i_head_unit','p3i_power_unit']:
            self.assertIsNone(at.selectbox(key=key).value)
        for key in ['p3i_flow','p3i_head','p3i_power','p3i_n1','p3i_n2']:
            self.assertIsNone(at.number_input(key=key).value)
        self.assertIn('(rpm)',at.number_input(key='p3i_n1').label)
        self.assertIn('(rpm)',at.number_input(key='p3i_n2').label)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3i_')])
        self.assertEqual(len(at.tabs),15);self.assertFalse(at.exception)

    def test_benchmark_shared_core(self):
        from pump_performance import affinity_laws_ui as ui
        with patch.object(ui,'calculate_speed_affinity',wraps=calculate_speed_affinity) as core:
            at=self.calculate(self.app())
        self.assertTrue(core.called)
        self.assertFalse(at.error);self.assertFalse(at.exception)
        for value in ['Speed Ratio: 1.2069','Affinity-Law Estimated Flow: 120.69 m³/hr',
                      'Affinity-Law Estimated Head: 58.264 m','Affinity-Law Estimated Shaft Power: 17.5796 kW',
                      'Flow Change: +20.6897%','Head Change: +45.6599%','Power Change: +75.7965%']:
            self.assertIn(value,self.text(at))
        self.assertIn('Original Speed: 1450 rpm',self.text(at))
        self.assertIn('New Speed: 1750 rpm',self.text(at))

    def test_reduction(self):
        at=self.calculate(self.app(),n1=1500,n2=1200)
        for value in ['Speed Ratio: 0.8','Estimated Flow: 80 m³/hr','Estimated Head: 25.6 m',
                      'Estimated Shaft Power: 5.12 kW','Flow Change: -20%','Head Change: -36%',
                      'Power Change: -48.8%']:self.assertIn(value,self.text(at))

    def test_identity(self):
        at=self.calculate(self.app(),n2=1450)
        self.assertIn('Speed Ratio: 1',self.text(at))
        self.assertIn('Estimated Flow: 100 m³/hr',self.text(at))
        self.assertIn('Estimated Head: 40 m',self.text(at))
        self.assertIn('Estimated Shaft Power: 10 kW',self.text(at))
        self.assertEqual(self.text(at).count('Change: +0%'),3)

    def test_zero_originals_na(self):
        at=self.calculate(self.app(),q=0,h=0,p=0)
        self.assertFalse(at.error);self.assertFalse(at.exception)
        self.assertEqual(self.text(at).count('N/A — original value is zero'),3)
        for value in ['Estimated Flow: 0 m³/hr','Estimated Head: 0 m','Estimated Shaft Power: 0 kW']:
            self.assertIn(value,self.text(at))

    def test_mixed_zero_original(self):
        at=self.calculate(self.app(),q=0)
        self.assertIn('Flow Change: N/A — original value is zero',self.text(at))
        self.assertIn('Head Change: +45.6599%',self.text(at))

    def test_zero_original_speed(self):
        at=self.calculate(self.app(),n1=0)
        self.assertTrue(any('Original Rotational Speed' in w.value for w in at.error))
        self.assertFalse(self.text(at));self.assertFalse(at.exception)

    def test_zero_new_speed(self):
        at=self.calculate(self.app(),n2=0)
        self.assertTrue(any('New Rotational Speed' in w.value for w in at.error))
        self.assertFalse(self.text(at));self.assertFalse(at.exception)

    def test_negative_speeds(self):
        at=self.app()
        for n1,n2 in [(-1,1750),(1450,-1)]:
            at=self.calculate(at,n1=n1,n2=n2)
            self.assertTrue(at.error);self.assertFalse(self.text(at));self.assertFalse(at.exception)

    def test_negative_performance_inputs(self):
        at=self.app()
        for values in [dict(q=-1),dict(h=-1),dict(p=-1)]:
            at=self.calculate(at,**values)
            self.assertTrue(at.error);self.assertFalse(self.text(at));self.assertFalse(at.exception)

    def test_units_equivalent_si_feet_mechanical_hp(self):
        at=self.calculate(self.app(),q=100/3600,h=40/HEAD_FACTORS['ft'],p=10000/MECHANICAL_HP_W,
                          flow_unit='m³/s',head_unit='ft',power_unit='Mechanical hp')
        self.assertFalse(at.error)
        self.assertIn('Estimated Flow: 0.0335249 m³/s',self.text(at))
        self.assertIn(f'Estimated Head: {58.26397146254459/HEAD_FACTORS["ft"]:.6g} ft',self.text(at))
        self.assertIn(f'Estimated Shaft Power: {17579.64656197466/MECHANICAL_HP_W:.6g} Mechanical hp',self.text(at))
        self.assertIn('Power Change: +75.7965%',self.text(at))

    def test_missing_units_and_values(self):
        at=self.app().button(key='p3i_calculate').click().run()
        self.assertTrue(at.error);self.assertFalse(at.exception)
        at=self.calculate(at)
        at.selectbox(key='p3i_power_unit').set_value(None)
        at.button(key='p3i_calculate').click().run()
        self.assertTrue(any('supported shaft power unit' in w.value for w in at.error))
        self.assertFalse(self.text(at))

    def test_static_guidance_and_terminology(self):
        at=self.calculate(self.app())
        captions='\n'.join(w.value for w in at.caption)
        self.assertIn('same impeller diameter',captions)
        self.assertIn('Actual shaft power may differ if pump efficiency changes',captions)
        self.assertIn('Sufficiently similar pump efficiency is assumed',captions)
        self.assertIn('not automatically acceptable',captions)
        self.assertIn('manufacturer limits',captions)
        self.assertTrue(any('connected system curve' in w.value for w in at.info))
        self.assertNotIn('Actual Operating Flow',self.text(at))
        for key in ['p3i_n1','p3i_n2']:
            self.assertEqual(at.number_input(key=key).proto.max,sys.float_info.max)

    def test_input_change_clears_stale_result(self):
        at=self.calculate(self.app())
        at.number_input(key='p3i_n2').set_value(1200).run()
        self.assertFalse(self.text(at))

if __name__=='__main__':unittest.main()
