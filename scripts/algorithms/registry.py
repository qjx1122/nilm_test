# -*- coding: utf-8 -*-
"""
算法注册中心与运行模式解析
==========================
[v15 多算法重构] 三个职责:

1. 注册表: 名称 -> AlgorithmModule 实例 (扩展新算法只需在此注册)
2. 三种自定义运行模式解析 (single / multi / all):
     - single : 指定单模型执行   (selected 列表取第一个)
     - multi  : 多模型选择性执行 (selected 列表原样执行)
     - all    : 全部模型遍历执行 (注册表内全部算法, 按注册顺序)
3. 优先级: CLI 覆盖 > time_filters 用户配置 (algorithms 字段) > 内置默认
   (内置默认 = main + rf, 与重构前行为完全一致; 若 v14 增强开关开启则追加 v14)

典型配置 (time_filters.json 用户级或 _default 级):
    "algorithms": {
        "mode": "all",                // "single" | "multi" | "all"
        "selected": ["main", "rf"],   // single 取第一个; multi 取整个列表
        "main": {...},                // [预留] 算法级私有覆盖 (未来扩展)
        "rf":   {...},
        "v14":  {...}
    }
"""
from __future__ import annotations

from typing import Optional, List, Tuple

from .base import AlgorithmModule
from .main_l4 import MainL4Module
from .rf_baseline import RfBaselineModule
from .v14_enhanced import V14Module

# ---------- 注册表 (扩展新算法 = 在此追加一行) ----------
REGISTERED_ALGORITHMS = {
    "main": MainL4Module(),
    "rf": RfBaselineModule(),
    "v14": V14Module(),
}

# 注册顺序即 all 模式遍历顺序
ALGORITHM_NAMES = tuple(REGISTERED_ALGORITHMS.keys())

# 内置默认 (与重构前"主模型 + RF 基线同训"行为对齐)
DEFAULT_ALGORITHMS = ("main", "rf")

ALGO_MODES = ("single", "multi", "all")


def get_algorithm(name: str) -> Optional[AlgorithmModule]:
    """按注册名取算法模块; 未注册返回 None."""
    return REGISTERED_ALGORITHMS.get((name or "").strip().lower())


def parse_algorithms_cli(cli_str: str) -> List[str]:
    """解析 CLI 算法列表: 支持逗号/加号/空白分隔, 大小写不敏感, 自动去重去空.

    特殊值 "all" -> 注册表全部算法.
    """
    raw = (cli_str or "").strip().lower()
    if not raw:
        return []
    tokens = []
    for part in raw.replace("+", ",").replace(" ", ",").split(","):
        token = part.strip()
        if token:
            tokens.append(token)
    if "all" in tokens:
        return list(ALGORITHM_NAMES)
    return list(dict.fromkeys(tokens))   # 去重且保序


def algorithms_to_cli_arg(names) -> str:
    """算法名列表 -> CLI 逗号字符串 (与 parse_algorithms_cli 互逆)."""
    return ",".join(str(n).strip().lower() for n in names if str(n).strip())


def algorithms_summary(names) -> str:
    """人类可读摘要 (日志/扫描表用)."""
    return ",".join(names) if names else "(默认)"


def resolve_algorithm_selection(
    algo_config: Optional[dict] = None,
    cli_algorithms: Optional[str] = None,
    cli_mode: Optional[str] = None,
    v14_hint: bool = False,
) -> Tuple[List[str], str, List[str]]:
    """解析最终执行的算法列表与运行模式.

    优先级 (高 -> 低):
      1. CLI 参数 (--algorithms / --algo-mode)
      2. time_filters 配置的 algorithms 字段 (mode / selected)
      3. 内置默认 (main + rf); v14_hint=True 时追加 v14

    返回:
      (selected_names, effective_mode, warnings)
        selected_names : 最终算法名列表 (恒非空, 恒为已注册算法)
        effective_mode : "single" | "multi" | "all"
        warnings       : 解析过程中产生的人类可读告警 (非法模式/未注册算法等)
    """
    warnings: List[str] = []

    # ---- 1. 解析 mode ----
    mode = ""
    if cli_mode:
        m = str(cli_mode).strip().lower()
        if m in ALGO_MODES:
            mode = m
        else:
            warnings.append(
                f"非法 --algo-mode={cli_mode!r} (合法值 {ALGO_MODES}), 已忽略")
    if not mode and isinstance(algo_config, dict):
        m = str(algo_config.get("mode", "") or "").strip().lower()
        if m:
            if m in ALGO_MODES:
                mode = m
            else:
                warnings.append(
                    f"配置 algorithms.mode={m!r} 非法 (合法值 {ALGO_MODES}), 已忽略")

    # ---- 2. 解析 selected 列表 ----
    selected: Optional[List[str]] = None
    if cli_algorithms is not None:
        selected = parse_algorithms_cli(cli_algorithms)
    elif isinstance(algo_config, dict):
        raw = algo_config.get("selected")
        if isinstance(raw, str):
            selected = parse_algorithms_cli(raw)
        elif isinstance(raw, (list, tuple)):
            selected = [str(x).strip().lower() for x in raw if str(x).strip()]
            selected = list(dict.fromkeys(selected))
    if selected is None:
        # 内置默认
        selected = list(DEFAULT_ALGORITHMS)
        if v14_hint and "v14" not in selected:
            selected.append("v14")
        if not mode:
            mode = "multi"

    # ---- 3. 校验: 剔除未注册算法 ----
    for name in selected:
        if name not in REGISTERED_ALGORITHMS:
            warnings.append(
                f"未注册算法 {name!r} 已剔除 (已注册: {list(ALGORITHM_NAMES)})")
    selected = [n for n in selected if n in REGISTERED_ALGORITHMS]

    # ---- 4. 空兜底 (全部非法 -> 内置默认) ----
    if not selected:
        warnings.append(f"算法列表解析后为空, 回退到内置默认 {list(DEFAULT_ALGORITHMS)}")
        selected = list(DEFAULT_ALGORITHMS)
        if not mode:
            mode = "multi"

    # ---- 5. 按模式定稿 ----
    if mode == "all":
        selected = list(ALGORITHM_NAMES)
        effective = "all"
    elif mode == "single":
        selected = selected[:1]
        effective = "single"
    else:
        effective = mode or ("single" if len(selected) == 1 else "multi")

    return selected, effective, warnings
