import math
from pathlib import Path
import unittest
from dataclasses import asdict
from piping_hydraulics.roughness import RECORDS, roughness_to_si, roughness_displays, roughness_ratio


class RoughnessTests(unittest.TestCase):
    def test_record_integrity(self):
        self.assertEqual(len(RECORDS),4)
        self.assertEqual(len({r.id for r in RECORDS}),4)
        expected={'Cast Iron':(.85,.00025908),'Galvanized Iron':(.5,.0001524),
                  'Plastic':(.005,.000001524),'Steel':(.15,.00004572)}
        for r in RECORDS:
            self.assertEqual((r.original_value,r.epsilon_m),expected[r.material])
            self.assertEqual(r.condition,'New pipe')
            self.assertAlmostEqual(roughness_to_si(r.original_value,r.original_units),r.epsilon_m,places=15)

    def test_metadata(self):
        for r in RECORDS:
            self.assertTrue(all(v is not None and v!='' for v in asdict(r).values()))
            self.assertIn('US EPA',r.source)
            self.assertIn('2.2',r.edition)
            self.assertIn('Table 3.2',r.location)
            self.assertIn('page 18',r.location)
            self.assertTrue(r.url.startswith('https://usepa.github.io/'))
            self.assertIn('representative',r.notes)

    def test_manual_benchmark(self):
        e=roughness_to_si(.045,'mm')
        self.assertAlmostEqual(e,.000045,places=15)
        self.assertAlmostEqual(roughness_ratio(e,.1),.00045,places=15)
        self.assertNotIn(e,[r.epsilon_m for r in RECORDS])

    def test_units(self):
        for v,u in [(.000045,'m'),(.045,'mm'),(45,'µm')]:
            self.assertAlmostEqual(roughness_to_si(v,u),.000045,places=15)
        displays=roughness_displays(.000045)
        self.assertAlmostEqual(displays['mm'],.045)
        self.assertAlmostEqual(displays['µm'],45)

    def test_zero(self):
        for u in ['m','mm','µm']:
            self.assertEqual(roughness_to_si(0,u),0)
        self.assertEqual(roughness_ratio(0,.1),0)
        self.assertTrue(all(v==0 for v in roughness_displays(0).values()))

    def test_invalid_roughness(self):
        for bad in [None,'','bad',True,-1,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):roughness_to_si(bad,'m')
            with self.assertRaises(ValueError):roughness_ratio(bad,.1)
            with self.assertRaises(ValueError):roughness_displays(bad)
        for u in [None,'C','Manning n','unknown']:
            with self.assertRaises(ValueError):roughness_to_si(1,u)

    def test_invalid_diameter(self):
        for bad in [None,'','bad',True,0,-1,math.nan,math.inf]:
            with self.assertRaises(ValueError):roughness_ratio(.000045,bad)
            with self.assertRaises(ValueError):roughness_ratio(0,bad)

    def test_ratio_and_range(self):
        self.assertAlmostEqual(roughness_ratio(.000045,.2),.000225)
        self.assertEqual(roughness_ratio(.1,1),.1) # Do not clamp to friction correlation domain.
        for fn,args in [(roughness_to_si,(5e-324,'µm')),(roughness_displays,(1e308,)),
                        (roughness_ratio,(1e308,1e-308))]:
            with self.assertRaises(ValueError):fn(*args)

    def test_ui(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),15)
        self.assertIsNone(at.selectbox(key='p2c_source').value)
        at.button(key='p2c_calculate').click().run()
        self.assertTrue(at.error)
        for r in RECORDS:
            at.selectbox(key='p2c_source').select(f'{r.material} — {r.condition}').run()
            at.button(key='p2c_calculate').click().run()
            self.assertFalse(at.error)
            self.assertFalse(at.exception)
            self.assertTrue(any(f'{r.epsilon_m:.12g} m' in x.value for x in at.text))
            self.assertTrue(any('Table 3.2' in x.value for x in at.caption))
        at.selectbox(key='p2c_source').select('Manual Roughness').run()
        self.assertIsNone(at.number_input(key='p2c_manual').value)
        at.button(key='p2c_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p2c_manual').set_value(.045)
        at.selectbox(key='p2c_unit').select('mm')
        at.number_input(key='p2c_diameter').set_value(.1)
        at.button(key='p2c_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('0.00045 (dimensionless)' in x.value for x in at.text))
        at.number_input(key='p2c_manual').set_value(0)
        at.button(key='p2c_calculate').click().run()
        self.assertTrue(any('Explicit ε = 0' in x.value for x in at.info))
        at.number_input(key='p2c_diameter').set_value(0)
        at.button(key='p2c_calculate').click().run()
        self.assertTrue(at.error)
        at.selectbox(key='p2c_source').select('Steel — New pipe').run()
        self.assertFalse(any('Relative roughness ε/D:' in x.value for x in at.text))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.text_input] for w in group]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertEqual(at.number_input(key='adv_friction_roughness').value,None)
        self.assertFalse(at.exception)
