import math
from pathlib import Path
import unittest
from advanced_engineering import major_loss,minor_loss
from piping_hydraulics.equivalent_length import equivalent_length


class EquivalentTests(unittest.TestCase):
    def test_benchmark(self):
        r=equivalent_length(2,.1,.02)
        self.assertEqual(r.le_over_d,100)
        self.assertEqual(r.length_m,10)
        self.assertAlmostEqual(r.length_ft,32.80839895013123)

    def test_zero_k(self):
        r=equivalent_length(0,.1,.02)
        self.assertEqual((r.le_over_d,r.length_m,r.length_ft),(0,0,0))

    def test_invalid_inputs(self):
        for i in range(3):
            for bad in [None,'','bad',True,-1,math.nan,math.inf,-math.inf]+([0] if i>0 else []):
                args=[2,.1,.02];args[i]=bad
                with self.subTest(i=i,bad=bad):
                    with self.assertRaises(ValueError):equivalent_length(*args)

    def test_individual_total(self):
        one=equivalent_length(.9,.1,.02)
        other=equivalent_length(.2,.1,.02)
        total=equivalent_length(2*.9+.2,.1,.02)
        self.assertEqual(total.length_m,2*one.length_m+other.length_m)

    def test_units(self):
        r=equivalent_length(2,.1,.02)
        self.assertAlmostEqual(r.length_ft*.3048,r.length_m,places=13)

    def test_physical_equivalence(self):
        for k,d,f,v in [(2,.1,.02,2),(.9,.05,.03,1),(0,.1,.02,2),(2,.1,.02,0),(10,.2,.04,3)]:
            le=equivalent_length(k,d,f).length_m
            hk=minor_loss(k,v,1000)
            hf=major_loss(le,d,v,1000,f)
            self.assertAlmostEqual(hk.head_m,hf.head_m,places=12)
            self.assertAlmostEqual(hk.pressure_pa,hf.pressure_pa,places=8)
        self.assertAlmostEqual(major_loss(10,.1,2,1000,.02).head_m,.4078864851911713)

    def test_double_counting(self):
        with self.assertRaisesRegex(ValueError,'Double counting'):
            equivalent_length(2,.1,.02,also_counted_as_k=True)

    def test_sensitivity_and_range(self):
        self.assertEqual(equivalent_length(2,.1,.04).length_m,5)
        self.assertEqual(equivalent_length(2,.2,.02).length_m,20)
        with self.assertRaises(ValueError):equivalent_length(1e308,1,1e-308)
        with self.assertRaises(ValueError):equivalent_length(5e-324,1e-308,1)

    def test_ui(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),15)
        self.assertIsNone(at.number_input(key='p2e_k').value)
        at.button(key='p2e_calculate').click().run()
        self.assertTrue(at.error)
        at.selectbox(key='p2e_basis').select('Total K — manual entry')
        for key,v in [('p2e_k',2),('p2e_diameter',.1),('p2e_darcy',.02)]:at.number_input(key=key).set_value(v)
        at.button(key='p2e_calculate').click().run()
        self.assertTrue(at.error)
        at.checkbox(key='p2e_confirm').check()
        at.button(key='p2e_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('Equivalent length Le: 10 m' in x.value for x in at.text))
        self.assertEqual([w.key for w in at.checkbox if w.key.startswith('p2e_')],['p2e_confirm'])
        self.assertTrue(any('Important — Avoid double-counting:' in w.value for w in at.info))
        at.selectbox(key='p2e_basis').select('Individual fitting K')
        at.number_input(key='p2e_k').set_value(0)
        at.button(key='p2e_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('Equivalent length Le: 0 m' in x.value for x in at.text))
        at.number_input(key='p2e_k').set_value(1).run()
        self.assertFalse(any('Equivalent length Le:' in x.value for x in at.text))
        self.assertIsNone(at.number_input(key='p2d_velocity').value)
        keys=[w.key for g in [at.number_input,at.selectbox,at.button,at.checkbox,at.text_input] for w in g]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.exception)

