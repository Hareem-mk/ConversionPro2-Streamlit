"""Bounded vendor NPSHR curves and shared 3G/2H/3J UI integration."""
import hashlib,json,math
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from app import FLOW
from pump_performance import npshr_curve as core,npshr_curve_ui as ui
from pump_performance.pump_curve import HEAD_FACTORS,create_pump_curve
from pump_performance.system_curve import model_from_reference
from pump_performance.operating_point import find_operating_points
from pump_performance.npsh_margin import calculate_npsh_margin,compare_required_margin

POINTS=[(50,2.5),(100,3.2),(150,4.4),(200,6),(250,8)]
PUMP=[(0,50),(50,48),(100,44),(150,38),(200,30)]
ROOT=Path(__file__).resolve().parents[1]

def curve(points=POINTS,unit='m³/hr',head_unit='m'):
    return core.create_npshr_curve(points,unit,head_unit,FLOW)

class NPSHRCurveTests(unittest.TestCase):
    def test_all_benchmarks(self):
        for q,r in [(125,3.8),(175,5.2),(150,4.4),(50,2.5),(250,8)]:
            self.assertAlmostEqual(core.interpolate_npshr(curve(),q/3600).npshr_m,r,12)
    def test_exact_points(self):
        c=curve()
        for p in c.points:
            r=core.interpolate_npshr(c,p.flow_m3_s);self.assertTrue(r.exact_point);self.assertEqual(r.npshr_m,p.npshr_m)
    def test_endpoints_roundoff_not_extrapolation(self):
        c=curve()
        for p,d in [(c.points[0],-math.inf),(c.points[-1],math.inf)]:
            self.assertEqual(core.interpolate_npshr(c,math.nextafter(p.flow_m3_s,d)).npshr_m,p.npshr_m)
            with self.assertRaisesRegex(ValueError,'not extrapolated'):core.interpolate_npshr(c,p.flow_m3_s+(-1 if d<0 else 1)*1e-10)
    def test_outside_range(self):
        for q in [25,275]:
            with self.assertRaisesRegex(ValueError,'not extrapolated'):core.interpolate_npshr(curve(),q/3600)
    def test_sort_nonmonotonic(self):
        c=curve([(150,4),(50,5),(100,3)])
        self.assertEqual([p.npshr_m for p in c.points],[5,3,4]);self.assertAlmostEqual(core.interpolate_npshr(c,125/3600).npshr_m,3.5)
    def test_extrema(self):
        e=core.find_npshr_extrema(curve());self.assertEqual(e.minimum_m,2.5);self.assertEqual(e.maximum_m,8);self.assertEqual(e.minimum_flows_m3_s,(50/3600,));self.assertEqual(e.maximum_flows_m3_s,(250/3600,))
    def test_all_tied_extrema_reported_once(self):
        c=curve([(0,3),(50,5),(100,3),(150,5),(200,4)])
        e=core.find_npshr_extrema(c);self.assertEqual(e.minimum_flows_m3_s,(0,100/3600));self.assertEqual(e.maximum_flows_m3_s,(50/3600,150/3600))
        e=core.find_npshr_extrema(curve([(0,3),(50,3),(100,3)]));self.assertEqual(len(e.minimum_flows_m3_s),3);self.assertEqual(len(e.maximum_flows_m3_s),3)
    def test_duplicate_malformed_minimum(self):
        for pts in [POINTS[:2],[(50,2),(50,3),(100,4)],[(1,1),None,(3,3)],[(1,1),(2,2),(3,)]]:
            with self.assertRaises(ValueError):curve(pts)
    def test_invalid_inputs(self):
        for column in [0,1]:
            for bad in [None,True,-1,math.nan,math.inf,-math.inf,'bad']+([0] if column==1 else []):
                pts=POINTS.copy();r=list(pts[0]);r[column]=bad;pts[0]=r
                with self.subTest(column=column,bad=bad),self.assertRaises(ValueError):curve(pts)
    def test_invalid_operating(self):
        for bad in [None,True,-1,math.nan,math.inf,-math.inf]:
            with self.assertRaises(ValueError):core.interpolate_npshr(curve(),bad)
    def test_unsupported_units_and_overflow(self):
        for fu,hu in [(None,'m'),('m³/hr',None),('bad','m'),('m³/hr','bad')]:
            with self.assertRaises(ValueError):curve(unit=fu,head_unit=hu)
        with self.assertRaises(ValueError):core.create_npshr_curve(POINTS,'huge','m',{'huge':1e308})
    def test_all_flow_and_head_units(self):
        for unit,f in FLOW.items():
            for hu,hf in HEAD_FACTORS.items():
                c=curve([(q/3600/f,r/hf) for q,r in POINTS],unit,hu)
                self.assertAlmostEqual(core.interpolate_npshr(c,125/3600).npshr_m,3.8,11)
    def test_zero_flow_allowed_positive_head(self):
        c=curve([(0,2),(1,3),(2,4)],'m³/s');self.assertEqual(core.interpolate_npshr(c,0).npshr_m,2)
    def test_immutable(self):
        with self.assertRaises(FrozenInstanceError):curve().points=()
    def test_integrated_3g_3j_values(self):
        pump=create_pump_curve(PUMP,'m³/hr','m',FLOW)
        model=model_from_reference(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,flow_unit='m³/hr',flow_factors=FLOW)
        op=find_operating_points(pump,model).points[0];r=core.interpolate_npshr(curve(),op.flow_m3_s)
        self.assertAlmostEqual(r.npshr_m,3.7903099600976735,12)
        m=calculate_npsh_margin(12.026359664105,r.npshr_m)
        self.assertAlmostEqual(m.margin_m,8.236049704007326,11)
        self.assertAlmostEqual(m.ratio,12.026359664105/r.npshr_m,13)
    def test_manual_3j_values(self):
        r=core.interpolate_npshr(curve(),125/3600);m=calculate_npsh_margin(12.026359664105,r.npshr_m)
        self.assertAlmostEqual(m.margin_m,8.226359664105,12);self.assertAlmostEqual(m.ratio,3.164831490553947,12);self.assertAlmostEqual(m.percent_margin,216.4831490553947,10)
    def test_plot_bounded_markers(self):
        c=curve();spec=ui.npshr_plot_spec(c,FLOW['m³/hr'],'m³/hr','m',core.interpolate_npshr(c,125/3600))
        self.assertEqual([r['flow'] for r in spec['layer'][0]['data']['values']],[50,100,150,200,250])
        self.assertNotIn('y',spec['encoding']);self.assertNotIn('encoding',spec['layer'][1]);self.assertEqual(spec['layer'][1]['data']['values'],[{'flow':125}]);self.assertAlmostEqual(spec['layer'][2]['data']['values'][0]['npshr'],3.8)

class NPSHRAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(ROOT/'app.py')).run()
    def fill(self,at=None,points=POINTS,q=125,unit='m³/hr',op_unit='m³/hr',r_unit='m',output_unit='m'):
        at=at or self.app();at.number_input(key='p3o_count').set_value(len(points)).run()
        for key,value in [('curve_unit',unit),('op_unit',op_unit),('r_unit',r_unit),('output_unit',output_unit)]:at.selectbox(key='p3o_'+key).select(value)
        for i,(qv,r) in enumerate(points):at.number_input(key=f'p3o_q_{i}').set_value(qv);at.number_input(key=f'p3o_r_{i}').set_value(r)
        at.number_input(key='p3o_operating').set_value(q);return at
    def calc(self,at):
        at.button(key='p3o_calculate').click().run();self.assertFalse(at.exception);return at
    def text(self,at):return '\n'.join(w.value for w in at.text)
    def manual_available(self,at,value=12.026359664105,unit='m'):
        at.selectbox(key='p3o_available_method').select('Manual NPSHA').run();at.number_input(key='p3o_available').set_value(value);at.selectbox(key='p3o_a_unit').select(unit);return at
    def integrated(self):
        at=self.app();at.selectbox(key='p3o_method').select(ui.METHODS_3O[1]).run();at.number_input(key='p3o_count').set_value(5);at.number_input(key='p3o_qh_count').set_value(5).run()
        for key,value in [('curve_unit','m³/hr'),('op_unit','m³/hr'),('r_unit','m'),('output_unit','m'),('head_unit','m')]:at.selectbox(key='p3o_'+key).select(value)
        for i,((q,r),(pq,h)) in enumerate(zip(POINTS,PUMP)):
            for key,value in [('q',q),('r',r),('pq',pq),('ph',h)]:at.number_input(key=f'p3o_{key}_{i}').set_value(value)
        for key,value in [('static',10),('reference',100),('friction',20)]:at.number_input(key='p3o_'+key).set_value(value)
        return at
    def phase2(self,at,source=True,gauge=False):
        at.selectbox(key='p3o_available_method').select('Vessel/Source Method' if source else 'Suction-Flange Method').run()
        at.selectbox(key='p3o_basis').select('Gauge' if gauge else 'Absolute').run()
        at.selectbox(key='p3o_pressure_unit').select('Kilopascal (kPa)');at.selectbox(key='p3o_vapor_unit').select('Kilopascal (kPa)')
        at.text_input(key='p3o_datum').set_value('Pump centreline')
        values=dict(pressure=0 if gauge else (101.325 if source else 150),vapor=3,density=1000,velocity=0 if source else 2,elevation=3 if source else 0,datum_elevation=0)
        if source:values['suction_loss']=1
        if gauge:values['atmosphere']=101.325;at.selectbox(key='p3o_atm_unit').select('Kilopascal (kPa)')
        for key,value in values.items():at.number_input(key='p3o_'+key).set_value(value)
        return at
    def test_initial_render_units_blank_inputs_guidance(self):
        at=self.app();self.assertFalse(at.exception);self.assertTrue(any(e.label=='3O — NPSHR Curve / Operating NPSHR' for e in at.expander))
        for key in ['curve_unit','op_unit','r_unit','output_unit']:self.assertIsNone(at.selectbox(key='p3o_'+key).value)
        for key in ['q_0','r_0','operating']:self.assertIsNone(at.number_input(key='p3o_'+key).value)
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3o_')]);self.assertTrue(any(ui.GUIDANCE in w.value for w in at.info))
        caps=' '.join(w.value for w in at.caption if 'NPSHR' in w.value);self.assertIn('does not generate or estimate',caps);self.assertNotIn('cavitation-free',caps)
    def test_125_and_extrema(self):
        at=self.calc(self.fill());text=self.text(at);self.assertFalse(at.error)
        for expected in ['Interpolated Vendor NPSHR: 3.8 m','Supplied NPSHR Flow Range: 50 to 250 m³/hr','Minimum Supplied NPSHR: 2.5 m','Maximum Supplied NPSHR: 8 m','Flow(s) at Minimum Supplied NPSHR: 50 m³/hr','Flow(s) at Maximum Supplied NPSHR: 250 m³/hr']:self.assertIn(expected,text)
        self.assertEqual(len(json.loads(at.get('vega_lite_chart')[0].proto.spec)['layer']),3)
    def test_175(self):self.assertIn('Interpolated Vendor NPSHR: 5.2 m',self.text(self.calc(self.fill(q=175))))
    def test_exact150(self):self.assertIn('Interpolated Vendor NPSHR: 4.4 m',self.text(self.calc(self.fill(q=150))))
    def test_lower50(self):self.assertIn('Interpolated Vendor NPSHR: 2.5 m',self.text(self.calc(self.fill(q=50))))
    def test_upper250(self):self.assertIn('Interpolated Vendor NPSHR: 8 m',self.text(self.calc(self.fill(q=250))))
    def test_below25(self):
        at=self.calc(self.fill(q=25));self.assertEqual(at.error[0].value,core.OUT_OF_RANGE);self.assertFalse(at.get('vega_lite_chart'));self.assertNotIn('Interpolated Vendor NPSHR:',self.text(at))
    def test_above275(self):
        at=self.calc(self.fill(q=275));self.assertEqual(at.error[0].value,core.OUT_OF_RANGE);self.assertFalse(at.get('vega_lite_chart'))
    def test_duplicate(self):
        at=self.calc(self.fill(points=[(50,2),(50,3),(100,4)]));self.assertIn('unique',at.error[0].value)
    def test_zero_npshr(self):
        at=self.calc(self.fill(points=[(50,0),(100,3),(150,4)]));self.assertTrue(at.error)
    def test_negative_npshr(self):
        at=self.calc(self.fill(points=[(50,-1),(100,3),(150,4)]));self.assertTrue(at.error)
    def test_nonmonotonic_tied_extrema(self):
        at=self.calc(self.fill(points=[(0,3),(50,5),(100,3),(150,5),(200,4)]));text=self.text(at)
        self.assertIn('Interpolated Vendor NPSHR: 4 m',text);self.assertIn('Flow(s) at Minimum Supplied NPSHR: 0, 100',text);self.assertIn('Flow(s) at Maximum Supplied NPSHR: 50, 150',text);self.assertFalse(at.error)
    def test_mixed_flow_units(self):
        for unit in ['m³/s','L/s','L/min','Gallon/min (US GPM)']:
            at=self.calc(self.fill(q=125/3600/FLOW[unit],op_unit=unit));self.assertIn('Interpolated Vendor NPSHR: 3.8 m',self.text(at))
    def test_ft_curve_m_result(self):
        at=self.calc(self.fill(points=[(q,r/HEAD_FACTORS['ft']) for q,r in POINTS],r_unit='ft'));self.assertIn('Interpolated Vendor NPSHR: 3.8 m',self.text(at))
    def test_m_curve_ft_result(self):
        at=self.calc(self.fill(output_unit='ft'));self.assertIn(f'Interpolated Vendor NPSHR: {3.8/HEAD_FACTORS["ft"]:.12g} ft',self.text(at))
    def test_manual_available_shared3j(self):
        at=self.manual_available(self.fill())
        with patch.object(ui,'calculate_npsh_margin',wraps=calculate_npsh_margin) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);text=self.text(at)
        for expected in ['NPSH Margin: 8.2263596641 m','NPSHA / NPSHR Ratio: 3.16483149055','Percent Margin: 216.483149055%','NPSHA is above entered NPSHR.']:self.assertIn(expected,text)
    def test_criterion_blank_no_default(self):
        at=self.manual_available(self.fill());self.assertIsNone(at.number_input(key='p3o_criterion').value);self.assertIsNone(at.selectbox(key='p3o_criterion_unit').value);self.calc(at);self.assertNotIn('Criterion Status:',self.text(at))
    def test_required_margin_reuses3j_inclusive(self):
        at=self.manual_available(self.fill());actual=calculate_npsh_margin(12.026359664105,core.interpolate_npshr(curve(),125/3600).npshr_m).margin_m
        at.number_input(key='p3o_criterion').set_value(actual);at.selectbox(key='p3o_criterion_unit').select('m')
        with patch.object(ui,'compare_required_margin',wraps=compare_required_margin) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Meets entered required margin',self.text(at));self.assertIn('Excess Above Required Margin: 0 m',self.text(at))
        at.number_input(key='p3o_criterion').set_value(actual+1);self.calc(at);self.assertIn('Does not meet entered required margin',self.text(at))
    def test_mixed_available_criterion_units(self):
        at=self.manual_available(self.fill(),12.026359664105/HEAD_FACTORS['ft'],'ft');at.number_input(key='p3o_criterion').set_value(1/HEAD_FACTORS['ft']);at.selectbox(key='p3o_criterion_unit').select('ft');self.calc(at);self.assertIn('Required Margin: 1 m',self.text(at));self.assertIn('Meets entered required margin',self.text(at))
    def test_negative_manual_available_rejected(self):
        at=self.calc(self.manual_available(self.fill(),-1));self.assertTrue(at.error)
    def test_negative_required_rejected(self):
        at=self.manual_available(self.fill());at.number_input(key='p3o_criterion').set_value(-1);at.selectbox(key='p3o_criterion_unit').select('m');self.calc(at);self.assertTrue(at.error)
    def test_shared3j_equal_below(self):
        r=core.interpolate_npshr(curve(),125/3600).npshr_m
        for a,status in [(r,'equals'),(r-1,'is below')]:
            at=self.calc(self.manual_available(self.fill(),a));self.assertIn('NPSHA '+status+' entered NPSHR.',self.text(at))
    def test_integrated3g_and3j(self):
        at=self.manual_available(self.integrated())
        with patch.object(ui,'find_operating_points',wraps=find_operating_points) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertIn('Operating Flow: 124.596248337 m³/hr',self.text(at));self.assertIn('Interpolated Vendor NPSHR: 3.7903099601 m',self.text(at));self.assertIn('NPSH Margin: 8.23604970401 m',self.text(at));self.assertFalse(at.error)
    def test_integrated_direct_k(self):
        at=self.integrated();at.selectbox(key='p3o_sys_method').select('From System Resistance Coefficient K').run();at.number_input(key='p3o_k').set_value(20/(100/3600)**2);self.calc(at);self.assertIn('Interpolated Vendor NPSHR: 3.7903099601 m',self.text(at))
    def test_integrated_no_root(self):
        at=self.integrated();at.number_input(key='p3o_static').set_value(100);self.calc(at);self.assertTrue(at.error);self.assertFalse(at.get('vega_lite_chart'))
    def test_multiple_and_coincident_roots_withheld(self):
        for roots in [SimpleNamespace(coincident_intervals=(),points=(1,2)),SimpleNamespace(coincident_intervals=(1,),points=())]:
            at=self.integrated()
            with patch.object(ui,'find_operating_points',return_value=roots):self.calc(at)
            self.assertTrue(at.error);self.assertNotIn('Interpolated Vendor NPSHR:',self.text(at))
    def test_phase2_source_reused(self):
        at=self.phase2(self.fill())
        with patch.object(ui,'source_npsha',wraps=ui.source_npsha) as spy,patch.object(ui,'margin_from_phase2h',wraps=ui.margin_from_phase2h) as margin:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertEqual(margin.call_count,1);self.assertIn('NPSHA: 12.0263596641 m',self.text(at));self.assertIn('NPSH Margin: 8.22635966411 m',self.text(at));self.assertFalse(at.error)
    def test_phase2_flange_reused(self):
        at=self.phase2(self.fill(),False)
        with patch.object(ui,'flange_npsha',wraps=ui.flange_npsha) as spy:self.calc(at)
        self.assertEqual(spy.call_count,1);self.assertIn('NPSHA: 15.1937715734 m',self.text(at));self.assertFalse(at.error)
    def test_phase2_gauge_and_explicit_atmosphere(self):
        at=self.phase2(self.fill(),gauge=True);self.calc(at);self.assertIn('NPSHA: 12.0263596641 m',self.text(at))
        at.number_input(key='p3o_atmosphere').set_value(None);self.calc(at);self.assertTrue(at.error)
    def test_phase2_signed_negative_and_warnings_retained(self):
        at=self.phase2(self.fill());at.number_input(key='p3o_suction_loss').set_value(30);self.calc(at);self.assertIn('NPSHA: -16.9736403359 m',self.text(at));self.assertTrue(at.warning);self.assertIn('NPSHA is below entered NPSHR.',self.text(at))
    def test_phase2_datum_required(self):
        at=self.phase2(self.fill());at.text_input(key='p3o_datum').set_value('');self.calc(at);self.assertIn('common elevation datum',at.error[0].value)
    def test_missing_units_stale_results(self):
        at=self.calc(self.fill());at.number_input(key='p3o_operating').set_value(175).run();self.assertNotIn('Interpolated Vendor NPSHR:',self.text(at));at.selectbox(key='p3o_output_unit').set_value(None);self.calc(at);self.assertTrue(at.error)
    def test_previous_files_unchanged(self):
        expected={'series_parallel.py': '0400d2031b8e0d05549cbd38b6812eebfc44d765c76aeff039c1ef0d23ca79fc', 'series_parallel_ui.py': 'e56a7d74786d02d227169863ee883d3536c80350c43e900624ece6e157ffa9de', 'power_curve.py': '81e75519b0be7b6c03ed544a46b7bec651933de5d7b74695f01cc8abcf27791d', 'power_curve_ui.py': '56344b333c7dac8c090bfac55bbd8788ca1484cb157a93713ca57e6815237c7e', 'efficiency_curve.py': 'c05f05b68d9f76a89908219c11b8f086559cd5dad562bb48395f1d4b5283856d', 'efficiency_curve_ui.py': 'febf597773051e347819203a2ef5aab52a414b277daf906f050bcdaf0ebe0012'}
        for name,digest in expected.items():self.assertEqual(hashlib.sha256((ROOT/'pump_performance'/name).read_bytes()).hexdigest(),digest)

if __name__=='__main__':unittest.main(verbosity=2)
