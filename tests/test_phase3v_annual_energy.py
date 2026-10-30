"""Duty-profile arithmetic, explicit energy boundaries and integrated control rows."""
import math,json,hashlib,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import FrozenInstanceError
from app import FLOW
from pump_performance import annual_energy as core,annual_energy_ui as ui
from pump_performance.pump_curve import create_pump_curve
from pump_performance.system_curve import model_from_reference
from pump_performance.power_curve import create_power_curve

ROOT=Path(__file__).resolve().parents[1]
HEAD=[(0,50),(50,48),(100,44),(150,38),(200,30)]
POWER=[(50,6),(100,8.5),(150,11.5),(200,14),(250,16)]
def direct(name='A',power=10,hours=4000,basis='Electrical Input Power',**kw):return core.DutyPoint(name,core.METHODS[2],hours,input_power=power,power_unit='kW',power_basis=basis,**kw)
def model_args(multiplier=1):return dict(curve=create_pump_curve(HEAD,'m³/hr','m',FLOW),reference_speed=1500,system=model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW),density=1000,power_curve=create_power_curve([(q,p*multiplier) for q,p in POWER],'m³/hr','kW',FLOW))
def modeled(method,basis='Shaft Power',q=100,hours=4000,**kw):return core.DutyPoint(method,method,hours,target_flow_si=q/3600,energy_basis=basis,**kw)

class AnnualCoreTests(unittest.TestCase):
    def test_single_electrical_energy_cost(self):
        r=core.evaluate_duty_profile([direct()],tariff=.1);self.assertEqual(r.rows[0].energy_kwh,40000);self.assertEqual(r.rows[0].cost,4000);self.assertEqual(r.comparable_supply_kwh,40000)
    def test_three_row_benchmark(self):
        r=core.evaluate_duty_profile([direct('A',10,2000),direct('B',8,3000),direct('C',5,1000)],tariff=.12);self.assertEqual([x.energy_kwh for x in r.rows],[20000,24000,5000]);self.assertEqual(r.total_hours,6000);self.assertEqual(r.comparable_supply_kwh,49000);self.assertEqual(r.comparable_supply_cost,5880)
    def test_unlike_bases_separate_costs(self):
        r=core.evaluate_duty_profile([direct(),direct('S',8,1000,'Shaft Power'),direct('H',5,1000,'Hydraulic Power'),direct('M',6,1000,'Motor Input Power')],tariff=.1);self.assertEqual(dict(r.energy_by_basis),{'Electrical Input Power':40000,'Motor Input Power':6000,'Shaft Power':8000,'Hydraulic Power':5000});self.assertEqual(r.comparable_supply_kwh,40000);self.assertIsNone(r.rows[1].cost);self.assertIsNone(r.rows[2].cost);self.assertEqual(r.rows[3].cost,600)
    def test_motor_efficiency_shared3c(self):
        with patch.object(core,'motor_power',wraps=core.motor_power) as spy:r=core.evaluate_duty_profile([direct(power=8.5,basis='Shaft Power',energy_basis='Motor Input Power',motor_efficiency_percent=90)])
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(r.rows[0].motor_w/1000,9.444444444444443,11);self.assertAlmostEqual(r.rows[0].energy_kwh,37777.777777777774,8);self.assertIsNone(r.comparable_supply_kwh)
    def test_vfd_efficiency_benchmark(self):
        r=core.evaluate_duty_profile([direct(power=8,basis='Motor Input Power',energy_basis='VFD Electrical Input Power',vfd_efficiency_percent=96)]);self.assertAlmostEqual(r.rows[0].vfd_w/1000,8.333333333333334,11);self.assertAlmostEqual(r.rows[0].energy_kwh,33333.333333333336,8)
    def test_hours_zero_missing_negative_nonfinite(self):
        r=core.evaluate_duty_profile([direct(hours=0)]);self.assertEqual(r.rows[0].energy_kwh,0);self.assertIsNone(r.rows[0].time_fraction_percent);self.assertIsNone(r.rows[0].electrical_share_percent)
        for hours in [None,-1,True,math.nan,math.inf]:
            r=core.evaluate_duty_profile([direct(hours=hours),direct('valid')]);self.assertIsNone(r.rows[0].energy_kwh);self.assertFalse(r.hours_complete);self.assertEqual(r.total_hours,4000);self.assertEqual(r.comparable_supply_kwh,40000)
    def test_over8760_warning_no_clamp(self):
        r=core.evaluate_duty_profile([direct(hours=10000)]);self.assertEqual(r.warning,core.HOURS_WARNING);self.assertEqual(r.total_hours,10000);self.assertEqual(r.comparable_supply_kwh,100000)
    def test_fraction_and_supply_share(self):
        r=core.evaluate_duty_profile([direct('A',10,2000),direct('B',8,3000),direct('C',5,1000)]);self.assertAlmostEqual(r.rows[0].time_fraction_percent,100/3,12);self.assertAlmostEqual(r.rows[1].electrical_share_percent,24000/49000*100,12)
    def test_power_units_equivalent(self):
        for unit,factor in ui.POWER_FACTORS.items():
            row=core.DutyPoint('A',core.METHODS[2],4000,input_power=10000/factor,power_unit=unit,power_basis=core.BASES[0]);r=core.evaluate_duty_profile([row]);self.assertAlmostEqual(r.comparable_supply_kwh,40000,8)
    def test_numeric_validation(self):
        for bad in [-1,None,True,math.nan,math.inf]:
            with self.assertRaises(ValueError):core.calculate_energy(bad,4000)
            with self.assertRaises(ValueError):core.calculate_operating_cost(40000,bad)
        self.assertEqual(core.calculate_energy(0,4000),0);self.assertEqual(core.calculate_operating_cost(40000,0),0)
        with self.assertRaises(ValueError):core.calculate_energy(1e308,1e308)
    def test_profile_count_and_full_precision(self):
        for rows in [[],[direct()]*21]:
            with self.assertRaises(ValueError):core.evaluate_duty_profile(rows)
        r=core.evaluate_duty_profile([direct(str(i),.123456789123,i+.1) for i in range(20)]);self.assertEqual(r.comparable_supply_kwh,math.fsum(.123456789123*(i+.1) for i in range(20)))
    def test_missing_basis_efficiency_no_invention(self):
        for row in [direct(basis=None),direct(basis='Shaft Power',energy_basis='Motor Input Power'),direct(basis='Motor Input Power',energy_basis='VFD Electrical Input Power')]:self.assertIsNone(core.evaluate_duty_profile([row]).rows[0].energy_kwh)
    def test_direct_zero_informational_flow(self):
        r=core.evaluate_duty_profile([direct(target_flow_si=0)]);self.assertEqual(r.comparable_supply_kwh,40000)
    def test_phase3u_constant_integration(self):
        with patch.object(core,'solve_constant_speed_system_for_target_flow',wraps=core.solve_constant_speed_system_for_target_flow) as spy:r=core.evaluate_duty_profile([modeled(core.METHODS[0])],**model_args())
        self.assertEqual(spy.call_count,1);p=r.rows[0];self.assertEqual(p.head_m,44);self.assertEqual(p.speed_rpm,1500);self.assertEqual(p.shaft_w,8500);self.assertEqual(p.energy_kwh,34000)
    def test_phase3t_vsd_scaled_power(self):
        args=model_args()
        with patch.object(core,'solve_speed_for_target_flow',wraps=core.solve_speed_for_target_flow) as t,patch.object(core,'scale_vendor_power_curve',wraps=core.scale_vendor_power_curve) as i,patch.object(core,'interpolate_power',wraps=core.interpolate_power) as n:r=core.evaluate_duty_profile([modeled(core.METHODS[1])],**args)
        self.assertEqual(t.call_count,1);self.assertEqual(i.call_count,1);self.assertEqual(n.call_count,1);self.assertIsNot(n.call_args.args[0],args['power_curve']);p=r.rows[0];self.assertAlmostEqual(p.speed_rpm,1270.302598778999,8);self.assertEqual(p.head_m,30);self.assertAlmostEqual(p.shaft_w,5821.5220936881715,8)
    def test_modeled_hydraulic_not_electrical(self):
        r=core.evaluate_duty_profile([modeled(core.METHODS[0],'Hydraulic Power')],**model_args());self.assertAlmostEqual(r.rows[0].hydraulic_w,11985.905555555555,8);self.assertIsNone(r.comparable_supply_kwh);self.assertIsNone(r.rows[0].cost)
    def test_inconsistent_modeled_power_blocks_electrical(self):
        r=core.evaluate_duty_profile([modeled(core.METHODS[0],'Motor Input Power',motor_efficiency_percent=90)],**model_args());self.assertIsNone(r.rows[0].energy_kwh);self.assertIn('below calculated hydraulic',r.rows[0].status)
    def test_invalid_targets_no_energy_valid_rows_preserved(self):
        r=core.evaluate_duty_profile([modeled(core.METHODS[0],q=250),direct()],**model_args());self.assertIsNone(r.rows[0].energy_kwh);self.assertIn(core.INVALID_POINT,r.rows[0].status);self.assertEqual(r.rows[1].energy_kwh,40000)
    def test_multiple_vsd_speeds_no_arbitrary_choice(self):
        args=model_args();args['curve']=create_pump_curve([(1,0),(2,4),(4,12)],'m³/s','m',FLOW);args['system']=type(args['system'])(.75,0)
        r=core.evaluate_duty_profile([core.DutyPoint('multiple',core.METHODS[1],100,target_flow_si=1,energy_basis='Hydraulic Power')],**args);self.assertIsNone(r.rows[0].energy_kwh);self.assertIn('375 rpm',r.rows[0].status);self.assertIn('1125 rpm',r.rows[0].status)
    def test_comparable_alternatives(self):
        r=core.evaluate_duty_profile([modeled(core.METHODS[0],'Motor Input Power',motor_efficiency_percent=90),modeled(core.METHODS[1],'VFD Electrical Input Power',motor_efficiency_percent=88,vfd_efficiency_percent=97)],**model_args(2),tariff=.12);c=core.compare_control_alternatives(*r.rows);self.assertAlmostEqual(c.difference_kwh,20995.83583964016,8);self.assertAlmostEqual(c.difference_cost,2519.500300756819,8)
        with self.assertRaises(ValueError):core.compare_control_alternatives(r.rows[1],r.rows[0])
    def test_energy_display_and_immutable(self):
        self.assertEqual(ui.energy_display(40000,'MWh'),40);r=core.evaluate_duty_profile([direct()])
        with self.assertRaises(FrozenInstanceError):r.total_hours=1

class AnnualAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,values=((10,4000,'Electrical Input Power'),)):
        at=self.app();at.number_input(key='p3v_count').set_value(len(values)).run()
        for i,(power,hours,basis) in enumerate(values):
            at.text_input(key=f'p3v_name_{i}').set_value(chr(65+i));at.number_input(key=f'p3v_power_{i}').set_value(power);at.number_input(key=f'p3v_hours_{i}').set_value(hours);at.selectbox(key=f'p3v_unit_{i}').select('kW');at.selectbox(key=f'p3v_basis_{i}').select(basis)
        return at
    def calc(self,at):at.button(key='p3v_evaluate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def test_render_blank_inputs_no_acknowledgements(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3V — Pump Annual Energy / Duty-Cycle Operating Cost Analysis' for e in at.expander))
        for w in at.number_input:
            if w.key.startswith('p3v_') and w.key!='p3v_count':self.assertIsNone(w.value)
        self.assertIsNone(at.selectbox(key='p3v_unit_0').value);self.assertEqual(at.text_input(key='p3v_currency').value,'');self.assertFalse([w for w in at.checkbox if w.key.startswith('p3v_')])
    def test_single_energy_and_cost(self):
        at=self.fill();at.number_input(key='p3v_tariff').set_value(.1);at.text_input(key='p3v_currency').set_value('units');self.calc(at)
        for t in ['Annual Energy: 40000 kWh/year','Annual Cost: 4000 units/year','Total Comparable Supply Electrical Energy: 40000 kWh/year','Annual Comparable Supply Electrical Cost: 4000 units/year']:self.assertIn(t,self.text(at))
    def test_three_rows_totals_tariff(self):
        at=self.fill(((10,2000,core.BASES[0]),(8,3000,core.BASES[0]),(5,1000,core.BASES[0])));at.number_input(key='p3v_tariff').set_value(.12);at.text_input(key='p3v_currency').set_value('units');self.calc(at)
        for t in ['Annual Energy: 20000 kWh/year','Annual Energy: 24000 kWh/year','Annual Energy: 5000 kWh/year','Total Operating Hours: 6000 h/year','Total Comparable Supply Electrical Energy: 49000 kWh/year','Annual Comparable Supply Electrical Cost: 5880 units/year']:self.assertIn(t,self.text(at))
        self.assertTrue(any('Quantity' not in w.value and '| Case | Control Method |' in w.value for w in at.markdown))
    def test_multiple_bases_not_unlabeled_sum(self):
        at=self.calc(self.fill(((10,4000,core.BASES[0]),(8,1000,'Shaft Power'),(5,1000,'Hydraulic Power'),(6,1000,'Motor Input Power'))))
        for t in ['Total Shaft Mechanical Energy: 8000 kWh/year','Total Hydraulic Energy: 5000 kWh/year','Total Motor Electrical Energy: 6000 kWh/year','Total Comparable Supply Electrical Energy: 40000 kWh/year']:self.assertIn(t,self.text(at))
    def test_motor_conversion_explicit_blank_efficiency(self):
        at=self.fill(((8.5,4000,'Shaft Power'),));at.run();at.selectbox(key='p3v_conversion_0').select('Motor Input Power').run();self.assertIsNone(at.number_input(key='p3v_motor_0').value);at.number_input(key='p3v_motor_0').set_value(90)
        with patch.object(core,'motor_power',wraps=core.motor_power) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Motor Input Power: 9.444444444 kW',self.text(at));self.assertIn('Annual Energy: 37777.77778 kWh/year',self.text(at))
    def test_vfd_conversion_explicit_blank_efficiency(self):
        at=self.fill(((8,4000,'Motor Input Power'),));at.run();at.selectbox(key='p3v_conversion_0').select('VFD Electrical Input Power').run();self.assertIsNone(at.number_input(key='p3v_vfd_0').value);at.number_input(key='p3v_vfd_0').set_value(96);self.calc(at);self.assertIn('Calculated VFD Electrical Input Power: 8.333333333 kW',self.text(at));self.assertIn('Annual Energy: 33333.33333 kWh/year',self.text(at))
    def test_negative_and_nonfinite_hours_invalid(self):
        at=self.calc(self.fill(((10,-1,core.BASES[0]),)));self.assertIn('Annual Energy: N/A',self.text(at));self.assertTrue(at.warning);self.assertNotIn('Annual Energy: 0 kWh/year',self.text(at))
    def test_zero_hours_valid_no_fraction(self):
        at=self.calc(self.fill(((10,0,core.BASES[0]),)));self.assertIn('Annual Energy: 0 kWh/year',self.text(at));self.assertIn('Time Fraction: N/A%',self.text(at))
    def test_over8760_warning(self):
        at=self.calc(self.fill(((10,10000,core.BASES[0]),)));self.assertTrue(any(w.value==core.HOURS_WARNING for w in at.warning));self.assertIn('Total Operating Hours: 10000 h/year',self.text(at))
    def test_fraction_and_energy_share(self):
        at=self.calc(self.fill(((10,2000,core.BASES[0]),(8,3000,core.BASES[0]),(5,1000,core.BASES[0]))));self.assertIn('Time Fraction: 33.33333333%',self.text(at));self.assertIn('Comparable Supply Electrical Energy Share: 48.97959184%',self.text(at))
    def test_power_unit_equivalence(self):
        for unit,factor in ui.POWER_FACTORS.items():
            at=self.fill();at.selectbox(key='p3v_unit_0').select(unit);at.number_input(key='p3v_power_0').set_value(10000/factor);self.calc(at);self.assertIn('Annual Energy: 40000 kWh/year',self.text(at))
    def test_mwh_display(self):
        at=self.fill();at.selectbox(key='p3v_energy_unit').select('MWh');self.calc(at);self.assertIn('Annual Energy: 40 MWh/year',self.text(at));self.assertIn('Total Comparable Supply Electrical Energy: 40 MWh/year',self.text(at))
    def test_tariff_not_applied_to_mechanical_hydraulic(self):
        at=self.fill(((10,4000,'Shaft Power'),(5,1000,'Hydraulic Power')));at.number_input(key='p3v_tariff').set_value(.1);at.text_input(key='p3v_currency').set_value('units');self.calc(at);self.assertNotIn('Annual Cost: 4000',self.text(at));self.assertIn('Annual Cost: N/A units/year',self.text(at))
    def test_currency_not_invented(self):
        at=self.fill();at.number_input(key='p3v_tariff').set_value(.1);self.calc(at);self.assertIn('Annual Cost: N/A currency not entered/year',self.text(at));self.assertTrue(any('Enter a currency label' in w.value for w in at.info))
    def model(self,methods=(core.METHODS[0],core.METHODS[1]),basis='Shaft Power',multiplier=1):
        at=self.app();at.selectbox(key='p3v_analysis').select('Include Pump / System Models').run();at.number_input(key='p3v_head_count').set_value(5);at.number_input(key='p3v_count').set_value(len(methods));at.selectbox(key='p3v_power_mode').select('Reference-Speed Vendor Power Curve').run();at.number_input(key='p3v_power_count').set_value(5).run()
        at.selectbox(key='p3v_flow_unit').select('m³/hr');at.selectbox(key='p3v_head_unit').select('m');at.selectbox(key='p3v_power_flow_unit').select('m³/hr');at.selectbox(key='p3v_power_value_unit').select('kW')
        for i,(q,h) in enumerate(HEAD):at.number_input(key=f'p3v_head_q_{i}').set_value(q);at.number_input(key=f'p3v_head_v_{i}').set_value(h)
        for i,(q,p) in enumerate(POWER):at.number_input(key=f'p3v_power_q_{i}').set_value(q);at.number_input(key=f'p3v_power_v_{i}').set_value(p*multiplier)
        for key,v in [('speed',1500),('static',10),('k',25920),('density',1000)]:at.number_input(key='p3v_'+key).set_value(v)
        for i,m in enumerate(methods):at.selectbox(key=f'p3v_method_{i}').select(m)
        at.run()
        for i in range(len(methods)):at.number_input(key=f'p3v_flow_{i}').set_value(100);at.number_input(key=f'p3v_hours_{i}').set_value(4000);at.selectbox(key=f'p3v_output_{i}').select(basis)
        return at
    def test_integrated_phase3u_3t_3n_scaling(self):
        at=self.model()
        with patch.object(core,'solve_constant_speed_system_for_target_flow',wraps=core.solve_constant_speed_system_for_target_flow) as u,patch.object(core,'solve_speed_for_target_flow',wraps=core.solve_speed_for_target_flow) as t,patch.object(core,'interpolate_power',wraps=core.interpolate_power) as n,patch.object(core,'scale_vendor_power_curve',wraps=core.scale_vendor_power_curve) as i:self.calc(at)
        self.assertEqual(u.call_count,1);self.assertEqual(t.call_count,1);self.assertEqual(n.call_count,2);self.assertEqual(i.call_count,1);self.assertIsNot(n.call_args_list[0].args[0],n.call_args_list[1].args[0]);self.assertIn('Operating Head: 44 m',self.text(at));self.assertIn('Operating Speed: 1270.302599 rpm',self.text(at));self.assertIn('Shaft Power: 5.821522094 kW',self.text(at))
    def test_invalid_modeled_target_no_energy(self):
        at=self.model(methods=(core.METHODS[0],));at.number_input(key='p3v_flow_0').set_value(250);self.calc(at);self.assertIn(core.INVALID_POINT,self.text(at));self.assertIn('Annual Energy: N/A',self.text(at))
    def test_modeled_hydraulic_basis(self):
        at=self.calc(self.model(methods=(core.METHODS[0],),basis='Hydraulic Power'));self.assertIn('Applicable Energy Basis: Hydraulic Energy',self.text(at));self.assertIn('Total Comparable Supply Electrical Energy: N/A',self.text(at))
    def test_inconsistent_modeled_power_no_electrical(self):
        at=self.model(methods=(core.METHODS[0],),basis='Motor Input Power');at.run();self.assertIsNone(at.number_input(key='p3v_motor_0').value);at.number_input(key='p3v_motor_0').set_value(90);self.calc(at);self.assertIn('below calculated hydraulic',self.text(at));self.assertIn('Annual Energy: N/A',self.text(at))
    def test_paired_control_alternatives_explicit(self):
        at=self.model(basis='Motor Input Power',multiplier=2);at.selectbox(key='p3v_output_1').select('VFD Electrical Input Power').run();at.number_input(key='p3v_motor_0').set_value(90);at.number_input(key='p3v_motor_1').set_value(88);at.number_input(key='p3v_vfd_1').set_value(97);at.selectbox(key='p3v_compare_constant').select('1. Duty Period 1');at.selectbox(key='p3v_compare_vsd').select('2. Duty Period 2');self.calc(at);self.assertIn('Annual Electrical Energy Difference: +20995.83584 kWh/year',self.text(at));self.assertFalse(at.error)
    def test_charts_distinct_units_valid_rows_only(self):
        at=self.calc(self.fill());charts=[json.loads(w.proto.spec) for w in at.get('vega_lite_chart')];self.assertEqual(len(charts),2);self.assertEqual(charts[0]['encoding']['y']['title'],'Annual Energy (kWh/year)');self.assertEqual(charts[1]['encoding']['y']['title'],'Operating Hours (h/year)')
    def test_guidance_no_extra_modules(self):
        at=self.calc(self.fill());captions='\n'.join(w.value for w in at.caption)
        for g in ui.GUIDANCE:self.assertIn(g,captions)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3v_')]);self.assertNotIn('guaranteed savings',self.text(at));self.assertNotIn('payback',self.text(at).lower())
    def test_stale_results_clear(self):
        at=self.calc(self.fill());at.number_input(key='p3v_hours_0').set_value(100).run();self.assertNotIn('Total Operating Hours:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
    def test_previous_files_unchanged(self):
        expected={'advanced_engineering.py': 'd054f5df78e50184e534bfdf5694add050d00c3154498835a50b8367cb072489', 'piping_hydraulics/pump_head.py': '065e3eace54789e7607d5bde38dddc5290f56637ad6fa44c507a76933e9c07cc', 'piping_hydraulics/units.py': '8b5e68c0e433297211098ee480887c1de5b81c094e811df647648ba6f9000fd1', 'piping_hydraulics/pipe_geometry.py': 'cfb33c97e6b702bac1cc1985947991949c85708c12faeaf2aed6dcb61130f5af', 'piping_hydraulics/ui.py': 'aeab04a44dcf562e904c7174406e7db670d838570e6dce534699c5052b5c9db1', 'piping_hydraulics/roughness.py': 'a2ab32e142a26f3d69bbcc1464b5a794377dab14f0bb20efca15f316d18e883e', 'piping_hydraulics/__init__.py': '841e0ce2d37c0a8cc8fbced25aec341dd80ca0cb3233eaafc7dd8e89ad52d680', 'piping_hydraulics/roughness_ui.py': '703a1b52772c271c8c93ddc460fa32c6955a621bfce5d7cf1b93fb5c0043d460', 'piping_hydraulics/equivalent_length.py': '882d2f16f087fea5129ade3ca2f1faa8dfc2ee8afd346382d1a235552e725ffc', 'piping_hydraulics/pipe_capacity.py': '4606e5d7033cad72a742fd0574b0c5e983d53955afc4868d0c7358dca5f6e8d2', 'piping_hydraulics/npsha.py': '9f0b027affac14defb2846563f2df7e3bcb46375fcf38a11fff9d9e27b598a87', 'piping_hydraulics/integrated_ui.py': '8355acc0d4de110042ecb9a87e9c750bbfacc72796bda81900f424d8634cdd8c', 'piping_hydraulics/fittings_ui.py': 'ca82d5083e538ec63f569dda43bc96d2dec489ceaf048d290811aba5a4e542e2', 'piping_hydraulics/integrated.py': '005e6ddf0c18f47f8984599570908311554e915ed15b1a0c5940c43d7386d713', 'piping_hydraulics/pump_head_ui.py': '6f6ac3066a0eb5166f1c1cc2d841fb7a18c4f81db145ed775f0883790d5d8352', 'piping_hydraulics/fittings.py': 'a5fee158ba3cf3ac76fa34a48c82284542f34a18e19aff3fd34141636f741086', 'piping_hydraulics/npsha_ui.py': '33e84e5116272271bab8ef8d795139f652e22b3bb076b999c8864045b1d4ab18', 'piping_hydraulics/capacity_ui.py': '69e2184afc4ed25350d88f48c5925b0488ebd56a2f3056ba5fed4bfd70ec40d7', 'tests/test_phase3u_control_strategy.py': 'd07890f6e10820eebbcbd3d268877eb1cb1afda752bb8764f72c2005e07dd4ac', 'tests/test_phase2_integrated.py': '45e956952c01980f2c70621bba5cdba401ac4a94cd0989ffdf489a661bce41a3', 'tests/test_phase3r_system_sensitivity.py': '6543cd57d690a3297a21e88cace7497344804cb9e8c015494264ef2297ab8647', 'tests/test_phase3t_target_speed.py': '72047c1805cbc87d37629d6b2661a6bd03d1919ee4d772de504ec84a1ed7585b', 'tests/test_phase2_roughness.py': '1ed621bb8c737c8b348fd0eb59b26a1deffa904a30a86f4819bce510cf807390', 'tests/test_phase3l_parallel_production_regression.py': '9b56e9e1fe72ad70b04357a856d07933fa445c22198a2340a0251c0218ab0384', 'tests/test_phase2_pipe_capacity.py': '28e3312aaa18774e478ffc703354c71502318f1b23935738c8197a211e1201f9', 'tests/test_phase3o_npshr_curve.py': 'a581157f7b52521df6d8445608443d1f4deb16e1f3f6a8508f599c715dfe4c77', 'tests/test_phase3b_shaft_power.py': 'a8c09d01781e8ab5b396a4a3599e20da9f5f491c3c22d7f13cedab654679873a', 'tests/test_phase3f_system_curve.py': '093c1a30db4bec02b60df0e6733fbfdb00137ab99d47dc983410d21c99c50e01', 'tests/test_phase2_npsha.py': 'efba26ae6fca86fffa26130c6eb5b509bc6d4ee01dbacef3680eb9477c6b208e', 'tests/test_phase3m_efficiency_curve.py': 'dd47e19ed72434b22f9b41850edfde2d3d5f22e3abef1182bbee37c44bc4f239', 'tests/test_phase3l_series_parallel.py': 'cc2f181f37f1ed18fe53d39ead1765bfece9c85c5e333b16f924123260a67403', 'tests/test_phase3d_pump_efficiency.py': 'a075f30b18c28e2b765eef5a7a05623983af17fb874b4a7794d87edafe8e6400', 'tests/test_phase3h_bep_operating_range.py': 'c189ede06b8537f0ed58521eb1a1ad5d3e9866ee04be27c14767a31775ed6011', 'tests/test_phase2_fittings.py': '0b0a589aae33724d0af020c64e680061b1dbc69065e01aa71f59369267ec9e0a', 'tests/test_phase3i_affinity_laws.py': 'ae959797900b55c955a11c6ad5d18ea2e45a2a7afb43f5ae81c0a4e4f6a8636f', 'tests/test_phase3p_performance_map.py': '70455b3d19ae9daf92b11e30594f8b79bd4cff9eede4c75ecc4f7654534ab86b', 'tests/test_phase2_pump_head.py': '11f85cf50513dcf7d3f6483000c74d386743cc7c2cfce6069be62923cf915ae7', 'tests/test_phase3k_duty_point_check.py': 'f6745c9b2c24bc6f65bd71f9b819851dd0eca5c0506dd9fe8e78c5d4f49d8710', 'tests/test_phase3a_hydraulic_power.py': '0f1b6d6c9be0b854f34c54b11ac97917d17198330b43c0a3b56a4c6d9249c359', 'tests/test_phase3q_curve_characteristics.py': 'd65b9e50bd1c75ede11af801b055b87dbbadc5d95d9ad9318e99233bca813a88', 'tests/test_phase3e_pump_curve.py': '3c3de6fb0344d1040a0656e88f5ce1cf00fab708db1ab15215a7e98d7e88489f', 'tests/test_phase3n_power_curve.py': '863cf099c8d9fa9300942903b043d8d0f5357ebd4b192a352214c62af9e9a26c', 'tests/test_phase3s_variable_speed.py': '2d5e6481ce8351d8c441d3170c4ae69afeeb5908eb411b58f302b46f0fcfd0f1', 'tests/test_phase3g_operating_point.py': '9b14e8a6aab228c9321a6ea699cdd7dbe0635a9e970b7b57137e0055fd169488', 'tests/test_phase2_pipe_sizing.py': 'cf08942d8fa140cf9f36065e2f65ec5e516ac7158eca7b9025162649696d14bf', 'tests/test_phase2_equivalent_length.py': 'bb7f79c9da2474f845dd09762a335d173efd6fcfcc07286ef59097925237d97f', 'tests/test_phase3c_motor_power.py': 'a500a6528aa71c47c76a4193c6a23c01c53a32aceb7da55da207020e2c29b702', 'tests/test_app.py': '147a94b35991d4d8d040591997e167bb00018f684c6f0ca9300ee341909147fa', 'tests/test_phase3j_npsh_margin.py': '68d5f003a4b40e6a0669e8389f3a4e036ad3c53b0d8703c4ae7cb71c52ea40dd', 'pump_performance/curve_characteristics.py': 'ffcf73532881e1d8e4153c1777c22dc7a907c8761e2ccb51c7bfc2beaf24c4ee', 'pump_performance/affinity_laws.py': '58473f2d5ef7dd27a6153a41d004c6fadae227608f424dde2fa1955d3effba0e', 'pump_performance/affinity_laws_ui.py': 'ae580e907722f847a0990ef10eb29d34734172b0e511d3a7808d531133ea6542', 'pump_performance/pump_curve_ui.py': '6d91872e74a1d96c3fe1fed661cea9de5d540ca04a5bb55ea6dd55ce45cdb9f3', 'pump_performance/shaft_power.py': 'c89ac8baaf8504d6a3daadf75b02214b113a5a60c59ff84c46c5f37e4254f304', 'pump_performance/system_curve_ui.py': '2859d7f1bcebde93fa6e95050600057d51ca169da3c167197d930f2fdc925217', 'pump_performance/variable_speed.py': '36d6b224e3ac26e42fcd2416ca63280ecef3ef9b0b6cd99ebb8d913ee260a1d4', 'pump_performance/control_strategy_ui.py': '13b63e57b7d58d88127a4643fa524e5e8640577836097447a3348537e480bfca', 'pump_performance/variable_speed_ui.py': '732039e64fb59046393b6cd963703e39f56a6e736ba102e7c073ee1c3239b77d', 'pump_performance/operating_point.py': '298726b755abf34cc34c785d3cc93ab7bd5934c1b2dcadbf9c7ba70069825e77', 'pump_performance/duty_point_check_ui.py': '1ca5f223ffbd304548892223716de9123b360f7d1064d89504382ad5b2f83faa', 'pump_performance/target_speed_ui.py': '9fb934746817c897ad8569c7c3920f6629025a8f015aa4673d3dc9382a578597', 'pump_performance/__init__.py': '2f5a43a377c73ab41ec8d6c0a4ea122f437027348d9f72bf8682779835ef375c', 'pump_performance/efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'pump_performance/npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'pump_performance/system_sensitivity.py': '1efde5d50baef4d4beefd863239458eb53eca239ed15ff46afb29bd3cd8e3e33', 'pump_performance/target_speed.py': '538a86a815f1cd71047752b1d4647f47d083501baf7fb6190a218df45c54aad6', 'pump_performance/performance_map_ui.py': 'd25a7599e4107bb72587b59ce8183dcd888430e5116217162fd7dd34343164c6', 'pump_performance/pump_curve.py': 'd99e7c455295e01992fc6dc11cf24b802657906bfd2df2723df9b1c2282643a7', 'pump_performance/pump_efficiency.py': '04e1f2ed5822f48c81b76fefcba834cf4098b2a6ded0652d34ab0ce8e65edc3d', 'pump_performance/series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'pump_performance/npsh_margin_ui.py': '1317c0d9058c939fccdbcd7f54dd5b3b18f79228b702d99050fa56bd8c24f144', 'pump_performance/hydraulic_power_ui.py': 'a806d62aeae1a4908803951bbb242da7c944f9e6e4e7ab09bb84937ebbb1958e', 'pump_performance/system_curve.py': 'ddcbb6f04cb79860ef9aa4b62efa5a890201d3c51cd7dfe3c5c49cc67d1c46fa', 'pump_performance/curve_characteristics_ui.py': '4484d9a372be07da9fafea44a377612d16ef60c4bb007238609f9396f8f249fe', 'pump_performance/power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'pump_performance/efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'pump_performance/shaft_power_ui.py': 'e87e27281be81f679533ef7ba1068bda456075302d0bb3ac6d6af0d9f7e15a6c', 'pump_performance/control_strategy.py': 'ba639b265ebeaaa6baa878b102591c8f8fa7222b223df1a289fa11ee4a78127e', 'pump_performance/duty_point_check.py': '9d47476296bc0e460a0114754d5656390218810d1d17df2d3bf6de66d7251817', 'pump_performance/performance_map.py': '9d9c93a28bda071dcc111691ae0a9560c631145d01ae3fa5351678cde9c1012f', 'pump_performance/motor_power.py': '326fc2bda9b14a6076768af6ad031cef90b2ffc2bbd350e1dab2abf859759bf1', 'pump_performance/motor_power_ui.py': 'd650ebb7f2860eb06b481c45be09a7692198f76ae048e29eb00be88f5cc3eb56', 'pump_performance/pump_efficiency_ui.py': 'fe5d915d1d5b46c7befd884d38cb6fa55dce4de766dd2c3026e1efd3fccc73e3', 'pump_performance/power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'pump_performance/system_sensitivity_ui.py': '79a65f056e15bb9e2260a26b8b5ef15abadb3b7ab086e70e54bad6b5b0a58b42', 'pump_performance/npsh_margin.py': 'd503a95d36823e79df2c8b47e8cca164e261f9a4997b3ff8522918755b26cef3', 'pump_performance/series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'pump_performance/bep_operating_range.py': '3aee4ad62902d57e75bca753c017b8b31ddbfb4f318e9893350ac790c8fc0ede', 'pump_performance/operating_point_ui.py': '27369fd5812a7cb517290a710570ed3a1921f335448bcad8b5bba6c8fa2aa0a5', 'pump_performance/npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae', 'pump_performance/bep_operating_range_ui.py': 'f2e910a599a48c4b9e365e393d0efd80feccd6577168f354197d0b030e27a9fa', 'pump_performance/hydraulic_power.py': '30aa62bafe5460a9cb2de45d81867b4a99894b35f43eb1531c5924b10322b779'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
