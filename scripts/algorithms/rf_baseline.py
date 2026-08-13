# -*- coding: utf-8 -*-
"""
算法模块: RF 基线 (rf)
======================
单阶段 RandomForestRegressor 基线, 原内嵌于 03_train.py 中与主模型耦合训练,
v15 多算法重构后解耦为独立算法模块:

- 训练: 03_train.py          (环境 NILM_ALGO_SELECT=rf -> 跳过主模型全部环节,
                              产出自包含 rf_bundle.pkl, 含 scaler/特征列/切分日期等
                              统一接口所需全部上下文)
- 评估: 04_evaluate.py --algo rf --no-baseline
- 推理: 05_inference.py --algo rf --no-baseline --model models/rf_bundle.pkl
- 模型资产 (models/<user_id>/rf/):
    rf_bundle.pkl, baseline_rf.pkl
"""
from .base import AlgorithmModule, AlgoContext


class RfBaselineModule(AlgorithmModule):
    name = "rf"
    display_name = "RF 基线 (单阶段随机森林)"
    train_script = "03_train.py"
    eval_script = "04_evaluate.py"
    infer_script = "05_inference.py"
    required_model_files = (
        "rf_bundle.pkl",
    )
    stage_algo_flag = "rf"

    def train_env(self, ctx: AlgoContext) -> dict:
        # 训练解耦门控: 仅训练 RF 基线, 跳过主模型全部环节
        return {"NILM_ALGO_SELECT": "rf"}

    def eval_args(self, ctx: AlgoContext) -> list:
        return ["--algo", "rf", "--no-baseline"]

    def infer_args(self, ctx: AlgoContext) -> list:
        rf_bundle = ctx.project_root / "models" / "rf_bundle.pkl"
        return ["--algo", "rf", "--no-baseline", "--model", str(rf_bundle)]
