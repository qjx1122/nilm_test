# -*- coding: utf-8 -*-
"""
[v15/v17] 多算法模型统一插件框架
================================
对外公开 API:

    REGISTERED_ALGORITHMS   : {"main": Module, "rf": Module, "v14": Module}
    ALGORITHM_NAMES         : 注册顺序元组 (all 模式遍历顺序)
    DEFAULT_ALGORITHMS      : 内置默认 ("main", "rf")
    get_algorithm(name)     : 按名取算法模块
    parse_algorithms_cli(s) : 解析 CLI 算法列表
    algorithms_to_cli_arg() : 列表 -> CLI 字符串
    algorithms_summary()    : 人类可读摘要
    resolve_algorithm_selection(...) : 三种运行模式 (single/multi/all) 统一解析

    [v17 各模型训练推理功能统一访问接口]
    StageRunner / StageResult / SOFT_SKIP_CODES : 统一阶段执行器与结构化结果
    train_models(names, ctx)    : 统一多模型训练入口
    evaluate_models(names, ctx) : 统一多模型评估入口
    infer_models(names, ctx)    : 统一多模型推理入口
    # 单模型直接调用:
    get_algorithm("main").train(ctx)    # -> StageResult
    get_algorithm("rf").evaluate(ctx)   # -> StageResult
    get_algorithm("v14").infer(ctx)     # -> StageResult

新算法接入步骤 (统一输入输出接口):
    1. 新建 scripts/algorithms/<new_algo>.py, 继承 base.AlgorithmModule
    2. 在 registry.REGISTERED_ALGORITHMS 注册
    3. (可选) 在 time_filters 配置 algorithms.selected 中引用, 或 CLI --algorithms 传入
    4. 训练/推理功能即自动获得统一访问接口 (train/evaluate/infer), 零流水线改动
"""
from .base import AlgorithmModule, AlgoContext
from .runner import StageRunner, StageResult, SOFT_SKIP_CODES
from .registry import (
    REGISTERED_ALGORITHMS,
    ALGORITHM_NAMES,
    DEFAULT_ALGORITHMS,
    ALGO_MODES,
    get_algorithm,
    parse_algorithms_cli,
    algorithms_to_cli_arg,
    algorithms_summary,
    resolve_algorithm_selection,
    train_models,
    evaluate_models,
    infer_models,
)

__all__ = [
    "AlgorithmModule", "AlgoContext",
    "StageRunner", "StageResult", "SOFT_SKIP_CODES",
    "REGISTERED_ALGORITHMS", "ALGORITHM_NAMES", "DEFAULT_ALGORITHMS", "ALGO_MODES",
    "get_algorithm", "parse_algorithms_cli", "algorithms_to_cli_arg",
    "algorithms_summary", "resolve_algorithm_selection",
    "train_models", "evaluate_models", "infer_models",
]
