# -*- coding: utf-8 -*-
"""
[v15] 多算法模型统一插件框架
============================
对外公开 API:

    REGISTERED_ALGORITHMS   : {"main": Module, "rf": Module, "v14": Module}
    ALGORITHM_NAMES         : 注册顺序元组 (all 模式遍历顺序)
    DEFAULT_ALGORITHMS      : 内置默认 ("main", "rf")
    get_algorithm(name)     : 按名取算法模块
    parse_algorithms_cli(s) : 解析 CLI 算法列表
    algorithms_to_cli_arg() : 列表 -> CLI 字符串
    algorithms_summary()    : 人类可读摘要
    resolve_algorithm_selection(...) : 三种运行模式 (single/multi/all) 统一解析

新算法接入步骤 (统一输入输出接口):
    1. 新建 scripts/algorithms/<new_algo>.py, 继承 base.AlgorithmModule
    2. 在 registry.REGISTERED_ALGORITHMS 注册
    3. (可选) 在 time_filters 配置 algorithms.selected 中引用, 或 CLI --algorithms 传入
"""
from .base import AlgorithmModule, AlgoContext
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
)

__all__ = [
    "AlgorithmModule", "AlgoContext",
    "REGISTERED_ALGORITHMS", "ALGORITHM_NAMES", "DEFAULT_ALGORITHMS", "ALGO_MODES",
    "get_algorithm", "parse_algorithms_cli", "algorithms_to_cli_arg",
    "algorithms_summary", "resolve_algorithm_selection",
]
