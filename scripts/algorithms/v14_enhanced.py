# -*- coding: utf-8 -*-
"""
算法模块: v14 增强版主模型 (v14)
================================
v14 是主模型槽位的"训练增强变体": 通过 14_train_v14.py 的 monkey-patch 机制
(focal 加权 / GBDT+LightGBM 集成 / 概率校准 / 小样本自动调参 / 健康报告 / 数据诊断)
训练主模型槽位, 产出与 main 同构的模型资产, 但归档在独立的 v14/ 子目录,
与 main / rf 完全解耦隔离 (不同子进程运行, 无 monkey-patch 泄漏风险).

- 训练: 14_train_v14.py      (环境 NILM_ALGO_SELECT=main + NILM_V14_* 开关)
- 评估: 04_evaluate.py --algo main --no-baseline
- 推理: 05_inference.py --algo main --no-baseline
- 模型资产 (models/<user_id>/v14/): 与 main 相同的 5 件套
- 增强开关: 来自 --v14-flags CLI 或 time_filters 配置 (经 ctx.v14_flags_spec 传入)
"""
import json

from .base import AlgorithmModule, AlgoContext

# v14 开关字段 -> 环境变量 映射 (与 feature_utils.py / v14 体系对齐)
_V14_FIELD_ENV_MAP = {
    "v14_enable": "NILM_V14_ENABLE",
    "v14_enabled": "NILM_V14_ENABLE",
    "physics": "NILM_V14_PHYSICS_FEATURES",
    "physics_features": "NILM_V14_PHYSICS_FEATURES",
    "focal": "NILM_V14_FOCAL",
    "ensemble": "NILM_V14_ENSEMBLE",
    "calibrate": "NILM_V14_CALIBRATE",
    "auto_config": "NILM_V14_AUTO_CONFIG",
    "health": "NILM_V14_HEALTH_REPORT",
    "health_report": "NILM_V14_HEALTH_REPORT",
    "diag": "NILM_V14_DATA_DIAG",
    "data_diag": "NILM_V14_DATA_DIAG",
}


def v14_flags_to_env(v14_flags_spec: str) -> dict:
    """把 --v14-flags JSON 字符串翻译为 NILM_V14_* 环境变量 dict (仅 v14 算法生效)。"""
    env = {"NILM_V14_ENABLE": "1"}   # 被选中即视为启用 v14 训练入口
    spec = (v14_flags_spec or "").strip()
    if not spec:
        return env
    try:
        cfg = json.loads(spec)
    except Exception:
        return env
    if not isinstance(cfg, dict):
        return env
    for field, env_name in _V14_FIELD_ENV_MAP.items():
        if field in cfg:
            env[env_name] = "1" if bool(cfg[field]) else "0"
    return env


class V14Module(AlgorithmModule):
    name = "v14"
    display_name = "v14 增强版主模型 (focal/集成/校准/诊断)"
    train_script = "14_train_v14.py"
    eval_script = "04_evaluate.py"
    infer_script = "05_inference.py"
    required_model_files = (
        "nilm_ac_two_stage.pkl",
        "model_meta.json",
        "scaler.pkl",
        "stage1_classifier.pkl",
        "stage2_moe_bundle.pkl",
    )
    stage_algo_flag = "main"

    def train_env(self, ctx: AlgoContext) -> dict:
        env = {"NILM_ALGO_SELECT": "main"}   # v14 训练主模型槽位, 跳过内嵌 RF
        env.update(v14_flags_to_env(ctx.v14_flags_spec))
        return env

    def eval_args(self, ctx: AlgoContext) -> list:
        return ["--algo", "main", "--no-baseline"]

    def infer_args(self, ctx: AlgoContext) -> list:
        return ["--algo", "main", "--no-baseline"]
