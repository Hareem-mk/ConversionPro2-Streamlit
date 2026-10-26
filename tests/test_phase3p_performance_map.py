"""Shared-kernel performance review, partial availability and production UI paths."""
import hashlib,json,math
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app import FLOW
from pump_performance import performance_map as core,performance_map_ui as ui
from pump_performance.pump_curve import create_pump_curve,HEAD_FACTORS
from pump_performance.efficiency_curve import create_efficiency_curve
from pump_performance.power_curve import create_power_curve
from pump_performance.npshr_curve import create_npshr_curve
from pump_performance.shaft_power import POWER_FACTORS

HEAD=[(0,50),(50,48),(100,44),(150,38),(200,30)]
EFF=[(50,65),(100,78),(150,84),(200,80),(250,70)]
POWER=[(50,6),(100,8.5),(150,11.5),(200,14),(250,16)]
NPSHR=[(50,2.5),(100,3.2),(150,4.4),(200,6),(250,8)]
ROOT=Path(__file__).resolve().parents[1]

def curves():
    return (create_pump_curve(HEAD,'m³/hr','m',FLOW),create_efficiency_curve(EFF,'m³/hr',FLOW),
            create_power_curve(POWER,'m³/hr','kW',FLOW),create_npshr_curve(NPSHR,'m³/hr','m',FLOW))
def evaluate(q=125,cs=None):return core.evaluate_performance_map(q/3600,*(cs or curves()))

class PerformanceMapCoreTests(unittest.TestCase):
    def test_manual_benchmark(self):
        r=evaluate();self.assertEqual(r.head_result.head_m,41);self.assertAlmostEqual(r.efficiency_result.efficiency_percent,81);self.assertEqual(r.power_result.shaft_power_w,10000);self.assertAlmostEqual(r.npshr_result.npshr_m,3.8)
    def test_common_range(self):
        r=core.determine_common_flow_range(*curves());self.assertEqual(r.minimum_m3_s,50/3600);self.assertEqual(r.maximum_m3_s,200/3600)
    def test_upper_partial225(self):
        r=evaluate(225);self.assertIsNone(r.head_result);self.assertEqual(r.efficiency_result.efficiency_percent,75);self.assertEqual(r.power_result.shaft_power_w,15000);self.assertEqual(r.npshr_result.npshr_m,7)
        self.assertIn('outside',dict(r.range_statuses)['Pump Head'])
    def test_lower_partial25(self):
        r=evaluate(25);self.assertEqual(r.head_result.head_m,49)
        for v in [r.efficiency_result,r.power_result,r.npshr_result]:self.assertIsNone(v)
    def test_all_outside(self):
        r=evaluate(300);self.assertTrue(all(v is None for v in [r.head_result,r.efficiency_result,r.power_result,r.npshr_result]));self.assertTrue(all('Unavailable' in s for _,s in r.range_statuses))
    def test_no_common_range_keeps_partial(self):
        cs=list(curves());cs[1]=create_efficiency_curve([(300,65),(400,70),(500,80)],'m³/hr',FLOW)
        r=evaluate(cs=cs);self.assertIsNone(r.common_flow_range);self.assertIsNone(r.efficiency_result);self.assertEqual(r.head_result.head_m,41)
    def test_single_contact_range(self):
        cs=list(curves());cs[1]=create_efficiency_curve([(200,65),(300,70),(400,80)],'m³/hr',FLOW)
        r=evaluate(200,cs);self.assertEqual(r.common_flow_range.minimum_m3_s,r.common_flow_range.maximum_m3_s);self.assertEqual(r.efficiency_result.efficiency_percent,65)
    def test_all_interpolation_kernels_reused(self):
        names=['interpolate_pump_head','interpolate_efficiency','interpolate_power','interpolate_npshr']
        from contextlib import ExitStack
        with ExitStack() as stack:
            spies=[stack.enter_context(patch.object(core,n,wraps=getattr(core,n))) for n in names];evaluate()
        for s in spies:self.assertEqual(s.call_count,1)
        self.assertEqual(spies[0].call_args.args[0].flow_factor,1);self.assertAlmostEqual(spies[0].call_args.args[1],125/3600)
    def test_unavailable_kernel_not_called(self):
        with patch.object(core,'interpolate_pump_head',side_effect=AssertionError('must not extrapolate')):self.assertIsNone(evaluate(225).head_result)
        for name in ['interpolate_efficiency','interpolate_power','interpolate_npshr']:
            with patch.object(core,name,side_effect=AssertionError('must not extrapolate')):evaluate(25)
    def test_nonrange_kernel_error_propagates(self):
        with patch.object(core,'interpolate_efficiency',side_effect=ValueError('numeric failure')):
            with self.assertRaisesRegex(ValueError,'numeric failure'):evaluate()
    def test_endpoint_roundoff(self):
        cs=curves();q=math.nextafter(200/3600,math.inf);r=core.evaluate_performance_map(q,*cs);self.assertEqual(r.head_result.head_m,30);self.assertEqual(r.operating_flow_m3_s,q)
        self.assertIsNone(core.evaluate_performance_map(200/3600+1e-10,*cs).head_result)
    def test_units_independent(self):
        for unit,f in FLOW.items():
            hf=HEAD_FACTORS['ft'];pf=POWER_FACTORS['Mechanical hp']
            cs=(create_pump_curve([(q/3600/f,h/hf) for q,h in HEAD],unit,'ft',FLOW),
                create_efficiency_curve(EFF,'m³/hr',FLOW),create_power_curve([(q/3600,p*1000/pf) for q,p in POWER],'m³/s','Mechanical hp',FLOW),
                create_npshr_curve([(q/3600/.001,r/hf) for q,r in NPSHR],'L/s','ft',FLOW))
            r=evaluate(cs=cs);self.assertAlmostEqual(r.head_result.head_m,41,11);self.assertAlmostEqual(r.power_result.shaft_power_w,10000,8);self.assertAlmostEqual(r.npshr_result.npshr_m,3.8,11)
    def test_immutable_and_invalid_flow(self):
        with self.assertRaises(FrozenInstanceError):evaluate().head_result=None
        for bad in [None,True,-1,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):core.evaluate_performance_map(bad,*curves())
    def test_valid_markers_only_and_bounded_lines(self):
        cs=curves()
        for q,lengths in [(125,[3,3,3,3]),(225,[1,3,3,3]),(25,[3,1,1,1])]:
            specs=ui.performance_plot_specs(evaluate(q),*cs,FLOW['m³/hr'],'m³/hr','m','kW')
            self.assertEqual([len(s['layer']) for s in specs],lengths)
            for s,c in zip(specs,cs):
                rows=s['layer'][0]['data']['values'];self.assertAlmostEqual(rows[0]['flow'],c.points[0].flow_m3_s*3600);self.assertAlmostEqual(rows[-1]['flow'],c.points[-1].flow_m3_s*3600)
                self.assertNotIn('y',s['encoding'])

class PerformanceMapAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,q=125,mixed=False):
        at=at or self.app()
        for k in ['head','eff','power','npshr']:at.number_input(key=f'p3p_{k}_count').set_value(5)
        at.run()
        units={'head':'m³/hr','eff':'m³/hr','power':'m³/hr','npshr':'m³/hr'}
        if mixed:units.update(head='L/s',eff='m³/s',power='Gallon/min (US GPM)',npshr='L/min')
        for k,u in units.items():at.selectbox(key=f'p3p_{k}_flow_unit').select(u)
        at.selectbox(key='p3p_head_value_unit').select('ft' if mixed else 'm')
        at.selectbox(key='p3p_power_value_unit').select('Mechanical hp' if mixed else 'kW')
        at.selectbox(key='p3p_npshr_value_unit').select('ft' if mixed else 'm')
        for key,unit in [('op_unit','m³/hr'),('result_head_unit','m'),('result_power_unit','kW')]:at.selectbox(key='p3p_'+key).select(unit)
        for key,points in [('head',HEAD),('eff',EFF),('power',POWER),('npshr',NPSHR)]:
            for i,(flow,v) in enumerate(points):
                if mixed:
                    flow=flow/3600/FLOW[units[key]]
                    if key in ['head','npshr']:v=v/HEAD_FACTORS['ft']
                    if key=='power':v=v*1000/POWER_FACTORS['Mechanical hp']
                at.number_input(key=f'p3p_{key}_q_{i}').set_value(flow);at.number_input(key=f'p3p_{key}_v_{i}').set_value(v)
        if at.selectbox(key='p3p_method').value==ui.METHODS_3P[0]:at.number_input(key='p3p_operating').set_value(q)
        return at
    def calc(self,at):
        at.button(key='p3p_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def integrated(self):
        at=self.app();at.selectbox(key='p3p_method').select(ui.METHODS_3P[1]).run();self.fill(at)
        for key,value in [('static',10),('reference',100),('friction',20)]:at.number_input(key='p3p_'+key).set_value(value)
        return at
    def optional(self,at):
        for key,value in [('bep',150),('npsha',12.026359664105),('driver',15)]:at.number_input(key='p3p_'+key).set_value(value)
        for key,value in [('bep_unit','m³/hr'),('npsha_unit','m'),('driver_unit','kW')]:at.selectbox(key='p3p_'+key).select(value)
        return at
    def specs(self,at):return [json.loads(c.proto.spec) for c in at.get('vega_lite_chart')]
    def test_initial_render_units_and_all_optionals_blank(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3P — Pump Performance Map / Integrated Vendor Curve Check' for e in at.expander))
        for w in at.selectbox:
            if w.key.startswith('p3p_') and w.key!='p3p_method':self.assertIsNone(w.value)
        for w in at.number_input:
            if w.key.startswith('p3p_') and not w.key.endswith('_count'):self.assertIsNone(w.value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3p_')])
        self.assertTrue(any(ui.CONSISTENCY in c.value for c in at.caption));self.assertTrue(any(ui.REVIEW in i.value for i in at.info))
    def test_manual_benchmark_common_range_and_plots(self):
        at=self.calc(self.fill());text=self.text(at);self.assertFalse(at.error)
        for expected in ['Pump Head (vendor interpolated): 41 m','Pump Efficiency (vendor interpolated): 81 %','Pump Shaft/Brake Power (vendor interpolated): 10 kW','Pump NPSHR (vendor interpolated): 3.8 m','Common Valid Vendor Data Flow Range: 50 to 200 m³/hr']:self.assertIn(expected,text)
        self.assertEqual(len(self.specs(at)),4);self.assertEqual([len(s['layer']) for s in self.specs(at)],[3]*4)
        self.assertNotIn('PASS',text);self.assertNotIn('FAIL',text);self.assertNotIn('APPROVED',text)
    def test_partial225(self):
        at=self.calc(self.fill(q=225));text=self.text(at)
        for expected in ['Pump Head: Unavailable','Pump Efficiency (vendor interpolated): 75 %','Pump Shaft/Brake Power (vendor interpolated): 15 kW','Pump NPSHR (vendor interpolated): 7 m']:self.assertIn(expected,text)
        warnings=[w for w in at.warning if 'Unavailable — operating flow' in w.value];self.assertEqual(len(warnings),1);self.assertIn('Pump Head',warnings[0].value);self.assertEqual([len(s['layer']) for s in self.specs(at)],[1,3,3,3])
    def test_partial25(self):
        at=self.calc(self.fill(q=25));text=self.text(at);self.assertIn('Pump Head (vendor interpolated): 49 m',text)
        for label in ['Pump Efficiency','Pump Shaft/Brake Power','Pump NPSHR']:self.assertIn(label+': Unavailable',text)
        self.assertEqual(len([w for w in at.warning if 'Unavailable — operating flow' in w.value]),3);self.assertEqual([len(s['layer']) for s in self.specs(at)],[3,1,1,1])
    def test_integrated_3g_benchmark(self):
        at=self.integrated()
        with patch.object(ui,'find_operating_points',wraps=ui.find_operating_points) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);text=self.text(at)
        for expected in ['124.596248337 m³/hr','Pump Head (vendor interpolated): 41.0484501995 m','Pump Efficiency (vendor interpolated): 80.9515498005 %','Pump Shaft/Brake Power (vendor interpolated): 9.97577490024 kW','Pump NPSHR (vendor interpolated): 3.7903099601 m']:self.assertIn(expected,text)
        self.assertEqual([len(s['layer']) for s in self.specs(at)],[4,3,3,3]);self.assertFalse(at.error)
    def test_integrated_direct_k(self):
        at=self.integrated();at.selectbox(key='p3p_sys_method').select('From System Resistance Coefficient K').run();at.number_input(key='p3p_k').set_value(20/(100/3600)**2);self.calc(at);self.assertIn('124.596248337 m³/hr',self.text(at))
    def test_integrated_missing_efficiency_coverage_keeps_others(self):
        at=self.integrated()
        for i,(q,e) in enumerate(EFF):at.number_input(key=f'p3p_eff_q_{i}').set_value(q+200)
        self.calc(at);self.assertIn('Pump Efficiency: Unavailable',self.text(at));self.assertIn('Pump Shaft/Brake Power (vendor interpolated): 9.97577490024 kW',self.text(at));self.assertFalse(at.error)
    def test_integrated_no_unique_root(self):
        for roots in [SimpleNamespace(coincident_intervals=(),points=()),SimpleNamespace(coincident_intervals=(),points=(1,2)),SimpleNamespace(coincident_intervals=(1,),points=())]:
            at=self.integrated()
            with patch.object(ui,'find_operating_points',return_value=roots):self.calc(at)
            self.assertTrue(at.error);self.assertFalse(at.get('vega_lite_chart'))
    def test_bep_3h_integration_correct_si(self):
        at=self.optional(self.integrated())
        with patch.object(ui,'compare_bep',wraps=ui.compare_bep) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertAlmostEqual(spy.call_args.args[0],124.59624833740307/3600);self.assertAlmostEqual(spy.call_args.args[1],150/3600);self.assertIn('Percent of BEP (calculated): 83.0641655583%',self.text(at))
    def test_npsh_3j_and_driver_3n_shared(self):
        at=self.optional(self.fill())
        with patch.object(ui,'calculate_npsh_margin',wraps=ui.calculate_npsh_margin) as n,patch.object(ui,'calculate_driver_margin',wraps=ui.calculate_driver_margin) as d:self.calc(at)
        self.assertEqual(n.call_count,1);self.assertEqual(d.call_count,1)
        for expected in ['NPSH Margin (calculated): 8.2263596641 m','NPSHA / NPSHR Ratio: 3.16483149055','Driver Power Margin (calculated): 5 kW','Driver Power Margin %: 50%']:self.assertIn(expected,self.text(at))
    def test_criteria_independent(self):
        at=self.optional(self.fill())
        for key,value in [('bep_min',80),('bep_max',90),('required_npsh',1),('required_driver',50)]:at.number_input(key='p3p_'+key).set_value(value)
        at.selectbox(key='p3p_required_npsh_unit').select('m');self.calc(at)
        for expected in ['BEP Criterion Status: Within entered operating range','NPSH Criterion Status: Meets entered required margin','Driver Criterion Status: Meets entered driver power margin']:self.assertIn(expected,self.text(at))
        at.number_input(key='p3p_required_driver').set_value(51);self.calc(at);self.assertIn('Does not meet entered driver power margin',self.text(at))
    def test_optional_invalid_criterion_preserves_summary_and_other_checks(self):
        at=self.optional(self.fill());at.number_input(key='p3p_bep_min').set_value(80);self.calc(at);self.assertTrue(at.error);self.assertIn('Pump Head (vendor interpolated): 41 m',self.text(at));self.assertIn('Driver Power Margin (calculated): 5 kW',self.text(at));self.assertEqual(len(self.specs(at)),4)
    def test_partial25_optionals_report_unavailable(self):
        at=self.calc(self.optional(self.fill(q=25)));self.assertIn('Pump Head (vendor interpolated): 49 m',self.text(at));self.assertTrue(any('NPSH margin unavailable' in i.value for i in at.info));self.assertTrue(any('Driver margin unavailable' in i.value for i in at.info));self.assertIn('Percent of BEP',self.text(at))
    def test_partial225_optionals_still_work(self):
        at=self.calc(self.optional(self.fill(q=225)));self.assertIn('Driver Power Margin (calculated): 0 kW',self.text(at));self.assertIn('NPSH Margin (calculated): 5.0263596641 m',self.text(at));self.assertFalse(at.error)
    def test_mixed_curve_units(self):
        at=self.calc(self.fill(mixed=True))
        for expected in ['Pump Head (vendor interpolated): 41 m','Pump Efficiency (vendor interpolated): 81 %','Pump Shaft/Brake Power (vendor interpolated): 10 kW','Pump NPSHR (vendor interpolated): 3.8 m']:self.assertIn(expected,self.text(at))
    def test_mixed_optional_units(self):
        at=self.fill();at.number_input(key='p3p_bep').set_value(150/3600);at.selectbox(key='p3p_bep_unit').select('m³/s')
        at.number_input(key='p3p_npsha').set_value(12.026359664105/HEAD_FACTORS['ft']);at.selectbox(key='p3p_npsha_unit').select('ft')
        at.number_input(key='p3p_driver').set_value(15000/POWER_FACTORS['Mechanical hp']);at.selectbox(key='p3p_driver_unit').select('Mechanical hp');self.calc(at)
        self.assertIn('Percent of BEP (calculated): 83.3333333333%',self.text(at));self.assertIn('Driver Power Margin (calculated): 5 kW',self.text(at))
    def test_missing_units_invalid_points_and_flow(self):
        at=self.app();self.calc(at);self.assertTrue(at.error)
        at=self.fill();at.number_input(key='p3p_npshr_v_0').set_value(0);self.calc(at);self.assertTrue(at.error)
        at.number_input(key='p3p_npshr_v_0').set_value(2.5);at.number_input(key='p3p_operating').set_value(-1);self.calc(at);self.assertTrue(at.error)
    def test_stale_results_clear(self):
        at=self.calc(self.fill());at.number_input(key='p3p_operating').set_value(225).run();self.assertNotIn('Integrated Performance Summary',' '.join(w.value for w in at.markdown));self.assertFalse(at.get('vega_lite_chart'))
    def test_zero_power_driver_na(self):
        at=self.optional(self.fill())
        for i in range(5):at.number_input(key=f'p3p_power_v_{i}').set_value(0)
        self.calc(at);self.assertIn('Driver Power Margin %: N/A — shaft power is zero',self.text(at))
    def test_no_common_range_ui(self):
        at=self.fill()
        for i,(q,e) in enumerate(EFF):at.number_input(key=f'p3p_eff_q_{i}').set_value(q+300)
        self.calc(at);self.assertIn('Common Valid Vendor Data Flow Range: None',self.text(at));self.assertIn('Pump Head (vendor interpolated): 41 m',self.text(at))
    def test_previous_modules_unchanged(self):
        expected={'series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012', 'power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'npshr_curve.py': '6d17823b568433f4dacfc34760687cf963b2a8040639698503ad98d573964c26', 'npshr_curve_ui.py': '4b343673e3188a1f39296ff2dfb03a9ff68b815b0f1c98077946845e1f3f7cae'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
