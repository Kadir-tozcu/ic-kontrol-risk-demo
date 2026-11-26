"""Run with python -m unittest tests/test_research.py (or unittest discover -s tests)."""
import unittest
import numpy as np
import pandas as pd
from suite.research_lab import generate, reference, metrics, benchmark
from suite.research_sources import analyze

class ResearchTests(unittest.TestCase):
    def test_seed(self):
        pd.testing.assert_frame_equal(generate(100,42),generate(100,42))
    def test_metrics(self):
        m=metrics(np.array([True,True,False,False]),np.array([True,False,True,False]),1)
        self.assertEqual((m["TP"],m["FP"],m["FN"],m["TN"]),(1,1,1,1))
        self.assertEqual(m["f1"],.5)
    def test_benchmark_without_api(self):
        r,_=benchmark(10000,5,3,False)
        self.assertEqual(len(r),18)
        self.assertTrue((r[r.method.str.startswith("B")].recall==1).all())
        self.assertFalse(r.method.str.startswith("C").any())
    def test_external_labels(self):
        d=pd.DataFrame({"Amount":np.arange(200),"Class":np.arange(200)%2})
        meta,r=analyze("ULB Credit Card (gerçek kaynaklı)",d)
        self.assertEqual(meta["evaluation_rows"],160)
        self.assertEqual(len(r),6)
        self.assertTrue((r.TP+r.FP+r.FN+r.TN==160).all())
    def test_berka(self):
        meta,r=analyze("Berka Financial (gerçek kaynaklı)",pd.DataFrame({"amount":[10,20],"balance":[-1,20],"date":[930101,930102]}))
        self.assertEqual(meta["negative_balance"],1)
        self.assertIsNone(r)

if __name__=="__main__":
    unittest.main()
