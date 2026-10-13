import math
from pathlib import Path
import unittest
from unittest.mock import patch
from app import FLOW, DENSITY
from pump_performance.shaft_power import POWER_FACTORS
from pump_performance.motor_power import motor_power, motor_power_from_conditions


def conditions(**changes):
    values = dict(density=1000, density_unit='kg/m³', flow=.01, flow_unit='m³/s',
                  head_m=20, pump_efficiency_percent=80, motor_efficiency_percent=90,
                  density_factors=DENSITY, flow_factors=FLOW)
    values.update(changes)
    return motor_power_from_conditions(**values)


class MotorPowerTests(unittest.TestCase):
    def test_benchmark(self):
        r = motor_power(2.4516625, 'kW', 90)
        self.assertAlmostEqual(r.input_watts, 2724.069444444444, places=10)
        self.assertAlmostEqual(r.input_kilowatts, 2.724069444444444, places=12)
        self.assertAlmostEqual(r.input_mechanical_hp, 3.653037298590855, places=12)
        self.assertEqual(POWER_FACTORS['Mechanical hp'], 745.6998715822702)
        self.assertAlmostEqual(r.input_mechanical_hp * POWER_FACTORS['Mechanical hp'], r.input_watts, places=10)

    def test_100_percent(self):
        r = motor_power(2.4516625, 'kW', 100)
        self.assertEqual(r.input_watts, r.shaft_watts)
        self.assertAlmostEqual(r.input_kilowatts, 2.4516625, places=12)

    def test_50_percent(self):
        self.assertAlmostEqual(motor_power(2.4516625, 'kW', 50).input_kilowatts, 4.903325, places=12)

    def test_zero_power(self):
        for unit in POWER_FACTORS:
            r = motor_power(0, unit, 90)
            self.assertEqual((r.input_watts, r.input_kilowatts, r.input_mechanical_hp), (0, 0, 0))

    def test_zero_efficiency_before_division(self):
        for value in (2451.6625, 0, None):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Motor efficiency'):
                motor_power(value, 'W', 0)

    def test_over_100(self):
        for value in (100.0001, 105, 1e308):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'no more than 100'):
                motor_power(2451.6625, 'W', value)

    def test_invalid_efficiencies(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'Motor efficiency'):
                motor_power(2451.6625, 'W', value)

    def test_power_units(self):
        for unit, factor in POWER_FACTORS.items():
            self.assertAlmostEqual(motor_power(2451.6625/factor, unit, 90).input_watts,
                                   2724.069444444444, places=10)

    def test_invalid_power(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                motor_power(value, 'W', 90)

    def test_missing_units(self):
        for unit in (None, '', 'hp', 'unsupported'):
            for value in (0, 2451.6625):
                with self.subTest(unit=unit, value=value), self.assertRaises(ValueError):
                    motor_power(value, unit, 90)

    def test_range(self):
        for value, unit, efficiency in [(1e308, 'kW', 90), (1e308, 'W', 1),
                                         (2451.6625, 'W', 5e-324), (5e-324, 'W', 100)]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                motor_power(value, unit, efficiency)
        self.assertEqual(motor_power(0, 'W', 1e-300).input_watts, 0)

    def test_chain(self):
        r = conditions()
        self.assertAlmostEqual(r.hydraulic_watts, 1961.33, places=10)
        self.assertAlmostEqual(r.shaft_watts, 2451.6625, places=10)
        self.assertAlmostEqual(r.input_watts, 2724.069444444444, places=10)
        self.assertEqual((r.pump_efficiency_percent, r.motor_efficiency_percent), (80, 90))

    def test_shared_kernels(self):
        from pump_performance import motor_power as module
        with patch.object(module, 'shaft_power_from_conditions', wraps=module.shaft_power_from_conditions) as kernel:
            conditions()
            kernel.assert_called_once()
        with patch.object(module, 'pump_efficiency', wraps=module.pump_efficiency) as validator:
            motor_power(2451.6625, 'W', 90)
            validator.assert_called_once_with(90)
        with patch.object(module, 'shaft_power_from_conditions') as kernel:
            with self.assertRaisesRegex(ValueError, 'Motor efficiency'):
                conditions(motor_efficiency_percent=0)
            kernel.assert_not_called()

    def test_chain_units_and_zero(self):
        for unit, factor in FLOW.items():
            self.assertAlmostEqual(conditions(flow=.01/factor, flow_unit=unit).input_watts,
                                   2724.069444444444, places=10)
        for unit, factor in DENSITY.items():
            self.assertAlmostEqual(conditions(density=1000/factor, density_unit=unit).input_watts,
                                   2724.069444444444, places=10)
        self.assertEqual(conditions(flow=0).input_watts, 0)
        self.assertEqual(conditions(head_m=0).input_watts, 0)

    def test_chain_invalid(self):
        for values in [dict(density=0), dict(flow=-1), dict(head_m=-1), dict(flow_unit=None),
                       dict(density_unit=None), dict(pump_efficiency_percent=0),
                       dict(pump_efficiency_percent=105), dict(pump_efficiency_percent=-1),
                       dict(motor_efficiency_percent=0), dict(motor_efficiency_percent=105)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                conditions(**values)


class MotorPowerAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self, at):
        at.selectbox(key='p3c_power_unit').select('kW')
        at.number_input(key='p3c_power').set_value(2.4516625)
        at.number_input(key='p3c_motor_efficiency').set_value(90)
        return at.button(key='p3c_calculate').click().run()

    def fill_chain(self, at):
        at.selectbox(key='p3c_method').select('From Hydraulic Conditions').run()
        at.selectbox(key='p3c_density_unit').select('kg/m³')
        at.selectbox(key='p3c_flow_unit').select('m³/s')
        for key, value in [('density', 1000), ('flow', .01), ('head', 20),
                           ('pump_efficiency', 80), ('motor_efficiency', 90)]:
            at.number_input(key='p3c_'+key).set_value(value)
        return at.button(key='p3c_calculate').click().run()

    def result(self, at):
        return '\n'.join(t.value for t in at.text if 'Motor Input Power\n' in t.value)

    def test_benchmark_and_labels(self):
        at = self.fill(self.app())
        self.assertIn('Motor Input Power\n2724.06944444 W\n2.72406944444 kW\n3.65303729859 Mechanical hp', self.result(at))
        self.assertEqual(at.number_input(key='p3c_power').label, 'Pump Shaft / Brake Power (kW)')
        self.assertEqual(at.number_input(key='p3c_motor_efficiency').label, 'Motor Efficiency (%)')
        self.assertTrue(any('Motor input power is the power supplied to the motor.' in w.value for w in at.info))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3c_')])
        self.assertEqual(len(at.tabs), 15)
        self.assertTrue(any(w.label == '3C — Motor Input Power' for w in at.expander))
        keys = [w.key for group in [at.number_input, at.selectbox, at.button, at.checkbox] for w in group]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertFalse(at.exception)
        self.assertFalse(at.error)

    def test_no_defaults_required(self):
        at = self.app()
        self.assertIsNone(at.number_input(key='p3c_motor_efficiency').value)
        self.assertIsNone(at.number_input(key='p3c_power').value)
        self.assertIsNone(at.selectbox(key='p3c_power_unit').value)
        at.button(key='p3c_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p3c_motor_efficiency').set_value(90)
        at.number_input(key='p3c_power').set_value(0)
        at.button(key='p3c_calculate').click().run()
        self.assertIn('Select a supported shaft power unit', at.error[0].value)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)

    def test_efficiency_cases(self):
        at = self.fill(self.app())
        for efficiency, watts in [(100, '2451.6625 W'), (50, '4903.325 W')]:
            at.number_input(key='p3c_motor_efficiency').set_value(efficiency)
            at.button(key='p3c_calculate').click().run()
            self.assertIn(watts, self.result(at).split('Motor Input Power\n')[1])
        for efficiency in (0, 105):
            at.number_input(key='p3c_motor_efficiency').set_value(efficiency)
            at.button(key='p3c_calculate').click().run()
            self.assertIn('Motor efficiency', at.error[0].value)
            self.assertFalse(self.result(at))
            self.assertFalse(at.exception)
        at.number_input(key='p3c_motor_efficiency').set_value(90)
        at.number_input(key='p3c_power').set_value(0)
        at.button(key='p3c_calculate').click().run()
        self.assertIn('Motor Input Power\n0 W\n0 kW\n0 Mechanical hp', self.result(at))

    def test_unit_equivalence(self):
        at = self.fill(self.app())
        for unit, factor in POWER_FACTORS.items():
            at.selectbox(key='p3c_power_unit').select(unit)
            at.number_input(key='p3c_power').set_value(2451.6625/factor)
            at.button(key='p3c_calculate').click().run()
            self.assertIn('2724.06944444 W', self.result(at))
            self.assertEqual(at.number_input(key='p3c_power').label, f'Pump Shaft / Brake Power ({unit})')
            self.assertFalse(at.exception)

    def test_chain_labels_and_benchmark(self):
        at = self.fill_chain(self.app())
        for key, label in [('density','Fluid Density (kg/m³)'), ('flow','Volumetric Flow Rate (m³/s)'),
                           ('head','Pump Head (m)'), ('pump_efficiency','Pump Efficiency (%)')]:
            self.assertEqual(at.number_input(key='p3c_'+key).label, label)
        self.assertIn('Hydraulic Power\n1961.33 W', self.result(at))
        self.assertIn('Pump Shaft / Brake Power\n2451.6625 W', self.result(at))
        self.assertIn('Motor Input Power\n2724.06944444 W', self.result(at))
        self.assertIn('Pump Efficiency: 80%', self.result(at))
        self.assertIn('Motor Efficiency: 90%', self.result(at))
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_chain_validation_and_zero(self):
        at = self.fill_chain(self.app())
        for key in ('pump_efficiency', 'motor_efficiency'):
            for efficiency in (0, 105):
                at.number_input(key='p3c_'+key).set_value(efficiency)
                at.button(key='p3c_calculate').click().run()
                self.assertTrue(at.error)
                self.assertFalse(self.result(at))
                self.assertFalse(at.exception)
            at.number_input(key='p3c_'+key).set_value(80 if key == 'pump_efficiency' else 90)
        at.number_input(key='p3c_flow').set_value(0)
        at.button(key='p3c_calculate').click().run()
        self.assertIn('Motor Input Power\n0 W', self.result(at))

    def test_stale_result_and_switch(self):
        at = self.fill(self.app())
        at.number_input(key='p3c_motor_efficiency').set_value(50).run()
        self.assertFalse(self.result(at))
        at.button(key='p3c_calculate').click().run()
        self.assertIn('4903.325 W', self.result(at))
        at.selectbox(key='p3c_method').select('From Hydraulic Conditions').run()
        self.assertFalse(self.result(at))
        self.assertIsNone(at.number_input(key='p3c_pump_efficiency').value)
        at.button(key='p3c_calculate').click().run()
        self.assertTrue(at.error)
        self.fill_chain(at)
        at.number_input(key='p3c_head').set_value(40).run()
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)
