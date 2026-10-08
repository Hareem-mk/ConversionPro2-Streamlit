from decimal import Decimal,localcontext
from pathlib import Path
import inspect
import math
import unittest
from app import PRESSURE
from piping_hydraulics.pump_head import system_required_head,flange_differential_head,pressure_to_pa

BASE=dict(density=1000,p1_pa=0,p2_pa=100000,z1=0,z2=10,v1=1,v2=2,
          basis1='Gauge',basis2='Gauge',datum='Site datum',reference_confirmed=True)
LOSSES=dict(suction_loss=2,discharge_loss=3,equipment_dp_pa=10000)


def system(**changes):
    return system_required_head(**(BASE|LOSSES|changes))


def flange(**changes):
    return flange_differential_head(**(BASE|changes))


class PumpHeadTests(unittest.TestCase):
    def test_system_decimal_benchmark(self):
        # Independent high-precision arithmetic, not a hard-coded disputed total.
        with localcontext() as c:
            c.prec=50
            rho=Decimal(1000);g=Decimal('9.80665')
            parts=[Decimal(100000)/(rho*g),Decimal(10),(Decimal(2)**2-Decimal(1)**2)/(2*g),
                   Decimal(2),Decimal(3),Decimal(10000)/(rho*g)]
            r=system()
            actual=[r.pressure_head_m,r.elevation_head_m,r.velocity_head_m,r.suction_loss_m,r.discharge_loss_m,r.equipment_head_m]
            for a,e in zip(actual,parts):self.assertAlmostEqual(a,float(e),places=12)
            self.assertAlmostEqual(r.total_head_m,float(sum(parts)),places=12)

    def test_component_sum(self):
        r=system()
        self.assertAlmostEqual(r.total_head_m,sum([r.pressure_head_m,r.elevation_head_m,r.velocity_head_m,
                               r.suction_loss_m,r.discharge_loss_m,r.equipment_head_m]),places=12)

    def test_flange_direct(self):
        r=flange(p1_pa=-20000,p2_pa=180000,z1=-1,z2=.5,v1=1,v2=3)
        expected=200000/(1000*9.80665)+1.5+(9-1)/(2*9.80665)
        self.assertAlmostEqual(r.total_head_m,expected,places=12)
        self.assertIsNone(r.suction_loss_m)
        self.assertIsNone(r.discharge_loss_m)
        self.assertIsNone(r.equipment_head_m)

    def test_gauge_absolute_equivalence(self):
        for fn in [system,flange]:
            a=fn(p1_pa=-20000,p2_pa=80000)
            b=fn(p1_pa=81325,p2_pa=181325,basis1='Absolute',basis2='Absolute')
            self.assertAlmostEqual(a.pressure_head_m,b.pressure_head_m,places=12)
            self.assertAlmostEqual(a.total_head_m,b.total_head_m,places=12)

    def test_mixed_basis_rejection(self):
        for fn in [system,flange]:
            with self.assertRaisesRegex(ValueError,'Mixed'):fn(basis2='Absolute')
            with self.assertRaises(ValueError):fn(basis1=None)
            with self.assertRaises(ValueError):fn(reference_confirmed=False)

    def test_elevation_sign(self):
        self.assertAlmostEqual(system(z2=10).total_head_m-system(z2=-10).total_head_m,20)
        self.assertAlmostEqual(system(z1=-5,z2=5).total_head_m,system(z1=0,z2=10).total_head_m)
        self.assertAlmostEqual(flange(z1=-5,z2=5).total_head_m,flange(z1=0,z2=10).total_head_m)

    def test_zero(self):
        self.assertEqual(system(p2_pa=0,z2=0,v2=1,suction_loss=0,discharge_loss=0,equipment_dp_pa=0).total_head_m,0)
        self.assertEqual(flange(p2_pa=0,z2=0,v2=1).total_head_m,0)

    def test_negative_head(self):
        # Equal-pressure reservoirs: destination 10 m lower, total dissipative loss 2 m.
        self.assertEqual(system(p2_pa=0,z2=-10,v1=0,v2=0,suction_loss=1,discharge_loss=1,equipment_dp_pa=0).total_head_m,-8)
        self.assertLess(flange(p2_pa=-10000,z2=0,v1=0,v2=0).total_head_m,0)

    def test_velocities(self):
        self.assertEqual(system(v1=3,v2=3).velocity_head_m,0)
        self.assertAlmostEqual(system(v1=2,v2=1).velocity_head_m,-3/(2*9.80665))
        self.assertEqual(flange(v1=0,v2=0).velocity_head_m,0)

    def test_loss_validation(self):
        for key in LOSSES:
            for bad in [-1,None,math.nan,math.inf,True]:
                with self.assertRaises(ValueError):system(**{key:bad})
        self.assertAlmostEqual(system(suction_loss=0,discharge_loss=0,equipment_dp_pa=0).total_head_m,flange().total_head_m)

    def test_density_and_finiteness(self):
        for fn in [system,flange]:
            for bad in [0,-1,None,math.inf,math.nan,True]:
                with self.assertRaises(ValueError):fn(density=bad)
            for key in ['p1_pa','p2_pa','z1','z2','v1','v2']:
                for bad in [None,'bad',True,math.inf,-math.inf,math.nan]:
                    with self.subTest(key=key,bad=bad):
                        with self.assertRaises(ValueError):fn(**{key:bad})
            with self.assertRaises(ValueError):fn(v1=-1)
            with self.assertRaises(ValueError):fn(datum=' ')
            with self.assertRaises(ValueError):fn(basis1='Absolute',basis2='Absolute',p1_pa=-1)

    def test_pressure_units(self):
        for unit,factor in PRESSURE.items():
            self.assertAlmostEqual(pressure_to_pa(100000/factor,unit,PRESSURE),100000,places=8)
            self.assertAlmostEqual(pressure_to_pa(-100000/factor,unit,PRESSURE),-100000,places=8)
        self.assertEqual(pressure_to_pa(1,'Bar',PRESSURE),pressure_to_pa(100,'Kilopascal (kPa)',PRESSURE))
        with self.assertRaises(ValueError):pressure_to_pa(1,'invalid',PRESSURE)

    def test_no_external_losses_in_flange(self):
        self.assertNotIn('suction_loss',inspect.signature(flange_differential_head).parameters)
        with self.assertRaises(TypeError):flange_differential_head(**BASE,**LOSSES)
        with self.assertRaisesRegex(ValueError,'re-add'):system(losses_already_in_reference_pressures=True)

    def test_numeric_limits(self):
        with self.assertRaises(ValueError):system(z1=-1e308,z2=1e308)
        with self.assertRaises(ValueError):flange(p1_pa=-1e308,p2_pa=1e308,density=1e-308)
        with self.assertRaises(ValueError):pressure_to_pa(1e308,'Bar',PRESSURE)

    def test_ui_modes_and_isolation(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertEqual(len(at.tabs),15)
        self.assertFalse(at.exception)
        at.selectbox(key='p2g_mode').select('SYSTEM REQUIRED PUMP HEAD').run()
        prefix='p2g_system_'
        at.button(key=prefix+'calculate').click().run()
        self.assertEqual(sum(w.value.startswith('Please confirm') for w in at.warning),2)
        self.assertFalse(at.error)
        at.selectbox(key=prefix+'basis').select('Gauge')
        at.selectbox(key=prefix+'unit').select('Kilopascal (kPa)')
        at.selectbox(key=prefix+'equipment_unit').select('Kilopascal (kPa)')
        at.text_input(key=prefix+'datum').set_value('Site datum')
        at.checkbox(key=prefix+'reference').check()
        at.checkbox(key=prefix+'losses_not_in_pressures_confirmed').check()
        for key,v in dict(density=1000,p1=0,p2=100,z1=0,z2=10,v1=1,v2=2,
                          suction_loss=2,discharge_loss=3,equipment_dp=10).items():
            at.number_input(key=prefix+key).set_value(v)
        at.button(key=prefix+'calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('TOTAL PUMP HEAD:' in t.value for t in at.text))
        at.checkbox(key=prefix+'losses_not_in_pressures_confirmed').uncheck()
        at.button(key=prefix+'calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('NOT already included' in w.value for w in at.warning))
        self.assertFalse(any('TOTAL PUMP HEAD:' in t.value for t in at.text))
        at.selectbox(key='p2g_mode').select('PUMP-FLANGE DIFFERENTIAL HEAD').run()
        self.assertFalse(any('suction_loss' in w.key for w in at.number_input if w.key.startswith('p2g_')))
        self.assertFalse(any('TOTAL PUMP HEAD:' in t.value for t in at.text))
        prefix='p2g_flange_'
        self.assertIsNone(at.number_input(key=prefix+'p1').value)
        at.selectbox(key=prefix+'basis').select('Gauge')
        at.selectbox(key=prefix+'unit').select('Kilopascal (kPa)')
        at.text_input(key=prefix+'datum').set_value('Pump centreline')
        at.checkbox(key=prefix+'reference').check()
        for key,v in dict(density=1000,p1=0,p2=0,z1=0,z2=-10,v1=0,v2=0).items():
            at.number_input(key=prefix+key).set_value(v)
        at.button(key=prefix+'calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('TOTAL PUMP DIFFERENTIAL HEAD: -10 m' in t.value for t in at.text))
        self.assertTrue(any('Negative head retained' in w.value for w in at.warning))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox,at.text_input] for w in group]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.exception)

