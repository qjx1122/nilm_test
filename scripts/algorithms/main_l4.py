# -*- coding: utf-8 -*-
"""
算法模块: 主模型 L4 (main)
==========================
两阶段主模型: Stage-1 开/关分类 + Stage-2 季节分层 MoE 条件功率回归,
含 L4 残差校正层与 L5 多模型动态切换 (均为主模型自带环节).

- 训练: 03_train.py          (环境 NILM_ALGO_SELECT=main -> 跳过 RF 基线, 完全解耦)
- 评估: 04_evaluate.py --algo main --no-baseline
- 推理: 05_inference.py --algo main --no-baseline
- 模型资产 (models/<user_id>/main/):
    nilm_ac_two_stage.pkl, model_meta.json, scaler.pkl,
    stage1_classifier.pkl, stage2_moe_bundle.pkl
"""
from .base import AlgorithmModule, AlgoContext


class MainL4Module(AlgorithmModule):
    name = "main"
    display_name = "主模型 L4 (两阶段分类 + 季节 MoE 回归)"
    train_script = "03_train.py"
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
        # 训练解耦门控: 仅训练主模型, 跳过内嵌 RF 基线 (RF 由 rf 算法模块独立负责)
        return {"NILM_ALGO_SELECT": "main"}

    def eval_args(self, ctx: AlgoContext) -> list:
        return ["--algo", "main", "--no-baseline"]

    def infer_args(self, ctx: AlgoContext) -> list:
        return ["--algo", "main", "--no-baseline"]
