# -*- coding: utf-8 -*-
"""
[v15 多算法重构] 算法注册框架 + 三种运行模式解析 单元测试
==========================================================
覆盖:
  1. 注册表完整性 (名称/显示名/阶段脚本/模型契约/产物子目录)
  2. CLI 列表解析 (分隔符/大小写/去重/all 别名)
  3. resolve_algorithm_selection 三种模式:
       single / multi / all 语义, CLI 覆盖优先级, 配置回退, v14 提示,
       未注册算法剔除, 空兜底, 告警输出
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from algorithms import (
    REGISTERED_ALGORITHMS, ALGORITHM_NAMES, DEFAULT_ALGORITHMS, ALGO_MODES,
    get_algorithm, parse_algorithms_cli, algorithms_to_cli_arg,
    algorithms_summary, resolve_algorithm_selection,
)
from algorithms.base import AlgoContext


def _ctx(tmp="/tmp"):
    return AlgoContext(
        project_root=Path(tmp), user_id="u1", target_col="p1",
        output_dir=Path(tmp) / "artifacts",
        train_bus="/t/bus.csv", train_branch="/t/br.csv",
    )


def test_registry_completeness():
    assert ALGORITHM_NAMES == ("main", "rf", "v14")
    for name in ("main", "rf", "v14"):
        mod = REGISTERED_ALGORITHMS[name]
        assert mod.name == name, f"{name}.name 与注册键不一致"
        assert mod.display_name, f"{name} 缺显示名"
        assert mod.train_script and mod.eval_script and mod.infer_script, \
            f"{name} 缺阶段脚本声明"
        assert mod.required_model_files, f"{name} 缺模型完整性契约"
        assert mod.artifact_subdir() == name, f"{name} 产物子目录应等于注册名"
    assert DEFAULT_ALGORITHMS == ("main", "rf")


def test_registry_interface_contract():
    # 统一接口: 三个模块都能构建出非空训练环境/评估参数/推理参数
    ctx = _ctx()
    for name in ("main", "rf", "v14"):
        mod = REGISTERED_ALGORITHMS[name]
        env = mod.train_env(ctx)
        assert isinstance(env, dict) and "NILM_ALGO_SELECT" in env, \
            f"{name} 训练环境缺 NILM_ALGO_SELECT 解耦门控"
        assert mod.eval_args(ctx) and mod.infer_args(ctx), f"{name} 评估/推理参数为空"
    # 隔离性: main/rf 门控互斥, v14 复用 main 槽位
    assert REGISTERED_ALGORITHMS["main"].train_env(ctx)["NILM_ALGO_SELECT"] == "main"
    assert REGISTERED_ALGORITHMS["rf"].train_env(ctx)["NILM_ALGO_SELECT"] == "rf"
    assert REGISTERED_ALGORITHMS["v14"].train_env(ctx)["NILM_ALGO_SELECT"] == "main"
    # v14 环境注入: flags JSON 翻译 (经 AlgoContext.v14_flags_spec)
    ctx14 = AlgoContext(
        project_root=Path("/tmp"), user_id="u1", target_col="p1",
        output_dir=Path("/tmp") / "artifacts",
        train_bus="/t/bus.csv", train_branch="/t/br.csv",
        v14_flags_spec='{"v14_enable":true,"physics":true,"focal":false}',
    )
    env14 = REGISTERED_ALGORITHMS["v14"].train_env(ctx14)
    assert env14["NILM_V14_ENABLE"] == "1"
    assert env14["NILM_V14_PHYSICS_FEATURES"] == "1"
    assert env14["NILM_V14_FOCAL"] == "0"
    # 特征一致性契约: v14 物理特征环境必须在 训练/评估/推理 三阶段一致注入
    for _env_fn in ("train_env", "eval_env", "infer_env"):
        _e = getattr(REGISTERED_ALGORITHMS["v14"], _env_fn)(ctx14)
        assert _e["NILM_V14_PHYSICS_FEATURES"] == "1", f"v14 {_env_fn} 缺物理特征环境"
        assert _e["NILM_V14_ENABLE"] == "1", f"v14 {_env_fn} 缺启用环境"


def test_v14_flags_to_env():
    from algorithms.v14_enhanced import v14_flags_to_env
    env = v14_flags_to_env('{"v14_enable":true,"physics":true,"focal":false,'
                           '"ensemble":1,"calibrate":0}')
    assert env["NILM_V14_ENABLE"] == "1"
    assert env["NILM_V14_PHYSICS_FEATURES"] == "1"
    assert env["NILM_V14_FOCAL"] == "0"
    assert env["NILM_V14_ENSEMBLE"] == "1"
    assert env["NILM_V14_CALIBRATE"] == "0"
    # 空/非法输入: 仅默认启用位
    assert v14_flags_to_env("") == {"NILM_V14_ENABLE": "1"}
    assert v14_flags_to_env("not-json") == {"NILM_V14_ENABLE": "1"}
    assert v14_flags_to_env('["list"]') == {"NILM_V14_ENABLE": "1"}


def test_parse_algorithms_cli():
    assert parse_algorithms_cli("main,rf,v14") == ["main", "rf", "v14"]
    assert parse_algorithms_cli("MAIN + RF") == ["main", "rf"]
    assert parse_algorithms_cli("main main rf") == ["main", "rf"]
    assert parse_algorithms_cli("all") == list(ALGORITHM_NAMES)
    assert parse_algorithms_cli("") == []
    assert parse_algorithms_cli(" ,, ") == []
    # 未注册名保留 (由 resolve 剔除并告警)
    assert parse_algorithms_cli("main,xxx") == ["main", "xxx"]
    # 往返
    assert algorithms_to_cli_arg(["main", "rf"]) == "main,rf"
    assert algorithms_summary(["main", "rf"]) == "main,rf"


def test_resolve_default_backward_compat():
    # 无任何配置: 内置默认 main+rf, mode=multi (与重构前行为一致)
    sel, mode, warns = resolve_algorithm_selection()
    assert sel == ["main", "rf"] and mode == "multi" and warns == []


def test_resolve_mode_all():
    sel, mode, warns = resolve_algorithm_selection(cli_mode="all")
    assert sel == list(ALGORITHM_NAMES) and mode == "all"
    # all 模式忽略 selected 列表
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "all", "selected": ["rf"]})
    assert sel == list(ALGORITHM_NAMES) and mode == "all"


def test_resolve_mode_single():
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "single", "selected": ["rf", "v14"]})
    assert sel == ["rf"] and mode == "single"
    # CLI 覆盖配置
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "all", "selected": ["main"]},
        cli_mode="single", cli_algorithms="rf,v14")
    assert sel == ["rf"] and mode == "single"


def test_resolve_mode_multi():
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "multi", "selected": ["main", "v14"]})
    assert sel == ["main", "v14"] and mode == "multi"
    # 只给列表不给 mode: 多个 -> multi, 单个 -> single
    sel, mode, warns = resolve_algorithm_selection(cli_algorithms="rf")
    assert sel == ["rf"] and mode == "single"
    sel, mode, warns = resolve_algorithm_selection(cli_algorithms="rf,main")
    assert sel == ["rf", "main"] and mode == "multi"


def test_resolve_cli_priority_over_config():
    # CLI --algorithms 完全覆盖配置 selected; CLI --algo-mode 覆盖配置 mode
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "all", "selected": ["v14"]},
        cli_algorithms="rf", cli_mode="single")
    assert sel == ["rf"] and mode == "single"
    assert warns == []


def test_resolve_unknown_algo_dropped_with_warning():
    sel, mode, warns = resolve_algorithm_selection(cli_algorithms="main,bad_algo")
    assert sel == ["main"]
    assert any("bad_algo" in w for w in warns)
    # 全部非法 -> 回退默认
    sel, mode, warns = resolve_algorithm_selection(cli_algorithms="nope,also_bad")
    assert sel == ["main", "rf"] and mode == "multi"
    assert any("回退" in w for w in warns)


def test_resolve_v14_hint():
    # 无显式配置但 v14 增强开启 -> 默认列表追加 v14
    sel, mode, warns = resolve_algorithm_selection(v14_hint=True)
    assert sel == ["main", "rf", "v14"]
    # 显式配置存在时 hint 不干扰
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"selected": ["main"]}, v14_hint=True)
    assert sel == ["main"] and mode == "single"


def test_resolve_invalid_mode_warning_fallback():
    sel, mode, warns = resolve_algorithm_selection(
        algo_config={"mode": "bogus", "selected": ["rf"]})
    assert mode == "single"          # 非法 mode 忽略, 按列表长度推定
    assert sel == ["rf"]
    assert any("bogus" in w for w in warns)
    sel, mode, warns = resolve_algorithm_selection(cli_mode="BOGUS")
    assert any("BOGUS" in w for w in warns)
    assert sel == ["main", "rf"]


def test_algo_modes_constant():
    assert ALGO_MODES == ("single", "multi", "all")
    assert get_algorithm("MAIN").name == "main"
    assert get_algorithm("nope") is None


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
