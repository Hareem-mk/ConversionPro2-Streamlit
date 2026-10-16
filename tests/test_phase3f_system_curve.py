import json
import math
from pathlib import Path
import unittest
from app import FLOW
from pump_performance.pump_curve import HEAD_FACTORS
from pump_performance.system_curve import (SystemModel, derive_system_k, system_friction_head,
                                            system_head, generate_system_curve, model_from_k,
                                            model_from_reference, head_from_metres)
from pump_performance.system_curve_ui import MODEL_GUIDANCE


def reference(**changes):
    inputs=dict(static_head=10,head_unit='m',reference_flow=100,reference_friction_head=20,
                flow_unit='m³/hr',flow_factors=FLOW)
    inputs.update(changes)
    return model_from_reference(**inputs)


class SystemCurveTests(unittest.TestCase):
    def test_derived_k(self):
        self.assertAlmostEqual(reference().k_si,25920,places=9)
        self.assertAlmostEqual(derive_system_k(100/3600,20),25920,places=9)

    def test_benchmark_100(self):
        r=reference().at_flow(100/3600)
        self.assertEqual(r.static_head_m,10)
        self.assertAlmostEqual(r.friction_head_m,20,places=12)
        self.assertAlmostEqual(r.total_head_m,30,places=12)

    def test_quadratic_scaling(self):
        for q,friction,total in [(0,0,10),(50,5,15),(100,20,30),(150,45,55),(200,80,90)]:
            r=reference().at_flow(q/3600)
            self.assertAlmostEqual(r.friction_head_m,friction,places=12)
            self.assertAlmostEqual(r.total_head_m,total,places=12)

    def test_selected_125(self):
        r=reference().at_flow(125/3600)
        self.assertAlmostEqual(r.friction_head_m,31.25,places=12)
        self.assertAlmostEqual(r.total_head_m,41.25,places=12)

    def test_zero_flow(self):
        r=reference().at_flow(0)
        self.assertEqual((r.friction_head_m,r.total_head_m),(0,10))

    def test_direct_k_equivalence(self):
        direct=model_from_k(10,'m',25920)
        for q in [0,50,100,125,150,200,250]:
            self.assertAlmostEqual(direct.at_flow(q/3600).total_head_m,
                                   reference().at_flow(q/3600).total_head_m,places=12)

    def test_zero_resistance_direct(self):
        model=model_from_k(10,'m',0)
        samples=generate_system_curve(model,200/3600)
        self.assertTrue(all(s.friction_head_m==0 and s.total_head_m==10 for s in samples))

    def test_zero_reference_friction(self):
        model=reference(reference_friction_head=0)
        self.assertEqual(model.k_si,0)
        self.assertEqual(model.at_flow(1e100).total_head_m,10)

    def test_zero_static_head(self):
        r=reference(static_head=0).at_flow(100/3600)
        self.assertEqual(r.static_head_m,0)
        self.assertAlmostEqual(r.friction_head_m,r.total_head_m,places=12)

    def test_flow_units(self):
        for unit,factor in FLOW.items():
            with self.subTest(unit=unit):
                model=reference(reference_flow=(100/3600)/factor,flow_unit=unit)
                self.assertAlmostEqual(model.k_si,25920,places=8)
                self.assertAlmostEqual(model.at_flow(100/3600).total_head_m,30,places=12)

    def test_head_units(self):
        factor=HEAD_FACTORS['ft']
        self.assertAlmostEqual(10/factor,32.8083989501,places=9)
        self.assertAlmostEqual(20/factor,65.6167979003,places=9)
        model=reference(static_head=10/factor,reference_friction_head=20/factor,head_unit='ft')
        self.assertAlmostEqual(model.k_si,reference().k_si,places=9)
        self.assertAlmostEqual(model.at_flow(125/3600).total_head_m,41.25,places=12)
        self.assertAlmostEqual(model_from_k(10/factor,'ft',25920).static_head_m,10,places=12)

    def test_generated_curve_si(self):
        samples=generate_system_curve(reference(),200/3600)
        self.assertEqual(len(samples),81)
        self.assertEqual(samples[0].flow_m3_s,0)
        self.assertEqual(samples[-1].flow_m3_s,200/3600)
        self.assertTrue(all(a.flow_m3_s<b.flow_m3_s for a,b in zip(samples,samples[1:])))
        for index,total in [(0,10),(20,15),(40,30),(60,55),(80,90)]:
            self.assertAlmostEqual(samples[index].total_head_m,total,places=12)

    def test_si_functions(self):
        self.assertAlmostEqual(system_friction_head(100/3600,25920),20,places=12)
        self.assertAlmostEqual(system_head(100/3600,10,25920),30,places=12)

    def test_invalid_static(self):
        for value in (None,'','bad',True,-1,math.nan,math.inf,-math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):reference(static_head=value)
            with self.subTest(value=value),self.assertRaises(ValueError):model_from_k(value,'m',25920)

    def test_invalid_k(self):
        for value in (None,'','bad',True,-1,math.nan,math.inf,-math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):model_from_k(10,'m',value)
            with self.subTest(value=value),self.assertRaises(ValueError):system_friction_head(0,value)

    def test_invalid_reference_flow(self):
        for value in (None,'','bad',True,0,-1,math.nan,math.inf,-math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):reference(reference_flow=value)
        with self.assertRaisesRegex(ValueError,'Reference flow.*greater than zero'):
            reference(reference_flow=0,reference_friction_head=0)

    def test_invalid_friction(self):
        for value in (None,'','bad',True,-1,math.nan,math.inf,-math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):reference(reference_friction_head=value)

    def test_invalid_selected_flow(self):
        for value in (None,'','bad',True,-1,math.nan,math.inf,-math.inf):
            with self.subTest(value=value),self.assertRaises(ValueError):reference().at_flow(value)

    def test_missing_units(self):
        for unit in (None,'','bad'):
            with self.assertRaises(ValueError):reference(flow_unit=unit)
            with self.assertRaises(ValueError):reference(head_unit=unit)
            with self.assertRaises(ValueError):model_from_k(10,unit,25920)

    def test_invalid_plot_range_count(self):
        for maximum in (None,0,-1,math.nan,math.inf):
            with self.assertRaises(ValueError):generate_system_curve(reference(),maximum)
        for count in (True,1,24,101,2.5):
            with self.assertRaises(ValueError):generate_system_curve(reference(),1,count)
        self.assertEqual(len(generate_system_curve(reference(),1,25)),25)
        self.assertEqual(len(generate_system_curve(reference(),1,100)),100)

    def test_display_head_range(self):
        self.assertAlmostEqual(head_from_metres(10,'ft'),32.80839895013123,places=12)
        with self.assertRaises(ValueError):head_from_metres(1e308,'ft')

    def test_numeric_range(self):
        for q,h in [(1e-300,1),(1e300,1)]:
            with self.assertRaises(ValueError):derive_system_k(q,h)
        with self.assertRaises(ValueError):system_friction_head(1e308,1)
        with self.assertRaises(ValueError):system_friction_head(1e-300,1e-300)
        with self.assertRaises(ValueError):system_head(1,1e308,1e308)
        with self.assertRaises(ValueError):generate_system_curve(SystemModel(10,0),5e-324)
        self.assertEqual(system_friction_head(1e308,0),0)
        self.assertEqual(system_friction_head(0,1e308),0)
        self.assertAlmostEqual(derive_system_k(1e200,1e300),1e-100)


class SystemCurveAppTests(unittest.TestCase):
    def app(self):
        from streamlit.testing.v1 import AppTest
        return AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()

    def fill(self,at):
        at.selectbox(key='p3f_flow_unit').select('m³/hr')
        at.selectbox(key='p3f_head_unit').select('m')
        for key,value in [('static',10),('reference_flow',100),('reference_friction',20),('maximum',200)]:
            at.number_input(key='p3f_'+key).set_value(value)
        return at.button(key='p3f_plot').click().run()

    def select(self,at,q):
        at.number_input(key='p3f_selected').set_value(q)
        return at.button(key='p3f_calculate').click().run()

    def result(self,at):
        return '\n'.join(w.value for w in at.text if 'Selected Flow:' in w.value)

    def charts(self,at):return at.get('vega_lite_chart')

    def test_empty_render_guidance(self):
        at=self.app()
        self.assertFalse(at.exception)
        self.assertTrue(any(w.label=='3F — System Curve' for w in at.expander))
        self.assertEqual(at.selectbox(key='p3f_method').value,'From Reference Flow and Friction Head')
        self.assertIsNone(at.selectbox(key='p3f_flow_unit').value)
        self.assertIsNone(at.selectbox(key='p3f_head_unit').value)
        self.assertIsNone(at.number_input(key='p3f_static').value)
        self.assertFalse(self.charts(at))
        self.assertFalse([w for w in at.checkbox if w.key.startswith('p3f_')])
        self.assertTrue(any(w.value==MODEL_GUIDANCE for w in at.info))
        self.assertTrue(any('No data are transferred automatically' in w.value for w in at.caption))
        self.assertTrue(any('intersection with a pump curve' in w.value for w in at.caption))
        self.assertEqual(len(at.tabs),15)
        at.button(key='p3f_plot').click().run()
        self.assertTrue(at.error)

    def test_reference_plot_and_labels(self):
        at=self.fill(self.app())
        self.assertFalse(at.error)
        self.assertFalse(at.exception)
        self.assertEqual(len(self.charts(at)),1)
        spec=json.loads(self.charts(at)[0].proto.spec)
        self.assertEqual(spec['title'],'System Curve')
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/hr)')
        self.assertEqual(spec['encoding']['y']['title'],'System Head (m)')
        rows=spec['layer'][0]['data']['values']
        total=[r for r in rows if r['component']=='System Total Head']
        self.assertEqual(len(total),81)
        self.assertEqual(len(rows),162)
        for index,head in [(0,10),(20,15),(40,30),(60,55),(80,90)]:
            self.assertAlmostEqual(total[index]['head'],head,places=12)
        self.assertTrue(all(r['head']==10 for r in rows if r['component']=='Static Head'))
        self.assertTrue(any('K_SI: 25920 s²/m⁵' in w.value for w in at.text))
        for key,label in [('static','Static Head (m)'),('reference_flow','Reference Flow (m³/hr)'),
                          ('reference_friction','Friction Head at Reference Flow (m)'),('maximum','Maximum Flow for Plot (m³/hr)')]:
            self.assertEqual(at.number_input(key='p3f_'+key).label,label)
        keys=[w.key for group in [at.number_input,at.selectbox,at.button,at.checkbox] for w in group]
        self.assertEqual(len(keys),len(set(keys)))

    def test_all_selected_benchmarks(self):
        at=self.fill(self.app())
        for q,friction,total in [(0,0,10),(50,5,15),(100,20,30),(125,31.25,41.25),(150,45,55),(200,80,90)]:
            self.select(at,q)
            self.assertIn(f'Friction Head: {friction:g} m',self.result(at))
            self.assertIn(f'Total System Head: {total:g} m',self.result(at))
            self.assertIn('Static Head: 10 m',self.result(at))
            self.assertFalse(at.error)
            self.assertFalse(at.exception)

    def test_direct_k_method(self):
        at=self.fill(self.app())
        self.select(at,125)
        expected=self.result(at)
        at.selectbox(key='p3f_method').select('From System Resistance Coefficient K').run()
        self.assertFalse(self.result(at))
        self.assertEqual(at.number_input(key='p3f_k').label,'System Resistance Coefficient K [for Q in m³/s] (s²/m⁵)')
        self.assertIsNone(at.number_input(key='p3f_k').value)
        at.number_input(key='p3f_k').set_value(25920)
        self.select(at,125)
        self.assertEqual(self.result(at),expected)
        self.assertFalse(at.exception)

    def test_zero_resistance_both_methods(self):
        at=self.fill(self.app())
        at.number_input(key='p3f_reference_friction').set_value(0)
        self.select(at,200)
        self.assertIn('Friction Head: 0 m\nTotal System Head: 10 m',self.result(at))
        rows=json.loads(self.charts(at)[0].proto.spec)['layer'][0]['data']['values']
        self.assertTrue(all(r['head']==10 for r in rows))
        at.selectbox(key='p3f_method').select('From System Resistance Coefficient K').run()
        at.number_input(key='p3f_k').set_value(0)
        self.select(at,200)
        self.assertIn('Total System Head: 10 m',self.result(at))
        self.assertFalse(at.error)

    def test_zero_reference_flow(self):
        at=self.fill(self.app())
        at.number_input(key='p3f_reference_flow').set_value(0)
        at.button(key='p3f_plot').click().run()
        self.assertIn('Reference flow',at.error[0].value)
        self.assertIn('greater than zero',at.error[0].value)
        self.assertFalse(self.charts(at))
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)

    def test_negative_inputs(self):
        at=self.fill(self.app())
        for key,restore in [('static',10),('reference_flow',100),('reference_friction',20),('maximum',200)]:
            at.number_input(key='p3f_'+key).set_value(-1)
            at.button(key='p3f_plot').click().run()
            self.assertTrue(at.error)
            self.assertFalse(self.charts(at))
            self.assertFalse(at.exception)
            at.number_input(key='p3f_'+key).set_value(restore)
        self.select(at,-1)
        self.assertTrue(at.error)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)
        at.selectbox(key='p3f_method').select('From System Resistance Coefficient K').run()
        at.number_input(key='p3f_k').set_value(-1)
        at.button(key='p3f_plot').click().run()
        self.assertTrue(at.error)
        self.assertFalse(at.exception)

    def test_unit_equivalence(self):
        at=self.fill(self.app())
        at.selectbox(key='p3f_flow_unit').select('m³/s')
        at.selectbox(key='p3f_head_unit').select('ft')
        factor=HEAD_FACTORS['ft']
        for key,value in [('static',10/factor),('reference_flow',100/3600),
                           ('reference_friction',20/factor),('maximum',200/3600)]:
            at.number_input(key='p3f_'+key).set_value(value)
        self.select(at,100/3600)
        self.assertIn(f'Total System Head: {30/factor:.12g} ft',self.result(at))
        spec=json.loads(self.charts(at)[0].proto.spec)
        self.assertEqual(spec['encoding']['x']['title'],'Flow Rate (m³/s)')
        self.assertEqual(spec['encoding']['y']['title'],'System Head (ft)')
        self.assertFalse(at.error)
        self.assertFalse(at.exception)

    def test_result_clearing_and_independent_range(self):
        at=self.fill(self.app())
        self.select(at,125)
        at.number_input(key='p3f_selected').set_value(100).run()
        self.assertFalse(self.result(at))
        self.assertEqual(len(self.charts(at)),1)
        self.select(at,250)
        self.assertIn('Total System Head: 135 m',self.result(at))
        at.number_input(key='p3f_static').set_value(20).run()
        self.assertFalse(self.result(at))
        at.number_input(key='p3f_maximum').set_value(None)
        self.select(at,100)
        self.assertIn('Total System Head: 40 m',self.result(at))
        self.assertFalse(at.error)
        self.assertFalse(self.charts(at))

    def test_direct_k_requires_flow_unit(self):
        at=self.app()
        at.selectbox(key='p3f_method').select('From System Resistance Coefficient K').run()
        at.selectbox(key='p3f_head_unit').select('m')
        at.number_input(key='p3f_static').set_value(10)
        at.number_input(key='p3f_k').set_value(25920)
        self.select(at,0)
        self.assertIn('Select a supported volumetric flow unit',at.error[0].value)
        self.assertFalse(self.result(at))
        self.assertFalse(at.exception)
