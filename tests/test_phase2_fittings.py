import math
from pathlib import Path
import unittest
from dataclasses import asdict
from piping_hydraulics.fittings import K_RECORDS,Component,calculate_fittings,quantity


def common(rows,**kw):
    return calculate_fittings(rows,mode='common',common_basis_confirmed=True,**kw)


class FittingsTests(unittest.TestCase):
    def test_manual_benchmark(self):
        r=common([Component(2,.9),Component(1,.2)],velocity=2,density=1000)
        self.assertEqual(r['k_total'],2)
        self.assertAlmostEqual(r['head_m'],.4078864851911713)
        self.assertAlmostEqual(r['pressure_pa'],4000)
        self.assertAlmostEqual(r['pressure_kpa'],4)
        self.assertAlmostEqual(r['pressure_bar'],.04)

    def test_database(self):
        self.assertEqual([r.k for r in K_RECORDS],[10,5,2.5,.2,.4,.6,1.8])
        self.assertEqual(len({r.id for r in K_RECORDS}),7)
        for r in K_RECORDS:
            self.assertTrue(all(v is not None and v!='' for v in asdict(r).values()))
            self.assertIn('Table 3.3',r.location)
            self.assertIn('US EPA',r.source)
            self.assertIn('2.2',r.edition)
            self.assertEqual(common([Component(2,r.k)])['k_total'],2*r.k)
        self.assertTrue(all(r.condition=='Fully open' for r in K_RECORDS[:4]))
        self.assertIn('run',K_RECORDS[-2].configuration)
        self.assertIn('branch',K_RECORDS[-1].configuration)

    def test_optional_density_and_velocity(self):
        rows=[Component(2,.9),Component(1,.2)]
        self.assertIsNone(common(rows)['head_m'])
        r=common(rows,velocity=2)
        self.assertAlmostEqual(r['head_m'],.4078864851911713)
        self.assertIsNone(r['pressure_pa'])
        with self.assertRaises(ValueError):common(rows,density=1000)

    def test_quantity_multiplication(self):
        self.assertEqual(common([Component(3,.2),Component(4,.5)])['k_total'],2.6)
        self.assertEqual(quantity(2.0),2)

    def test_zero(self):
        for rows,v in [([Component(1,0)],2),([Component(0,.9)],2),([Component(2,.9)],0)]:
            r=common(rows,velocity=v,density=1000)
            self.assertEqual(r['head_m'],0)
            self.assertEqual(r['pressure_pa'],0)

    def test_invalid_k(self):
        for k in [None,'bad',True,-1,math.nan,math.inf]:
            with self.assertRaises(ValueError):common([Component(1,k)])

    def test_invalid_quantity(self):
        for n in [None,'bad',True,-1,.5,math.nan,math.inf,2**54]:
            with self.assertRaises(ValueError):common([Component(n,.9)])
        with self.assertRaises(ValueError):common([])

    def test_invalid_velocity_density(self):
        for v in [-1,math.nan,math.inf,True]:
            with self.assertRaises(ValueError):common([Component(1,.9)],velocity=v)
        for rho in [0,-1,math.nan,math.inf,True]:
            with self.assertRaises(ValueError):common([Component(1,.9)],velocity=0,density=rho)

    def test_common_basis(self):
        with self.assertRaises(ValueError):calculate_fittings([Component(1,.9)],mode='common',velocity=2)
        with self.assertRaises(ValueError):common([Component(1,.9,3)],velocity=2)

    def test_different_velocities(self):
        r=calculate_fittings([Component(1,1,2),Component(1,1,4)],mode='separate',density=1000)
        self.assertIsNone(r['k_total'])
        self.assertAlmostEqual(r['head_m'],20/(2*9.80665))
        self.assertAlmostEqual(r['pressure_pa'],10000)
        self.assertAlmostEqual(sum(r['rows']),r['head_m'])
        with self.assertRaises(ValueError):calculate_fittings([Component(1,1,None)],mode='separate')
        with self.assertRaises(ValueError):calculate_fittings([Component(1,1,2)],mode='separate',velocity=2)

    def test_duplicate_prevention(self):
        with self.assertRaisesRegex(ValueError,'Double counting'):
            common([Component(1,.9,counted_as_equivalent_length=True)],velocity=2)

    def test_overflow(self):
        with self.assertRaises(ValueError):common([Component(100,1e308)])
        with self.assertRaises(ValueError):common([Component(1,1)],velocity=1e308)

    def test_ui_manual(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.tabs),15)
        at.button(key='p2d_calculate').click().run()
        self.assertTrue(at.error)
        for i in range(2):at.selectbox(key=f'p2d_source_{i}').select('Manual K')
        at.run()
        for i,n,k in [(0,2,.9),(1,1,.2)]:
            at.number_input(key=f'p2d_qty_{i}').set_value(n)
            at.number_input(key=f'p2d_k_{i}').set_value(k)
        at.checkbox(key='p2d_basis_common').check()
        at.button(key='p2d_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('K total: 2' in t.value for t in at.text))
        at.number_input(key='p2d_velocity').set_value(2)
        at.number_input(key='p2d_density').set_value(1000)
        at.button(key='p2d_calculate').click().run()
        self.assertTrue(any('4000 Pa | 4 kPa | 0.04 bar' in t.value for t in at.text))
        at.checkbox(key='p2d_duplicate_0').check()
        at.button(key='p2d_calculate').click().run()
        self.assertTrue(any('Double counting' in e.value for e in at.error))
        keys=[w.key for g in [at.number_input,at.selectbox,at.button,at.checkbox,at.text_input] for w in g]
        self.assertEqual(len(keys),len(set(keys)))
        self.assertFalse(at.exception)

    def test_ui_database_and_separate(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).resolve().parents[1]/'app.py')).run()
        at.number_input(key='p2d_count').set_value(1).run()
        for r in K_RECORDS:
            at.selectbox(key='p2d_source_0').select(r.component).run()
            at.number_input(key='p2d_qty_0').set_value(1)
            at.checkbox(key='p2d_basis_common').check()
            at.button(key='p2d_calculate').click().run()
            self.assertTrue(at.error)
            at.checkbox(key=f'p2d_approve_0_{r.id}').check()
            at.button(key='p2d_calculate').click().run()
            self.assertFalse(at.error)
            self.assertTrue(any('Table 3.3' in c.value for c in at.caption))
        at.selectbox(key='p2d_mode').select('Separate row reference velocities').run()
        at.checkbox(key='p2d_basis_separate').check()
        at.number_input(key='p2d_velocity_0').set_value(2)
        at.button(key='p2d_calculate').click().run()
        self.assertFalse(at.error)
        self.assertTrue(any('No combined K' in t.value for t in at.text))
        self.assertFalse(at.exception)
