import math
from pathlib import Path
import unittest
from unittest.mock import patch

from app import FLOW, DENSITY
from pump_performance.shaft_power import POWER_FACTORS
from pump_performance.pump_efficiency import calculate_pump_efficiency, pump_efficiency_from_conditions


def calculate(**changes):
    inputs = dict(hydraulic_value=1.96133, hydraulic_unit='kW', shaft_value=2.4516625, shaft_unit='kW')
    inputs.update(changes)
    return calculate_pump_efficiency(**inputs)


def conditions(**changes):
    inputs = dict(density=1000, density_unit='kg/m³', flow=.01, flow_unit='m³/s', head_m=20,
                  shaft_value=2.4516625, shaft_unit='kW', density_factors=DENSITY, flow_factors=FLOW)
    inputs.update(changes)
    return pump_efficiency_from_conditions(**inputs)


class PumpEfficiencyTests(unittest.TestCase):
    def test_80_percent_benchmark(self):
        r = calculate()
        self.assertAlmostEqual(r.hydraulic_watts, 1961.33, places=10)
        self.assertAlmostEqual(r.shaft_watts, 2451.6625, places=10)
        self.assertAlmostEqual(r.ratio, .8, places=14)
        self.assertAlmostEqual(r.percent, 80, places=12)

    def test_100_percent(self):
        r = calculate(hydraulic_value=2, shaft_value=2)
        self.assertEqual((r.ratio, r.percent), (1, 100))

    def test_50_percent(self):
        r = calculate(hydraulic_value=1, shaft_value=2)
        self.assertEqual((r.ratio, r.percent), (.5, 50))

    def test_zero_hydraulic(self):
        r = calculate(hydraulic_value=0, shaft_value=2)
        self.assertEqual((r.ratio, r.percent), (0, 0))

    def test_zero_shaft_before_division(self):
        for hydraulic in (0, 1, None):
            with self.subTest(hydraulic=hydraulic), self.assertRaisesRegex(ValueError, 'greater than zero'):
                calculate(hydraulic_value=hydraulic, shaft_value=0)

    def test_excess_hydraulic_rejected(self):
        for hydraulic in (2.5, math.nextafter(2, math.inf)):
            with self.subTest(hydraulic=hydraulic), self.assertRaisesRegex(ValueError, 'Hydraulic power cannot exceed pump shaft power'):
                calculate(hydraulic_value=hydraulic, shaft_value=2)

    def test_watt_kilowatt_equivalence(self):
        r = calculate(hydraulic_value=1961.33, hydraulic_unit='W', shaft_value=2451.6625, shaft_unit='W')
        self.assertEqual(r.percent, calculate().percent)

    def test_hp_and_mixed_unit_equivalence(self):
        self.assertEqual(POWER_FACTORS['Mechanical hp'], 745.6998715822702)
        for h_unit, h_factor in POWER_FACTORS.items():
            for s_unit, s_factor in POWER_FACTORS.items():
                with self.subTest(h_unit=h_unit, s_unit=s_unit):
                    r = calculate(hydraulic_value=1961.33/h_factor, hydraulic_unit=h_unit,
                                  shaft_value=2451.6625/s_factor, shaft_unit=s_unit)
                    self.assertAlmostEqual(r.percent, 80, places=12)

    def test_invalid_hydraulic(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(hydraulic_value=value)

    def test_invalid_shaft(self):
        for value in (None, '', 'bad', True, -1, math.nan, math.inf, -math.inf):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate(shaft_value=value)

    def test_explicit_units_required(self):
        for unit in (None, '', 'hp', 'unsupported'):
            for changes in (dict(hydraulic_unit=unit), dict(shaft_unit=unit),
                            dict(hydraulic_value=0, hydraulic_unit=unit)):
                with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, 'Select a supported'):
                    calculate(**changes)

    def test_numeric_range(self):
        for changes in (dict(hydraulic_value=1e308), dict(shaft_value=1e308),
                        dict(hydraulic_value=5e-324, hydraulic_unit='W', shaft_value=1e308, shaft_unit='W')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                calculate(**changes)
        self.assertEqual(calculate(hydraulic_value=0, shaft_value=1e308, shaft_unit='W').percent, 0)
        self.assertEqual(calculate(hydraulic_value=5e-324, hydraulic_unit='W', shaft_value=5e-324, shaft_unit='W').percent, 100)

    def test_phase3a_conditions_benchmark(self):
        r = conditions()
        self.assertAlmostEqual(r.hydraulic_watts, 1961.33, places=10)
        self.assertAlmostEqual(r.ratio, .8, places=14)
        self.assertAlmostEqual(r.percent, 80, places=12)

    def test_conditions_reuse_kernel(self):
        from pump_performance import pump_efficiency as module
        with patch.object(module, 'hydraulic_power', wraps=module.hydraulic_power) as kernel:
            conditions()
            kernel.assert_called_once()
        with patch.object(module, 'hydraulic_power') as kernel:
            with self.assertRaisesRegex(ValueError, 'greater than zero'):
                conditions(shaft_value=0)
            kernel.assert_not_called()

    def test_conditions_flow_density_units(self):
        for unit, factor in FLOW.items():
            self.assertAlmostEqual(conditions(flow=.01/factor, flow_unit=unit).percent, 80, places=12)
        for unit, factor in DENSITY.items():
            self.assertAlmostEqual(conditions(density=1000/factor, density_unit=unit).percent, 80, places=12)
        for unit, factor in POWER_FACTORS.items():
            self.assertAlmostEqual(conditions(shaft_value=2451.6625/factor, shaft_unit=unit).percent, 80, places=12)

    def test_conditions_zero_flow_or_head(self):
        self.assertEqual(conditions(flow=0).percent, 0)
        self.assertEqual(conditions(head_m=0).percent, 0)

    def test_conditions_validation(self):
        for changes in (dict(density=0), dict(flow=-1), dict(head_m=-1), dict(flow_unit=None),
                        dict(density_unit=None), dict(shaft_unit=None), dict(shaft_value=-1)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                conditions(**changes)
        with self.assertRaisesRegex(ValueError, 'Hydraulic power cannot exceed pump shaft power'):
            conditions(shaft_value=1)

    def test_ratio_sensitivity(self):
        self.assertAlmostEqual(calculate(hydraulic_value=.980665).percent, 40, places=12)
        self.assertAlmostEqual(calculate(shaft_value=4.903325).percent, 40, places=12)


class PumpEfficiencyAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill_power(self, at):
        at.selectbox(key='p3d_hydraulic_unit').select('kW')
        at.selectbox(key='p3d_shaft_unit').select('kW')
        at.number_input(key='p3d_hydraulic').set_value(1.96133)
        at.number_input(key='p3d_shaft').set_value(2.4516625)
        return at.button(key='p3d_calculate').click().run()

    def fill_conditions(self, at):
        at.selectbox(key='p3d_method').select('From Flow, Head, Density and Shaft Power').run()
        at.selectbox(key='p3d_density_unit').select('kg/m³')
        at.selectbox(key='p3d_flow_unit').select('m³/s')
        at.selectbox(key='p3d_shaft_unit').select('kW')
        for key, value in [('density',1000), ('flow',.01), ('head',20), ('shaft',2.4516625)]:
            at.number_input(key='p3d_'+key).set_value(value)
        return at.button(key='p3d_calculate').click().run()

    def result(self, at):
        return '\n'.join(w.value for w in at.text if 'Pump Efficiency:' in w.value and 'Efficiency ratio:' in w.value)

    def test_mode_a_benchmark_labels_guidance(self):
        at = self.fill_power(self.app())
        self.assertIn('Pump Efficiency: 80.00 %\nEfficiency ratio: 0.8000', self.result(at))
        self.assertIn('Hydraulic Power\n1961.33 W', self.result(at))
        self.assertIn('Pump Shaft / Brake Power\n2451.6625 W', self.result(at))
        self.assertEqual(at.number_input(key='p3d_hydraulic').label,'Hydraulic Power (kW)')
        self.assertEqual(at.number_input(key='p3d_shaft').label,'Pump Shaft / Brake Power (kW)')
        self.assertTrue(any('ratio of hydraulic power delivered to the fluid' in w.value for w in at.info))
        self.assertTrue(any('Pump efficiency must be between 0% and 100%' in w.value for w in at.caption))
        self.assertTrue(any('separate from motor efficiency' in w.value for w in at.caption))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3d_')])
        self.assertEqual(len(at.tabs),15)
        self.assertTrue(any(w.label=='3D — Pump Efficiency' for w in at.expander))
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox] for w in group]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_required_inputs_units(self):
        at=self.app()
        for key in ('p3d_hydraulic_unit','p3d_shaft_unit'):
            self.assertIsNone(at.selectbox(key=key).value)
        for key in ('p3d_hydraulic','p3d_shaft'):
            self.assertIsNone(at.number_input(key=key).value)
        at.button(key='p3d_calculate').click().run()
        self.assertTrue(at.error)
        at.number_input(key='p3d_shaft').set_value(2)
        at.number_input(key='p3d_hydraulic').set_value(0)
        at.button(key='p3d_calculate').click().run()
        self.assertTrue(at.error)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)

    def test_100_50_zero_cases(self):
        at=self.fill_power(self.app())
        at.number_input(key='p3d_shaft').set_value(2)
        for value,percent in [(2,'100.00'),(1,'50.00'),(0,'0.00')]:
            at.number_input(key='p3d_hydraulic').set_value(value)
            at.button(key='p3d_calculate').click().run()
            self.assertIn(f'Pump Efficiency: {percent} %',self.result(at))
            self.assertFalse(at.error)
            self.assertFalse(at.exception)

    def test_zero_shaft_and_excess_hydraulic(self):
        at=self.fill_power(self.app())
        at.number_input(key='p3d_shaft').set_value(0)
        at.button(key='p3d_calculate').click().run()
        self.assertIn('greater than zero',at.error[0].value)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)
        at.number_input(key='p3d_shaft').set_value(2)
        at.number_input(key='p3d_hydraulic').set_value(2.5)
        at.button(key='p3d_calculate').click().run()
        self.assertIn('Hydraulic power cannot exceed pump shaft power',at.error[0].value)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)

    def test_units_and_mixed_units(self):
        at=self.fill_power(self.app())
        for h_unit,h_factor in POWER_FACTORS.items():
            for s_unit,s_factor in POWER_FACTORS.items():
                at.selectbox(key='p3d_hydraulic_unit').select(h_unit)
                at.selectbox(key='p3d_shaft_unit').select(s_unit)
                at.number_input(key='p3d_hydraulic').set_value(1961.33/h_factor)
                at.number_input(key='p3d_shaft').set_value(2451.6625/s_factor)
                at.button(key='p3d_calculate').click().run()
                self.assertIn('Pump Efficiency: 80.00 %',self.result(at))
                self.assertEqual(at.number_input(key='p3d_hydraulic').label,f'Hydraulic Power ({h_unit})')
                self.assertEqual(at.number_input(key='p3d_shaft').label,f'Pump Shaft / Brake Power ({s_unit})')
                self.assertFalse(at.exception)

    def test_mode_b_benchmark_and_labels(self):
        at=self.fill_conditions(self.app())
        self.assertIn('Hydraulic Power\n1961.33 W',self.result(at))
        self.assertIn('Pump Efficiency: 80.00 %',self.result(at))
        for key,label in [('density','Fluid Density (kg/m³)'),('flow','Volumetric Flow Rate (m³/s)'),
                          ('head','Pump Head (m)'),('shaft','Pump Shaft / Brake Power (kW)')]:
            self.assertEqual(at.number_input(key='p3d_'+key).label,label)
        at.selectbox(key='p3d_flow_unit').select('m³/hr')
        at.number_input(key='p3d_flow').set_value(36)
        at.button(key='p3d_calculate').click().run()
        self.assertIn('Pump Efficiency: 80.00 %',self.result(at))
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_mode_b_zero_and_invalid(self):
        at=self.fill_conditions(self.app())
        for key in ('flow','head'):
            at.number_input(key='p3d_'+key).set_value(0)
            at.button(key='p3d_calculate').click().run()
            self.assertIn('Pump Efficiency: 0.00 %',self.result(at))
            at.number_input(key='p3d_'+key).set_value(.01 if key=='flow' else 20)
        at.number_input(key='p3d_shaft').set_value(0)
        at.button(key='p3d_calculate').click().run()
        self.assertTrue(at.error)
        self.assertFalse(self.result(at))
        at.number_input(key='p3d_shaft').set_value(1)
        at.button(key='p3d_calculate').click().run()
        self.assertIn('Hydraulic power cannot exceed pump shaft power',at.error[0].value)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)

    def test_stale_result_and_mode_switch(self):
        at=self.fill_power(self.app())
        at.number_input(key='p3d_hydraulic').set_value(1).run()
        self.assertFalse(self.result(at))
        at.button(key='p3d_calculate').click().run()
        self.assertTrue(self.result(at))
        at.selectbox(key='p3d_method').select('From Flow, Head, Density and Shaft Power').run()
        self.assertFalse(self.result(at))
        at.button(key='p3d_calculate').click().run()
        self.assertTrue(at.error)
        self.fill_conditions(at)
        at.number_input(key='p3d_head').set_value(10).run()
        self.assertFalse(self.result(at))
        at.selectbox(key='p3d_shaft_unit').select('W').run()
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)
