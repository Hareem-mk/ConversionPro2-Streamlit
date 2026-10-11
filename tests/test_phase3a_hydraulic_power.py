import math
from pathlib import Path
import unittest

from app import DENSITY, FLOW
from pump_performance.hydraulic_power import hydraulic_power, MECHANICAL_HP_W


def calculate(**changes):
    inputs = dict(density=1000, density_unit='kg/m³', flow=.010,
                  flow_unit='m³/s', head_m=20, density_factors=DENSITY, flow_factors=FLOW)
    inputs.update(changes)
    return hydraulic_power(**inputs)


class HydraulicPowerTests(unittest.TestCase):
    def test_benchmark(self):
        r = calculate()
        self.assertAlmostEqual(r.watts, 1961.33, places=10)
        self.assertAlmostEqual(r.kilowatts, 1.96133, places=12)
        self.assertAlmostEqual(r.mechanical_hp, 2.6301868549854164, places=12)
        self.assertEqual(MECHANICAL_HP_W, 745.6998715822702)
        self.assertAlmostEqual(r.mechanical_hp * MECHANICAL_HP_W, r.watts, places=10)

    def test_zero_flow(self):
        r = calculate(flow=0)
        self.assertEqual((r.watts, r.kilowatts, r.mechanical_hp), (0, 0, 0))

    def test_zero_head(self):
        self.assertEqual(calculate(head_m=0).watts, 0)

    def test_flow_equivalence(self):
        for unit in FLOW:
            with self.subTest(unit=unit):
                self.assertAlmostEqual(calculate(flow=.010/FLOW[unit], flow_unit=unit).watts,
                                       1961.33, places=10)
        self.assertAlmostEqual(calculate(flow=36, flow_unit='m³/hr').watts, 1961.33, places=10)

    def test_density_effect(self):
        self.assertAlmostEqual(calculate(density=800).watts, 1569.064, places=10)

    def test_head_effect(self):
        self.assertAlmostEqual(calculate(head_m=40).watts, 3922.66, places=10)

    def test_density_units(self):
        for unit, factor in DENSITY.items():
            with self.subTest(unit=unit):
                self.assertAlmostEqual(calculate(density=1000/factor, density_unit=unit).watts,
                                       1961.33, places=10)

    def test_invalid_density(self):
        for value in (None, '', 'bad', True, 0, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(density=value)

    def test_invalid_flow(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(flow=value)

    def test_invalid_head(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(head_m=value)

    def test_missing_and_unknown_units(self):
        for unit in (None, '', 'unsupported'):
            for values in (dict(density_unit=unit), dict(flow_unit=unit), dict(flow=0, flow_unit=unit)):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    calculate(**values)

    def test_invalid_factors(self):
        for factor in (0, -1, True, math.nan, math.inf):
            for values in (dict(density_factors={'kg/m³': factor}),
                           dict(flow_factors={'m³/s': factor}),
                           dict(flow=0, flow_factors={'m³/s': factor})):
                with self.subTest(values=values), self.assertRaises(ValueError):
                    calculate(**values)

    def test_numeric_range(self):
        for values in (dict(density=1e308), dict(flow=1e308), dict(head_m=1e308),
                       dict(flow=1e-300, head_m=1e-300),
                       dict(density=1e308, density_unit='g/cm³')):
            with self.subTest(values=values), self.assertRaises(ValueError):
                calculate(**values)
        self.assertEqual(calculate(density=1e308, head_m=0).watts, 0)
        self.assertEqual(calculate(density=1e308, flow=0).watts, 0)


class HydraulicPowerAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self, at):
        at.selectbox(key='p3a_density_unit').select('kg/m³')
        at.selectbox(key='p3a_flow_unit').select('m³/s')
        for key, value in [('density', 1000), ('flow', .010), ('head', 20)]:
            at.number_input(key='p3a_'+key).set_value(value)
        return at.button(key='p3a_calculate').click().run()

    def test_ui_benchmark_and_guidance(self):
        at = self.fill(self.app())
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertEqual(len(at.tabs), 15)
        self.assertTrue(any(e.label == '3A — Hydraulic Power' for e in at.expander))
        self.assertEqual(at.number_input(key='p3a_density').label, 'Fluid Density (kg/m³)')
        self.assertEqual(at.number_input(key='p3a_flow').label, 'Volumetric Flow Rate (m³/s)')
        self.assertEqual(at.number_input(key='p3a_head').label, 'Pump Head (m)')
        self.assertTrue(any('1961.33 W\n1.96133 kW\n2.63018685499 Mechanical hp' in t.value for t in at.text))
        self.assertTrue(any('does not include pump or motor efficiency losses' in t.value for t in at.info))
        self.assertTrue(any('handled separately in Phase 3B' in t.value for t in at.caption))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3a_')])
        keys = [w.key for group in [at.number_input, at.selectbox, at.button, at.checkbox] for w in group]
        self.assertEqual(len(keys), len(set(keys)))

    def test_ui_required_inputs(self):
        at = self.app()
        self.assertIsNone(at.selectbox(key='p3a_flow_unit').value)
        self.assertIsNone(at.selectbox(key='p3a_density_unit').value)
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(at.error)
        self.fill(at)
        at.number_input(key='p3a_density').set_value(0)
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(at.error)
        self.assertFalse(any(t.value.startswith('Hydraulic Power\n') for t in at.text))
        self.assertFalse(at.exception)

    def test_ui_zero_and_equivalence(self):
        at = self.fill(self.app())
        at.number_input(key='p3a_flow').set_value(0)
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(any('Hydraulic Power\n0 W\n0 kW\n0 Mechanical hp' in t.value for t in at.text))
        at.number_input(key='p3a_flow').set_value(.010)
        at.number_input(key='p3a_head').set_value(0)
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(any('Hydraulic Power\n0 W' in t.value for t in at.text))
        at.number_input(key='p3a_head').set_value(20)
        at.selectbox(key='p3a_flow_unit').select('m³/hr')
        at.number_input(key='p3a_flow').set_value(36)
        at.button(key='p3a_calculate').click().run()
        self.assertEqual(at.number_input(key='p3a_flow').label, 'Volumetric Flow Rate (m³/hr)')
        self.assertTrue(any('1961.33 W' in t.value for t in at.text))
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_ui_stale_result(self):
        at = self.fill(self.app())
        at.number_input(key='p3a_head').set_value(40).run()
        self.assertFalse(any(t.value.startswith('Hydraulic Power\n') for t in at.text))
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(any('3922.66 W' in t.value for t in at.text))
        at.selectbox(key='p3a_flow_unit').select('L/s').run()
        self.assertFalse(any(t.value.startswith('Hydraulic Power\n') for t in at.text))
