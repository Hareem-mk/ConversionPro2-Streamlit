from decimal import Decimal, localcontext
from pathlib import Path
import inspect
import math
import unittest
from app import PRESSURE
from piping_hydraulics.npsha import flange_npsha, source_npsha, absolute_pressure, COMPARISON
from piping_hydraulics.pump_head import pressure_to_pa
BASE=dict(pressure_pa=150000,basis='Absolute',vapor_pressure_pa=3000,density=1000,velocity=2,elevation=0,datum_elevation=0)
SOURCE=BASE|dict(pressure_pa=101325,velocity=0,elevation=3,suction_loss=1)
def flange(**kw):return flange_npsha(**(BASE|kw))
def source(**kw):return source_npsha(**(SOURCE|kw))

class NPSHATests(unittest.TestCase):
    def test_flange_decimal_benchmark(self):
        with localcontext() as c:
            c.prec=50;g=Decimal('9.80665');r=flange()
            expected=[Decimal(3000)/(1000*g),Decimal(147000)/(1000*g),Decimal(4)/(2*g)]
            for a,b in zip([r.vapor_head_m,r.pressure_above_vapor_head_m,r.velocity_head_m],expected):self.assertAlmostEqual(a,float(b),places=12)
            self.assertAlmostEqual(r.total_npsha_m,float(expected[1]+expected[2]),places=12)
            self.assertEqual(r.elevation_head_m,0);self.assertIsNone(r.suction_loss_m);self.assertFalse(r.warnings)

    def test_source_decimal_benchmark(self):
        with localcontext() as c:
            c.prec=50;p=Decimal(98325)/(Decimal(1000)*Decimal('9.80665'));r=source()
            self.assertAlmostEqual(r.pressure_above_vapor_head_m,float(p),places=12)
            self.assertAlmostEqual(r.total_npsha_m,float(p+3-1),places=12)
            self.assertEqual((r.velocity_head_m,r.elevation_head_m,r.suction_loss_m),(0,3,1))

    def test_gauge_conversion(self):
        self.assertEqual(absolute_pressure(48675,'Gauge',101325),150000)
        self.assertEqual(absolute_pressure(-21325,'Gauge',101325),80000)
        for atm in [None,0,-1,math.nan,math.inf,True]:
            with self.assertRaises(ValueError):absolute_pressure(0,'Gauge',atm)
        for p in [-101325,-200000]:
            with self.assertRaises(ValueError):absolute_pressure(p,'Gauge',101325)
        with self.assertRaises(ValueError):absolute_pressure(100000,'Absolute',101325)
        with self.assertRaises(ValueError):absolute_pressure(100000,None)

    def test_gauge_absolute_equivalence(self):
        for fn,p in [(flange,150000),(source,101325)]:self.assertEqual(fn().total_npsha_m,fn(pressure_pa=p-101325,basis='Gauge',atmospheric_pa=101325).total_npsha_m)

    def test_velocities(self):
        self.assertEqual(source().velocity_head_m,0)
        self.assertAlmostEqual(source(velocity=2).total_npsha_m-source().total_npsha_m,4/(2*9.80665),places=12)
        for fn in [source,flange]:
            for bad in [None,-1]:
                with self.assertRaises(ValueError):fn(velocity=bad)

    def test_signed_elevations_and_datum(self):
        self.assertAlmostEqual(source(elevation=8).total_npsha_m-source().total_npsha_m,5,places=12)
        self.assertEqual(source(elevation=-7,datum_elevation=-10).total_npsha_m,source().total_npsha_m)
        self.assertEqual(flange(elevation=-5,datum_elevation=-5).total_npsha_m,flange().total_npsha_m)

    def test_suction_loss_sensitivity(self):
        self.assertEqual(source(suction_loss=3).total_npsha_m-source().total_npsha_m,-2)
        self.assertEqual(source(suction_loss=0).total_npsha_m-source().total_npsha_m,1)

    def test_vapor_sensitivity(self):
        for fn in [source,flange]:
            self.assertAlmostEqual(fn(vapor_pressure_pa=4000).total_npsha_m-fn().total_npsha_m,-1000/(1000*9.80665),places=12)
            self.assertEqual(fn(vapor_pressure_pa=0).vapor_head_m,0)

    def test_pressure_at_or_below_vapor(self):
        for fn in [source,flange]:
            for p in [2000,3000]:
                r=fn(pressure_pa=p,elevation=10);self.assertGreater(r.total_npsha_m,0)
                self.assertTrue(any('at or below liquid vapor pressure' in w for w in r.warnings))

    def test_nonpositive_retained(self):
        r=flange(pressure_pa=3000,velocity=0);self.assertEqual(r.total_npsha_m,0);self.assertEqual(len(r.warnings),2)
        # 12 m suction lift with 1 m loss: the assumed liquid suction condition is infeasible.
        r=source(elevation=-12);self.assertLess(r.total_npsha_m,0)
        self.assertAlmostEqual(r.total_npsha_m,98325/(1000*9.80665)-13,places=12)
        self.assertTrue(any('not an acceptable normal pump suction condition' in w for w in r.warnings))
        self.assertLess(flange(pressure_pa=2000,velocity=0).total_npsha_m,0)

    def test_invalid_density(self):
        for fn in [source,flange]:
            for bad in [0,-1,None,True,'bad',math.nan,math.inf]:
                with self.subTest(fn=fn,bad=bad):
                    with self.assertRaises(ValueError):fn(density=bad)

    def test_invalid_vapor_and_loss(self):
        for bad in [-1,None,True,'bad',math.nan,math.inf]:
            for fn in [source,flange]:
                with self.assertRaises(ValueError):fn(vapor_pressure_pa=bad)
            with self.assertRaises(ValueError):source(suction_loss=bad)

    def test_nonfinite_and_invalid_absolute(self):
        for fn in [source,flange]:
            for key in ['pressure_pa','velocity','elevation','datum_elevation']:
                for bad in [math.nan,math.inf,-math.inf,None,True,'bad']:
                    with self.subTest(fn=fn,key=key,bad=bad):
                        with self.assertRaises(ValueError):fn(**{key:bad})
            for bad in [0,-1]:
                with self.assertRaises(ValueError):fn(pressure_pa=bad)

    def test_numeric_range(self):
        for changes in [dict(velocity=1e308),dict(density=1e-308),dict(elevation=1e308,datum_elevation=-1e308)]:
            with self.assertRaises(ValueError):flange(**changes)

    def test_no_flange_loss_double_counting(self):
        self.assertNotIn('suction_loss',inspect.signature(flange_npsha).parameters)
        with self.assertRaises(TypeError):flange(suction_loss=1)

    def test_cross_mode_consistency(self):
        # Bernoulli independently derives flange pressure, including signed datum and velocities.
        for zs,zf,zd,vs,vf,loss in [(3,0,0,0,2,1),(-2,-4,-3,1,3,2)]:
            ps=101325+1000*9.80665*(zs-zf-loss)+1000*(vs**2-vf**2)/2
            a=source(elevation=zs,datum_elevation=zd,velocity=vs,suction_loss=loss)
            b=flange(pressure_pa=ps,elevation=zf,datum_elevation=zd,velocity=vf)
            self.assertAlmostEqual(a.total_npsha_m,b.total_npsha_m,places=12)

    def test_pressure_unit_equivalence(self):
        for unit,factor in PRESSURE.items():
            r=flange(pressure_pa=pressure_to_pa(150000/factor,unit,PRESSURE),vapor_pressure_pa=pressure_to_pa(3000/factor,unit,PRESSURE))
            self.assertAlmostEqual(r.total_npsha_m,flange().total_npsha_m,places=12)

    def ui(self,source_mode=False):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertEqual(len(at.tabs),15);self.assertFalse(at.exception)
        at.selectbox(key='p2h_mode').select('SUCTION-VESSEL / SOURCE NPSHA' if source_mode else 'SUCTION-FLANGE NPSHA').run()
        return at,'p2h_source_' if source_mode else 'p2h_flange_'

    def fill(self,at,p,source_mode=False):
        at.selectbox(key=p+'basis').select('Absolute').run()
        at.selectbox(key=p+'unit').select('Kilopascal (kPa)')
        at.selectbox(key=p+'vapor_unit').select('Kilopascal (kPa)')
        at.text_input(key=p+'datum').set_value('Site benchmark')
        at.checkbox(key=p+'reference').check();at.checkbox(key=p+'fluid').check()
        values=dict(pressure=101.325 if source_mode else 150,vapor=3,density=1000,velocity=0 if source_mode else 2,elevation=3 if source_mode else 0,datum_elevation=0)
        if source_mode:values['suction_loss']=1
        for key,val in values.items():at.number_input(key=p+key).set_value(val)
        at.button(key=p+'calculate').click().run();self.assertFalse(at.exception);self.assertFalse(at.error)

    def test_ui_flange_validation_and_gauge(self):
        at,p=self.ui();at.button(key=p+'calculate').click().run();self.assertTrue(at.error)
        self.assertIsNone(at.number_input(key=p+'velocity').value)
        self.fill(at,p);self.assertTrue(any('TOTAL NPSHA: 15.193' in t.value for t in at.text))
        self.assertFalse(any(w.key==p+'suction_loss' for w in at.number_input))
        at.selectbox(key=p+'basis').select('Gauge').run()
        self.assertFalse(any('TOTAL NPSHA:' in t.value for t in at.text))
        self.assertIsNone(at.number_input(key=p+'atmosphere').value)
        at.button(key=p+'calculate').click().run();self.assertTrue(at.error)
        at.number_input(key=p+'pressure').set_value(48.675);at.number_input(key=p+'atmosphere').set_value(101.325)
        at.selectbox(key=p+'atm_unit').select('Kilopascal (kPa)')
        at.button(key=p+'calculate').click().run();self.assertFalse(at.error)
        self.assertTrue(any('150000 Pa absolute' in t.value for t in at.text))
        self.assertTrue(any('TOTAL NPSHA: 15.193' in t.value for t in at.text))
        self.assertTrue(any(COMPARISON in t.value for t in at.info))
        at.checkbox(key=p+'fluid').uncheck();at.button(key=p+'calculate').click().run();self.assertTrue(at.error)
        self.assertFalse(at.exception)

    def test_ui_source_negative_and_mode_isolation(self):
        at,p=self.ui(True);self.assertIsNone(at.number_input(key=p+'velocity').value);self.fill(at,p,True)
        self.assertTrue(any('TOTAL NPSHA: 12.026' in t.value for t in at.text))
        at.number_input(key=p+'elevation').set_value(-12);at.button(key=p+'calculate').click().run()
        self.assertTrue(any('TOTAL NPSHA: -2.973' in t.value for t in at.text))
        self.assertTrue(any('not an acceptable normal pump suction condition' in t.value for t in at.warning))
        at.selectbox(key='p2h_mode').select('SUCTION-FLANGE NPSHA').run()
        self.assertIsNone(at.number_input(key='p2h_flange_pressure').value)
        self.assertFalse(any('TOTAL NPSHA:' in t.value for t in at.text));self.assertFalse(at.exception)

    def test_ui_zero_and_unique_keys(self):
        at,p=self.ui();self.fill(at,p)
        at.number_input(key=p+'pressure').set_value(3);at.number_input(key=p+'velocity').set_value(0)
        at.button(key=p+'calculate').click().run()
        self.assertTrue(any('TOTAL NPSHA: 0 m' in t.value for t in at.text));self.assertEqual(sum('vapor pressure' in w.value or 'vapor-pressure energy reference' in w.value for w in at.warning),2)
        for mode in ['SUCTION-FLANGE NPSHA','SUCTION-VESSEL / SOURCE NPSHA']:
            at.selectbox(key='p2h_mode').select(mode).run();p='p2h_source_' if 'VESSEL' in mode else 'p2h_flange_'
            for basis in ['Gauge','Absolute']:
                at.selectbox(key=p+'basis').select(basis).run()
                keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox,at.text_input] for w in group]
                self.assertEqual(len(keys),len(set(keys)));self.assertFalse(at.exception)
