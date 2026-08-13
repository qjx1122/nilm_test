# -*- coding: utf-8 -*-
"""
[v16 数据模块解耦] 数据配置模块统一接口 单元测试
================================================
覆盖:
  1. ConfigResolver 从 dict / path 构建
  2. resolve(): 各字段解析 (target_col / guard / 时段 / splits / common / v14 / algorithms)
  3. CLI 覆盖优先级 (v14 flags CLI > 配置; algorithms CLI > 配置)
  4. _default 回退
  5. UserConfig 序列化接口 (to_pipeline_cli / guard_cli / *_cli / plan_line)
  6. 环境翻译接口 (common_overrides_to_env / guard_cli_to_env / v14_flags_to_env /
     splits_spec_cli_to_env / v14_enabled_from_spec)
"""
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_config import (
    ConfigResolver, UserConfig,
    COMMON_OVERRIDE_FIELDS,
    common_overrides_to_env, clear_common_override_env,
    guard_cli_to_env, v14_flags_to_env, splits_spec_cli_to_env,
    v14_enabled_from_spec,
)

CFG = {
    "u_full": {
        "target_col": "p2",
        "guard_enabled": True,
        "on_thr_w": 50,
        "split_ratios": [0.7, 0.15, 0.15],
        "train": {"exclude": [["2026-06-05", "2026-06-05"]]},
        "infer": {"include": [["2026-08-01", "2026-08-15"]]},
        "splits": {"val": {"include": [["2026-06-01", "2026-06-01"]]}},
        "v14": {"v14_enable": True, "physics": True},
        "algorithms": {"mode": "all"},
    },
    "u_alg_single": {
        "algorithms": {"mode": "single", "selected": ["rf"]},
    },
    "u_none": {},
    "_default": {
        "algorithms": {"mode": "multi", "selected": ["main"]},
    },
}


def test_resolver_from_dict_and_path():
    r = ConfigResolver(config=CFG)
    assert r.config is CFG
    # 从路径加载
    tmp = Path("/tmp/_data_config_test.json")
    tmp.write_text(json.dumps(CFG, ensure_ascii=False), encoding="utf-8")
    r2 = ConfigResolver(config_path=str(tmp))
    assert set(r2.config) == set(CFG)
    tmp.unlink()


def test_resolve_full_fields():
    r = ConfigResolver(config=CFG)
    uc = r.resolve("u_full")
    assert uc.target_col == "p2"
    assert uc.guard_enabled is True
    assert uc.common_overrides["on_thr_w"] == 50
    assert uc.train_spec is not None and uc.train_spec["exclude"]
    assert uc.infer_spec is not None and uc.infer_spec["include"]
    assert uc.splits_spec is not None and "val" in uc.splits_spec
    assert uc.v14_flags.get("v14_enable") is True
    assert uc.v14_flags.get("physics") is True
    assert uc.algorithms == ["main", "rf", "v14"] and uc.algo_mode == "all"


def test_resolve_default_fallback_and_empty():
    r = ConfigResolver(config=CFG)
    # 未列出的用户 -> _default 回退
    uc = r.resolve("u_unknown")
    assert uc.algorithms == ["main"] and uc.algo_mode == "multi"
    assert uc.target_col is None
    assert uc.guard_enabled is None
    # 用户存在但无 algorithms 字段 -> 内置默认 main+rf (不穿透 _default, 与既有字段语义一致)
    uc2 = r.resolve("u_none")
    assert uc2.algorithms == ["main", "rf"] and uc2.algo_mode == "multi"
    # 无配置 -> 内置默认 main+rf
    r2 = ConfigResolver(config={})
    uc3 = r2.resolve("any_user")
    assert uc3.algorithms == ["main", "rf"] and uc3.algo_mode == "multi"


def test_resolve_cli_priority():
    # CLI algorithms/mode 覆盖配置
    r = ConfigResolver(config=CFG, cli_algorithms="rf", cli_algo_mode="single")
    uc = r.resolve("u_full")
    assert uc.algorithms == ["rf"] and uc.algo_mode == "single"
    # CLI v14 flags 覆盖配置 (配置 v14_enable=True 但 CLI 关闭 physics)
    r2 = ConfigResolver(config=CFG, cli_v14_flags='{"v14_enable":true,"physics":false}')
    uc2 = r2.resolve("u_full")
    assert uc2.v14_flags.get("physics") is False


def test_resolve_v14_hint_appends_v14():
    # 配置 v14 开启但 algorithms 未配置 -> 默认列表追加 v14
    cfg = {"u1": {"v14": {"v14_enable": True}}}
    uc = ConfigResolver(config=cfg).resolve("u1")
    assert uc.algorithms == ["main", "rf", "v14"]
    # v14 关闭 -> 不追加
    cfg2 = {"u2": {"v14": {"v14_enable": False}}}
    uc2 = ConfigResolver(config=cfg2).resolve("u2")
    assert uc2.algorithms == ["main", "rf"]


def test_resolve_warnings_and_verbose_log():
    cfg = {"u1": {"algorithms": {"selected": ["main", "no_such"]}}}
    r = ConfigResolver(config=cfg)
    lines = []
    uc = r.resolve("u1", verbose=True, logger_print=lines.append)
    assert uc.algorithms == ["main"]
    assert any("no_such" in w for w in uc.warnings)
    assert any("算法计划: main (mode=single)" in ln for ln in lines)


def test_user_config_serialization():
    uc = UserConfig(user_id="u1", target_col="p1+p2",
                    guard_enabled=False,
                    train_spec={"include": [], "exclude": []},
                    common_overrides={"on_thr_w": 42.0},
                    v14_flags={"v14_enable": True},
                    algorithms=["main", "rf"], algo_mode="multi")
    cli = uc.to_pipeline_cli()
    assert cli["guard_enabled"] == "false"
    assert cli["algorithms"] == "main,rf" and cli["algo_mode"] == "multi"
    assert "42" in cli["common_overrides"]
    assert cli["v14_flags"].strip()
    # 空值序列化
    uc2 = UserConfig(user_id="u2")
    assert uc2.to_pipeline_cli()["guard_enabled"] == ""
    assert uc2.to_pipeline_cli()["v14_flags"] == ""
    assert uc2.to_pipeline_cli()["algorithms"] == "main,rf"
    assert uc2.plan_line() == "  [v15] 算法计划: main,rf (mode=multi)"


def test_env_translation():
    # common overrides -> env
    env = common_overrides_to_env({"on_thr_w": 50, "use_weather_features": False,
                                   "split_ratios": [0.7, 0.15, 0.15]})
    assert env["NILM_USER_ON_THR_W"] == "50"
    assert env["NILM_USER_USE_WEATHER_FEATURES"] == "0"
    assert json.loads(env["NILM_USER_SPLIT_RATIOS"]) == [0.7, 0.15, 0.15]
    assert "NILM_USER_POST_MIN_ON" not in env
    # 清除接口
    os.environ["NILM_USER_ON_THR_W"] = "999"
    clear_common_override_env()
    assert "NILM_USER_ON_THR_W" not in os.environ
    # guard
    assert guard_cli_to_env("true") == {"NILM_USER_GUARD_ENABLED": "1"}
    assert guard_cli_to_env("false") == {"NILM_USER_GUARD_ENABLED": "0"}
    assert guard_cli_to_env("") == {}
    # splits
    assert splits_spec_cli_to_env('{"train":{}}') == {"NILM_SPLITS_FILTER_SPEC": '{"train":{}}'}
    assert splits_spec_cli_to_env("") == {}
    # v14
    env14 = v14_flags_to_env('{"v14_enable":true,"focal":true}')
    assert env14["NILM_V14_ENABLE"] == "1" and env14["NILM_V14_FOCAL"] == "1"
    assert v14_flags_to_env("") == {"NILM_V14_ENABLE": "1"}


def test_v14_enabled_from_spec():
    assert v14_enabled_from_spec('{"v14_enable":true}') is True
    assert v14_enabled_from_spec('{"v14_enabled":1}') is True
    assert v14_enabled_from_spec('{"physics":true}') is False
    assert v14_enabled_from_spec("") is False
    assert v14_enabled_from_spec("not-json") is False


def test_common_override_fields_mapping():
    names = {env_name for _, env_name in COMMON_OVERRIDE_FIELDS}
    assert names == {
        "NILM_USER_ON_THR_W", "NILM_USER_POST_MIN_ON",
        "NILM_USER_POST_FILL_SHORT_OFF", "NILM_USER_SPLIT_STRATEGY",
        "NILM_USER_SPLIT_RATIOS", "NILM_USER_WEATHER_LATITUDE",
        "NILM_USER_WEATHER_LONGITUDE", "NILM_USER_USE_WEATHER_FEATURES",
        "NILM_USER_USE_TEMP_BASED_SEASON",
    }


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
