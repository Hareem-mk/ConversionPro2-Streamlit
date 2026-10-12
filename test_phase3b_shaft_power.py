import math
from pathlib import Path
import unittest
from unittest.mock import patch

from app import DENSITY, FLOW
from pump_performance.hydraulic_power import MECHANICAL_HP_W
from pump_performance.shaft_power import shaft_power, shaft_power_from_conditions


def conditions(**changes):
    inputs = dict(density=1000, density_unit='kg/m³', flow=.010, flow_unit='m³/s',
                  head_m=20, efficiency_percent=80, density_factors=DENSITY, flow_factors=FLOW)
    inputs.update(changes)
    return shaft_power_from_conditions(**inputs)


class ShaftPowerTests(unittest.TestCase):
    def test_standard_benchmark(self):
        r = shaft_power(1.96133, 'kW', 80)
        self.assertAlmostEqual(r.hydraulic_watts, 1961.33, places=10)
        self.assertEqual(r.efficiency_percent, 80)
        self.assertAlmostEqual(r.shaft_watts, 2451.6625, places=10)
        self.assertAlmostEqual(r.shaft_kilowatts, 2.4516625, places=12)
        self.assertAlmostEqual(r.shaft_mechanical_hp, 3.28773356873177, places=12)
        self.assertAlmostEqual(r.shaft_mechanical_hp * MECHANICAL_HP_W, r.shaft_watts, places=10)

    def test_100_percent(self):
        r = shaft_power(1.96133, 'kW', 100)
        self.assertEqual(r.shaft_watts, r.hydraulic_watts)
        self.assertAlmostEqual(r.shaft_kilowatts, 1.96133, places=12)

    def test_50_percent(self):
        self.assertAlmostEqual(shaft_power(1.96133, 'kW', 50).shaft_kilowatts, 3.92266, places=12)

    def test_zero_hydraulic_power(self):
        for unit in ('W', 'kW', 'Mechanical hp'):
            r = shaft_power(0, unit, 80)
            self.assertEqual((r.shaft_watts, r.shaft_kilowatts, r.shaft_mechanical_hp), (0, 0, 0))

    def test_zero_efficiency_before_division(self):
        # A valid or zero power must never allow division by zero; efficiency
        # is checked before even accepting hydraulic input.
        for power in (1961.33, 0, None):
            with self.subTest(power=power), self.assertRaisesRegex(ValueError, 'Pump efficiency'):
                shaft_power(power, 'W', 0)

    def test_over_100_efficiency(self):
        for efficiency in (100.000001, 105, 1e308):
            with self.subTest(efficiency=efficiency), self.assertRaisesRegex(ValueError, 'no more than 100'):
                shaft_power(1961.33, 'W', efficiency)

    def test_invalid_efficiency(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Pump efficiency'):
                shaft_power(1961.33, 'W', value)

    def test_power_unit_equivalence(self):
        for unit, power in [('W', 1961.33), ('kW', 1.96133),
                            ('Mechanical hp', 1961.33/MECHANICAL_HP_W)]:
            with self.subTest(unit=unit):
                self.assertAlmostEqual(shaft_power(power, unit, 80).shaft_watts, 2451.6625, places=10)

    def test_invalid_hydraulic_power(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                shaft_power(value, 'W', 80)

    def test_missing_or_unknown_power_unit(self):
        for unit in (None, '', 'hp', 'unsupported'):
            for power in (0, 1961.33):
                with self.subTest(unit=unit, power=power), self.assertRaisesRegex(ValueError, 'Select a supported'):
                    shaft_power(power, unit, 80)

    def test_numeric_range(self):
        for power, unit, efficiency in [(1e308, 'kW', 80), (1e308, 'W', 1),
                                         (1961.33, 'W', 5e-324), (5e-324, 'W', 100)]:
            with self.subTest(power=power, unit=unit, efficiency=efficiency), self.assertRaises(ValueError):
                shaft_power(power, unit, efficiency)
        self.assertEqual(shaft_power(0, 'W', 1e-300).shaft_watts, 0)
        self.assertTrue(math.isfinite(shaft_power(1, 'W', .001).shaft_watts))

    def test_conditions_benchmark(self):
        r = conditions()
        self.assertAlmostEqual(r.hydraulic_watts, 1961.33, places=10)
        self.assertAlmostEqual(r.shaft_watts, 2451.6625, places=10)
        self.assertAlmostEqual(r.shaft_kilowatts, 2.4516625, places=12)

    def test_conditions_reuses_phase3a(self):
        from pump_performance import shaft_power as module
        with patch.object(module, 'hydraulic_power', wraps=module.hydraulic_power) as kernel:
            conditions()
            kernel.assert_called_once()
        with patch.object(module, 'hydraulic_power') as kernel:
            with self.assertRaisesRegex(ValueError, 'Pump efficiency'):
                conditions(efficiency_percent=0)
            kernel.assert_not_called()

    def test_conditions_unit_equivalence(self):
        for unit, factor in FLOW.items():
            with self.subTest(unit=unit):
                self.assertAlmostEqual(conditions(flow=.010/factor, flow_unit=unit).shaft_watts,
                                       2451.6625, places=10)
        for unit, factor in DENSITY.items():
            with self.subTest(unit=unit):
                self.assertAlmostEqual(conditions(density=1000/factor, density_unit=unit).shaft_watts,
                                       2451.6625, places=10)

    def test_conditions_zero_flow_or_head(self):
        self.assertEqual(conditions(flow=0).shaft_watts, 0)
        self.assertEqual(conditions(head_m=0).shaft_watts, 0)

    def test_conditions_validation(self):
        for values in [dict(density=0), dict(density=-1), dict(flow=-1), dict(head_m=-1),
                       dict(flow_unit=None), dict(density_unit=None), dict(head_m=None),
                       dict(flow=math.inf), dict(density=math.nan), dict(efficiency_percent=105)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                conditions(**values)

    def test_efficiency_sensitivity(self):
        low = shaft_power(1000, 'W', 50)
        high = shaft_power(1000, 'W', 80)
        self.assertGreater(low.shaft_watts, high.shaft_watts)
        self.assertGreater(high.shaft_watts, high.hydraulic_watts)


class ShaftPowerAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill_power(self, at):
        at.selectbox(key='p3b_power_unit').select('kW')
        at.number_input(key='p3b_power').set_value(1.96133)
        at.number_input(key='p3b_efficiency').set_value(80)
        return at.button(key='p3b_calculate').click().run()

    def fill_conditions(self, at):
        at.selectbox(key='p3b_method').select('From Flow, Head and Density').run()
        at.selectbox(key='p3b_density_unit').select('kg/m³')
        at.selectbox(key='p3b_flow_unit').select('m³/s')
        for key, value in [('density', 1000), ('flow', .010), ('head', 20), ('efficiency', 80)]:
            at.number_input(key='p3b_'+key).set_value(value)
        return at.button(key='p3b_calculate').click().run()

    def result_text(self, at):
        return '\n'.join(t.value for t in at.text if 'Pump Shaft / Brake Power\n' in t.value)

    def test_mode_a_benchmark_and_labels(self):
        at = self.fill_power(self.app())
        self.assertFalse(at.exception)
        self.assertFalse(at.error)
        self.assertIn('Hydraulic Power\n1961.33 W\n1.96133 kW', self.result_text(at))
        self.assertIn('Pump Efficiency: 80%', self.result_text(at))
        self.assertIn('2451.6625 W\n2.4516625 kW\n3.28773356873 Mechanical hp', self.result_text(at))
        self.assertEqual(at.number_input(key='p3b_power').label, 'Hydraulic Power (kW)')
        self.assertEqual(at.number_input(key='p3b_efficiency').label, 'Pump Efficiency (%)')
        self.assertTrue(any('Brake power and shaft power refer here' in w.value for w in at.caption))
        self.assertTrue(any('Motor losses will be handled separately in Phase 3C' in w.value for w in at.caption))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3b_')])
        self.assertEqual(len(at.tabs), 15)
        self.assertTrue(any(w.label == '3B — Pump Shaft / Brake Power' for w in at.expander))
        keys = [w.key for group in [at.number_input, at.selectbox, at.button, at.checkbox] for w in group]
        self.assertEqual(len(keys), len(set(keys)))

    def test_required_inputs_and_no_defaults(self):
        at = self.app()
        self.assertIsNone(at.number_input(key='p3b_efficiency').value)
        self.assertIsNone(at.number_input(key='p3b_power').value)
        self.assertIsNone(at.selectbox(key='p3b_power_unit').value)
        at.button(key='p3b_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p3b_efficiency').set_value(80)
        at.number_input(key='p3b_power').set_value(0)
        at.button(key='p3b_calculate').click().run()
        self.assertTrue(at.error)
        self.assertIn('Select a supported hydraulic power unit', at.error[0].value)
        self.assertFalse(self.result_text(at))
        self.assertFalse(at.exception)

    def test_efficiency_limits_and_zero_power(self):
        at = self.fill_power(self.app())
        for efficiency, expected in [(100, '1.96133 kW'), (50, '3.92266 kW')]:
            at.number_input(key='p3b_efficiency').set_value(efficiency)
            at.button(key='p3b_calculate').click().run()
            self.assertIn(expected, self.result_text(at).split('Pump Shaft / Brake Power\n')[1])
            self.assertFalse(at.error)
        for efficiency in (0, 105):
            at.number_input(key='p3b_efficiency').set_value(efficiency)
            at.button(key='p3b_calculate').click().run()
            self.assertTrue(at.error)
            self.assertIn('Pump efficiency', at.error[0].value)
            self.assertFalse(self.result_text(at))
            self.assertFalse(at.exception)
        at.number_input(key='p3b_power').set_value(0)
        at.number_input(key='p3b_efficiency').set_value(80)
        at.button(key='p3b_calculate').click().run()
        self.assertIn('Pump Shaft / Brake Power\n0 W\n0 kW\n0 Mechanical hp', self.result_text(at))

    def test_mode_a_unit_equivalence(self):
        at = self.fill_power(self.app())
        for unit, power in [('W', 1961.33), ('Mechanical hp', 1961.33/MECHANICAL_HP_W)]:
            at.selectbox(key='p3b_power_unit').select(unit)
            at.number_input(key='p3b_power').set_value(power)
            at.button(key='p3b_calculate').click().run()
            self.assertIn('2451.6625 W', self.result_text(at))
            self.assertEqual(at.number_input(key='p3b_power').label, f'Hydraulic Power ({unit})')
            self.assertFalse(at.exception)

    def test_mode_b_benchmark_and_zero_cases(self):
        at = self.fill_conditions(self.app())
        self.assertIn('Hydraulic Power\n1961.33 W', self.result_text(at))
        self.assertIn('Pump Shaft / Brake Power\n2451.6625 W', self.result_text(at))
        self.assertEqual(at.number_input(key='p3b_density').label, 'Fluid Density (kg/m³)')
        self.assertEqual(at.number_input(key='p3b_flow').label, 'Volumetric Flow Rate (m³/s)')
        self.assertEqual(at.number_input(key='p3b_head').label, 'Pump Head (m)')
        for key in ('flow', 'head'):
            at.number_input(key='p3b_'+key).set_value(0)
            at.button(key='p3b_calculate').click().run()
            self.assertIn('Pump Shaft / Brake Power\n0 W', self.result_text(at))
            at.number_input(key='p3b_'+key).set_value(.010 if key == 'flow' else 20)
        at.selectbox(key='p3b_flow_unit').select('m³/hr')
        at.number_input(key='p3b_flow').set_value(36)
        at.button(key='p3b_calculate').click().run()
        self.assertIn('2451.6625 W', self.result_text(at))
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_stale_results_and_mode_switch(self):
        at = self.fill_power(self.app())
        at.number_input(key='p3b_efficiency').set_value(50).run()
        self.assertFalse(self.result_text(at))
        at.button(key='p3b_calculate').click().run()
        self.assertIn('3922.66 W', self.result_text(at))
        at.selectbox(key='p3b_method').select('From Flow, Head and Density').run()
        self.assertFalse(self.result_text(at))
        at.button(key='p3b_calculate').click().run()
        self.assertTrue(at.error)
        self.fill_conditions(at)
        at.number_input(key='p3b_head').set_value(40).run()
        self.assertFalse(self.result_text(at))
        at.selectbox(key='p3b_method').select('From Hydraulic Power').run()
        self.assertFalse(self.result_text(at))
        self.assertFalse(at.exception)

    def test_mode_b_efficiency_errors(self):
        at = self.fill_conditions(self.app())
        for efficiency in (0, 105):
            at.number_input(key='p3b_efficiency').set_value(efficiency)
            at.button(key='p3b_calculate').click().run()
            self.assertTrue(at.error)
            self.assertIn('Pump efficiency', at.error[0].value)
            self.assertFalse(self.result_text(at))
            self.assertFalse(at.exception)

    def test_phase3a_still_independent(self):
        at = self.fill_power(self.app())
        at.selectbox(key='p3a_density_unit').select('kg/m³')
        at.selectbox(key='p3a_flow_unit').select('m³/s')
        for key, value in [('density', 1000), ('flow', .010), ('head', 20)]:
            at.number_input(key='p3a_'+key).set_value(value)
        at.button(key='p3a_calculate').click().run()
        self.assertTrue(any('Hydraulic Power\n1961.33 W\n1.96133 kW' in w.value for w in at.text))
        self.assertFalse(self.result_text(at))
        self.assertEqual(at.number_input(key='p3b_power').value, 1.96133)
        self.assertFalse(at.exception)
