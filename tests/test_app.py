import ast
import math
from pathlib import Path
import re
import unittest
import app


def converted(text):
    if text.startswith('Error:'):
        raise AssertionError(text)
    return float(text.split(' = ')[1].split()[0].replace(',', ''))


class Calculations(unittest.TestCase):
    def test_reference_conversions(self):
        cases = [(app.PRESSURE, 'Atmosphere (atm)', 'Pascal (Pa)', 101325),
                 (app.VOLUME, 'Gallon (US)', 'Liter (L)', 3.785411784),
                 (app.MASS, 'Pound (lb)', 'Kilogram (kg)', .45359237),
                 (app.ENERGY, 'Kilowatt-hour (kWh)', 'Joule (J)', 3600000),
                 (app.POWER, 'Horsepower (mechanical hp)', 'Watt (W)', 745.699871582),
                 (app.FLOW, 'Gallon/min (US GPM)', 'L/min', 3.785411784),
                 (app.DENSITY, 'g/cm³', 'kg/m³', 1000)]
        for table, a, b, expected in cases:
            with self.subTest(a=a):
                self.assertAlmostEqual(converted(app.ratio_converter(1, a, b, table)), expected, delta=5.1e-7)
        # Exercise every pair, including tiny factors and extreme ratios.
        for table in [app.PRESSURE, app.VOLUME, app.MASS, app.ENERGY, app.POWER, app.FLOW, app.DENSITY]:
            for a in table:
                for b in table:
                    actual = converted(app.ratio_converter(1, a, b, table))
                    self.assertTrue(math.isclose(actual, table[a]/table[b], rel_tol=1e-7, abs_tol=5.1e-7))

    def test_temperature(self):
        for value, a, b, expected in [(0, 0, 1, 32), (100, 0, 2, 373.15), (-40, 0, 1, -40), (0, 2, 3, 0), (491.67, 3, 0, 0)]:
            self.assertAlmostEqual(converted(app.temperature(value, app.TEMP[a], app.TEMP[b])), expected, places=4)
        for v, unit in [(-274, 0), (-460, 1), (-1, 2), (-1, 3)]:
            self.assertTrue(app.temperature(v, app.TEMP[unit], app.TEMP[0]).startswith('Error:'))

    def test_mass_flow(self):
        for args, expected in [((1, 'm³/hr', 'kg/hr', 850), 850), ((850, 'kg/hr', 'm³/hr', 850), 1),
                              ((1, 'US GPM', 'kg/hr', 1000), 227.12470824), ((60, 'L/min', 'm³/hr', None), 3.6),
                              ((1, 'kg/hr', 'lb/hr', 0), 2.20462262185), ((1, 'SCFM (standard ft³/min)', 'kg/hr', 1.2), 2.038812954624)]:
            self.assertAlmostEqual(converted(app.mass_flow(*args)), expected, delta=5.1e-7)
        for rho in [None, 0, -1, math.inf, math.nan]:
            self.assertTrue(app.mass_flow(1, 'kg/hr', 'm³/hr', rho).startswith('Error:'))
        self.assertTrue(app.mass_flow(1, 'SCFM (standard ft³/min)', 'ft³/min (CFM)', 1.2).startswith('Error:'))
        for table in [app.MASS_FLOW_MASS, app.MASS_FLOW_VOL]:
            for a in table:
                self.assertAlmostEqual(converted(app.mass_flow(1, a, a, None)), 1)

    def test_viscosity(self):
        for args, expected in [((1, 'Centipoise (cP)', 'Centistoke (cSt)', 1000), 1),
            ((10, 'Centipoise (cP)', 'Centistoke (cSt)', 800), 12.5),
            ((12.5, 'Centistoke (cSt)', 'Centipoise (cP)', 800), 10),
            ((1, 'Poise (P)', 'Centipoise (cP)', None), 100),
            ((1, 'Stoke (St)', 'Centistoke (cSt)', None), 100)]:
            self.assertAlmostEqual(converted(app.viscosity(*args)), expected)
        for rho in [None, 0, -1, math.inf]:
            self.assertTrue(app.viscosity(1, 'Centipoise (cP)', 'Centistoke (cSt)', rho).startswith('Error:'))

    def test_geometry_integrals(self):
        # Independent midpoint integration of horizontal slices.
        n = 20000
        r, length, height = 2, 5, 6
        for frac in [.001, .1, .5, .9, .999]:
            h = 2*r*frac
            dx = h/n
            cyl = sum(2*math.sqrt(max(0,r*r-(r-(i+.5)*dx)**2))*length*dx for i in range(n))
            sphere = sum(math.pi*(r*r-(r-(i+.5)*dx)**2)*dx for i in range(n))
            self.assertAlmostEqual(app.hcy(r,h,length), cyl, delta=2e-5)
            self.assertAlmostEqual(app.sph(r,h), sphere, delta=1e-6)
            h=height*frac; dx=h/n
            conical=sum(math.pi*(r*((i+.5)*dx)/height)**2*dx for i in range(n))
            self.assertAlmostEqual(app.cone(r,height,h), conical, delta=1e-6)
        for f, args, full in [(app.hcy,(r,2*r,length),math.pi*r*r*length),
                              (app.sph,(r,2*r),4*math.pi*r**3/3), (app.cone,(r,height,height),math.pi*r*r*height/3)]:
            self.assertAlmostEqual(f(*args),full)
        self.assertEqual(app.hcy(r,0,length),0)
        self.assertEqual(app.sph(r,0),0)
        self.assertEqual(app.cone(r,height,0),0)

    def test_shallow_horizontal_segment(self):
        for h in [1e-6, 1e-9, 1e-12, 1e-15]:
            actual=app.hcy(1,h,1)
            leading=(4*math.sqrt(2)/3)*h**1.5
            self.assertGreater(actual,0)
            self.assertTrue(math.isclose(actual,leading,rel_tol=2e-7))
            self.assertTrue(math.isclose(app.hcy(1,2-h,1)+actual,math.pi,abs_tol=1e-14))

    def test_all_tanks(self):
        cases=[('Vertical Cylindrical Tank',6*math.pi,3*math.pi),
               ('Horizontal Cylindrical Tank',5*math.pi,2.5*math.pi),
               ('Spherical Tank',4*math.pi/3,2*math.pi/3),
               ('Rectangular Tank',120,60),('Square Tank',96,48),('Conical Tank',2*math.pi,math.pi/4)]
        for t,gross,liquid in cases:
            span=2 if t in ['Horizontal Cylindrical Tank','Spherical Tank'] else 6
            result=app.tank(t,2,5,6,4,span/2,span/2)
            vals=[float(x.replace(',','')) for x in re.findall(r'([\d,.]+) m³',result)]
            self.assertEqual(len(vals),4,result)
            for a,b in zip(vals,[gross,liquid,liquid,gross-liquid]):
                self.assertAlmostEqual(a,b,delta=.000051)
            self.assertTrue(app.tank(t,2,5,6,4,span+1,0).startswith('Error:'))
            self.assertTrue(app.tank(t,2,5,6,4,0,span+1).startswith('Error:'))
            self.assertFalse(app.tank(t,2,5,6,4,0,span).startswith('Error:'))
        self.assertTrue(app.tank('unknown',2,5,6,4,0,0).startswith('Error:'))

    def test_pipeline(self):
        result=app.pipeline(100,'mm',10,'m³/hr','Water')
        self.assertIn('0.3537 m/s', result)
        for diameter, unit in [(0.1,'m'),(10,'cm'),(100/25.4,'inch')]:
            self.assertIn('0.3537 m/s',app.pipeline(diameter,unit,10,'m³/hr','Water'))
        self.assertIn('0.0000 m/s',app.pipeline(100,'mm',0,'L/s','Water'))
        for diameter,q in [(0,1),(-1,1),(1,-1)]:
            self.assertTrue(app.pipeline(diameter,'mm',q,'L/s','Water').startswith('Error:'))

    def test_special_and_invalid(self):
        self.assertIn('34.9706 °API', app.special(.85,'Specific Gravity to API Gravity'))
        self.assertIn('0.850000',app.special(34.970588235294116,'API Gravity to Specific Gravity'))
        self.assertIn('1.0000 %',app.special(10000,'ppm to percentage (%)'))
        for value in [None,'','bad',math.inf,math.nan]:
            self.assertTrue(app.ratio_converter(value,'Bar','Pascal (Pa)',app.PRESSURE).startswith('Error:'))
        self.assertTrue(app.ratio_converter(1e308,'Megapascal (MPa)','Pascal (Pa)',app.PRESSURE).startswith('Error:'))
        self.assertIn('1.6021766e-19',app.ratio_converter(1,'Electronvolt (eV)','Joule (J)',app.ENERGY))


class Interface(unittest.TestCase):
    def test_streamlit(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run()
        self.assertFalse(at.exception)
        keys=[w.key for group in [at.number_input, at.selectbox, at.button] for w in group]
        self.assertNotIn(None,keys)
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(len(at.tabs),14)
        for button in [b for b in at.button if not b.key.startswith("adv_")]:
            at.button(key=button.key).click().run()
            self.assertFalse(at.exception,button.key)
        for tank in ['Horizontal Cylindrical Tank','Spherical Tank','Rectangular Tank','Square Tank','Conical Tank']:
            at.selectbox(key='tank_type').select(tank).run()
            at.button(key='tank_calculate').click().run()
            self.assertFalse(at.exception)
            self.assertFalse(at.error)
        at.number_input(key='vis_value').set_value(10)
        at.number_input(key='vis_density').set_value(800)
        at.button(key='vis_convert').click().run()
        self.assertTrue(any('12.500000' in x.value for x in at.text))


if __name__=='__main__':
    unittest.main(verbosity=2)
