# -*- coding: utf-8 -*-
"""
[v16] 数据输出模块 — 统一输出访问接口
======================================
职责: 输出产物的持久化、归档、汇总与批量状态管理。是"数据输入 / 数据输出 /
数据配置"三大解耦模块中的输出底座, 编排层 (批量调度 + 单用户流水线) 与
阶段脚本 (03/04/05) 的数据出口统一收敛到这里。

对外统一接口:
    # 通用 CSV 写出
    write_csv(df, path, logger=None)
    # 预测 / 指标 CSV 写出门面 (底层实现 metrics_utils)
    save_predictions_csv / save_metrics_csv / save_daily_metrics_csv /
    build_comparison_table / build_leak_ood_metric_rows /
    build_daily_metrics_rows / compute_raw_daily_counts /
    compute_classification_metrics / compute_regression_metrics /
    flatten_metrics_to_rows
    # 模型资产持久化
    resolve_model_path(algo, model_path, model_dir=None)
    load_model_bundle(path, logger=None)
    save_model_bundle(bundle, bundle_path, backup_tag=None, backup_prefix=None,
                      max_backups=3, backup_exclude=None, logger=None)
    save_model_components(components=None, model_dir=None, meta=None,
                          meta_name="model_meta.json", logger=None)
    # 单用户流水线: 模型资产检查/恢复 + 算法维度归档 + 顶层清理
    check_algo_model_complete / restore_algo_models_to_top /
    archive_algo_outputs / cleanup_artifacts_top
    # 批量层: 断点续跑执行状态 + 软跳过汇总 + 指标聚合
    _execution_state_path / _load_execution_state / _get_completed_users /
    _upsert_execution_state / collect_skip_reasons / aggregate_metrics

依赖方向: 依赖底层实现层 (metrics_utils / common), 不依赖数据输入/数据配置模块
(算法模块与上下文以参数传入, 惰性 import 算法注册表避免模块级耦合).
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd

from common import MODEL_DIR

# ---------- 预测 / 指标 CSV 底层实现门面再导出 (统一输出入口) ----------
from metrics_utils import (
    compute_classification_metrics,
    compute_regression_metrics,
    save_predictions_csv,
    flatten_metrics_to_rows,
    save_metrics_csv,
    build_comparison_table,
    build_leak_ood_metric_rows,
    build_daily_metrics_rows,
    save_daily_metrics_csv,
    compute_raw_daily_counts,
)


# ============================================================
# 通用 CSV 写出
# ============================================================
def write_csv(df: pd.DataFrame, path, logger=None) -> Path:
    """统一 CSV 写出接口 (utf-8-sig, 无索引, 自动建父目录)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    if logger is not None:
        logger.info(f"  ✓ 写出 CSV -> {path}  ({len(df)} 行 × {df.shape[1]} 列)")
    return path


# ============================================================
# 模型资产持久化
# ============================================================
def resolve_model_path(algo: str, model_path: Path, model_dir: Path = None) -> Path:
    """[v16] 解析阶段脚本实际加载的模型路径 (算法感知).

    rf 算法: 优先加载自包含 rf_bundle.pkl (03_train NILM_ALGO_SELECT=rf 产出);
    缺失时回退主模型 bundle (旧版合并训练布局, bundle 内含 'rf' 字段).
    其余算法: 原样返回.
    """
    if algo != "rf" or model_path.exists():
        return model_path
    md = Path(model_dir) if model_dir is not None else MODEL_DIR
    rf_bundle = md / "rf_bundle.pkl"
    if rf_bundle.exists():
        return rf_bundle
    return model_path


def load_model_bundle(path, logger=None) -> dict:
    """统一模型 bundle 加载接口 (joblib)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"模型文件不存在: {path}")
    bundle = joblib.load(path)
    if logger is not None:
        logger.info(f"  ✓ 加载模型 bundle -> {path}  "
                    f"({path.stat().st_size / 1024:.1f} KB)")
    return bundle


def save_model_bundle(bundle, bundle_path, backup_tag: str = None,
                      backup_prefix: str = None, max_backups: int = 3,
                      backup_exclude=None, logger=None) -> Path:
    """统一模型 bundle 落盘接口 (主文件 + 可选时间戳备份 + 滚动清理).

    Args:
        bundle:         待持久化对象 (dict)
        bundle_path:    主文件路径
        backup_tag:     备份文件名时间戳 (若备份启用); None 则自动生成
        backup_prefix:  备份文件前缀 (如 "nilm_ac_two_stage_"); None = 不写备份
        max_backups:    滚动保留的最大备份数
        backup_exclude: 集合, 滚动清理时豁免的文件名 (如主文件/历史对照文件)
        logger:         日志器 (可选)
    """
    bundle_path = Path(bundle_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, bundle_path)
    if logger is not None:
        logger.info(f"  ✓ 模型 bundle -> {bundle_path}  "
                    f"({bundle_path.stat().st_size / 1024:.1f} KB)")
    if backup_prefix:
        tag = backup_tag or datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = bundle_path.parent / f"{backup_prefix}{tag}.pkl"
        joblib.dump(bundle, backup)
        if logger is not None:
            logger.info(f"  ✓ 备份模型 -> {backup}")
        # 滚动清理: 仅保留最近 max_backups 份带时间戳的备份
        exclude = set(backup_exclude or set()) | {bundle_path.name}
        backups = sorted(
            [p for p in bundle_path.parent.glob(f"{backup_prefix}*.pkl")
             if p.name not in exclude],
            key=lambda p: p.stat().st_mtime, reverse=True,
        )
        if len(backups) > max_backups:
            for old in backups[max_backups:]:
                try:
                    size_kb = old.stat().st_size / 1024
                    old.unlink()
                    if logger is not None:
                        logger.info(f"  [清理] 删除旧备份 {old.name} ({size_kb:.1f} KB)")
                except Exception as e:
                    if logger is not None:
                        logger.warning(f"  [清理] 删除 {old.name} 失败: {e}")
    return bundle_path


def save_model_components(components=None, model_dir: Path = None,
                          meta: dict = None, meta_name: str = "model_meta.json",
                          logger=None) -> Path:
    """统一模型组件落盘接口 (组件 pkl 拆分 + 可选 meta JSON)."""
    components = components or {}
    model_dir = Path(model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)
    for fname, obj in components.items():
        joblib.dump(obj, model_dir / fname)
    if meta is not None:
        with open(model_dir / meta_name, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False, default=str)
    if logger is not None:
        names = ", ".join(sorted(components.keys())) or "(无组件)"
        logger.info(f"  ✓ 组件拆分 {names}" +
                    (f" + {meta_name}" if meta is not None else "") +
                    f" 已保存 -> {model_dir}")
    return model_dir


# ============================================================
# 单用户流水线: 模型资产检查/恢复 + 算法维度归档 + 顶层清理
# ============================================================
def check_algo_model_complete(algo_mod, ctx):
    """[v15] 按算法模块的 required_model_files 契约检查模型资产完整性.

    返回 (exists: bool, missing_files: list[str], model_dir: Path)
    """
    complete, missing, model_dir = algo_mod.check_model_complete(ctx)
    return complete, missing, model_dir


def restore_algo_models_to_top(algo_mod, ctx, model_dir: Path):
    """[v15] 把 models/<user_id>/<algo>/*.pkl + *.json 复制到 models/ 顶层.

    用途: 跳过训练复用旧模型时, 阶段脚本 (04/05) 默认从 models/ 顶层加载,
    所以推理/评估前先从该算法子目录把模型 "恢复" 到顶层.
    每个算法运行结束后由 cleanup_artifacts_top() 清掉, 保证算法间零污染.
    """
    top = ctx.project_root / "models"
    for f in model_dir.iterdir():
        if f.is_file() and (f.suffix == ".pkl" or f.suffix == ".json"):
            shutil.copy(f, top / f.name)


def archive_algo_outputs(project_root, output_dir, user_id, algo_mod, ctx,
                         has_inference: bool, did_train: bool = True):
    """[v15 算法解耦] 按算法维度归档单用户产物.

    新结构 (相对 project_root):
      models/<user_id>/<algo>/            : 该算法全部模型 pkl + meta json
      artifacts/trains/<user_id>/<algo>/  : 该算法训练评估 metrics + 预测 + plots
      artifacts/infers/<user_id>/<algo>/  : 该算法推理 metrics + 预测 + plots
      logs/<user_id>/                     : 本次运行的所有 .log (算法共享)
    """
    algo = algo_mod.artifact_subdir()
    # 1. 归档模型 -> models/<user_id>/<algo>/ (仅 did_train=True 时)
    if did_train:
        models_src = project_root / "models"
        models_dst = project_root / "models" / user_id / algo
        models_dst.mkdir(parents=True, exist_ok=True)
        for f in models_src.glob("*"):
            if f.is_file():
                shutil.copy(f, models_dst / f.name)

    # 2. 归档日志 -> logs/<user_id>/ (算法共享, 重复拷贝幂等)
    logs_dst = project_root / "logs" / user_id
    logs_dst.mkdir(parents=True, exist_ok=True)
    for f in (project_root / "logs").glob("*.log"):
        shutil.copy(f, logs_dst / f.name)

    # 3. 分流 metrics / predictions / plots 到该算法的 trains|infers 子目录
    train_dst = output_dir / "trains" / user_id / algo
    if did_train:
        train_dst.mkdir(parents=True, exist_ok=True)
        # [v13 bug 修复] 本次训练成功 -> 清除该算法上次遗留的 skip_reason.json
        # 否则批量汇总 aggregate_metrics 会误判该算法为"软跳过"
        _stale_skip = train_dst / "skip_reason.json"
        if _stale_skip.exists():
            _stale_skip.unlink()
            print(f"  [archive] 清除 {algo} 上次遗留的 skip_reason.json (本次训练成功)")
    infer_dst = output_dir / "infers" / user_id / algo
    if has_inference:
        infer_dst.mkdir(parents=True, exist_ok=True)

    metrics_src = project_root / "artifacts" / "metrics"
    for f in metrics_src.glob("*.csv"):
        name = f.name.lower()
        if "inference" in name:
            if has_inference:
                shutil.copy(f, infer_dst / f.name)
        elif did_train:
            shutil.copy(f, train_dst / f.name)

    pred_src = project_root / "artifacts" / "predictions"
    for f in pred_src.glob("*.csv"):
        name = f.name.lower()
        if "inference" in name or "infer" in name:
            if has_inference:
                shutil.copy(f, infer_dst / f.name)
        elif did_train:
            shutil.copy(f, train_dst / f.name)

    arti = project_root / "artifacts"
    for f in arti.glob("*.png"):
        name = f.name.lower()
        if "inference" in name or "infer" in name:
            if has_inference:
                shutil.copy(f, infer_dst / f.name)
        elif did_train:
            shutil.copy(f, train_dst / f.name)

    # 4. 清理顶层临时产物 (保证下一个算法的运行环境干净)
    cleanup_artifacts_top(project_root)

    print(f"  [archive] 已归档 (算法={algo}):")
    if did_train:
        print(f"    model -> {project_root / 'models' / user_id / algo}")
        print(f"    train metrics -> {train_dst}")
    else:
        print(f"    model -> [复用] {project_root / 'models' / user_id / algo}")
        print(f"    train metrics -> [复用] {train_dst} (上次训练结果保留)")
    print(f"    logs  -> {logs_dst}")
    if has_inference:
        print(f"    infer metrics -> {infer_dst}")


def cleanup_artifacts_top(project_root):
    """[v9] 清理 artifacts/ 顶层临时产物 + models/ logs/ 中间状态

    保留:
      artifacts/<永久结构>/  (trains/, infers/, summary_*.csv 等)
      models/<user_id>/      (已归档的)
      logs/<user_id>/        (已归档的) 与 logs/_batch/ (批量日志)
    清除:
      artifacts/ 顶层所有文件 (含 aligned_15min.csv 等) + metrics/ predictions/ 子目录
      models/ 顶层 *.pkl 与 *.json
      logs/ 顶层 *.log
    """
    arti = project_root / "artifacts"
    # [v13.17] 白名单: 这些顶层文件是批量层持久化状态, 不能被单用户 pipeline 清掉
    # [v15 算法解耦] aligned_15min.csv / feature_corr_with_ac.csv / skip_reason.json
    # 为多算法共享执行期状态: 算法逐个执行期间必须保留 (后序算法训练/评估仍要读),
    # 由流水线在全部算法跑完后统一收尾清理.
    _CLEANUP_WHITELIST = {
        "batch_execution_state.csv",           # v13.17 断点续跑状态
        "batch_execution_state.csv.tmp",       # 原子写中间文件 (若崩溃残留)
        "batch_run_summary.csv",               # v9 批量执行汇总
        "summary_metrics_all_users.csv",       # v9 指标汇总
        "skipped_users.csv",                   # 软跳过汇总
        "aligned_15min.csv",                   # [v15] 多算法共享对齐数据 (收尾清理)
        "feature_corr_with_ac.csv",            # [v15] 多算法共享相关性表 (收尾清理)
        "skip_reason.json",                    # [v15] 多算法共享跳过状态 (收尾清理)
        ".gitkeep",
    }
    # 顶层文件
    for f in arti.glob("*"):
        if f.is_file():
            if f.name in _CLEANUP_WHITELIST:
                continue   # [v13.17] 保护批量层持久化文件
            f.unlink()
        elif f.is_dir() and f.name in ("metrics", "predictions"):
            shutil.rmtree(f)
    # 重建空骨架
    (arti / "metrics").mkdir(exist_ok=True)
    (arti / "predictions").mkdir(exist_ok=True)
    (arti / ".gitkeep").touch()
    # models/ 顶层临时模型 (子目录如 <user_id>/ 保留)
    for f in (project_root / "models").glob("*"):
        if f.is_file():
            f.unlink()
    # logs/ 顶层临时日志 (子目录如 <user_id>/, _batch/ 保留)
    for f in (project_root / "logs").glob("*"):
        if f.is_file():
            f.unlink()


# ============================================================
# 批量层: 断点续跑执行状态 (v13.17)
# ============================================================
_EXECUTION_STATE_CSV_NAME = "batch_execution_state.csv"
_EXECUTION_STATE_COLS = ["user_id", "status", "success",
                         "started_at", "finished_at", "duration_s",
                         "message", "target_col", "algorithms", "run_id"]


def _execution_state_path(output_dir) -> "Path":
    """返回状态 CSV 的路径 (统一在 output_dir 根下)."""
    return Path(output_dir) / _EXECUTION_STATE_CSV_NAME


def _load_execution_state(output_dir, logger_print=None) -> "pd.DataFrame":
    """[v13.17] 读取批量执行状态 CSV.

    返回 DataFrame; 若文件不存在, 返回带列头的空 DataFrame (不抛异常).
    若文件损坏 (JSON/CSV 解析失败), 打印 WARN 后返回空表 (走全部重跑).
    """
    p = _execution_state_path(output_dir)
    if not p.exists():
        if logger_print:
            logger_print(f"  [v13.17 续跑] 状态文件不存在: {p} -> 全部用户重新执行")
        return pd.DataFrame(columns=_EXECUTION_STATE_COLS)
    try:
        df = pd.read_csv(p, encoding="utf-8-sig")
        # 兼容性检查: 若缺关键列, 视为损坏
        for c in ["user_id", "status"]:
            if c not in df.columns:
                if logger_print:
                    logger_print(f"  [v13.17 续跑] 状态文件缺列 {c!r}, 视为损坏 -> 全部重跑")
                return pd.DataFrame(columns=_EXECUTION_STATE_COLS)
        # 补齐可能缺失的新列 (向后兼容旧格式)
        for c in _EXECUTION_STATE_COLS:
            if c not in df.columns:
                df[c] = ""
        if logger_print:
            done_users = df[df["status"].isin(["ok", "soft_skip"])]["user_id"].tolist()
            logger_print(f"  [v13.17 续跑] 已加载状态文件: {p}")
            logger_print(f"  [v13.17 续跑] 历史记录 {len(df)} 行, "
                         f"已完成 (ok/soft_skip) {len(done_users)} 用户")
        return df
    except Exception as e:
        if logger_print:
            logger_print(f"  [v13.17 续跑] 状态文件读取失败 ({e!r}), 视为损坏 -> 全部重跑")
        return pd.DataFrame(columns=_EXECUTION_STATE_COLS)


def _get_completed_users(state_df, retry_failed: bool = True) -> set:
    """[v13.17] 从状态 DataFrame 提取已完成用户集合.

    Args:
        state_df:     _load_execution_state() 返回的 DataFrame
        retry_failed: True (默认): fail 用户重跑, 只跳 ok/soft_skip
                      False: fail 也跳过 (需手工删行才重试)

    Returns:
        set[str] 应跳过的 user_id 集合
    """
    if state_df is None or len(state_df) == 0:
        return set()
    if retry_failed:
        keep = state_df[state_df["status"].isin(["ok", "soft_skip"])]
    else:
        keep = state_df[state_df["status"].isin(["ok", "soft_skip", "fail"])]
    return set(keep["user_id"].astype(str).tolist())


def _upsert_execution_state(output_dir, row: dict, logger_print=None) -> None:
    """[v13.17] 原子写: 追加/更新单行到状态 CSV.

    - 若 user_id 已存在, 更新对应行 (支持重跑覆盖)
    - 用 .tmp + os.replace() 原子替换, 避免中断时 CSV 损坏
    - 每个用户跑完立即调用, 保证崩溃时最多丢当前正在跑的用户
    """
    p = _execution_state_path(output_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    # 载入现有 (若有)
    if p.exists():
        try:
            df = pd.read_csv(p, encoding="utf-8-sig")
        except Exception:
            df = pd.DataFrame(columns=_EXECUTION_STATE_COLS)
    else:
        df = pd.DataFrame(columns=_EXECUTION_STATE_COLS)
    # 补齐所有列
    for c in _EXECUTION_STATE_COLS:
        if c not in df.columns:
            df[c] = ""
    # 保证 row 字段齐全
    for c in _EXECUTION_STATE_COLS:
        row.setdefault(c, "")
    # upsert (删旧行 + append 新行)
    df = df[df["user_id"].astype(str) != str(row["user_id"])]
    new_row = pd.DataFrame([row])[_EXECUTION_STATE_COLS]
    if len(df) == 0:
        # 空 df + concat 会触发 pandas 3.0 FutureWarning; 直接用 new_row
        df = new_row
    else:
        df = pd.concat([df, new_row], ignore_index=True)
    # 原子写: 先写 .tmp 再 os.replace
    tmp = p.with_suffix(p.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(str(tmp), str(p))
    if logger_print:
        logger_print(f"    [v13.17 状态] {row['user_id']}: {row['status']} -> {p.name}")


# ============================================================
# 批量层: 软跳过汇总 + 指标聚合 (v15 算法维度)
# ============================================================
def collect_skip_reasons(output_dir: Path, summary_dir: Path):
    """[v9/v15] 收集所有用户 × 算法的 skip_reason.json 汇总成 CSV

    v15 新布局: 扫描 artifacts/trains/<user_id>/<algo>/skip_reason.json (软跳过
    属训练阶段失败, 按算法隔离), 汇总成 artifacts/skipped_users.csv (新增 algo 列).
    旧扁平布局 (trains/<user_id>/skip_reason.json) 仅在用户无任何 per-algo 记录时读取.
    """
    import re as _re
    from algorithms.registry import ALGORITHM_NAMES
    _USER_DIR_RE = _re.compile(r"^\d+_\d+$")
    train_root = output_dir / "trains"
    rows = []
    if not train_root.exists():
        return None, 0
    for user_dir in sorted(train_root.iterdir()):
        if not user_dir.is_dir() or not _USER_DIR_RE.match(user_dir.name):
            continue
        # 1. 新布局: per-algo skip_reason.json
        per_algo_rows = []
        for algo_dir in sorted(user_dir.iterdir()):
            if not algo_dir.is_dir() or algo_dir.name not in ALGORITHM_NAMES:
                continue
            skip_f = algo_dir / "skip_reason.json"
            if not skip_f.exists():
                continue
            try:
                info = json.loads(skip_f.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"  [WARN] 读取 {skip_f} 失败: {e}")
                continue
            row = {"user_id": user_dir.name, "algo": algo_dir.name}
            row.update(info)
            per_algo_rows.append(row)
        if per_algo_rows:
            rows += per_algo_rows
            continue
        # 2. 旧扁平布局兼容 (仅当该用户无任何 per-algo 记录)
        flat_f = user_dir / "skip_reason.json"
        if not flat_f.exists():
            continue
        try:
            info = json.loads(flat_f.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [WARN] 读取 {flat_f} 失败: {e}")
            continue
        row = {"user_id": user_dir.name, "algo": "flat"}
        row.update(info)
        rows.append(row)
    if not rows:
        return None, 0
    # 列顺序: user_id, algo, skip_reason, detail, 其余字段按出现顺序
    fixed = ["user_id", "algo", "skip_reason", "detail"]
    other = []
    for r in rows:
        for k in r.keys():
            if k not in fixed and k not in other:
                other.append(k)
    cols = fixed + other
    df = pd.DataFrame(rows)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    df = df[cols]
    out = summary_dir / "skipped_users.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return out, len(df)


def aggregate_metrics(output_dir: Path, summary_dir: Path):
    """[v15 算法维度] 汇总所有用户 × 算法的指标到 summary_metrics_all_users.csv

    v15 新目录结构 (算法维度子目录):
      output_dir (= artifacts/) 下:
        trains/<user_id>/<algo>/{train_val_metrics.csv, test_metrics.csv, skip_reason.json, ...}
        infers/<user_id>/<algo>/{inference_metrics.csv, ...}
    兼容旧扁平布局 (algo 列记 "flat"):
        trains/<user_id>/{train_val_metrics.csv, ...}

    输出: artifacts/summary_metrics_all_users.csv
      每用户 × 每算法 4 行 (stage = train / val / test / inference):
        主模型类算法 (main/v14) 优选 model: main (train/val/test) / main_final (inference)
        rf 算法优选 model: rf
      列: user_id, algo, stage, status, Accuracy, Precision, Recall, F1, AUC,
          TN, FP, FN, TP, MAE_W, RMSE_W, SAE, NDE,
          kWh_true, kWh_pred, kWh_err, n_samples

    软跳过算法 4 行均为占位 (指标 NaN, status='soft_skip:<reason>'),
    无推理用户的 inference 行为占位 (status='no_inference').
    """
    import re as _re
    from algorithms.registry import ALGORITHM_NAMES
    summary_dir.mkdir(parents=True, exist_ok=True)

    # ---- 列定义 ----
    METRIC_COLS = [
        "Accuracy", "Precision", "Recall", "F1", "AUC",
        "TN", "FP", "FN", "TP",
        "MAE_W", "RMSE_W", "SAE", "NDE",
        "kWh_true", "kWh_pred", "kWh_err", "n_samples",
    ]
    HEADER_COLS = ["user_id", "algo", "stage", "status"] + METRIC_COLS
    INT_COLS = {"TN", "FP", "FN", "TP", "n_samples"}

    # 各 stage 的源 CSV 与所在子目录
    # (stage_key, parent_subdir, src_csv_name, split_val_in_csv)
    STAGE_PLAN = [
        ("train",     "trains", "train_val_metrics.csv", "train"),
        ("val",       "trains", "train_val_metrics.csv", "val"),
        ("test",      "trains", "test_metrics.csv",      "test"),
        ("inference", "infers", "inference_metrics.csv", "inference"),
    ]
    # 各算法模型优选顺序 (train/val/test 与 inference 分开)
    _ALGO_MODEL_PREF = {
        "main": {"tvt": ["main"],                "inf": ["main_final", "main"]},
        "v14":  {"tvt": ["main"],                "inf": ["main_final", "main"]},
        "rf":   {"tvt": ["rf"],                  "inf": ["rf"]},
        "flat": {"tvt": ["main"],                "inf": ["main_final", "main"]},
    }

    def _empty_row(uid: str, algo: str, stage: str, status: str) -> dict:
        row = {c: None for c in HEADER_COLS}
        row["user_id"] = uid
        row["algo"] = algo
        row["stage"] = stage
        row["status"] = status
        return row

    # 收集所有用户 id (取 trains/ 与 infers/ 子目录并集)
    _USER_DIR_RE = _re.compile(r"^\d+_\d+$")
    train_root = output_dir / "trains"
    infer_root = output_dir / "infers"
    all_users = set()
    for root in (train_root, infer_root):
        if root.exists():
            for d in root.iterdir():
                if d.is_dir() and _USER_DIR_RE.match(d.name):
                    all_users.add(d.name)

    rows = []
    src_cache: dict = {}  # (user_id, algo, parent_subdir, src_csv) -> DataFrame or None

    def _read_metrics_csv(uid: str, algo: str, parent_subdir: str, src_csv_name: str):
        key = (uid, algo, parent_subdir, src_csv_name)
        if key in src_cache:
            return src_cache[key]
        if algo == "flat":
            f = output_dir / parent_subdir / uid / src_csv_name
        else:
            f = output_dir / parent_subdir / uid / algo / src_csv_name
        if not f.exists():
            src_cache[key] = None
            return None
        try:
            src_cache[key] = pd.read_csv(f)
        except Exception as e:
            print(f"  [WARN] {uid}/{algo}: 读取 {f.name} 失败: {e}")
            src_cache[key] = None
        return src_cache[key]

    def _discover_user_algos(uid: str):
        """返回 [(algo, skip_reason_or_None), ...] (新布局 per-algo; 旧布局 flat)."""
        entries = []
        t_dir = train_root / uid
        if t_dir.exists():
            found_per_algo = False
            for d in sorted(t_dir.iterdir()):
                if d.is_dir() and d.name in ALGORITHM_NAMES:
                    found_per_algo = True
                    skip = None
                    sf = d / "skip_reason.json"
                    if sf.exists():
                        try:
                            skip = json.loads(sf.read_text(encoding="utf-8")) \
                                .get("skip_reason", "skipped")
                        except Exception:
                            skip = "skipped"
                    entries.append((d.name, skip))
            if not found_per_algo:
                # 旧扁平布局兼容
                skip = None
                flat_sf = t_dir / "skip_reason.json"
                if flat_sf.exists():
                    try:
                        skip = json.loads(flat_sf.read_text(encoding="utf-8")) \
                            .get("skip_reason", "skipped")
                    except Exception:
                        skip = "skipped"
                entries.append(("flat", skip))
        # infers 侧算法目录补充 (仅推理产出的算法)
        i_dir = infer_root / uid
        if i_dir.exists():
            for d in sorted(i_dir.iterdir()):
                if d.is_dir() and d.name in ALGORITHM_NAMES \
                        and not any(a == d.name for a, _ in entries):
                    entries.append((d.name, None))
        if not entries:
            entries.append(("flat", None))
        return entries

    for user_id in sorted(all_users):
        for algo, skip_reason in _discover_user_algos(user_id):
            pref = _ALGO_MODEL_PREF.get(algo, _ALGO_MODEL_PREF["flat"])
            for stage, parent_subdir, src_csv, split_val in STAGE_PLAN:
                # 软跳过算法: 全 4 stage 都是占位
                if skip_reason is not None:
                    rows.append(_empty_row(user_id, algo, stage, f"soft_skip:{skip_reason}"))
                    continue

                df = _read_metrics_csv(user_id, algo, parent_subdir, src_csv)
                if df is None or len(df) == 0:
                    # 没源 csv: 训练阶段 = no_train_metrics, 推理阶段 = no_inference
                    placeholder = ("no_inference" if parent_subdir == "infers"
                                   else f"no_{stage}_metrics")
                    rows.append(_empty_row(user_id, algo, stage, placeholder))
                    continue
                if "split" not in df.columns or "model" not in df.columns:
                    rows.append(_empty_row(user_id, algo, stage, f"bad_{stage}_csv"))
                    continue
                df_s = df[df["split"] == split_val]
                if len(df_s) == 0:
                    rows.append(_empty_row(user_id, algo, stage, f"no_{stage}_rows"))
                    continue

                # 按算法模型优选顺序找
                model_pref = pref["inf"] if stage == "inference" else pref["tvt"]
                chosen = None
                chosen_model = None
                for m in model_pref:
                    sub = df_s[df_s["model"] == m]
                    if len(sub) > 0:
                        chosen = sub
                        chosen_model = m
                        break
                if chosen is None:
                    first_model = df_s["model"].iloc[0]
                    chosen = df_s[df_s["model"] == first_model]
                    chosen_model = first_model

                row = _empty_row(user_id, algo, stage, f"ok:{chosen_model}")
                for _, r in chosen.iterrows():
                    mname = r.get("metric")
                    mval = r.get("value")
                    if mname in METRIC_COLS:
                        row[mname] = mval
                rows.append(row)

    if not rows:
        return []

    df_all = pd.DataFrame(rows)[HEADER_COLS]
    for c in INT_COLS:
        try:
            df_all[c] = pd.to_numeric(df_all[c], errors="coerce").astype("Int64")
        except Exception:
            pass
    out = summary_dir / "summary_metrics_all_users.csv"
    df_all.to_csv(out, index=False, encoding="utf-8-sig")
    return [("summary_metrics_all_users.csv", len(df_all), out)]
