# -*- coding: utf-8 -*-
"""
[v15 多算法重构] time_filter_config.algorithms 配置字段解析 单元测试
====================================================================
覆盖:
  1. get_user_algorithms_config: 用户级命中 / _default 回退 / 缺失 / 非 dict 防御
  2. get_user_algorithms_selection: 配置 -> 三种模式 解析 + CLI 覆盖 + v14_hint
  3. algorithms_config_summary: 摘要输出
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from time_filter_utils import (
    get_user_algorithms_config,
    get_user_algorithms_selection,
    algorithms_config_summary,
)

CFG = {
    "u_all": {
        "algorithms": {"mode": "all"},
    },
    "u_single": {
        "algorithms": {"mode": "single", "selected": ["rf", "v14"]},
    },
    "u_multi": {
        "algorithms": {"mode": "multi", "selected": ["main", "v14"]},
    },
    "u_none": {},
    "_default": {
        "algorithms": {"mode": "multi", "selected": ["main"]},
    },
}


def test_get_user_algorithms_config_hit():
    cfg = get_user_algorithms_config(CFG, "u_all")
    assert cfg == {"mode": "all"}


def test_get_user_algorithms_config_default_fallback():
    # 未配置用户 -> 回退 _default
    cfg = get_user_algorithms_config(CFG, "u_unknown")
    assert cfg == {"mode": "multi", "selected": ["main"]}


def test_get_user_algorithms_config_missing_and_defense():
    # 用户配置存在但无 algorithms 字段 -> None (u_none 命中自身, 不回退 _default)
    assert get_user_algorithms_config(CFG, "u_none") is None
    # 全空 / 非 dict
    assert get_user_algorithms_config({}, "u1") is None
    assert get_user_algorithms_config(None, "u1") is None
    assert get_user_algorithms_config({"u1": {"algorithms": "not-a-dict"}}, "u1") is None
    assert get_user_algorithms_config({"u1": "not-a-dict"}, "u1") is None


def test_selection_from_config_all():
    sel, mode, warns = get_user_algorithms_selection(CFG, "u_all")
    assert mode == "all"
    assert sel == ["main", "rf", "v14"]


def test_selection_from_config_single():
    sel, mode, warns = get_user_algorithms_selection(CFG, "u_single")
    assert mode == "single" and sel == ["rf"]


def test_selection_from_config_multi():
    sel, mode, warns = get_user_algorithms_selection(CFG, "u_multi")
    assert mode == "multi" and sel == ["main", "v14"]


def test_selection_default_backward_compat():
    # 无 algorithms 配置 -> 内置默认 main+rf
    sel, mode, warns = get_user_algorithms_selection({"u1": {}}, "u1")
    assert sel == ["main", "rf"] and mode == "multi"


def test_selection_cli_overrides_config():
    sel, mode, warns = get_user_algorithms_selection(
        CFG, "u_all", cli_algorithms="rf", cli_mode="single")
    assert sel == ["rf"] and mode == "single"


def test_selection_v14_hint_append():
    sel, mode, warns = get_user_algorithms_selection({"u1": {}}, "u1", v14_hint=True)
    assert sel == ["main", "rf", "v14"]


def test_selection_unknown_algo_warning():
    cfg = {"u1": {"algorithms": {"selected": ["main", "no_such"]}}}
    sel, mode, warns = get_user_algorithms_selection(cfg, "u1")
    assert sel == ["main"]
    assert any("no_such" in w for w in warns)


def test_algorithms_config_summary():
    assert algorithms_config_summary(None) == "(未配置)"
    assert algorithms_config_summary({"mode": "all"}) == "mode=all, selected=(默认)"
    assert algorithms_config_summary(
        {"mode": "multi", "selected": ["main", "rf"]}
    ) == "mode=multi, selected=main,rf"
    assert algorithms_config_summary({"selected": ["v14"]}) == "mode=(自动), selected=v14"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
