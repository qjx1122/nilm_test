# -*- coding: utf-8 -*-
"""
[v16 数据模块解耦] 数据输出模块统一接口 单元测试
================================================
覆盖:
  1. write_csv / 写出门面再导出
  2. 模型资产: resolve_model_path / save_model_bundle(备份+滚动清理) /
     load_model_bundle / save_model_components
  3. 归档: archive_algo_outputs (算法维度目录) + cleanup_artifacts_top (白名单保护)
  4. 执行状态: _upsert/_load/_get_completed (精简, 全量在 test_batch_execution_state.py)
  5. 批量汇总: aggregate_metrics (算法维度 + 旧扁平布局) / collect_skip_reasons
"""
import shutil
import sys
import json
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_output import (
    write_csv, save_predictions_csv, save_metrics_csv, flatten_metrics_to_rows,
    resolve_model_path, save_model_bundle, load_model_bundle, save_model_components,
    archive_algo_outputs, cleanup_artifacts_top,
    _load_execution_state, _get_completed_users, _upsert_execution_state,
    _execution_state_path, _EXECUTION_STATE_COLS,
    collect_skip_reasons, aggregate_metrics,
)

TMP = Path("/tmp/nilm_data_output_test")


@dataclass
class _FakeCtx:
    project_root: Path
    user_id: str = "9000001_4200001"


class _FakeAlgo:
    name = "main"

    def artifact_subdir(self):
        return self.name


def _mk_proj():
    shutil.rmtree(TMP, ignore_errors=True)
    proj = TMP / "proj"
    for d in ("artifacts/metrics", "artifacts/predictions", "models", "logs",
              "data"):
        (proj / d).mkdir(parents=True, exist_ok=True)
    return proj


def test_write_csv_and_writer_facade():
    proj = _mk_proj()
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    p = write_csv(df, proj / "artifacts" / "out" / "x.csv")
    assert p.exists()
    back = pd.read_csv(p, encoding="utf-8-sig")
    assert list(back["a"]) == [1, 2]
    # 预测/指标写入门面可调用 (行为契约由既有 metrics_utils 测试保障)
    import numpy as np
    save_predictions_csv(pd.to_datetime(["2026-06-01 00:00"]),
                         np.array([10.0]), np.array([12.0]),
                         out_path=proj / "artifacts" / "predictions" / "p.csv")
    rows = flatten_metrics_to_rows(
        "test", "main",
        cls_metrics={"F1": 0.8, "Accuracy": 0.9},
        reg_metrics={"MAE_W": 5.0},
        source="evaluate")
    assert len(rows) == 3
    save_metrics_csv(rows, proj / "artifacts" / "metrics" / "m.csv")
    assert (proj / "artifacts" / "predictions" / "p.csv").exists()
    assert (proj / "artifacts" / "metrics" / "m.csv").exists()


def test_resolve_model_path_rf_fallback():
    proj = _mk_proj()
    (proj / "models" / "rf_bundle.pkl").write_bytes(b"x")
    # rf 算法 + 主路径不存在 -> 回退 rf_bundle.pkl
    assert resolve_model_path("rf", proj / "models" / "nilm_ac_two_stage.pkl",
                              proj / "models").name == "rf_bundle.pkl"
    # rf 算法 + 主路径存在 -> 不切换
    (proj / "models" / "nilm_ac_two_stage.pkl").write_bytes(b"y")
    assert resolve_model_path("rf", proj / "models" / "nilm_ac_two_stage.pkl",
                              proj / "models").name == "nilm_ac_two_stage.pkl"
    # main 算法 -> 原样
    assert resolve_model_path("main", proj / "models" / "nilm_ac_two_stage.pkl",
                              proj / "models").name == "nilm_ac_two_stage.pkl"


def test_save_load_bundle_and_backup_rotation():
    proj = _mk_proj()
    md = proj / "models"
    for i in range(5):
        save_model_bundle({"i": i}, md / "main.pkl",
                          backup_tag=f"t{i}", backup_prefix="main_",
                          max_backups=2, backup_exclude={"main.pkl"})
    assert (md / "main.pkl").exists()
    backups = sorted(p.name for p in md.glob("main_*.pkl"))
    assert len(backups) == 2, f"滚动保留 2 份, 实际 {backups}"
    assert load_model_bundle(md / "main.pkl") == {"i": 4}
    # 主文件豁免删除
    assert (md / "main.pkl").exists()
    # 缺失文件报错
    try:
        load_model_bundle(md / "nope.pkl")
        raise AssertionError("应抛出 FileNotFoundError")
    except FileNotFoundError:
        pass


def test_save_model_components():
    proj = _mk_proj()
    md = proj / "models"
    save_model_components({"scaler.pkl": {"a": 1}}, md,
                          meta={"version": "v1"}, meta_name="model_meta.json")
    assert (md / "scaler.pkl").exists()
    meta = json.loads((md / "model_meta.json").read_text(encoding="utf-8"))
    assert meta["version"] == "v1"
    save_model_components({}, md, meta={"k": "v"}, meta_name="rf_bundle_meta.json")
    assert (md / "rf_bundle_meta.json").exists()


def test_archive_algo_outputs_layout_and_cleanup():
    proj = _mk_proj()
    out = proj / "artifacts"
    ctx = _FakeCtx(project_root=proj)
    algo = _FakeAlgo()
    # 顶层临时产物
    (proj / "models" / "nilm_ac_two_stage.pkl").write_bytes(b"bundle")
    (proj / "models" / "model_meta.json").write_text("{}")
    (proj / "artifacts" / "metrics" / "train_val_metrics.csv").write_text("a")
    (proj / "artifacts" / "metrics" / "inference_metrics.csv").write_text("b")
    (proj / "artifacts" / "predictions" / "test_pred.csv").write_text("c")
    (proj / "artifacts" / "predictions" / "inference_result.csv").write_text("d")
    (proj / "logs" / "run.log").write_text("log")
    (proj / "artifacts" / "batch_execution_state.csv").write_text("state")
    (proj / "artifacts" / "aligned_15min.csv").write_text("shared")

    archive_algo_outputs(proj, out, ctx.user_id, algo, ctx, has_inference=True)

    # 算法维度目录
    assert (proj / "models" / ctx.user_id / "main" / "nilm_ac_two_stage.pkl").exists()
    t = out / "trains" / ctx.user_id / "main"
    i = out / "infers" / ctx.user_id / "main"
    assert (t / "train_val_metrics.csv").exists()
    assert (t / "test_pred.csv").exists()
    assert (i / "inference_metrics.csv").exists()
    assert (i / "inference_result.csv").exists()
    assert (proj / "logs" / ctx.user_id / "run.log").exists()
    # 顶层临时被清; 白名单保留
    assert not (proj / "models" / "nilm_ac_two_stage.pkl").exists()
    assert not (proj / "artifacts" / "metrics" / "train_val_metrics.csv").exists()
    assert (out / "batch_execution_state.csv").exists()
    assert (out / "aligned_15min.csv").exists()   # [v15] 执行期共享保留


def test_cleanup_artifacts_top_whitelist():
    proj = _mk_proj()
    out = proj / "artifacts"
    keep = ["batch_execution_state.csv", "batch_run_summary.csv",
            "summary_metrics_all_users.csv", "skipped_users.csv", ".gitkeep"]
    for f in keep:
        (out / f).write_text("x")
    (out / "junk.csv").write_text("x")
    (out / "aligned_15min.csv").write_text("x")
    (out / "skip_reason.json").write_text("x")
    (out / "metrics" / "m.csv").write_text("x")
    cleanup_artifacts_top(proj)
    for f in keep + ["aligned_15min.csv", "skip_reason.json"]:
        assert (out / f).exists(), f"{f} 应保留"
    assert not (out / "junk.csv").exists()
    # metrics/predictions 骨架重建
    assert (out / "metrics").is_dir() and (out / "predictions").is_dir()


def test_execution_state_upsert_and_completed():
    proj = _mk_proj()
    out = proj / "artifacts"
    _upsert_execution_state(out, {"user_id": "u1", "status": "ok",
                                  "success": True, "started_at": "",
                                  "finished_at": "", "duration_s": 1.2,
                                  "message": "", "target_col": "p1",
                                  "algorithms": "main,rf", "run_id": "r1"})
    _upsert_execution_state(out, {"user_id": "u2", "status": "fail"})
    df = _load_execution_state(out)
    assert len(df) == 2
    assert list(df.columns) == _EXECUTION_STATE_COLS
    assert _get_completed_users(df) == {"u1"}           # 只跳 ok
    assert _get_completed_users(df, retry_failed=False) == {"u1", "u2"}
    # upsert 覆盖
    _upsert_execution_state(out, {"user_id": "u1", "status": "fail"})
    df2 = _load_execution_state(out)
    assert len(df2) == 2 and df2[df2["user_id"] == "u1"]["status"].iloc[0] == "fail"
    # 文件不存在 -> 空表
    assert len(_load_execution_state(proj / "artifacts" / "none")) == 0


def _mk_metrics_csv(path, split_model_map):
    rows = []
    for (split, model), mets in split_model_map.items():
        for mname, mval in mets.items():
            rows.append({"split": split, "model": model, "metric": mname,
                         "value": mval})
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8-sig")


def test_aggregate_metrics_algo_and_flat():
    proj = _mk_proj()
    out = proj / "artifacts"
    u = "9000001_4200001"
    # 算法维度布局: main (train/val/test/inference) + rf
    mets = {"Accuracy": 0.9, "F1": 0.8, "MAE_W": 5.0, "SAE": 0.1,
            "kWh_true": 10.0, "kWh_pred": 9.5, "n_samples": 100}
    (out / "trains" / u / "main").mkdir(parents=True)
    (out / "infers" / u / "main").mkdir(parents=True)
    (out / "trains" / u / "rf").mkdir(parents=True)
    (out / "infers" / u / "rf").mkdir(parents=True)
    _mk_metrics_csv(out / "trains" / u / "main" / "train_val_metrics.csv",
                    {("train", "main"): mets, ("val", "main"): mets})
    _mk_metrics_csv(out / "trains" / u / "main" / "test_metrics.csv",
                    {("test", "main"): mets})
    _mk_metrics_csv(out / "infers" / u / "main" / "inference_metrics.csv",
                    {("inference", "main_final"): mets, ("inference", "main"): mets})
    _mk_metrics_csv(out / "trains" / u / "rf" / "train_val_metrics.csv",
                    {("train", "rf"): mets, ("val", "rf"): mets})
    _mk_metrics_csv(out / "trains" / u / "rf" / "test_metrics.csv",
                    {("test", "rf"): mets})
    _mk_metrics_csv(out / "infers" / u / "rf" / "inference_metrics.csv",
                    {("inference", "rf"): mets})

    written = aggregate_metrics(out, out)
    assert written and written[0][0] == "summary_metrics_all_users.csv"
    sm = pd.read_csv(out / "summary_metrics_all_users.csv", encoding="utf-8-sig")
    assert set(sm["algo"]) == {"main", "rf"}
    assert len(sm) == 8, f"每算法 4 行, 实际 {len(sm)}"
    main_inf = sm[(sm["algo"] == "main") & (sm["stage"] == "inference")]
    assert main_inf["status"].iloc[0] == "ok:main_final"   # 模型优选
    rf_inf = sm[(sm["algo"] == "rf") & (sm["stage"] == "inference")]
    assert rf_inf["status"].iloc[0] == "ok:rf"
    assert sm[(sm["algo"] == "main") & (sm["stage"] == "train")]["F1"].iloc[0] == 0.8

    # 旧扁平布局兼容
    proj2 = _mk_proj()
    out2 = proj2 / "artifacts"
    (out2 / "trains" / u).mkdir(parents=True)
    _mk_metrics_csv(out2 / "trains" / u / "train_val_metrics.csv",
                    {("train", "main"): mets, ("val", "main"): mets})
    aggregate_metrics(out2, out2)
    sm2 = pd.read_csv(out2 / "summary_metrics_all_users.csv", encoding="utf-8-sig")
    assert set(sm2["algo"]) == {"flat"}


def test_collect_skip_reasons_algo_and_flat():
    proj = _mk_proj()
    out = proj / "artifacts"
    u = "9000001_4200001"
    (out / "trains" / u / "rf").mkdir(parents=True)
    (out / "trains" / u / "rf" / "skip_reason.json").write_text(
        json.dumps({"skip_reason": "aligned_too_few", "detail": "x"}))
    csv, n = collect_skip_reasons(out, out)
    assert n == 1
    df = pd.read_csv(csv, encoding="utf-8-sig")
    assert df["algo"].iloc[0] == "rf" and df["skip_reason"].iloc[0] == "aligned_too_few"
    # 旧扁平布局
    proj2 = _mk_proj()
    out2 = proj2 / "artifacts"
    (out2 / "trains" / u).mkdir(parents=True)
    (out2 / "trains" / u / "skip_reason.json").write_text(
        json.dumps({"skip_reason": "single_class_label"}))
    csv2, n2 = collect_skip_reasons(out2, out2)
    df2 = pd.read_csv(csv2, encoding="utf-8-sig")
    assert n2 == 1 and df2["algo"].iloc[0] == "flat"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
    shutil.rmtree(TMP, ignore_errors=True)
