import math
from pathlib import Path
import unittest
from app import FLOW
from piping_hydraulics.pipe_capacity import pipe_capacity, capacity_flow_outputs
from piping_hydraulics.pipe_geometry import required_internal_diameter
from piping_hydraulics.units import flow_to_si


class CapacityTests(unittest.TestCase):
    def test_numerical_benchmark(self):
        r=pipe_capacity(.1,2)
        self.assertAlmostEqual(r.area_m2,.007853981633974483,places=15)
        self.assertEqual(r.velocity_m_s,2)
        self.assertAlmostEqual(r.flow_m3_s,.015707963267948967,places=15)
        values=capacity_flow_outputs(r.flow_m3_s,FLOW)
        for unit,expected in [('m³/hr',56.54866776461628),('L/s',15.707963267948967),
                              ('L/min',942.4777960769379),('Gallon/min (US GPM)',248.9762936916292)]:
            self.assertAlmostEqual(values[unit],expected,places=8)

    def test_inverse_consistency(self):
        for d,v in [(.01,.2),(.1,2),(.5,4)]:
            r=pipe_capacity(d,v)
            q=capacity_flow_outputs(r.flow_m3_s,FLOW)['m³/hr']
            self.assertAlmostEqual(required_internal_diameter(flow_to_si(q,'m³/hr',FLOW),v).diameter_m,d,places=14)
        self.assertAlmostEqual(required_internal_diameter(flow_to_si(56.5486678,'m³/hr',FLOW),2).diameter_m,.1,places=9)

    def test_unit_equivalence(self):
        q=pipe_capacity(.1,2).flow_m3_s
        for unit,value in capacity_flow_outputs(q,FLOW).items():
            self.assertAlmostEqual(flow_to_si(value,unit,FLOW),q,places=14)
        gpm=capacity_flow_outputs(q,FLOW)['Gallon/min (US GPM)']
        self.assertAlmostEqual(gpm,q*60/.003785411784,places=10)

    def test_zero_flow(self):
        r=pipe_capacity(.1,0)
        self.assertGreater(r.area_m2,0)
        self.assertEqual(r.velocity_m_s,0)
        self.assertEqual(r.flow_m3_s,0)
        self.assertTrue(all(q==0 for q in capacity_flow_outputs(r.flow_m3_s,FLOW).values()))
        with self.assertRaises(ValueError):pipe_capacity(0,0)

    def test_invalid_inputs(self):
        bad=[None,'','bad',True,-1,math.nan,math.inf,-math.inf]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):pipe_capacity(value,2)
                with self.assertRaises(ValueError):pipe_capacity(.1,value)
                with self.assertRaises(ValueError):capacity_flow_outputs(value,FLOW)
        with self.assertRaises(ValueError):pipe_capacity(0,2)
        with self.assertRaises(ValueError):capacity_flow_outputs(1,{})

    def test_numerical_range(self):
        for d,v in [(1e308,1),(1e-300,1),(1,1e309),(1e100,1e200),(1e-100,1e-200)]:
            with self.assertRaises(ValueError):pipe_capacity(d,v)
        with self.assertRaises(ValueError):capacity_flow_outputs(1e308,FLOW)

    def test_sensitivity(self):
        q=pipe_capacity(.1,2).flow_m3_s
        self.assertAlmostEqual(pipe_capacity(.2,2).flow_m3_s,4*q)
        self.assertAlmostEqual(pipe_capacity(.1,4).flow_m3_s,2*q)

    def test_ui(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),15)
        self.assertIsNone(at.number_input(key='p2b_diameter').value)
        self.assertIsNone(at.number_input(key='p2b_velocity').value)
        at.button(key='p2b_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p2b_diameter').set_value(0)
        at.number_input(key='p2b_velocity').set_value(2)
        at.button(key='p2b_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p2b_diameter').set_value(.1)
        at.button(key='p2b_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('56.5486677646 m³/hr' in x.value for x in at.text))
        at.number_input(key='p2b_velocity').set_value(0)
        at.button(key='p2b_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('Flow: 0 m³/s' in x.value for x in at.text))
        at.number_input(key='p2b_velocity').set_value(2).run()
        self.assertFalse(any('Cross-sectional area:' in x.value for x in at.text))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button] for w in group]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.exception)
