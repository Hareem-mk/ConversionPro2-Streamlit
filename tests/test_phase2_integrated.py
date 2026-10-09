import math
from pathlib import Path
import unittest
from unittest.mock import patch
import advanced_engineering as p1
from app import FLOW
from piping_hydraulics.integrated import integrated_section
from piping_hydraulics.pipe_capacity import pipe_capacity

BASE=dict(flow=.01,flow_unit='m³/s',diameter=.1,length=100,density=1000,viscosity=.001,
          roughness=.000045,k_total=2,flow_factors=FLOW,common_k_basis=True)


def run(**changes):
    return integrated_section(**(BASE|changes))


class IntegratedTests(unittest.TestCase):
    def test_core(self):
        r=run()
        self.assertAlmostEqual(r['area_m2'],.007853981633974483,places=15)
        self.assertAlmostEqual(r['velocity_m_s'],1.2732395447351628,places=13)
        self.assertAlmostEqual(r['reynolds'],127323.95447351628,places=7)
        self.assertAlmostEqual(r['relative_roughness'],.00045,places=15)
        self.assertEqual(r['regime'],'Turbulent')
        self.assertTrue(r['complete'])
        self.assertLess(abs(r['friction']['residual']),1e-10)

    def test_independent_loss_equations(self):
        r=run();f=r['friction']['darcy'];v=.01/(math.pi*.1**2/4)
        expected_major=f*(100/.1)*v*v/(2*9.80665)
        expected_minor=2*v*v/(2*9.80665)
        for name,h in [('major',expected_major),('minor',expected_minor),('total',expected_major+expected_minor)]:
            self.assertAlmostEqual(r[name].head_m,h,places=12)
            self.assertAlmostEqual(r[name].pressure_pa,1000*9.80665*h,places=8)
        residual=1/math.sqrt(f)+2*math.log10(.00045/3.7+2.51/(r['reynolds']*math.sqrt(f)))
        self.assertLess(abs(residual),1e-10)

    def test_cross_module(self):
        r=run();v=r['velocity_m_s']
        self.assertAlmostEqual(pipe_capacity(.1,v).flow_m3_s,.01)
        self.assertEqual(pipe_capacity(.1,0).area_m2,r['area_m2'])
        self.assertEqual(p1.reynolds(1000,v,.1,.001),(r['reynolds'],r['regime']))
        self.assertEqual(p1.relative_roughness(.000045,.1),r['relative_roughness'])
        self.assertEqual(p1.friction_factor(r['reynolds'],.000045,.1),r['friction'])
        f=r['friction']['darcy']
        self.assertEqual(p1.major_loss(100,.1,v,1000,f),r['major'])
        self.assertEqual(p1.minor_loss(2,v,1000),r['minor'])
        self.assertEqual(p1.total_loss(100,.1,v,1000,f,2),(r['major'],r['minor'],r['total']))

    def test_zero(self):
        with patch.object(p1,'colebrook',side_effect=AssertionError('must not solve')):
            r=run(flow=0)
        self.assertEqual((r['velocity_m_s'],r['reynolds'],r['regime']),(0,0,'No flow'))
        self.assertIsNone(r['friction']['darcy'])
        for name in ['major','minor','total']:self.assertEqual(r[name],p1.Loss(0,0))

    def test_laminar(self):
        r=run(flow=math.pi*.1**2/4*.01)
        self.assertEqual(r['regime'],'Laminar')
        self.assertAlmostEqual(r['reynolds'],1000)
        self.assertAlmostEqual(r['friction']['darcy'],.064)

    def test_transition(self):
        for length in [100,0]:
            r=run(flow=math.pi*.1**2/4*.03,length=length)
            self.assertAlmostEqual(r['reynolds'],3000)
            self.assertEqual(r['regime'],'Transitional')
            self.assertFalse(r['complete'])
            for key in ['major','total']:self.assertIsNone(r[key])
            self.assertIsNone(r['friction']['darcy'])
            self.assertGreater(r['minor'].head_m,0)

    def test_smooth_and_sj_range(self):
        r=run(roughness=0)
        self.assertGreater(r['friction']['darcy'],0)
        self.assertIsNone(r['friction']['swamee_jain'])
        self.assertIsNotNone(run()['friction']['swamee_jain'])

    def test_zero_k_length(self):
        self.assertEqual(run(k_total=0)['minor'].head_m,0)
        self.assertEqual(run(length=0)['major'].head_m,0)
        self.assertEqual(run(length=0,k_total=0)['total'].head_m,0)

    def test_invalid(self):
        for key in ['flow','diameter','length','density','viscosity','roughness','k_total']:
            for bad in [None,'bad',True,-1,math.nan,math.inf]+([0] if key in ['diameter','density','viscosity'] else []):
                with self.subTest(key=key,bad=bad):
                    with self.assertRaises(ValueError):run(**{key:bad})
        for flow in [0,.01]:
            with self.assertRaises(ValueError):run(flow=flow,flow_unit='SCFM')
        with self.assertRaises(ValueError):run(roughness=.01)
        with self.assertRaises(ValueError):run(flow=0,density=0)

    def test_units(self):
        ref=run()
        for unit,factor in FLOW.items():
            r=run(flow=.01/factor,flow_unit=unit)
            self.assertAlmostEqual(r['total'].pressure_pa,ref['total'].pressure_pa,places=7)
            self.assertEqual(run(flow=0,flow_unit=unit)['total'].pressure_pa,0)

    def test_summation(self):
        r=run()
        self.assertEqual(r['total'].head_m,r['major'].head_m+r['minor'].head_m)
        self.assertEqual(r['total'].pressure_pa,r['major'].pressure_pa+r['minor'].pressure_pa)

    def test_basis_duplicate_guards(self):
        with self.assertRaises(ValueError):run(common_k_basis=False)
        with self.assertRaisesRegex(ValueError,'straight pipe length only'):
            run(length_contains_equivalent_fittings=True)

    def test_ui(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertEqual(len(at.tabs),15)
        self.assertFalse(at.exception)
        self.assertIsNone(at.number_input(key='p2f_roughness').value)
        at.button(key='p2f_calculate').click().run()
        self.assertTrue(at.error)
        for name in ['flow','diameter','length','density','viscosity','roughness','k_total']:
            at.number_input(key='p2f_'+name).set_value(BASE[name])
        at.selectbox(key='p2f_unit').select('m³/s')
        at.checkbox(key='p2f_basis').check()
        at.button(key='p2f_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('Total ΔP:' in t.value for t in at.text))
        at.number_input(key='p2f_flow').set_value(0)
        at.button(key='p2f_calculate').click().run()
        self.assertTrue(any('Flow regime: No flow' in t.value for t in at.text))
        self.assertTrue(any('Total ΔP: 0 Pa' in t.value for t in at.text))
        at.number_input(key='p2f_flow').set_value(math.pi*.1**2/4*.03)
        at.button(key='p2f_calculate').click().run()
        self.assertTrue(any('INCOMPLETE' in w.value for w in at.warning))
        self.assertTrue(any('Total head loss and ΔP: UNAVAILABLE' in t.value for t in at.text))
        self.assertEqual([w.key for w in at.checkbox if w.key.startswith('p2f_')],['p2f_basis'])
        self.assertTrue(any('Important — Avoid double-counting:' in w.value for w in at.info))
        self.assertEqual(at.number_input(key='p2f_flow').label,'Volumetric Flow Rate (m³/s)')
        at.selectbox(key='p2f_unit').select('m³/hr').run()
        self.assertEqual(at.number_input(key='p2f_flow').label,'Volumetric Flow Rate (m³/hr)')
        keys=[w.key for g in [at.number_input,at.selectbox,at.button,at.checkbox,at.text_input] for w in g]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.exception)

