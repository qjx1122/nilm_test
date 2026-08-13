# -*- coding: utf-8 -*-
"""
[v16] 数据配置模块 — 统一配置访问接口
======================================
职责: 集中式用户配置 (time_filters JSON + CLI 覆盖) 的加载、解析、序列化与
运行环境翻译。是"数据输入 / 数据输出 / 数据配置"三大解耦模块中的配置底座。

对外统一接口:
    ConfigResolver                : 集中式配置解析器 (配置 + CLI 覆盖 -> 每用户生效配置)
      .resolve(user_id, ...)      : -> UserConfig (统一配置访问返回对象)
    UserConfig                    : 单用户全部生效配置的数据对象
      .to_pipeline_cli()          : -> 透传给单用户流水线子进程的 CLI 参数字典
      .plan_line()                : -> 扫描/执行阶段的人类可读计划行
    common_overrides_to_env()     : 通用常量覆盖 -> NILM_USER_* 环境变量
    guard_cli_to_env()            : 守卫开关 -> 环境变量
    v14_flags_to_env()            : v14 增强开关 JSON -> NILM_V14_* 环境变量
    v14_enabled_from_spec()       : 从 v14 flags JSON 判断是否启用
    load_time_filter_config() 等  : time_filter_utils 底层实现的门面再导出

依赖方向: 仅依赖底层实现层 (time_filter_utils / algorithms), 不依赖数据输入/输出模块.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

# ---------- 底层实现层门面再导出 (统一配置访问入口) ----------
from time_filter_utils import (
    load_time_filter_config,
    get_user_stage_spec,
    get_user_target_col,
    get_user_guard_enabled,
    get_user_common_overrides,
    get_user_v14_flags,
    load_splits_time_filter,
    get_user_algorithms_selection,
    get_user_algorithms_config,
    spec_to_cli_arg,
    cli_arg_to_spec,
    parse_ranges,
    spec_summary,
    splits_spec_to_cli_arg,
    cli_arg_to_splits_spec,
    splits_spec_summary,
    algorithms_config_summary,
)

# ---------- 通用常量覆盖字段 -> 环境变量映射 ----------
COMMON_OVERRIDE_FIELDS = [
    ("on_thr_w",              "NILM_USER_ON_THR_W"),
    ("post_min_on",           "NILM_USER_POST_MIN_ON"),
    ("post_fill_short_off",   "NILM_USER_POST_FILL_SHORT_OFF"),
    ("split_strategy",        "NILM_USER_SPLIT_STRATEGY"),
    ("split_ratios",          "NILM_USER_SPLIT_RATIOS"),   # JSON list str
    ("weather_latitude",      "NILM_USER_WEATHER_LATITUDE"),
    ("weather_longitude",     "NILM_USER_WEATHER_LONGITUDE"),
    ("use_weather_features",  "NILM_USER_USE_WEATHER_FEATURES"),
    ("use_temp_based_season", "NILM_USER_USE_TEMP_BASED_SEASON"),
]


@dataclass
class UserConfig:
    """单用户解析后的完整生效配置 (统一配置访问接口的返回对象).

    字段均为"已解析的生效值": 配置缺失时用内置默认, 语义与 time_filter_utils
    各 getter 完全一致 (WARN + Fallback 降级链).
    """
    user_id: str
    target_col: Optional[str] = None          # pN 或 pA+pB[+pC...]
    guard_enabled: Optional[bool] = None      # None = 未指定 (走全局开关/自动检测)
    train_spec: Optional[dict] = None         # {'include': [...], 'exclude': [...]}
    infer_spec: Optional[dict] = None
    splits_spec: Optional[dict] = None        # {'train': {...}, 'val': {...}, 'test': {...}}
    common_overrides: Dict = field(default_factory=dict)
    v14_flags: Dict = field(default_factory=dict)
    algorithms: List[str] = field(default_factory=lambda: ["main", "rf"])
    algo_mode: str = "multi"                  # single / multi / all
    warnings: List[str] = field(default_factory=list)

    # ---------- 序列化接口 (透传给单用户流水线子进程) ----------
    def guard_cli(self) -> str:
        if self.guard_enabled is True:
            return "true"
        if self.guard_enabled is False:
            return "false"
        return ""

    def train_spec_cli(self) -> str:
        return spec_to_cli_arg(self.train_spec)

    def infer_spec_cli(self) -> str:
        return spec_to_cli_arg(self.infer_spec)

    def splits_spec_cli(self) -> str:
        return splits_spec_to_cli_arg(self.splits_spec) if self.splits_spec else ""

    def common_overrides_cli(self) -> str:
        return json.dumps(self.common_overrides, ensure_ascii=False) \
            if self.common_overrides else ""

    def v14_flags_cli(self) -> str:
        return json.dumps(self.v14_flags, ensure_ascii=False) \
            if any(bool(v) for v in self.v14_flags.values()) else ""

    def algorithms_cli(self) -> str:
        return ",".join(self.algorithms)

    def to_pipeline_cli(self) -> Dict[str, str]:
        """透传给 run_user_pipeline.py 的完整 CLI 参数字典 (统一出口)."""
        return {
            "train_time_filter_spec": self.train_spec_cli(),
            "infer_time_filter_spec": self.infer_spec_cli(),
            "guard_enabled": self.guard_cli(),
            "splits_time_filter_spec": self.splits_spec_cli(),
            "common_overrides": self.common_overrides_cli(),
            "v14_flags": self.v14_flags_cli(),
            "algorithms": self.algorithms_cli(),
            "algo_mode": self.algo_mode,
        }

    def plan_line(self) -> str:
        return f"  [v15] 算法计划: {self.algorithms_cli()} (mode={self.algo_mode})"


def v14_enabled_from_spec(v14_flags_spec: str) -> bool:
    """从 v14 flags JSON 字符串判断 v14 是否显式启用 (用于默认算法列表提示)."""
    spec = (v14_flags_spec or "").strip()
    if not spec:
        return False
    try:
        cfg = json.loads(spec)
        if isinstance(cfg, dict):
            return bool(cfg.get("v14_enable", cfg.get("v14_enabled", False)))
    except Exception:
        pass
    return False


class ConfigResolver:
    """[v16] 集中式配置解析器: 配置文件 + CLI 覆盖 -> 每用户生效配置.

    优先级 (与历史行为一致):
      - target_col / guard_enabled / train·infer 时段 / splits / common 覆盖: 仅配置
      - v14 增强开关: CLI > 配置
      - 算法选择: CLI > 配置 algorithms 字段 > 内置默认 (main+rf, v14 开关开启则追加 v14)
    """

    def __init__(self, config: Optional[dict] = None,
                 config_path: Union[str, Path, None] = None,
                 cli_algorithms: str = "", cli_algo_mode: str = "",
                 cli_v14_flags: str = ""):
        if config is None and config_path:
            config = load_time_filter_config(config_path)
        self.config = config if isinstance(config, dict) else {}
        self.cli_algorithms = cli_algorithms or ""
        self.cli_algo_mode = cli_algo_mode or ""
        self.cli_v14_flags = cli_v14_flags or ""

    @classmethod
    def from_batch_args(cls, args, config: Optional[dict] = None,
                        config_path: Union[str, Path, None] = None) -> "ConfigResolver":
        """从 run_batch_users 的 argparse 参数构建解析器 (统一入口)."""
        return cls(
            config=config, config_path=config_path,
            cli_algorithms=getattr(args, "algorithms", "") or "",
            cli_algo_mode=getattr(args, "algo_mode", "") or "",
            cli_v14_flags=getattr(args, "v14_flags", "") or "",
        )

    def resolve(self, user_id: str, verbose: bool = False,
                logger_print=None) -> UserConfig:
        """解析单个用户的全部生效配置 (统一访问接口)."""
        uc = UserConfig(user_id=user_id)
        pr = logger_print or (print if verbose else None)

        def _log(msg: str):
            if pr is not None:
                pr(msg)

        if self.config:
            # ---- 目标列 (配置显式指定优先, 否则由数据输入模块按文件名反推) ----
            try:
                uc.target_col = get_user_target_col(self.config, user_id)
            except Exception as e:
                uc.warnings.append(f"读取配置 target_col 失败: {e}")

            # ---- 时段过滤 (train / infer 独立) ----
            uc.train_spec = get_user_stage_spec(self.config, user_id, "train")
            uc.infer_spec = get_user_stage_spec(self.config, user_id, "infer")
            if uc.train_spec is not None or uc.infer_spec is not None:
                _log(f"  [v12] 时段过滤: train={spec_summary(uc.train_spec)}, "
                     f"infer={spec_summary(uc.infer_spec)}")

            # ---- d87 守卫开关 ----
            _g = get_user_guard_enabled(self.config, user_id)
            if _g is True:
                uc.guard_enabled = True
                _log("  [v13] d87 守卫: 强制开启 (来自配置)")
            elif _g is False:
                uc.guard_enabled = False
                _log("  [v13] d87 守卫: 强制关闭 (来自配置)")
            else:
                _log("  [v13] d87 守卫: 未指定, 走全局 D87_ADAPTIVE_GUARD_ENABLED "
                     "(可能被自动降级)")

            # ---- per-split 时段过滤 ----
            uc.splits_spec = load_splits_time_filter(self.config, user_id)
            if uc.splits_spec is not None:
                _log(f"  [v13] per-split time_filter: {splits_spec_summary(uc.splits_spec)}")

            # ---- 通用常量覆盖 ----
            uc.common_overrides = get_user_common_overrides(self.config, user_id)
            if uc.common_overrides:
                _log(f"  [v13.5] common 覆盖 {len(uc.common_overrides)} 项: "
                     f"{', '.join(f'{k}={v}' for k, v in uc.common_overrides.items())}")

            # ---- v14 增强开关 (CLI 优先, 否则配置) ----
            if not self.cli_v14_flags.strip():
                uc.v14_flags = get_user_v14_flags(self.config, user_id)
                if any(uc.v14_flags.values()):
                    _log(f"  [v14] v14 增强配置: enabled="
                         f"{uc.v14_flags.get('v14_enable', False)}")
        if self.cli_v14_flags.strip():
            try:
                _cli_v14 = json.loads(self.cli_v14_flags)
                if isinstance(_cli_v14, dict):
                    uc.v14_flags = _cli_v14
            except Exception:
                uc.v14_flags = {}

        # ---- 多算法选择 (与配置文件解耦: CLI 可独立生效) ----
        _v14_hint = bool(uc.v14_flags.get("v14_enable")
                         or uc.v14_flags.get("v14_enabled"))
        _sel, _mode, _warns = get_user_algorithms_selection(
            self.config, user_id,
            cli_algorithms=(self.cli_algorithms or None),
            cli_mode=(self.cli_algo_mode or None),
            v14_hint=_v14_hint,
        )
        uc.algorithms = _sel
        uc.algo_mode = _mode
        uc.warnings += _warns
        for _w in _warns:
            _log(f"    [v15 WARN] {_w}")
        _log(uc.plan_line())
        return uc


# ============================================================
# 配置 -> 运行环境翻译接口 (供流水线子进程注入)
# ============================================================
def common_overrides_to_env(overrides: dict) -> Dict[str, str]:
    """把 common 常量覆盖 dict 翻译为 NILM_USER_* 环境变量 (空值字段跳过)."""
    env: Dict[str, str] = {}
    for field, env_name in COMMON_OVERRIDE_FIELDS:
        if field not in overrides:
            continue
        val = overrides[field]
        if field == "split_ratios":
            env_val = json.dumps(list(val))
        elif isinstance(val, bool):
            env_val = "1" if val else "0"
        else:
            env_val = str(val)
        env[env_name] = env_val
    return env


def clear_common_override_env() -> None:
    """清除全部 NILM_USER_* 常量覆盖环境变量 (避免跨用户残留污染)."""
    for _, env_name in COMMON_OVERRIDE_FIELDS:
        os.environ.pop(env_name, None)


def guard_cli_to_env(guard: str) -> Dict[str, str]:
    """d87 守卫 CLI 值 -> 环境变量 ("" 表示未指定, 清除由调用方处理)."""
    if guard == "true":
        return {"NILM_USER_GUARD_ENABLED": "1"}
    if guard == "false":
        return {"NILM_USER_GUARD_ENABLED": "0"}
    return {}


def v14_flags_to_env(v14_flags_spec: str) -> Dict[str, str]:
    """v14 增强开关 JSON -> NILM_V14_* 环境变量 (三阶段特征一致性契约)."""
    from algorithms.v14_enhanced import v14_flags_to_env as _impl
    return _impl(v14_flags_spec)


def splits_spec_cli_to_env(splits_spec_str: str) -> Dict[str, str]:
    """per-split 时段过滤 CLI 字符串 -> 环境变量 (空则返回空 dict, 调用方自行清除)."""
    spec = (splits_spec_str or "").strip()
    if spec:
        return {"NILM_SPLITS_FILTER_SPEC": spec}
    return {}
