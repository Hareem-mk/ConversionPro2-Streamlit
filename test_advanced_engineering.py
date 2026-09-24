import math
from pathlib import Path
import unittest
from unittest.mock import patch
import advanced_engineering as ae


class NumericalTests(unittest.TestCase):
    def test_reynolds_reference(self):
        self.assertEqual(ae.reynolds(1000, 2, .1, .001), (200000, 'Turbulent'))
        self.assertEqual(ae.reynolds(800, .1, .02, .1), (16, 'Laminar'))

    def test_regime_boundaries(self):
        for re, expected in [(0,'No flow'), (2299.999,'Laminar'), (2300,'Transitional'),
                             (3999.999,'Transitional'), (4000,'Turbulent')]:
            self.assertEqual(ae.regime(re), expected)
        self.assertEqual(ae.reynolds(1000,0,.1,.001), (0,'No flow'))

    def test_laminar_and_transition(self):
        self.assertEqual(ae.friction_factor(1000,0,.1)['darcy'], .064)
        for re in [0,2300,3000,3999.99]:
            self.assertIsNone(ae.friction_factor(re,0,.1)['darcy'])
        self.assertIsNotNone(ae.friction_factor(4000,0,.1)['darcy'])

    def test_colebrook_references(self):
        # Established Colebrook reference values, independently checked residual below.
        for re, rr, expected in [(1e5,0,.01798977308427384),
                                  (1e5,.001,.022174535944515076),
                                  (1e6,.01,.03796474187616006)]:
            result = ae.colebrook(re,rr,1)
            self.assertAlmostEqual(result.factor,expected,places=11)
            residual = 1/math.sqrt(result.factor)+2*math.log10(rr/3.7+2.51/re/math.sqrt(result.factor))
            self.assertLessEqual(abs(residual),1e-10)
            self.assertLessEqual(result.iterations,200)

    def test_colebrook_grid(self):
        for re in [4000,5000,1e4,1e5,1e8,1e12]:
            for rr in [0,1e-6,.001,.01,.05]:
                result=ae.colebrook(re,rr,1)
                self.assertGreater(result.factor,0)
                self.assertLessEqual(abs(result.residual),1e-10)

    def test_nonconvergence_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'did not converge'):
            ae.colebrook(1e5,.001,1,max_iterations=1)

    def test_final_residual_rejection(self):
        with patch.object(ae,'colebrook_residual',return_value=.01):
            with self.assertRaisesRegex(ValueError,'residual failed'):
                ae.colebrook(1e5,.001,1)
        with patch.object(ae,'colebrook_residual',return_value=math.nan):
            with self.assertRaises(ValueError):
                ae.colebrook(1e5,.001,1)

    def test_swamee_reference(self):
        self.assertAlmostEqual(ae.swamee_jain(1e5,.001,1),.02234241216395183,places=12)
        r=ae.friction_factor(1e5,.001,1)
        self.assertAlmostEqual(r['comparison_percent'],.757067565,places=5)

    def test_swamee_applicability(self):
        for re in [5000,1e8]:
            for rr in [1e-6,.01]:
                self.assertGreater(ae.swamee_jain(re,rr,1),0)
        for re,rr in [(4999,.001),(1e8+1,.001),(1e5,0),(1e5,1e-7),(1e5,.01001)]:
            with self.assertRaisesRegex(ValueError,'outside applicability'):
                ae.swamee_jain(re,rr,1)
            self.assertIsNone(ae.friction_factor(re,rr,1)['swamee_jain'])

    def test_major_reference(self):
        r=ae.major_loss(100,.1,2,1000,.02)
        self.assertAlmostEqual(r.head_m,4.078864851911713)
        self.assertAlmostEqual(r.pressure_pa,40000)
        self.assertAlmostEqual(r.pressure_kpa,40)
        self.assertAlmostEqual(r.pressure_bar,.4)

    def test_minor_reference(self):
        r=ae.minor_loss(5,2,1000)
        self.assertAlmostEqual(r.head_m,1.0197162129779282)
        self.assertAlmostEqual(r.pressure_pa,10000)
        self.assertAlmostEqual(r.pressure_kpa,10)
        self.assertAlmostEqual(r.pressure_bar,.1)

    def test_total_reference(self):
        major,minor,total=ae.total_loss(100,.1,2,1000,.02,5)
        self.assertAlmostEqual(total.head_m,5.098581064889641)
        self.assertAlmostEqual(total.pressure_pa,50000)
        self.assertEqual(total.head_m,major.head_m+minor.head_m)
        self.assertEqual(total.pressure_pa,major.pressure_pa+minor.pressure_pa)

    def test_zero_losses(self):
        for result in [ae.major_loss(0,.1,2,1000,.02),ae.major_loss(100,.1,0,1000,.02),
                       ae.minor_loss(0,2,1000),ae.minor_loss(5,0,1000),
                       ae.total_loss(100,.1,0,1000,.02,5)[2]]:
            self.assertEqual(result,ae.Loss(0,0))

    def test_invalid_inputs_every_calculation(self):
        cases=[(ae.reynolds,[1000,2,.1,.001],{0,2,3}),
               (ae.colebrook,[1e5,.001,1],{0,2}),
               (ae.swamee_jain,[1e5,.001,1],{0,2}),
               (ae.friction_factor,[1e5,.001,1],{2}),
               (ae.major_loss,[100,.1,2,1000,.02],{1,3,4}),
               (ae.minor_loss,[5,2,1000],{2}),
               (ae.total_loss,[100,.1,2,1000,.02,5],{1,3,4})]
        for fn, good, positive_indices in cases:
            for i in range(len(good)):
                for bad in [None,'', 'bad',-1,math.nan,math.inf,-math.inf,True]+([0] if i in positive_indices else []):
                    args=good.copy();args[i]=bad
                    with self.subTest(function=fn.__name__,i=i,bad=bad):
                        with self.assertRaises(ValueError):fn(*args)

    def test_outside_colebrook_domain(self):
        for re in [0,1000,3000]:
            with self.assertRaises(ValueError):ae.colebrook(re,.001,1)
        with self.assertRaises(ValueError):ae.colebrook(1e5,.051,1)

    def test_overflow(self):
        for fn,args in [(ae.reynolds,(1e308,1e308,1,1)),
                        (ae.major_loss,(1e308,.1,1e308,1000,.02)),
                        (ae.minor_loss,(1e308,1e308,1000)),
                        (ae.total_loss,(1e308,.1,1e308,1000,.02,1))]:
            with self.assertRaises(ValueError):fn(*args)


class AdvancedUI(unittest.TestCase):
    def test_panels_and_calculations(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),14)
        self.assertEqual(len(at.expander),5)
        for w in at.number_input:
            if w.key.startswith('adv_'):self.assertIsNone(w.value)
        cases={'reynolds':dict(density=1000,velocity=2,diameter=.1,viscosity=.001),
               'friction':dict(re=1e5,roughness=.001,diameter=1),
               'major':dict(length=100,diameter=.1,velocity=2,density=1000,darcy=.02),
               'minor':dict(k_total=5,velocity=2,density=1000),
               'total':dict(length=100,diameter=.1,velocity=2,density=1000,darcy=.02,k_total=5)}
        for panel,values in cases.items():
            at.button(key=f'adv_{panel}_calculate').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(at.error)
            for name,v in values.items():at.number_input(key=f'adv_{panel}_{name}').set_value(v)
            at.button(key=f'adv_{panel}_calculate').click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error)
            self.assertTrue(at.text)
        self.assertTrue(any('Total major + minor frictional pressure loss' in m.value for m in at.markdown))
        self.assertTrue(any('equipment pressure losses' in i.value for i in at.info))
        at.number_input(key='adv_friction_re').set_value(4500)
        at.button(key='adv_friction_calculate').click().run()
        self.assertTrue(any('withheld' in w.value for w in at.warning))
        self.assertFalse(at.exception)


if __name__=='__main__':
    unittest.main(verbosity=2)
