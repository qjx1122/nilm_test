# -*- coding: utf-8 -*-
"""Stage-1/Stage-2 独立特征视图的 bundle 兼容解析。"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from feature_utils import build_features, assert_no_nan_features


@dataclass
class ModelFeatureViews:
    stage1_df: object
    stage2_df: object
    stage1_cols: list
    stage2_cols: list
    stage1_scaler: object
    stage2_scaler: object
    stage1_lut: dict | None
    stage2_lut: dict | None

    def arrays(self, stage_name="model"):
        assert_no_nan_features(self.stage1_df, stage_name=f"{stage_name}/stage1",
                               raise_on_nan=True)
        assert_no_nan_features(self.stage2_df, stage_name=f"{stage_name}/stage2",
                               raise_on_nan=True)
        return (self.stage1_df.values.astype(np.float32),
                self.stage2_df.values.astype(np.float32))


def build_model_feature_views(df, bundle, weather_df=None):
    """按新 bundle 构造双视图；旧 bundle 自动退化为共享视图。"""
    legacy_cols = bundle["feat_cols"]
    legacy_scaler = bundle["scaler"]
    legacy_lut = bundle.get("temp_power_lut")

    stage1_cols = list(bundle.get("stage1_feat_cols", legacy_cols))
    stage2_cols = list(bundle.get("stage2_feat_cols", legacy_cols))
    stage1_scaler = bundle.get("stage1_scaler", legacy_scaler)
    stage2_scaler = bundle.get("stage2_scaler", legacy_scaler)
    stage1_lut = bundle.get("stage1_temp_power_lut", legacy_lut)
    stage2_lut = bundle.get("stage2_temp_power_lut", legacy_lut)

    stage1_df = build_features(df, stage1_cols, weather_df=weather_df,
                               temp_power_lut=stage1_lut)
    # 旧模型或完全相同视图直接复用，避免重复特征工程。
    if stage2_cols == stage1_cols and stage2_lut is stage1_lut:
        stage2_df = stage1_df
    else:
        stage2_df = build_features(df, stage2_cols, weather_df=weather_df,
                                   temp_power_lut=stage2_lut)
    return ModelFeatureViews(
        stage1_df=stage1_df, stage2_df=stage2_df,
        stage1_cols=stage1_cols, stage2_cols=stage2_cols,
        stage1_scaler=stage1_scaler, stage2_scaler=stage2_scaler,
        stage1_lut=stage1_lut, stage2_lut=stage2_lut,
    )
