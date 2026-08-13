# -*- coding: utf-8 -*-
"""
[v17 统一训练/推理访问接口] 单元测试
====================================
覆盖:
  1. StageRunner 真实子进程: 退出码翻译 (0->ok / 11->soft_skip / 7->fail)、
     环境注入隔离、stdout 捕获
  2. AlgorithmModule 统一接口 dispatch: main/rf/v14 的 train/evaluate/infer
     正确组装 脚本/参数/环境 (注入假执行器录制调用)
  3. infer() 通用参数自动组装: --bus / --branch / --no-branch / --time-filter-spec
  4. 注册表级统一多模型入口: train_models/evaluate_models/infer_models
  5. StageResult 判定属性与摘要
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from algorithms import (
    get_algorithm, REGISTERED_ALGORITHMS, ALGORITHM_NAMES,
    train_models, evaluate_models, infer_models,
    StageRunner, StageResult, SOFT_SKIP_CODES,
)
from algorithms.base import AlgoContext

TMP = Path("/tmp/nilm_algo_runner_test")


def _ctx(**kw):
    defaults = dict(
        project_root=Path("/tmp/proj"), user_id="u1", target_col="p1",
        output_dir=Path("/tmp/proj") / "artifacts",
        train_bus="/t/bus.csv", train_branch="/t/br.csv",
        infer_bus="/t/ibus.csv", infer_branch="/t/ibr.csv",
        infer_bus_staged="/tmp/proj/data/infer_bus.csv",
        infer_branch_staged="/tmp/proj/data/infer_branch.csv",
        has_inference=True,
    )
    defaults.update(kw)
    return AlgoContext(**defaults)


class FakeRunner:
    """录制调用的假执行器: 按 (algo, stage) 返回预置结果, 或默认 ok."""
    def __init__(self, results=None):
        self.calls = []
        self.results = results or {}

    def run(self, script, args=None, env=None, label="", algo="", stage=""):
        self.calls.append(dict(script=script, args=list(args or []),
                               env=dict(env or {}), label=label,
                               algo=algo, stage=stage))
        return self.results.get((algo, stage),
                                StageResult(algo=algo, stage=stage,
                                            status="ok", exit_code=0))


# ============================================================
# 1. StageRunner 真实子进程
# ============================================================
def _mk_probe_script():
    TMP.mkdir(parents=True, exist_ok=True)
    probe = TMP / "probe_stage.py"
    probe.write_text(
        "import os, sys\n"
        "print('probe stdout ok')\n"
        "print('ENV_VAR=' + os.environ.get('TEST_ENV', 'unset'))\n"
        "sys.exit(int(os.environ.get('TEST_EXIT', '0')))\n",
        encoding="utf-8")
    return probe


def test_stage_runner_exit_code_mapping():
    probe = _mk_probe_script()
    runner = StageRunner(cwd=str(TMP))
    # ok
    r = runner.run(str(probe), env={"TEST_EXIT": "0", "TEST_ENV": "x"},
                   label="t", algo="main", stage="train")
    assert r.ok and r.exit_code == 0 and r.algo == "main" and r.stage == "train"
    assert "probe stdout ok" in r.stdout_tail
    # soft_skip (11)
    r = runner.run(str(probe), env={"TEST_EXIT": "11"}, label="t", algo="rf", stage="train")
    assert r.is_soft_skip and r.exit_code == 11 and not r.is_fail
    # 12/13 同属软跳过集合
    assert SOFT_SKIP_CODES == (11, 12, 13)
    # fail (7)
    r = runner.run(str(probe), env={"TEST_EXIT": "7"}, label="t", algo="rf", stage="train")
    assert r.is_fail and r.exit_code == 7 and "非零退出" in r.message


def test_stage_runner_env_isolation():
    probe = _mk_probe_script()
    os.environ.pop("TEST_ENV", None)
    # env 只注入子进程, 不污染父进程
    runner = StageRunner(cwd=str(TMP))
    r = runner.run(str(probe), env={"TEST_ENV": "child"}, label="t")
    assert r.ok
    assert "ENV_VAR=child" in r.stdout_tail
    assert os.environ.get("TEST_ENV") is None, "父进程环境被污染"


def test_stage_runner_missing_script():
    runner = StageRunner(cwd=str(TMP))
    r = runner.run("no_such_script_xyz.py", label="t")
    # python 可启动但脚本不存在 -> 非零退出, 判定为 fail
    assert r.is_fail and "非零退出" in r.message


# ============================================================
# 2. AlgorithmModule 统一接口 dispatch (假执行器)
# ============================================================
def test_main_module_unified_dispatch():
    mod = get_algorithm("main")
    fr = FakeRunner()
    ctx = _ctx()
    tr = mod.train(ctx, runner=fr)
    assert tr.ok and tr.stage == "train"
    call = fr.calls[0]
    assert call["script"] == "03_train.py"
    assert call["env"]["NILM_ALGO_SELECT"] == "main"   # 训练门控走隔离环境
    er = mod.evaluate(ctx, runner=fr)
    assert er.ok and fr.calls[1]["script"] == "04_evaluate.py"
    assert "--algo" in fr.calls[1]["args"] and "main" in fr.calls[1]["args"]
    assert "--no-baseline" in fr.calls[1]["args"]
    ir = mod.infer(ctx, runner=fr)
    assert ir.ok and fr.calls[2]["script"] == "05_inference.py"
    assert "--algo" in fr.calls[2]["args"] and "main" in fr.calls[2]["args"]


def test_rf_module_unified_dispatch():
    mod = get_algorithm("rf")
    fr = FakeRunner()
    ctx = _ctx()
    tr = mod.train(ctx, runner=fr)
    assert tr.ok and fr.calls[0]["env"]["NILM_ALGO_SELECT"] == "rf"
    ir = mod.infer(ctx, runner=fr)
    call = fr.calls[-1]
    assert "--algo" in call["args"] and "rf" in call["args"]
    assert "--model" in call["args"]
    i = call["args"].index("--model")
    assert call["args"][i + 1].endswith("rf_bundle.pkl")


def test_v14_module_unified_dispatch():
    mod = get_algorithm("v14")
    fr = FakeRunner()
    ctx = _ctx(v14_flags_spec='{"v14_enable":true,"physics":true}')
    tr = mod.train(ctx, runner=fr)
    assert tr.ok and fr.calls[0]["script"] == "14_train_v14.py"
    assert fr.calls[0]["env"]["NILM_V14_ENABLE"] == "1"
    assert fr.calls[0]["env"]["NILM_ALGO_SELECT"] == "main"
    er = mod.evaluate(ctx, runner=fr)
    # 特征一致性契约: 评估/推理阶段同样注入 v14 环境
    assert fr.calls[1]["env"]["NILM_V14_PHYSICS_FEATURES"] == "1"
    ir = mod.infer(ctx, runner=fr)
    assert fr.calls[2]["env"]["NILM_V14_ENABLE"] == "1"


# ============================================================
# 3. infer() 通用参数自动组装
# ============================================================
def test_infer_common_args_with_branch():
    mod = get_algorithm("main")
    fr = FakeRunner()
    ctx = _ctx(infer_time_filter_spec='{"include":[]}')
    mod.infer(ctx, runner=fr)
    args = fr.calls[0]["args"]
    i = args.index("--bus")
    assert args[i + 1] == ctx.infer_bus_staged
    j = args.index("--branch")
    assert args[j + 1] == ctx.infer_branch_staged
    assert "--time-filter-spec" in args and '{"include":[]}' in args


def test_infer_common_args_no_branch_no_filter():
    mod = get_algorithm("rf")
    fr = FakeRunner()
    ctx = _ctx(infer_branch_staged="", infer_time_filter_spec="")
    mod.infer(ctx, runner=fr)
    args = fr.calls[0]["args"]
    assert "--no-branch" in args and "--branch" not in args
    assert "--time-filter-spec" not in args


def test_infer_missing_staged_bus_fails_fast():
    mod = get_algorithm("main")
    fr = FakeRunner()
    ctx = _ctx(infer_bus_staged="")
    r = mod.infer(ctx, runner=fr)
    assert r.is_fail and "infer_bus_staged" in r.message
    assert fr.calls == [], "未落地时不应发起执行"


# ============================================================
# 4. 注册表级统一多模型入口
# ============================================================
def test_train_evaluate_infer_models_iterate_in_order():
    fr = FakeRunner()
    ctx = _ctx()
    names = ["main", "rf", "v14"]
    tr = train_models(names, ctx, runner=fr)
    assert list(tr.keys()) == names and all(r.ok for r in tr.values())
    assert [c["algo"] for c in fr.calls] == names
    assert all(c["stage"] == "train" for c in fr.calls)
    er = evaluate_models(names, ctx, runner=fr)
    assert list(er.keys()) == names
    assert all(c["stage"] == "evaluate" for c in fr.calls[3:])
    ir = infer_models(names, ctx, runner=fr)
    assert list(ir.keys()) == names
    assert all(c["stage"] == "inference" for c in fr.calls[6:])
    assert len(fr.calls) == 9


def test_models_api_propagates_status():
    # 统一入口如实透传各算法阶段状态 (软跳过/失败不吞掉)
    fr = FakeRunner({("rf", "train"): StageResult(algo="rf", stage="train",
                                                  status="soft_skip", exit_code=12)})
    tr = train_models(["main", "rf"], _ctx(), runner=fr)
    assert tr["main"].ok and tr["rf"].is_soft_skip and tr["rf"].exit_code == 12


# ============================================================
# 5. StageResult 判定与摘要
# ============================================================
def test_stage_result_properties_and_summary():
    ok = StageResult(algo="main", stage="train", status="ok", exit_code=0)
    sk = StageResult(algo="rf", stage="train", status="soft_skip", exit_code=11)
    fl = StageResult(algo="v14", stage="inference", status="fail", exit_code=1)
    assert ok.ok and not ok.is_fail and not ok.is_soft_skip
    assert sk.is_soft_skip and not sk.ok and not sk.is_fail
    assert fl.is_fail and not fl.ok and not fl.is_soft_skip
    assert "✓" in ok.summary() and "◐" in sk.summary() and "✗" in fl.summary()
    assert fl.message == "" or isinstance(fl.message, str)


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
