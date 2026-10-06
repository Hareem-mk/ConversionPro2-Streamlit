import math
from pathlib import Path
import unittest
from app import FLOW
from piping_hydraulics.pipe_geometry import required_internal_diameter
from piping_hydraulics.units import flow_to_si


class PipeSizing(unittest.TestCase):
    def test_benchmark(self):
        r=required_internal_diameter(.01,2)
        self.assertAlmostEqual(r.diameter_m,.07978845608028654,places=14)
        self.assertAlmostEqual(r.diameter_mm,79.78845608028654,places=10)
        self.assertAlmostEqual(r.diameter_inches,3.141277798436478,places=10)

    def test_inverse(self):
        for d,v in [(.025,.5),(.1,2),(1,3)]:
            q=math.pi*d*d*v/4
            self.assertAlmostEqual(required_internal_diameter(q,v).diameter_m,d,places=13)

    def test_sensitivity(self):
        d=required_internal_diameter(.01,2).diameter_m
        self.assertAlmostEqual(required_internal_diameter(.04,2).diameter_m,2*d)
        self.assertAlmostEqual(required_internal_diameter(.01,8).diameter_m,d/2)

    def test_units(self):
        for unit,value in [('m³/s',.01),('m³/hr',36),('L/s',10),('L/min',600),('L/hr',36000)]:
            self.assertAlmostEqual(flow_to_si(value,unit,FLOW),.01,places=14)
        for unit,factor in FLOW.items():
            self.assertAlmostEqual(required_internal_diameter(flow_to_si(.01/factor,unit,FLOW),2).diameter_mm,79.78845608028654,places=10)
        self.assertAlmostEqual(flow_to_si(1,'Gallon/min (US GPM)',FLOW),.003785411784/60,places=14)

    def test_invalid(self):
        for bad in [None,'', 'bad',0,-1,math.nan,math.inf,-math.inf,True]:
            for args in [(bad,2),(.01,bad)]:
                with self.subTest(args=args):
                    with self.assertRaises(ValueError):required_internal_diameter(*args)
            with self.assertRaises(ValueError):flow_to_si(bad,'m³/s',FLOW)
        for unit in [None,'SCFM','invalid']:
            with self.assertRaises(ValueError):flow_to_si(1,unit,FLOW)

    def test_numeric_range(self):
        with self.assertRaises(ValueError):flow_to_si(5e-324,'L/hr',FLOW)
        with self.assertRaises(ValueError):required_internal_diameter(1e308,5e-324)
        self.assertAlmostEqual(required_internal_diameter(1e308,1e308).diameter_m,math.sqrt(4/math.pi))

    def test_ui(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),15)
        self.assertIsNone(at.number_input(key='p2a_flow').value)
        self.assertIsNone(at.number_input(key='p2a_velocity').value)
        self.assertIsNone(at.selectbox(key='p2a_flow_unit').value)
        at.button(key='p2a_calculate').click().run()
        self.assertTrue(at.error)
        for q,v in [(0,2),(36,0)]:
            at.number_input(key='p2a_flow').set_value(q)
            at.selectbox(key='p2a_flow_unit').select('m³/hr')
            at.number_input(key='p2a_velocity').set_value(v)
            at.button(key='p2a_calculate').click().run()
            self.assertTrue(at.error)
            self.assertFalse(at.exception)
        at.number_input(key='p2a_flow').set_value(36)
        at.number_input(key='p2a_velocity').set_value(2)
        at.button(key='p2a_calculate').click().run()
        self.assertFalse(at.error)
        self.assertFalse(at.exception)
        self.assertTrue(any('79.7884560803 mm' in t.value for t in at.text))
        at.number_input(key='p2a_flow').set_value(72).run()
        self.assertFalse(any('Required INTERNAL diameter' in t.value for t in at.text))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button] for w in group]
        self.assertEqual(len(keys),len(set(keys)))
