"""Phase 3N numerical boundaries, shared kernels and production UI workflows."""
import hashlib
import json
import math
from pathlib import Path
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app import FLOW,DENSITY
from pump_performance import power_curve as core,power_curve_ui as ui
from pump_performance.efficiency_curve import create_efficiency_curve
from pump_performance.shaft_power import POWER_FACTORS
from pump_performance.pump_curve import create_pump_curve
from pump_performance.system_curve import model_from_reference
from pump_performance.operating_point import find_operating_points

POINTS=[(50,6),(100,8.5),(150,11.5),(200,14),(250,16)]
EFFICIENCY=[(50,65),(100,78),(150,84),(200,80),(250,70)]
PUMP=[(0,50),(50,48),(100,44),(150,38),(200,30)]
ROOT=Path(__file__).resolve().parents[1]


def curve(points=POINTS,flow_unit='m³/hr',power_unit='kW'):
    return core.create_power_curve(points,flow_unit,power_unit,FLOW)


class PowerCurveCoreTests(unittest.TestCase):
    def test_benchmarks(self):
        for q,p in [(125,10000),(175,12750),(150,11500),(50,6000),(250,16000)]:
            with self.subTest(q=q):self.assertAlmostEqual(core.interpolate_power(curve(),q/3600).shaft_power_w,p,9)
    def test_exact_points(self):
        c=curve()
        for p in c.points:
            r=core.interpolate_power(c,p.flow_m3_s);self.assertTrue(r.exact_point);self.assertEqual(r.shaft_power_w,p.shaft_power_w)
    def test_endpoint_tolerance(self):
        c=curve()
        for p,direction in [(c.points[0],-math.inf),(c.points[-1],math.inf)]:
            self.assertEqual(core.interpolate_power(c,math.nextafter(p.flow_m3_s,direction)).shaft_power_w,p.shaft_power_w)
            with self.assertRaisesRegex(ValueError,'not extrapolated'):core.interpolate_power(c,p.flow_m3_s+(-1 if direction<0 else 1)*1e-10)
    def test_outside_range(self):
        for q in [25,275]:
            with self.assertRaisesRegex(ValueError,'not extrapolated'):core.interpolate_power(curve(),q/3600)
    def test_sort_nonmonotonic_and_zero(self):
        pts=[(2,0),(0,10),(1,20)]
        c=curve(pts,'m³/s','W');self.assertEqual([p.shaft_power_w for p in c.points],[10,20,0]);self.assertEqual(core.interpolate_power(c,2).shaft_power_w,0)
    def test_maximum_and_ties(self):
        m=core.find_maximum_supplied_power(curve());self.assertEqual(m.shaft_power_w,16000);self.assertEqual(m.flows_m3_s,(250/3600,))
        m=core.find_maximum_supplied_power(curve([(50,16),(100,10),(150,16)]));self.assertEqual(m.flows_m3_s,(50/3600,150/3600))
    def test_duplicate_minimum_malformed(self):
        for pts in [POINTS[:2],[(50,6),(50,7),(100,8)],[(1,1),None,(3,2)],[(1,1),(2,2),(3,)]]:
            with self.assertRaises(ValueError):curve(pts)
    def test_invalid_values(self):
        for column in [0,1]:
            for bad in [None,True,-1,math.nan,math.inf,-math.inf,'bad']:
                pts=POINTS.copy();row=list(pts[0]);row[column]=bad;pts[0]=row
                with self.subTest(column=column,bad=bad),self.assertRaises(ValueError):curve(pts)
    def test_invalid_operating_flow(self):
        for q in [None,True,-1,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):core.interpolate_power(curve(),q)
    def test_units_and_overflow_rejected(self):
        with self.assertRaises(ValueError):curve(flow_unit=None)
        with self.assertRaises(ValueError):curve(power_unit='hp')
        with self.assertRaises(ValueError):curve([(1,1e308),(2,2),(3,3)])
        with self.assertRaises(ValueError):core.create_power_curve(POINTS,'huge','W',{'huge':1e308})
    def test_all_flow_and_power_units(self):
        for unit,factor in FLOW.items():
            for pu,pf in POWER_FACTORS.items():
                c=curve([(q/3600/factor,p*1000/pf) for q,p in POINTS],unit,pu)
                self.assertAlmostEqual(core.interpolate_power(c,125/3600).shaft_power_w,10000,8)
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):curve().points=()
    def test_driver_standard_equal_below(self):
        for shaft,rating,margin,percent,status in [(10000,15000,5000,50,'is above'),(10000,10000,0,0,'equals'),(12000,10000,-2000,-16.666666666666664,'is below')]:
            r=core.calculate_driver_margin(shaft,rating);self.assertEqual(r.margin_w,margin);self.assertAlmostEqual(r.margin_percent,percent,11)
            self.assertEqual(r.relationship_status,f'Entered driver rating {status} interpolated shaft power.')
    def test_driver_roundoff_status_retains_margin(self):
        r=core.calculate_driver_margin(10000,math.nextafter(10000,math.inf));self.assertIn('equals',r.relationship_status);self.assertGreater(r.margin_w,0)
    def test_zero_shaft_and_driver_validation(self):
        r=core.calculate_driver_margin(0,15000);self.assertIsNone(r.margin_percent);self.assertEqual(r.margin_w,15000)
        self.assertEqual(core.compare_driver_margin(None,10),'N/A — shaft power is zero')
        for bad in [None,0,-1,True,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):core.calculate_driver_margin(10000,bad)
        with self.assertRaises(ValueError):core.calculate_driver_margin(1e-308,1e308)
    def test_criterion_inclusive_and_validation(self):
        self.assertEqual(core.compare_driver_margin(50,50),'Meets entered driver power margin')
        self.assertEqual(core.compare_driver_margin(50,51),'Does not meet entered driver power margin')
        self.assertEqual(core.compare_driver_margin(-10,0),'Does not meet entered driver power margin')
        for required in [-1,math.nan,math.inf,None,True]:
            with self.assertRaises(ValueError):core.compare_driver_margin(50,required)
        with self.assertRaises(ValueError):core.compare_driver_margin(math.inf,10)
    def test_shared_3g(self):
        p=create_pump_curve(PUMP,'m³/hr','m',FLOW)
        m=model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)
        op=find_operating_points(p,m).points[0]
        self.assertAlmostEqual(core.interpolate_power(curve(),op.flow_m3_s).shaft_power_w/1000,9.975774900244184,11)
    def comparison(self,**kw):
        args=dict(vendor_power_w=10000,flow_si=125/3600,density=1000,density_unit='kg/m³',head_m=40,density_factors=DENSITY,flow_factors=FLOW,efficiency_percent=81)
        args.update(kw);return core.compare_calculated_power(**args)
    def test_optional_calculated_power_shared_kernels(self):
        with patch.object(core,'hydraulic_power',wraps=core.hydraulic_power) as hp,patch.object(core,'shaft_power',wraps=core.shaft_power) as sp:
            r=self.comparison()
        self.assertEqual(hp.call_count,1);self.assertEqual(sp.call_count,1)
        self.assertAlmostEqual(r.calculated_power_w,16815.243484224964,8);self.assertAlmostEqual(r.difference_w,6815.243484224964,8);self.assertAlmostEqual(r.percent_difference,68.15243484224964,10)
    def test_optional_3m_reused(self):
        c=create_efficiency_curve(EFFICIENCY,'m³/hr',FLOW)
        with patch.object(core,'interpolate_efficiency',wraps=core.interpolate_efficiency) as spy:
            r=self.comparison(efficiency_percent=None,efficiency_curve=c)
        self.assertEqual(spy.call_count,1);self.assertEqual(r.efficiency_percent,81)
    def test_optional_comparison_zero_and_invalid(self):
        self.assertIsNone(self.comparison(vendor_power_w=0).percent_difference)
        for kw in [dict(efficiency_percent=None),dict(efficiency_percent=0),dict(efficiency_curve=create_efficiency_curve(EFFICIENCY,'m³/hr',FLOW))]:
            with self.assertRaises(ValueError):self.comparison(**kw)
    def test_plot_domain_markers(self):
        c=curve();s=ui.power_plot_spec(c,FLOW['m³/hr'],'m³/hr','kW',core.interpolate_power(c,125/3600))
        self.assertEqual(len(s['layer']),4)
        self.assertNotIn('y',s['encoding']);self.assertNotIn('encoding',s['layer'][2])
        for i in (0,1,3):self.assertEqual(s['layer'][i]['encoding']['y']['field'],'power')
        self.assertEqual([r['flow'] for r in s['layer'][0]['data']['values']],[50,100,150,200,250])
        self.assertEqual(s['layer'][1]['data']['values'][0]['power'],16)
        self.assertEqual(s['layer'][2]['data']['values'],[{'flow':125}]);self.assertEqual(s['layer'][3]['data']['values'],[{'flow':125,'power':10}])


class PowerCurveAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,points=POINTS,q=125,unit='m³/hr',op_unit='m³/hr',power_unit='kW',output_unit='kW'):
        at=at or self.app();at.number_input(key='p3n_count').set_value(len(points)).run()
        for key,value in [('curve_unit',unit),('op_unit',op_unit),('power_unit',power_unit),('output_unit',output_unit)]:at.selectbox(key='p3n_'+key).select(value)
        for i,(flow,power) in enumerate(points):
            at.number_input(key=f'p3n_q_{i}').set_value(flow);at.number_input(key=f'p3n_p_{i}').set_value(power)
        at.number_input(key='p3n_operating').set_value(q);return at
    def calculate(self,at):
        at.button(key='p3n_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def integrated(self):
        at=self.app();at.selectbox(key='p3n_method').select(ui.METHODS_3N[1]).run()
        at.number_input(key='p3n_count').set_value(5);at.number_input(key='p3n_qh_count').set_value(5).run()
        for key,value in [('curve_unit','m³/hr'),('op_unit','m³/hr'),('power_unit','kW'),('output_unit','kW'),('head_unit','m')]:at.selectbox(key='p3n_'+key).select(value)
        for i,((q,p),(pq,h)) in enumerate(zip(POINTS,PUMP)):
            for key,value in [('q',q),('p',p),('pq',pq),('ph',h)]:at.number_input(key=f'p3n_{key}_{i}').set_value(value)
        for key,value in [('static',10),('reference',100),('friction',20)]:at.number_input(key='p3n_'+key).set_value(value)
        return at
    def driver(self,at,rating=15,unit='kW'):
        at.number_input(key='p3n_driver').set_value(rating);at.selectbox(key='p3n_driver_unit').select(unit);return at
    def test_render_explicit_units_blank_criteria_guidance(self):
        at=self.app();self.assertFalse(at.exception)
        self.assertTrue(any(e.label=='3N — Pump Power Curve / Driver Loading Check' for e in at.expander))
        for key in ['curve_unit','op_unit','power_unit','output_unit','driver_unit']:self.assertIsNone(at.selectbox(key='p3n_'+key).value)
        for key in ['driver','required','operating','q_0','p_0']:self.assertIsNone(at.number_input(key='p3n_'+key).value)
        self.assertEqual(at.selectbox(key='p3n_method').options,list(ui.METHODS_3N))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3n_')])
        self.assertTrue(any(ui.GUIDANCE in w.value for w in at.info))
        self.assertTrue(any('relevant operating range' in w.value for w in at.caption))
    def test_125_maximum_plot(self):
        at=self.calculate(self.fill());text=self.text(at)
        self.assertIn('Vendor Interpolated Shaft Power: 10 kW',text);self.assertIn('Maximum Supplied Vendor Power: 16 kW',text);self.assertIn('Flow(s) at Maximum Supplied Vendor Power: 250 m³/hr',text)
        self.assertNotIn('Driver Power Margin',text);self.assertFalse(at.error)
        self.assertEqual(len(json.loads(at.get('vega_lite_chart')[0].proto.spec)['layer']),4)
    def test_175(self):self.assertIn('Vendor Interpolated Shaft Power: 12.75 kW',self.text(self.calculate(self.fill(q=175))))
    def test_exact150(self):self.assertIn('Vendor Interpolated Shaft Power: 11.5 kW',self.text(self.calculate(self.fill(q=150))))
    def test_lower50(self):self.assertIn('Vendor Interpolated Shaft Power: 6 kW',self.text(self.calculate(self.fill(q=50))))
    def test_upper250(self):self.assertIn('Vendor Interpolated Shaft Power: 16 kW',self.text(self.calculate(self.fill(q=250))))
    def test_below25(self):
        at=self.calculate(self.fill(q=25));self.assertEqual(at.error[0].value,core.OUT_OF_RANGE);self.assertNotIn('Vendor Interpolated Shaft Power:',self.text(at));self.assertFalse(at.get('vega_lite_chart'))
    def test_above275(self):
        at=self.calculate(self.fill(q=275));self.assertEqual(at.error[0].value,core.OUT_OF_RANGE);self.assertFalse(at.get('vega_lite_chart'))
    def test_duplicate(self):
        at=self.calculate(self.fill(points=[(50,6),(50,8),(150,11)]));self.assertIn('unique',at.error[0].value)
    def test_negative_vendor_power(self):
        at=self.calculate(self.fill(points=[(50,-6),(100,8.5),(150,11.5)]));self.assertTrue(at.error)
    def test_nonmonotonic_and_tied_maxima(self):
        at=self.calculate(self.fill(points=[(50,16),(100,8),(150,16)]));self.assertIn('Vendor Interpolated Shaft Power: 12 kW',self.text(at));self.assertIn('Power: 50, 150 m³/hr',self.text(at));self.assertFalse(at.error)
    def test_mixed_flow_units(self):
        for unit in ['m³/s','L/s','L/min','Gallon/min (US GPM)']:
            at=self.calculate(self.fill(q=125/3600/FLOW[unit],op_unit=unit));self.assertIn('Vendor Interpolated Shaft Power: 10 kW',self.text(at))
    def test_mixed_power_units(self):
        hp=POWER_FACTORS['Mechanical hp'];at=self.fill(points=[(q,p*1000/hp) for q,p in POINTS],power_unit='Mechanical hp',output_unit='W');self.driver(at,15,'kW');self.calculate(at)
        self.assertIn('Vendor Interpolated Shaft Power: 10000 W',self.text(at));self.assertIn('Driver Power Margin: 5000 W',self.text(at))
    def test_hp_display(self):
        at=self.calculate(self.fill(output_unit='Mechanical hp'));self.assertIn(f'{10000/POWER_FACTORS["Mechanical hp"]:.12g} Mechanical hp',self.text(at))
    def test_driver_standard(self):
        at=self.calculate(self.driver(self.fill()));text=self.text(at);self.assertIn('Driver Power Margin: 5 kW',text);self.assertIn('Driver Power Margin %: 50%',text);self.assertIn('Entered driver rating is above interpolated shaft power.',text)
    def test_driver_equal(self):
        at=self.calculate(self.driver(self.fill(),10));self.assertIn('Driver Power Margin: 0 kW',self.text(at));self.assertIn('Margin %: 0%',self.text(at));self.assertIn('rating equals interpolated shaft power.',self.text(at))
    def test_driver_below_signed(self):
        at=self.calculate(self.driver(self.fill(points=[(50,12),(125,12),(250,12)]),10));self.assertIn('Driver Power Margin: -2 kW',self.text(at));self.assertIn('Margin %: -16.6666666667%',self.text(at));self.assertIn('rating is below interpolated shaft power.',self.text(at))
    def test_zero_shaft_percent_na(self):
        at=self.fill(points=[(50,0),(125,0),(250,0)]);self.driver(at);at.number_input(key='p3n_required').set_value(10);self.calculate(at)
        self.assertIn('Driver Power Margin %: N/A — shaft power is zero',self.text(at));self.assertIn('Criterion Status: N/A — shaft power is zero',self.text(at))
    def test_inclusive_criterion(self):
        at=self.driver(self.fill());at.number_input(key='p3n_required').set_value(50);self.calculate(at);self.assertIn('Meets entered driver power margin',self.text(at))
        at.number_input(key='p3n_required').set_value(51);self.calculate(at);self.assertIn('Does not meet entered driver power margin',self.text(at))
    def test_criterion_requires_driver(self):
        at=self.fill();at.number_input(key='p3n_required').set_value(10);self.calculate(at);self.assertIn('Enter Driver/Motor Rated Power',at.error[0].value)
    def test_negative_criterion_and_zero_driver_rejected(self):
        at=self.driver(self.fill());at.number_input(key='p3n_required').set_value(-1);self.calculate(at);self.assertTrue(at.error)
        at.number_input(key='p3n_required').set_value(None);at.number_input(key='p3n_driver').set_value(0);self.calculate(at);self.assertTrue(at.error)
    def test_missing_units_and_stale_results(self):
        at=self.calculate(self.fill());self.assertIn('Vendor Interpolated Shaft Power:',self.text(at))
        at.number_input(key='p3n_operating').set_value(175).run();self.assertNotIn('Vendor Interpolated Shaft Power:',self.text(at))
        at.selectbox(key='p3n_output_unit').set_value(None);self.calculate(at);self.assertTrue(at.error)
    def test_integrated_3g_shared_solver(self):
        at=self.integrated()
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as spy:self.calculate(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Vendor Interpolated Shaft Power: 9.97577490024 kW',self.text(at));self.assertIn('Operating Flow: 124.596248337 m³/hr',self.text(at));self.assertFalse(at.error)
    def test_integrated_direct_k(self):
        at=self.integrated();at.selectbox(key='p3n_sys_method').select('From System Resistance Coefficient K').run();at.number_input(key='p3n_k').set_value(20/(100/3600)**2);self.calculate(at)
        self.assertIn('Vendor Interpolated Shaft Power: 9.97577490024 kW',self.text(at))
    def test_integrated_no_root(self):
        at=self.integrated();at.number_input(key='p3n_static').set_value(100);self.calculate(at);self.assertTrue(at.error);self.assertNotIn('Vendor Interpolated Shaft Power:',self.text(at))
    def test_integrated_multiple_and_coincident(self):
        for roots in [SimpleNamespace(coincident_intervals=(),points=(1,2)),SimpleNamespace(coincident_intervals=(1,),points=())]:
            at=self.integrated()
            with patch.object(ui,'find_operating_points',return_value=roots):self.calculate(at)
            self.assertTrue(at.error);self.assertNotIn('Vendor Interpolated Shaft Power:',self.text(at))
    def enable_comparison(self,at,mode=1):
        at.selectbox(key='p3n_comparison').select(ui.COMPARISONS[mode]).run()
        at.number_input(key='p3n_density').set_value(1000);at.selectbox(key='p3n_density_unit').select('kg/m³')
        return at
    def test_optional_manual_comparison(self):
        at=self.enable_comparison(self.fill());at.number_input(key='p3n_comparison_head').set_value(40);at.selectbox(key='p3n_comparison_head_unit').select('m');at.number_input(key='p3n_efficiency').set_value(81)
        self.calculate(at);self.assertIn('Calculated Shaft Power: 16.8152434842 kW',self.text(at));self.assertIn('Power Difference: 6.81524348422 kW',self.text(at));self.assertIn('Power Difference %: 68.1524348422%',self.text(at))
    def test_optional_integrated_3m_comparison(self):
        at=self.enable_comparison(self.integrated(),2);at.number_input(key='p3n_eff_count').set_value(5).run()
        for i,(q,e) in enumerate(EFFICIENCY):at.number_input(key=f'p3n_eq_{i}').set_value(q);at.number_input(key=f'p3n_ee_{i}').set_value(e)
        with patch.object(core,'interpolate_efficiency',wraps=core.interpolate_efficiency) as spy:self.calculate(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Comparison Pump Efficiency: 80.9515498005%',self.text(at));self.assertIn('Calculated Shaft Power:',self.text(at));self.assertFalse(at.error)
    def test_optional_efficiency_range_rejected(self):
        at=self.enable_comparison(self.fill(),2);at.number_input(key='p3n_comparison_head').set_value(40);at.selectbox(key='p3n_comparison_head_unit').select('m')
        for i,(q,e) in enumerate([(150,65),(200,80),(250,70)]):at.number_input(key=f'p3n_eq_{i}').set_value(q);at.number_input(key=f'p3n_ee_{i}').set_value(e)
        self.calculate(at);self.assertIn('efficiency is not extrapolated',at.error[0].value);self.assertNotIn('Vendor Interpolated Shaft Power:',self.text(at))
    def test_prior_3l_3m_files_unchanged(self):
        expected={'series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
