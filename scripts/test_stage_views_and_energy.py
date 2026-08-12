#!/usr/bin/env python3
"""独立视图新增能力的快速回归测试。"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import feature_utils
from metrics_utils import compute_regression_metrics


class TestEnergyDecomposition(unittest.TestCase):
    def test_on_bias_and_off_false_energy_do_not_cancel(self):
        y_true = np.array([0.0, 50.0, 100.0, 200.0])
        y_pred = np.array([10.0, 20.0, 80.0, 240.0])
        with patch.dict(os.environ, {"NILM_USER_ON_THR_W": "60"}):
            got = compute_regression_metrics(
                y_true, y_pred, sample_period_h=0.25)
        self.assertAlmostEqual(got["ON_kWh_true"], 0.075)
        self.assertAlmostEqual(got["ON_kWh_pred"], 0.080)
        self.assertAlmostEqual(got["ON_kWh_err"], 0.005)
        self.assertAlmostEqual(got["ON_energy_bias"], 1.0 / 15.0)
        self.assertAlmostEqual(got["OFF_false_kWh"], 0.0075)
        # 净误差不足以替代分量；两项必须独立存在。
        self.assertNotAlmostEqual(got["kWh_err"], got["ON_kWh_err"])


class TestNuisanceLabel(unittest.TestCase):
    def test_optional_nuisance_label_uses_non_target_branches(self):
        bus_time = pd.date_range("2026-01-01", periods=10, freq="5min")
        branch_time = pd.date_range("2026-01-01", periods=4, freq="15min")
        bus = pd.DataFrame({"event_time": bus_time, "load_iden_data0": np.arange(10)})
        branch = pd.DataFrame({
            "time": branch_time,
            "p1": [10.0, 20.0, 30.0, 40.0],
            "p2": [1.0, 2.0, 3.0, 4.0],
            "p1+p2": [11.0, 22.0, 33.0, 44.0],
            "p3": [100.0, 0.0, 50.0, 5.0],
            "p4": [5.0, 10.0, 0.0, 15.0],
        })
        with patch.object(feature_utils, "TARGET_COL", "p1+p2"), \
             patch.dict(os.environ, {"NILM_ENABLE_NUISANCE_AUX": "1"}):
            got = feature_utils.resample_and_align(
                bus, branch, keep_cols=["load_iden_data0"])
        self.assertIn("y_nuisance", got.columns)
        np.testing.assert_allclose(
            got["y_nuisance"].values, [105.0, 10.0, 50.0, 20.0])
        np.testing.assert_allclose(got["y_ac"].values, [11.0, 22.0, 33.0, 44.0])


if __name__ == "__main__":
    unittest.main()
