# -*- coding: utf-8 -*-
"""
单用户端到端流水线 (v6.12.6+v6.15.0 + v15 多算法解耦): 训练 + 评估 + 推理 + 指标归档
用法:
  python scripts/run_user_pipeline.py \
    --user-id user1 \
    --target-col p1 \
    --train-bus /path/train_bus.csv \
    --train-branch /path/train_branch.csv \
    --infer-bus /path/infer_bus.csv \
    --infer-branch /path/infer_branch.csv \
    --output-dir /path/output_user1 \
    --algorithms main,rf --algo-mode all

[v15 多算法重构]:
  1. 数据准备 (02 对齐 / 分析) 与算法执行完全解耦: 02 只在任一算法需要训练时跑一次
  2. 按 --algorithms / --algo-mode 解析的算法序列逐个执行 (single/multi/all 三种模式),
     每个算法通过 scripts/algorithms/ 统一接口构建 训练->评估->推理 命令与隔离环境
  3. 产物按算法维度隔离归档:
       models/<user_id>/<algo>/          模型资产
       artifacts/trains/<user_id>/<algo>/ 训练评估 metrics + 预测 + plots
       artifacts/infers/<user_id>/<algo>/ 推理 metrics + 预测 + plots
  4. 算法间故障隔离: 单算法软跳过/硬失败不阻塞其他算法; 退出码 0=≥1 成功,
     10=全部软跳过, 1=无算法成功

v6.12.6+v6.15.0 优雅降级 (保留):
  --infer-bus / --infer-branch 为可选参数:
    - 无推理总线: 跳过 05 推理, 仅完成训练/验证/测试
    - 无推理分路: 跑 05 仅产出预测 CSV, 无评估指标
"""
import argparse, sys, subprocess, shutil, json, os
from pathlib import Path

import pandas as pd
import numpy as np

# Windows GBK 控制台兼容: 强制 stdout/stderr 用 UTF-8
# 否则 print("STEP: 05 推理 — 跳过") 等含全角破折号的语句会抛 UnicodeEncodeError
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 添加 scripts 目录到 path 以便后续 import
sys.path.insert(0, str(Path(__file__).resolve().parent))


def patch_common(target_col: str):
    """临时修改 common.py 的 TARGET_COL (备份原文件)"""
    common_path = Path(__file__).resolve().parent / "common.py"
    backup_path = common_path.with_suffix(".py.bak")
    if not backup_path.exists():
        shutil.copy(common_path, backup_path)
    content = backup_path.read_text(encoding="utf-8")
    # 替换 TARGET_COL
    import re
    new_content = re.sub(
        r'TARGET_COL\s*=\s*"\w+"',
        f'TARGET_COL = "{target_col}"',
        content, count=1
    )
    common_path.write_text(new_content, encoding="utf-8")
    print(f"  [patch] TARGET_COL -> '{target_col}'")


def restore_common():
    common_path = Path(__file__).resolve().parent / "common.py"
    backup_path = common_path.with_suffix(".py.bak")
    if backup_path.exists():
        shutil.copy(backup_path, common_path)
        backup_path.unlink()
        print(f"  [restore] common.py 已恢复")


def setup_user_data(user_id, train_bus, train_branch, project_root,
                    extra_train_bus="", extra_train_branch="", extra_train_dates="",
                    clean_labels=False, clean_d87_thr=50.0, target_col="p1"):
    """把用户的训练数据复制为 data/merged_bus.csv + merged_branch.csv

    v6.14 新增:
      - 增量训练: 合并 extra_train_bus/branch (可指定日期窗口 extra_train_dates)
      - 标签清洗: 用 d87 启动信号确定空调真实起点, 启动前小负荷归 0
    """
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    bus_dst = data_dir / "merged_bus.csv"
    br_dst = data_dir / "merged_branch.csv"

    # 1. 加载基础训练数据
    bus = pd.read_csv(train_bus)
    br = pd.read_csv(train_branch)
    print(f"  [data] 基础训练: bus {bus.shape}, br {br.shape}")

    # 2. v6.14 增量训练: 合并额外训练数据
    if extra_train_bus and extra_train_branch and Path(extra_train_bus).exists():
        extra_bus = pd.read_csv(extra_train_bus)
        extra_br = pd.read_csv(extra_train_branch)
        # 限制额外日期
        if extra_train_dates.strip():
            extra_dates = [pd.Timestamp(d.strip()).date()
                           for d in extra_train_dates.split(",") if d.strip()]
            extra_bus["event_time"] = pd.to_datetime(extra_bus["event_time"])
            extra_br["time"] = pd.to_datetime(extra_br["time"])
            extra_bus_mask = extra_bus["event_time"].dt.date.isin(extra_dates)
            extra_br_mask = extra_br["time"].dt.date.isin(extra_dates)
            extra_bus = extra_bus[extra_bus_mask].reset_index(drop=True)
            extra_br = extra_br[extra_br_mask].reset_index(drop=True)
            print(f"  [v6.14 增量] 额外训练日期 {extra_dates}: bus {extra_bus.shape}, br {extra_br.shape}")
        # 取公共列再合并
        common_bus_cols = list(set(bus.columns) & set(extra_bus.columns))
        common_bus_cols = [c for c in bus.columns if c in common_bus_cols]
        bus = pd.concat([bus[common_bus_cols], extra_bus[common_bus_cols]],
                        ignore_index=True)
        common_br_cols = list(set(br.columns) & set(extra_br.columns))
        common_br_cols = [c for c in br.columns if c in common_br_cols]
        br = pd.concat([br[common_br_cols], extra_br[common_br_cols]],
                       ignore_index=True)
        print(f"  [v6.14 增量] 合并后: bus {bus.shape}, br {br.shape}")

    # 3. v6.14 标签清洗
    if clean_labels:
        sys.path.insert(0, str(project_root / "scripts"))
        from label_cleaner import clean_branch_labels
        print(f"  [v6.14 清洗] 应用 d87 启动签名标签清洗 (阈值 {clean_d87_thr})")
        br, report = clean_branch_labels(bus, br, target_col,
                                          d87_startup_thr=clean_d87_thr)
        print(f"  [v6.14 清洗] 报告: {report}")

    # 4. 写入磁盘
    bus.to_csv(bus_dst, index=False, encoding="utf-8-sig")
    print(f"  [data] bus  -> {bus_dst} ({bus.shape})")
    br.to_csv(br_dst, index=False, encoding="utf-8-sig")
    print(f"  [data] br   -> {br_dst} ({br.shape})")


def setup_infer_data(infer_bus, infer_branch, project_root):
    """把用户推理数据复制到 data/infer_bus.csv + data/infer_branch.csv

    设计动机 (v6.12.6+v6.15.0):
      训推路径完全分离 -- 训练用 merged_bus.csv, 推理用 infer_bus.csv
      避免 "推理数据覆盖训练数据" 的隐患, 也让 inference_result 中 bus_csv
      字段始终是稳定的 infer_bus.csv 便于审计
    """
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    bus_dst = data_dir / "infer_bus.csv"
    br_dst  = data_dir / "infer_branch.csv"

    bus = pd.read_csv(infer_bus)
    bus.to_csv(bus_dst, index=False, encoding="utf-8-sig")
    print(f"  [infer-data] bus -> {bus_dst} ({bus.shape})")

    if infer_branch and Path(infer_branch).exists():
        br = pd.read_csv(infer_branch)
        br.to_csv(br_dst, index=False, encoding="utf-8-sig")
        print(f"  [infer-data] br  -> {br_dst} ({br.shape})")
        return str(bus_dst), str(br_dst)
    else:
        print(f"  [infer-data] br  -> 无 (推理仅总线)")
        return str(bus_dst), None


def run_analyze_step(stage: str, br_csv: str, target_col: str, on_thr_w: float,
                     out_dir: Path, project_root: Path,
                     date_labels: dict = None,
                     phase: str = "pre",
                     bus_csv: str = None,
                     time_filter_spec: str = None) -> None:
    """[v13.6 / v13.10 / v13.17] 训练/推理阶段的分路开机时段分析 (集成 analyze_on_periods.py)

    v13.6 首版: 训练前 + 推理前各跑一次 (无 dataset 归属列)
    v13.10 增强: 支持 date_labels 传入, 输出 CSV 追加 dataset 列 (归属训练集/验证集/测试集/未使用/推理已用/推理已排除)
    v13.17 增强: 支持 bus_csv 传入, daily CSV 追加 n_bus_raw / n_branch_raw 2 列 (与
                v13.16-daily_raw 同名同义). time_filter_spec 用于让统计口径与
                实际用到的天数一致.

    Args:
        stage:        "train" or "infer" (用于文件名前缀 + 日志)
        br_csv:       分路 CSV 路径 (原始训练/推理分路, 不是 merged_*.csv)
        target_col:   目标列名 (如 p1, p2)
        on_thr_w:     ON 阈值 (W, 与训练评估同口径)
        out_dir:      输出目录 (会自动 mkdir -p)
        project_root: 项目根 (用于定位 scripts/)
        date_labels:  [v13.10] dict {"yyyy-mm-dd": "train"/"val"/"test"/"未使用"/"used"/"excluded"}
                      不传 = v13.6 老行为, 不加 dataset 列
        phase:        [v13.10] "pre" (训练/推理前跑, 数据视图) or "post" (训练后跑, 有归属信息)
        bus_csv:      [v13.17] 总线 CSV 路径 (可选). 传入后 daily CSV 会追加
                      n_bus_raw 列 (当天总线原始采样点数). 不传 -> 该列不输出
        time_filter_spec: [v13.17] JSON 字符串, 若传入则应用 time_filter 过滤
                          原始点统计. 【设计建议】analyze 场景默认应**不传**,
                          让 n_bus_raw/n_branch_raw 反映真实每天原始采集完整性
                          (与 daily_metrics 的"参与训练/推理"视角互补).
    """
    assert stage in ("train", "infer"), f"stage 必须 train/infer, 收到 {stage!r}"
    ver = "v13.10" if date_labels is not None else "v13.6"
    phase_desc = "训练后" if phase == "post" else ("推理前" if stage == "infer" else "训练前")
    print(f"\n{'='*70}\n  STEP: {stage.upper()} {phase_desc}分路开机时段分析 ({ver})\n{'='*70}")

    if not br_csv or not Path(br_csv).exists():
        print(f"  [SKIP] 分路 CSV 不存在或未提供: {br_csv!r}")
        return

    try:
        # 复用 analyze_on_periods 的核心函数, 避免 subprocess 开销
        sys.path.insert(0, str(project_root / "scripts"))
        from analyze_on_periods import compute_on_periods, compute_daily_summary
        import pandas as _pd

        df = _pd.read_csv(br_csv)
        print(f"  [analyze] 读取 {br_csv} ({len(df)} 行, 列={df.columns.tolist()})")
        print(f"  [analyze] target_col={target_col}, on_thr_w={on_thr_w:.2f} W")
        if date_labels is not None:
            _labels_summary = {}
            for v in date_labels.values():
                _labels_summary[v] = _labels_summary.get(v, 0) + 1
            print(f"  [analyze v13.10] date_labels 归属分布: {_labels_summary}")

        periods = compute_on_periods(df, target_col, float(on_thr_w), split_by_day=True,
                                     date_labels=date_labels)

        # [v13.17] 计算原始采集点数 (总线+分路), 用于给 daily CSV 加 n_bus_raw / n_branch_raw
        _bus_counts = None
        _br_counts = None
        try:
            from metrics_utils import compute_raw_daily_counts
            # 分路计数总是可算 (br_csv 就是本函数入参)
            _br_counts = compute_raw_daily_counts(
                br_csv, "time",
                time_filter_spec=time_filter_spec,
                logger=None)
            # 总线计数仅当 bus_csv 提供时算
            if bus_csv and Path(bus_csv).exists():
                _bus_counts = compute_raw_daily_counts(
                    bus_csv, "event_time",
                    time_filter_spec=time_filter_spec,
                    logger=None)
                print(f"  [v13.17] 每日采集点统计: 总线 {len(_bus_counts)} 天, "
                      f"分路 {len(_br_counts)} 天")
            else:
                print(f"  [v13.17] 每日采集点统计: 分路 {len(_br_counts)} 天 "
                      f"(未提供 bus_csv, n_bus_raw 列不输出)")
        except Exception as _e:
            print(f"  [v13.17 WARN] compute_raw_daily_counts 失败: {_e} — "
                  f"daily CSV 不含 n_bus_raw/n_branch_raw 2 列")
            _bus_counts, _br_counts = None, None

        daily = compute_daily_summary(periods, target_col, date_labels=date_labels,
                                       bus_daily_counts=_bus_counts,
                                       branch_daily_counts=_br_counts)

        out_dir.mkdir(parents=True, exist_ok=True)
        periods_path = out_dir / f"{stage}_on_periods.csv"
        daily_path   = out_dir / f"{stage}_on_periods_daily.csv"
        periods.to_csv(periods_path, index=False, encoding="utf-8-sig")
        daily.to_csv(daily_path, index=False, encoding="utf-8-sig")

        n_seg = len(periods)
        total_h = float(periods["duration_min"].sum()) / 60.0 if n_seg else 0.0
        total_e = float(periods["energy_kwh"].sum()) if n_seg else 0.0
        print(f"  [OK] {n_seg} 段 ON / {len(daily)} 天 / 累计 {total_h:.2f} 小时 / 用电 {total_e:.3f} kWh")
        print(f"  [OK] 段级明细 -> {periods_path}")
        print(f"  [OK] 每日汇总 -> {daily_path}")

        # [v13.10] 打印 dataset 归属分布 (若有)
        if date_labels is not None and "dataset" in daily.columns:
            counts = daily["dataset"].value_counts().to_dict()
            print(f"  [OK] dataset 归属分布 (按天): {counts}")
    except Exception as e:
        # 分析失败不阻塞主流程 (analyze 是辅助报告, 不是关键路径)
        import traceback
        print(f"  [WARN] 分路开机时段分析失败, 忽略并继续主流程: {e}")
        print(f"  [WARN] 详细堆栈:")
        traceback.print_exc()


def _load_bundle_split_dates(project_root: Path,
                             bundle_name: str = "nilm_ac_two_stage.pkl") -> dict:
    """[v13.10/v15] 从 models/<bundle_name> 读 train_dates/val_dates/test_dates.

    03_train.py (v13.8+) 会把 3 个日期集合写入 bundle. 本函数读出并组装成
    date_labels: {"yyyy-mm-dd": "train"/"val"/"test"} 供 run_analyze_step 用.

    [v15 算法解耦] bundle_name 由算法模块的 bundle_file_name() 提供:
      主模型/v14 -> nilm_ac_two_stage.pkl, rf -> rf_bundle.pkl.

    未列在 3 集合中的日期会在 analyze 时显示为 "未使用" (通过 _build_train_date_labels).

    返回 None 表示 bundle 不存在或缺 train_dates 键 (旧模型/尚未训练).
    """
    bundle_path = project_root / "models" / bundle_name
    if not bundle_path.exists():
        return None
    try:
        import joblib
        b = joblib.load(bundle_path)
        return {
            "train": list(b.get("train_dates", []) or []),
            "val":   list(b.get("val_dates", []) or []),
            "test":  list(b.get("test_dates", []) or []),
        }
    except Exception:
        return None


def _build_train_date_labels(all_train_data_dates: list, bundle_split: dict) -> dict:
    """[v13.10] 组装训练阶段 date_labels.

    输入:
      all_train_data_dates: 训练分路 CSV 中出现的所有自然日 (yyyy-mm-dd 列表)
      bundle_split: {"train": [...], "val": [...], "test": [...]} 各自的日期集合

    返回 dict: {日期: "train"/"val"/"test"/"未使用"}
        - 优先级: test > val > train (若一天被多集合覆盖, 按此顺序)
        - 未列日期标 "未使用"
    """
    train_set = set(bundle_split.get("train", []))
    val_set   = set(bundle_split.get("val", []))
    test_set  = set(bundle_split.get("test", []))
    labels = {}
    for d in all_train_data_dates:
        if d in test_set:
            labels[d] = "test"
        elif d in val_set:
            labels[d] = "val"
        elif d in train_set:
            labels[d] = "train"
        else:
            labels[d] = "未使用"
    return labels


def _build_infer_date_labels(all_infer_data_dates: list, infer_tf_spec_str: str) -> dict:
    """[v13.10] 组装推理阶段 date_labels.

    输入:
      all_infer_data_dates: 推理分路 CSV 中出现的所有自然日
      infer_tf_spec_str:    --infer-time-filter-spec 传入的 JSON 字符串 (可能为空)

    返回 dict: {日期: "used" / "excluded"}
      - 用 apply_time_filter 逻辑判断: 该日是否被 include/exclude 后保留在推理集
      - 若无过滤规格, 所有日都标 "used"
    """
    if not infer_tf_spec_str or not infer_tf_spec_str.strip():
        return {d: "used" for d in all_infer_data_dates}

    try:
        from time_filter_utils import cli_arg_to_spec
        import pandas as _pd
        spec = cli_arg_to_spec(infer_tf_spec_str)
        if spec is None:
            return {d: "used" for d in all_infer_data_dates}

        # 构造一个 dummy DataFrame 一次性判定所有日期
        dummy = _pd.DataFrame({"date": [_pd.Timestamp(d) for d in all_infer_data_dates]})
        dummy["date_str"] = [d for d in all_infer_data_dates]

        # 应用 include/exclude 语义 (逐日粒度)
        includes = spec.get("include", []) or []
        excludes = spec.get("exclude", []) or []

        labels = {}
        for d in all_infer_data_dates:
            ts = _pd.Timestamp(d)
            # 先 include 再 exclude
            if includes:
                in_incl = any(_pd.Timestamp(s) <= ts <= _pd.Timestamp(e) for s, e in includes)
                if not in_incl:
                    labels[d] = "excluded"
                    continue
            in_excl = any(_pd.Timestamp(s) <= ts <= _pd.Timestamp(e) for s, e in excludes)
            labels[d] = "excluded" if in_excl else "used"
        return labels
    except Exception:
        # 解析失败降级: 全 "used"
        return {d: "used" for d in all_infer_data_dates}


def _list_dates_in_branch_csv(br_csv: str) -> list:
    """[v13.10] 从分路 CSV 提取所有出现的自然日 (ISO yyyy-mm-dd)"""
    import pandas as _pd
    try:
        df = _pd.read_csv(br_csv, usecols=["time"])
        ts = _pd.to_datetime(df["time"], errors="coerce").dropna()
        return sorted(set(ts.dt.strftime("%Y-%m-%d")))
    except Exception:
        return []


def _filter_inference_metrics(project_root, eval_dates_str,
                              bundle_name: str = "nilm_ac_two_stage.pkl"):
    """v6.14/v15: 推理后处理 - 仅在指定日期窗口内重算指标 (避免数据泄漏)

    场景: --extra-train-dates 把推理段一部分加入了训练, 此时若要看模型在
          剩余日期 (从未训练过的) 上的真实泛化, 必须只算这些日期的指标

    [v15 算法解耦] bundle_name 由算法模块的 bundle_file_name() 提供 (rf 用 rf_bundle.pkl).
    """
    sys.path.insert(0, str(project_root / "scripts"))
    from metrics_utils import (compute_classification_metrics,
                               compute_regression_metrics,
                               flatten_metrics_to_rows,
                               save_metrics_csv)
    # [v13.5 bug 修复] 从 bundle 读 ON_THR (与训练标签一致), 避免用旧 common 值
    # 优先级: bundle.ON_THR > common.ON_THR_BUSINESS_W > 硬编码 50
    try:
        import joblib as _jl
        _bundle_path = project_root / "models" / bundle_name
        if _bundle_path.exists():
            _b = _jl.load(_bundle_path)
            ON_THR_BUSINESS_W = float(_b.get("ON_THR",
                                              _b.get("ON_THR_BUSINESS", 50.0)))
            print(f"  [v13.5] 评估过滤 ON 阈值 = {ON_THR_BUSINESS_W}W (从 bundle 读)")
        else:
            from common import ON_THR_BUSINESS_W
    except Exception as _e:
        try:
            from common import ON_THR_BUSINESS_W
        except ImportError:
            ON_THR_BUSINESS_W = 50.0

    eval_dates = [pd.Timestamp(d.strip()).date()
                  for d in eval_dates_str.split(",") if d.strip()]

    pred_csv = project_root / "artifacts" / "predictions" / "inference_result.csv"
    if not pred_csv.exists():
        print(f"  [v6.14 评估过滤] 推理结果不存在, 跳过")
        return

    df = pd.read_csv(pred_csv)
    df["time"] = pd.to_datetime(df["time"])
    mask = df["time"].dt.date.isin(eval_dates)
    df_eval = df[mask].reset_index(drop=True)

    print(f"\n  [v6.14 评估过滤] 限制评估日期 {eval_dates}")
    print(f"  [v6.14 评估过滤] 原始推理 {len(df)} 行 -> 评估 {len(df_eval)} 行")

    if "y_true_W" not in df_eval.columns:
        print(f"  [v6.14 评估过滤] 缺 y_true_W, 跳过 (无标签场景)")
        return

    y_true = df_eval["y_true_W"].values
    s_true = (y_true >= ON_THR_BUSINESS_W).astype(int)

    eval_metrics_rows = []
    pred_cols = [c for c in df_eval.columns if c.startswith("y_pred_W")]

    print(f"\n  [v6.14 评估过滤] 仅评估窗口 ({len(df_eval)} 步) 的指标:")
    print(f"  {'模型':22s}{'F1':>8}{'P':>8}{'R':>8}{'MAE_W':>9}{'SAE':>7}  kWh真/预    误差")
    print(f"  {'-'*90}")

    for col in pred_cols:
        model_name = col.replace("y_pred_W_", "")
        y_pred = df_eval[col].values
        s_pred = (y_pred >= ON_THR_BUSINESS_W).astype(int)
        cls = compute_classification_metrics(s_true, s_pred, y_pred)
        reg = compute_regression_metrics(y_true, y_pred)
        print(f"  {model_name:22s}{cls['F1']:>8.4f}{cls['Precision']:>8.4f}"
              f"{cls['Recall']:>8.4f}{reg['MAE_W']:>9.2f}{reg['SAE']*100:>7.2f}%"
              f"{reg['kWh_true']:>7.2f}/{reg['kWh_pred']:>7.2f}{reg['kWh_err']:>+9.2f}")

        # 同时写入独立的 inference_metrics_filtered.csv
        eval_metrics_rows += flatten_metrics_to_rows(
            "inference_filtered", model_name,
            cls_metrics=cls, reg_metrics=reg,
            extra={"note": f"v6.14 过滤评估窗口: {eval_dates_str}"}
        )

    filtered_csv = project_root / "artifacts" / "metrics" / "inference_metrics_filtered.csv"
    save_metrics_csv(eval_metrics_rows, filtered_csv, append=False)
    print(f"  [v6.14 评估过滤] 已保存 -> {filtered_csv}")


def run_step(cmd, name, project_root, extra_env=None):
    print(f"\n{'='*70}\n  STEP: {name}\n{'='*70}")
    print(f"  CMD: {' '.join(cmd)}")
    # v6.12.6+v6.15.0-graceful-v3 修复:
    #   Windows 默认 locale = GBK, subprocess.run(text=True) 会用 GBK 解码子进程 stdout,
    #   而子进程脚本本身打印中文 / 含 UTF-8 多字节字符 → 父端 _readerthread 抛
    #   UnicodeDecodeError, result.stdout 变成 None, 下游 .strip() 二次 AttributeError 崩溃.
    #   修复策略: 父端显式 encoding="utf-8" + errors="replace" (任何非 UTF-8 字节兜底为 ?,
    #   不再崩); 同时给子进程注入 PYTHONIOENCODING=utf-8 强制其 stdout 用 UTF-8 输出.
    sub_env = dict(os.environ)
    sub_env.setdefault("PYTHONIOENCODING", "utf-8")
    # [v15 算法解耦] 算法模块隔离环境: 只对本算法的子进程生效, 不污染其他算法
    if extra_env:
        sub_env.update(extra_env)
    try:
        result = subprocess.run(
            cmd, cwd=str(project_root / "scripts"),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            env=sub_env,
        )
    except FileNotFoundError as e:
        # Windows 常见: 硬编码 "python3" 会找不到 (应使用 sys.executable)
        print(f"  [FAIL] FileNotFoundError: {e}")
        print(f"     当前 Python 解释器: {sys.executable}")
        print(f"     建议: 用 sys.executable 替代硬编码 'python3' / 'python'")
        raise RuntimeError(f"Step {name} 启动失败: {e}")
    # None 防御: 即使将来 reader 线程仍因任何原因失败导致 stdout=None, 也不能再二次崩
    stdout_text = result.stdout if result.stdout is not None else ""
    stderr_text = result.stderr if result.stderr is not None else ""
    # ---------- [v6.12.6+v6.15.0-graceful-v5] 软跳过退出码 ----------
    # 03_train.py 的 3 个数据质量门: 11=对齐过少 / 12=单类 / 13=val/test 空
    # 此类退出非"错误", 而是数据本身不可训练 -> 抛 _SoftSkip 让上层做差异化处理
    if result.returncode in (11, 12, 13):
        # 打印最后 30 行 (含 [SKIP] 提示)
        tail = stdout_text.strip().split("\n")[-30:]
        print("\n".join(tail))
        raise _SoftSkip(code=result.returncode, step=name)
    if result.returncode != 0:
        print("STDOUT:", stdout_text[-2000:])
        print("STDERR:", stderr_text[-2000:])
        raise RuntimeError(f"Step {name} failed (code={result.returncode})")
    # 仅打印最后 30 行
    tail = stdout_text.strip().split("\n")[-30:]
    print("\n".join(tail))
    return stdout_text


class _SoftSkip(Exception):
    """数据质量门触发的软跳过 (非异常路径) - graceful-v5 引入"""
    def __init__(self, code: int, step: str):
        self.code = code
        self.step = step
        super().__init__(f"[SKIP code={code}] at step {step}")


def _v14_enabled_from_spec(v14_flags_spec: str) -> bool:
    """[v15] 从 --v14-flags JSON 字符串判断 v14 是否显式启用 (用于默认算法列表提示)."""
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
    # data/ 顶层 merged_*.csv / infer_*.csv 临时文件 (运行时由 setup_train_data 写入)
    # [v15 算法解耦] 执行期保留 (后序算法训练/推理仍要读), 由流水线收尾统一清理
    # data_dir = project_root / "data"
    # for fname in ("merged_bus.csv", "merged_branch.csv",
    #               "infer_bus.csv", "infer_branch.csv"):
    #     f = data_dir / fname
    #     if f.exists():
    #         f.unlink()


def run_algorithm_flow(algo_name, ctx, args, project_root, output_dir,
                       has_inference, infer_bus_dst, infer_br_dst,
                       effective_on_thr_w) -> str:
    """[v15 多算法重构] 执行单个算法的 训练/复用 -> 评估 -> 推理 -> 归档 流程.

    返回状态字符串:
      "ok"                  : 该算法全流程成功
      "soft_skip:<code>"    : 数据质量门触发 (软跳过, 不阻塞其他算法)
      "fail:<原因>"         : 真异常 (记录后继续其他算法, 保证算法间隔离)
    """
    from algorithms.registry import REGISTERED_ALGORITHMS
    algo_mod = REGISTERED_ALGORITHMS[algo_name]
    PY = sys.executable
    print(f"\n{'#'*70}\n  算法执行: [{algo_name}] {algo_mod.display_name}\n{'#'*70}")

    train_ok = False   # [v15] 训练+评估是否已成功 (05 失败时用于部分归档, 不丢弃训练产物)
    try:
        # ---- 3. 决定是否训练该算法 (按算法模型契约; --force-retrain 强制) ----
        model_ok, missing_files, model_dir = check_algo_model_complete(algo_mod, ctx)
        did_train = True
        if (not ctx.force_retrain) and model_ok:
            did_train = False
            print(f"\n{'='*70}\n  [v15] 跳过训练: 复用已有模型 (算法={algo_name})\n{'='*70}")
            print(f"  模型目录: {model_dir}")
            print(f"  完整性检查: {len(algo_mod.required_model_files)} 个必备文件存在")
            print(f"  (如需强制重训, 加 --force-retrain)")
            restore_algo_models_to_top(algo_mod, ctx, model_dir)
        else:
            if ctx.force_retrain and model_ok:
                print(f"\n  [v15] --force-retrain 已开启, 强制重训算法 {algo_name}")
            elif not model_ok:
                print(f"\n  [v15] 算法 {algo_name} 模型不完整, 需要训练")
                print(f"  模型目录: {model_dir}")
                print(f"  缺失文件: {missing_files}")
            run_step([PY, algo_mod.train_script] + algo_mod.train_args(ctx),
                     f"03 训练 [{algo_name}] ({algo_mod.display_name})",
                     project_root, extra_env=algo_mod.train_env(ctx))
            run_step([PY, algo_mod.eval_script] + algo_mod.eval_args(ctx),
                     f"04 评估 [{algo_name}] ({algo_mod.display_name})",
                     project_root, extra_env=algo_mod.eval_env(ctx))

            # [v13.10/v15] 训练完成后, 从该算法 bundle 读切分日期补跑训练 analyze
            if not args.skip_analyze:
                _bundle_split = _load_bundle_split_dates(
                    project_root, bundle_name=algo_mod.bundle_file_name(ctx))
                if _bundle_split is not None:
                    _all_train_dates = _list_dates_in_branch_csv(ctx.train_branch)
                    _train_labels = _build_train_date_labels(_all_train_dates, _bundle_split)
                    _train_analyze_out = output_dir / "trains" / ctx.user_id
                    run_analyze_step(
                        stage="train",
                        br_csv=ctx.train_branch,
                        target_col=ctx.target_col,
                        on_thr_w=effective_on_thr_w,
                        out_dir=_train_analyze_out,
                        project_root=project_root,
                        date_labels=_train_labels,
                        phase="post",
                        bus_csv=ctx.train_bus,
                    )
                else:
                    print(f"\n  [v13.10] 跳过训练后补跑 analyze: "
                          f"{algo_mod.bundle_file_name(ctx)} 未含 train_dates (旧模型?)")

        train_ok = True   # [v15] 训练+评估阶段完成

        # ---- 4. 该算法推理 (使用用户的推理数据) ----
        if has_inference:
            infer_cmd = [PY, algo_mod.infer_script, "--bus", infer_bus_dst]
            infer_cmd += algo_mod.infer_args(ctx)
            if infer_br_dst:
                infer_cmd += ["--branch", infer_br_dst]
            else:
                infer_cmd += ["--no-branch"]
            if ctx.infer_time_filter_spec.strip():
                infer_cmd += ["--time-filter-spec", ctx.infer_time_filter_spec]
            run_step(infer_cmd, f"05 推理 [{algo_name}] ({algo_mod.display_name})",
                     project_root, extra_env=algo_mod.infer_env(ctx))
            # v6.14 推理后处理: 若指定 --infer-eval-dates, 只算这些日期的指标
            if args.infer_eval_dates.strip():
                _filter_inference_metrics(
                    project_root, args.infer_eval_dates,
                    bundle_name=algo_mod.bundle_file_name(ctx))

        # ---- 5. 该算法归档 (按算法维度隔离) ----
        archive_algo_outputs(project_root, output_dir, ctx.user_id,
                             algo_mod, ctx, has_inference, did_train=did_train)
        return "ok"

    except _SoftSkip as ss:
        # [v15] 数据质量门触发: 仅该算法软跳过, 不阻塞其他算法
        print(f"\n{'='*70}\n  [SKIP] 算法 {algo_name} 数据质量门触发 ({ss})\n{'='*70}")
        try:
            skip_src = project_root / "artifacts" / "skip_reason.json"
            if skip_src.exists():
                algo_dst = output_dir / "trains" / ctx.user_id / algo_mod.artifact_subdir()
                algo_dst.mkdir(parents=True, exist_ok=True)
                shutil.copy(skip_src, algo_dst / "skip_reason.json")
                print(f"  [SKIP] 跳过原因已归档 -> {algo_dst / 'skip_reason.json'}")
            # 兼容: 同时写用户级扁平 skip_reason.json (旧批量层读这里)
            flat_dst = output_dir / "trains" / ctx.user_id
            flat_dst.mkdir(parents=True, exist_ok=True)
            if skip_src.exists():
                shutil.copy(skip_src, flat_dst / "skip_reason.json")
        except Exception as _e:
            print(f"  [SKIP WARN] 跳过原因归档失败: {_e}")
        cleanup_artifacts_top(project_root)
        return f"soft_skip:{ss.code}"

    except Exception as e:
        import traceback
        print(f"\n{'='*70}\n  [FAIL] 算法 {algo_name} 执行失败: {type(e).__name__}: {e}\n{'='*70}")
        traceback.print_exc()
        # [v15] 训练已成功而推理失败时, 部分归档训练侧产物 (不丢弃已训好的模型/指标)
        if train_ok:
            try:
                archive_algo_outputs(project_root, output_dir, ctx.user_id,
                                     algo_mod, ctx, has_inference=False,
                                     did_train=True)
            except Exception as _ae:
                print(f"  [FAIL WARN] 部分归档失败: {_ae}")
        # 硬失败不中断其他算法: 清理顶层临时产物, 保证下一个算法环境干净
        cleanup_artifacts_top(project_root)
        return f"fail:{type(e).__name__}:{e}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user-id", required=True)
    # [v13.4-fix] 从 choices=[p1,p2,p3,p4] 硬约束改为通用 pN 格式验证
    # (与 run_batch_users.py 里 re.fullmatch(r"p\d+") 分路列匹配正则一致)
    # 通过 type= 参数在 CLI 层校验, 非法值直接报错不进下游
    # [v13.16] 再放宽支持 "p1+p2" / "p1+p2+p3" 复合列语义
    def _validate_target_col(s):
        import re as _re, argparse as _ap
        # 去所有空白 + 统一小写 (允许 "P1 + p2" / "p1+p2" 等)
        s = "".join(str(s).split()).lower()
        if not _re.fullmatch(r"p\d+(\+p\d+)*", s):
            raise _ap.ArgumentTypeError(
                f"--target-col={s!r} 不符合格式. "
                f"合法: 'pN' 或 'pA+pB[+pC...]' (N 为 ≥0 整数). "
                f"例: p1 / p2 / p1+p2 / p1+p2+p3 / p0+p5+p10"
            )
        # 复合列防呆: 分量去重 (p1+p1 无意义)
        if "+" in s:
            parts = s.split("+")
            if len(set(parts)) != len(parts):
                raise _ap.ArgumentTypeError(
                    f"--target-col={s!r} 含重复分量 (如 p1+p1), 语义无意义"
                )
        return s
    ap.add_argument("--target-col", required=True, type=_validate_target_col,
                    help="目标分路列名. 格式 'pN' (N ≥ 0 整数) 或 "
                         "[v13.16] 复合 'pA+pB[+pC...]'. "
                         "例: p1 / p2 / p1+p2 / p1+p2+p3 均合法. "
                         "复合语义: 加载分路 CSV 时新增列, 值 = 各分量按行求和")
    ap.add_argument("--train-bus", required=True)
    ap.add_argument("--train-branch", required=True)
    ap.add_argument("--infer-bus",    default="",
                    help="推理总线 CSV (可选, 缺则跳过 05 推理仅跑 02->03->04)")
    ap.add_argument("--infer-branch", default="",
                    help="推理分路 CSV (可选, 缺则推理仅出预测无评估指标)")
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--exclude-dates", default="",
                    help="逗号分隔的训练数据排除日期 (v6.12.3 数据清洗), 传递给 02_align_and_feat.py")
    # v6.14 新增: 增量训练 + 标签清洗
    ap.add_argument("--extra-train-bus", default="",
                    help="额外训练 bus CSV (v6.14, 例如把推理段一部分加入训练)")
    ap.add_argument("--extra-train-branch", default="",
                    help="额外训练 branch CSV (v6.14)")
    ap.add_argument("--extra-train-dates", default="",
                    help="逗号分隔的额外训练日期 (YYYY-MM-DD), 仅这些日期会被合并到训练集")
    ap.add_argument("--infer-eval-dates", default="",
                    help="逗号分隔的推理评估日期 (限制 OOD 评估范围, 避免数据泄漏)")
    ap.add_argument("--clean-labels", action="store_true",
                    help="v6.14: 启用标签清洗 (用 d87 启动信号确定真实空调起点, 启动前小负荷归 0)")
    ap.add_argument("--clean-d87-thr", type=float, default=50.0,
                    help="标签清洗 d87 启动阈值 (默认 50)")
    ap.add_argument("--skip-clean", action="store_true",
                    help="不清理 artifacts/logs (用于调试)")
    # [v10] 新增: 模型复用控制
    ap.add_argument("--force-retrain", action="store_true",
                    help="[v10] 强制重新训练 (即使 models/<user>/ 已有完整模型);"
                         " 默认 False = 模型存在则跳过训练只跑推理")
    # [v12] 新增: 时段过滤 (可分别指定 train / infer)
    ap.add_argument("--train-time-filter-spec", default="",
                    help="[v12] JSON 字符串, 训练数据时段过滤规格 "
                         "{'include':[[start,end],...],'exclude':[[start,end],...]}. "
                         "闭区间, 支持任意时段 (不限于整天). "
                         "会透传给 02_align_and_feat.py --time-filter-spec")
    ap.add_argument("--infer-time-filter-spec", default="",
                    help="[v12] JSON 字符串, 推理数据时段过滤规格 (与 train 独立). "
                         "会透传给 05_inference.py --time-filter-spec")
    # [v13] 用户级 d87 守卫开关 (覆盖全局 common.D87_ADAPTIVE_GUARD_ENABLED)
    ap.add_argument("--guard-enabled", default="",
                    choices=["", "true", "false"],
                    help="[v13] 用户级 d87 守卫开关. "
                         "'true'  = 强制开启守卫 (覆盖全局关闭); "
                         "'false' = 强制关闭守卫 (覆盖全局开启, 适用于变频/小功率空调用户); "
                         "''(空)   = 未指定, 走全局 common.D87_ADAPTIVE_GUARD_ENABLED, "
                         "        若全局 True 且训练集 |d87|.max < 50W, 会自动降级关闭")
    # [v13] per-split time_filter (train/val/test 独立 include/exclude)
    ap.add_argument("--splits-time-filter-spec", default="",
                    help="[v13] JSON 字符串, per-split 切分时段过滤规格. "
                         "结构: {'train':{'include':[[s,e],...],'exclude':[...]}, "
                         "'val':{...}, 'test':{...}}. "
                         "语义: include=硬锚定该样本入指定 split; exclude=从指定 split 移除. "
                         "冲突时按 train->val->test 顺序 include 优先. "
                         "严格保持原切分策略的形状 (大小不变). "
                         "会透传给 03_train.py 和 04_evaluate.py (环境变量 NILM_SPLITS_FILTER_SPEC)")
    # [v13.5] 8 项 common 常量覆盖 - 从 JSON 字符串反序列化 (batch 层组装)
    ap.add_argument("--skip-analyze", action="store_true",
                    help="[v13.6] 跳过训练前+推理前的分路开机时段分析 (analyze_on_periods). "
                         "默认启用分析, 输出到 artifacts/trains|infers/<user>/<stage>_on_periods*.csv")
    ap.add_argument("--common-overrides", default="",
                    help="[v13.5] JSON 字符串, 用户级 common.py 常量覆盖. "
                         "支持 9 个字段 (on_thr_w/split_ratios/split_strategy/"
                         "post_min_on/post_fill_short_off/weather_latitude/weather_longitude/"
                         "use_weather_features/use_temp_based_season). "
                         "内部会翻译为 NILM_USER_<字段名大写> 环境变量给 03_train.py")
    ap.add_argument("--v14-flags", default="",
                    help="[v14] JSON 字符串, 用户级 v14 增强开关配置. "
                         "例如: '{\"v14_enable\":true,\"physics\":true,...}'. "
                         "[v15] 仅在 v14 算法被选中时生效, 经算法模块隔离注入")
    # [v15] 多算法运行模式
    ap.add_argument("--algorithms", default="",
                    help="[v15] 逗号分隔算法列表 (main/rf/v14, 支持 'all' 别名). "
                         "与 --algo-mode 配合: single=指定单模型, multi=多模型选择性, all=全部遍历. "
                         "优先级: CLI > time_filters 配置 > 内置默认 (main+rf)")
    ap.add_argument("--algo-mode", default="",
                    choices=["", "single", "multi", "all"],
                    help="[v15] 运行模式: single=单模型 / multi=多模型选择性 / all=全部模型遍历")
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    output_dir = Path(args.output_dir)

    # [v13] 用户级 d87 守卫开关: 注入环境变量, 由 03_train.py 读取
    #   "true" -> "1" (强制开启)
    #   "false" -> "0" (强制关闭)
    #   ""     -> 不设置, 走全局 D87_ADAPTIVE_GUARD_ENABLED
    if args.guard_enabled == "true":
        os.environ["NILM_USER_GUARD_ENABLED"] = "1"
        print(f"  [v13] 用户级 d87 守卫: 强制开启 (NILM_USER_GUARD_ENABLED=1)")
    elif args.guard_enabled == "false":
        os.environ["NILM_USER_GUARD_ENABLED"] = "0"
        print(f"  [v13] 用户级 d87 守卫: 强制关闭 (NILM_USER_GUARD_ENABLED=0)")
    else:
        # 未指定, 清除环境变量避免受上次运行影响
        os.environ.pop("NILM_USER_GUARD_ENABLED", None)

    # [v13] per-split time_filter spec 通过环境变量传给 03_train.py 和 04_evaluate.py
    if args.splits_time_filter_spec.strip():
        os.environ["NILM_SPLITS_FILTER_SPEC"] = args.splits_time_filter_spec.strip()
        print(f"  [v13] per-split time_filter 已启用 (spec 长度 {len(args.splits_time_filter_spec)} 字节)")
    else:
        os.environ.pop("NILM_SPLITS_FILTER_SPEC", None)

    # [v13.5] 用户级 common 常量覆盖 - 从 JSON 解析后翻译为 NILM_USER_* env vars
    # 与 v13.1/v13.4 一致模式: env var 空 -> 走 03_train.py / common.py 默认
    # 字段名 -> env var 名 (字段名大写)
    _COMMON_OVERRIDE_FIELDS = [
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
    # 先清除所有旧 env vars 避免残留污染
    for _, env_name in _COMMON_OVERRIDE_FIELDS:
        os.environ.pop(env_name, None)

    # [v13.6] 记录本次生效的 on_thr_w (给 analyze 步骤同口径用). 默认走 common.
    _co_dict = {}
    if args.common_overrides.strip():
        try:
            _co = json.loads(args.common_overrides)
            if not isinstance(_co, dict):
                raise ValueError(f"--common-overrides 必须是 JSON 对象, 收到 {type(_co).__name__}")
            _co_dict = _co
            _applied = []
            for field, env_name in _COMMON_OVERRIDE_FIELDS:
                if field not in _co:
                    continue
                val = _co[field]
                # split_ratios 是 list, 需 json.dumps 保留结构
                if field == "split_ratios":
                    env_val = json.dumps(list(val))
                elif isinstance(val, bool):
                    env_val = "1" if val else "0"
                else:
                    env_val = str(val)
                os.environ[env_name] = env_val
                _applied.append(f"{field}={env_val}")
            if _applied:
                print(f"  [v13.5] 用户级 common 覆盖 {len(_applied)} 项: {', '.join(_applied)}")
        except Exception as e:
            print(f"  [v13.5 WARN] --common-overrides 解析失败 ({e}), 忽略, 走 common.py 默认")

    # [v14/v15] v14 增强配置: 仅解析记录 (环境注入由 v14 算法模块按需隔离完成)
    v14_flags_spec = getattr(args, "v14_flags", "") or ""
    v14_enable_hint = _v14_enabled_from_spec(v14_flags_spec)
    if v14_flags_spec.strip():
        print(f"  [v15] v14 增强配置已携带 (启用提示={v14_enable_hint}), "
              f"仅当 v14 算法被选中时经模块隔离注入")

    # [v15] 多算法选择解析 (single/multi/all 三种运行模式统一入口)
    from algorithms.base import AlgoContext
    from algorithms.registry import (resolve_algorithm_selection,
                                     REGISTERED_ALGORITHMS,
                                     algorithms_summary)
    selected_algos, algo_mode, algo_warnings = resolve_algorithm_selection(
        algo_config=None,
        cli_algorithms=(args.algorithms or None),
        cli_mode=(args.algo_mode or None),
        v14_hint=v14_enable_hint,
    )
    for w in algo_warnings:
        print(f"  [v15 WARN] {w}")
    print(f"  [v15] 运行模式: mode={algo_mode}, "
          f"算法序列={algorithms_summary(selected_algos)}")

    # [v13.6] 计算本次分析用的 on_thr_w (与训练评估同口径)
    #   优先级: --common-overrides.on_thr_w > common.ON_THR_W 默认
    if "on_thr_w" in _co_dict:
        try:
            _effective_on_thr_w = float(_co_dict["on_thr_w"])
        except (TypeError, ValueError):
            from common import ON_THR_W as _ON_THR_W_DEFAULT
            _effective_on_thr_w = float(_ON_THR_W_DEFAULT)
    else:
        from common import ON_THR_W as _ON_THR_W_DEFAULT
        _effective_on_thr_w = float(_ON_THR_W_DEFAULT)

    print(f"\n{'#'*70}")
    print(f"  用户流水线: {args.user_id} (target={args.target_col})")
    print(f"  算法计划  : {algorithms_summary(selected_algos)} (mode={algo_mode})")
    print(f"{'#'*70}")

    # 组装算法上下文 (算法模块只读)
    ctx = AlgoContext(
        project_root=project_root,
        user_id=args.user_id,
        target_col=args.target_col,
        output_dir=output_dir,
        train_bus=args.train_bus,
        train_branch=args.train_branch,
        infer_bus=args.infer_bus,
        infer_branch=args.infer_branch,
        has_inference=bool(args.infer_bus and Path(args.infer_bus).exists()),
        force_retrain=args.force_retrain,
        exclude_dates=args.exclude_dates,
        train_time_filter_spec=args.train_time_filter_spec,
        infer_time_filter_spec=args.infer_time_filter_spec,
        guard_enabled=args.guard_enabled,
        splits_time_filter_spec=args.splits_time_filter_spec,
        common_overrides_spec=args.common_overrides,
        v14_flags_spec=v14_flags_spec,
    )

    try:
        # 1. 切换 TARGET_COL
        patch_common(args.target_col)

        # 2. 清理 + 准备数据
        if not args.skip_clean:
            for sub in ["artifacts/metrics", "artifacts/predictions",
                        "models", "logs"]:
                d = project_root / sub
                if d.exists():
                    for f in d.iterdir():
                        if f.name != ".gitkeep" and f.is_file():
                            f.unlink()

        # v6.14: 支持增量训练 + 标签清洗
        setup_user_data(args.user_id, args.train_bus, args.train_branch,
                        project_root,
                        extra_train_bus=args.extra_train_bus,
                        extra_train_branch=args.extra_train_branch,
                        extra_train_dates=args.extra_train_dates,
                        clean_labels=args.clean_labels,
                        clean_d87_thr=args.clean_d87_thr,
                        target_col=args.target_col)

        # 2.5 [v13.6] 训练前分路开机时段分析 (数据视图, 与算法无关, 只跑一次)
        if not args.skip_analyze:
            _train_analyze_out = output_dir / "trains" / args.user_id
            run_analyze_step(
                stage="train",
                br_csv=args.train_branch,
                target_col=args.target_col,
                on_thr_w=_effective_on_thr_w,
                out_dir=_train_analyze_out,
                project_root=project_root,
                bus_csv=args.train_bus,
            )
        else:
            print(f"\n{'='*70}\n  STEP: TRAIN 前分路开机时段分析 -- 跳过 (--skip-analyze)\n{'='*70}")

        # 2.7 [v15] 02 对齐: 只要任一算法需要训练就跑 (对齐数据为训练前置依赖)
        PY = sys.executable
        _any_train_needed = ctx.force_retrain or any(
            not REGISTERED_ALGORITHMS[n].check_model_complete(ctx)[0]
            for n in selected_algos
        )
        if _any_train_needed:
            cmd02 = [PY, "02_align_and_feat.py"]
            if args.exclude_dates.strip():
                cmd02 += ["--exclude-dates", args.exclude_dates]
            if args.train_time_filter_spec.strip():
                cmd02 += ["--time-filter-spec", args.train_time_filter_spec]
                print(f"  [v12] 训练时段过滤已启用 (spec 长度 {len(args.train_time_filter_spec)} 字节)")
            run_step(cmd02, "02 对齐+特征", project_root)
        else:
            print(f"\n{'='*70}\n  [v15] 全部所选算法模型已完整, 跳过 02 对齐\n{'='*70}")

        # 3. [v15] 推理数据准备 (与算法无关, 只跑一次)
        has_inference = False
        infer_bus_dst = infer_br_dst = None
        if ctx.has_inference:
            has_inference = True
            infer_bus_dst, infer_br_dst = setup_infer_data(
                args.infer_bus, args.infer_branch, project_root
            )
            # [v13.6 / v13.10] 推理前分路开机时段分析 (数据视图, 只跑一次)
            if not args.skip_analyze and args.infer_branch and Path(args.infer_branch).exists():
                _infer_analyze_out = output_dir / "infers" / args.user_id
                _all_infer_dates = _list_dates_in_branch_csv(args.infer_branch)
                _infer_labels = _build_infer_date_labels(_all_infer_dates, args.infer_time_filter_spec)
                run_analyze_step(
                    stage="infer",
                    br_csv=args.infer_branch,
                    target_col=args.target_col,
                    on_thr_w=_effective_on_thr_w,
                    out_dir=_infer_analyze_out,
                    project_root=project_root,
                    date_labels=_infer_labels,
                    phase="pre",
                    bus_csv=args.infer_bus,
                )
            elif args.skip_analyze:
                print(f"\n{'='*70}\n  STEP: INFER 前分路开机时段分析 -- 跳过 (--skip-analyze)\n{'='*70}")
            else:
                print(f"\n{'='*70}\n  STEP: INFER 前分路开机时段分析 -- 跳过 (无推理分路)\n{'='*70}")
        else:
            print(f"\n{'='*70}\n  STEP: 05 推理 -- 跳过\n{'='*70}")
            print(f"  [跳过] 未提供 --infer-bus 或文件不存在: '{args.infer_bus}'")
            print(f"  [跳过] 仅完成训练/验证/测试流程")

        # 4. [v15] 按算法序列逐个执行 (训练/复用 -> 评估 -> 推理 -> 按算法归档)
        algo_results = {}
        for algo_name in selected_algos:
            algo_results[algo_name] = run_algorithm_flow(
                algo_name, ctx, args, project_root, output_dir,
                has_inference, infer_bus_dst, infer_br_dst,
                _effective_on_thr_w,
            )

        # 4.5 [v15] 收尾清理: 全部算法跑完后, 清除共享对齐数据等顶层临时产物
        _FINAL_KEEP = {
            "batch_execution_state.csv", "batch_execution_state.csv.tmp",
            "batch_run_summary.csv", "summary_metrics_all_users.csv",
            "skipped_users.csv", ".gitkeep",
        }
        for _f in (project_root / "artifacts").glob("*"):
            if _f.is_file() and _f.name not in _FINAL_KEEP:
                _f.unlink()
        (project_root / "artifacts" / "metrics").mkdir(exist_ok=True)
        (project_root / "artifacts" / "predictions").mkdir(exist_ok=True)
        # 清理运行期共享数据文件 (全部算法执行完毕后不再需要)
        for _fname in ("merged_bus.csv", "merged_branch.csv",
                       "infer_bus.csv", "infer_branch.csv"):
            _f = project_root / "data" / _fname
            if _f.exists():
                _f.unlink()

        # 5. [v15] 汇总退出码: ≥1 算法成功=0; 全部软跳过=10; 其余=1
        n_ok = sum(1 for s in algo_results.values() if s == "ok")
        n_soft = sum(1 for s in algo_results.values() if s.startswith("soft_skip"))
        print(f"\n{'='*70}\n  {args.user_id} 多算法执行汇总\n{'='*70}")
        for algo_name, status in algo_results.items():
            icon = "✓" if status == "ok" else ("◐" if status.startswith("soft_skip") else "✗")
            print(f"    {icon} [{algo_name:<6}] {status}")
        print(f"  成功 {n_ok} / 软跳过 {n_soft} / 失败 "
              f"{len(algo_results) - n_ok - n_soft} (共 {len(algo_results)} 个算法)")
        if n_ok > 0:
            print(f"\n{'='*70}\n  {args.user_id} 流水线 完成! (≥1 算法成功)\n{'='*70}")
            sys.exit(0)
        elif n_soft == len(algo_results):
            print(f"\n{'='*70}\n  {args.user_id} 流水线 软跳过 (全部算法数据质量门触发, 无模型)\n{'='*70}")
            sys.exit(10)
        else:
            print(f"\n{'='*70}\n  {args.user_id} 流水线 失败 (无算法成功)\n{'='*70}")
            sys.exit(1)
    finally:
        restore_common()


if __name__ == "__main__":
    main()
