# -*- coding: utf-8 -*-
"""
批量用户训练 + 评估 + 推理流水线 (v6.12.6+v6.15.0-graceful-v9)
=================================================================
扫描 data/trains/ 和 data/infers/ 取用户 ID 并集, 对每个有训练数据的用户:
  1. 自动解析 train/infer 总线 + 分路 CSV (按命名规范, 兼容 -1 / -infer 后缀)
  2. 自动反推 target_col (总线 -Ch{N}- 优先, 分路有则用, 否则退到分路第1个pN列)
  3. 调用 run_user_pipeline.py 完整跑 02->03->04->05
  4. 产物按新目录结构分流归档 (见下)

------ 新目录结构 (v9) ------
data/
  trains/<user_id>/                  训练用 csv (总线 + 分路)
  infers/<user_id>/                  推理用 csv (可选, 缺失则跳过 05)
models/
  <user_id>/                         所有模型 pkl + model_meta.json
logs/
  <user_id>/                         单用户运行日志
  _batch/                            批量执行日志
artifacts/
  summary_metrics_all_users.csv      [汇总] 每用户 4 行 (train/val/test/inference)
  batch_run_summary.csv              [汇总] 批量执行记录 (每次跑完覆盖)
  batch_execution_state.csv          [v13.17 断点续跑] 实时增量状态: 每个用户跑完立即
                                     追加/更新 (user_id, status, success, started_at,
                                     finished_at, duration_s, message, target_col, run_id).
                                     原子写 (.tmp + os.replace), 崩溃时最多丢当前正跑的.
                                     用 --resume 启用断点续跑 (默认跳过 ok/soft_skip;
                                     加 --resume-skip-failed 也跳过 fail).
  skipped_users.csv                  [汇总] 软跳过用户 × 算法原因 (若有)
  trains/<user_id>/                  训练前/后开机时段分析 (数据视图, 算法无关)
  trains/<user_id>/<algo>/           [v15] 该算法训练评估 metrics + 预测 + plots
  infers/<user_id>/<algo>/           [v15] 该算法推理 metrics + 预测 + plots
                                     (algo ∈ main / rf / v14, 按 --algorithms/--algo-mode
                                      或 time_filters 配置 algorithms 字段选择)

------ 文件命名规范 (设备编号在前, 用户编号在后) ------
  文件夹: <device>_<user>            例: 800080252842_4206894986488
  总线:   e241_<device>_<user>-Ch{N}-<start>-<end>[-1|-infer].csv
  分路:   <user>-<start>-<end>[-infer].csv
  (因目录已区分训推, 后缀 -1 / -infer 已可省略, 但解析兼容历史命名)

------ 优雅降级 ------
  - 缺训练数据 (data/trains/<u>/ 为空 或不存在)  -> 跳过整个用户 (硬要求)
  - 缺推理数据 (data/infers/<u>/ 为空 或不存在)  -> 跳过 05 推理, 仍跑训练/验证/测试
  - 03 数据质量门触发 (对齐过少 / 单类标签 / 切分空) -> 软跳过 + skip_reason 入汇总

使用:
  python scripts/run_batch_users.py                 # 跑 data/trains/ 下全部用户
  python scripts/run_batch_users.py --users 800080252842_4206894986488 ...
  python scripts/run_batch_users.py --data-dir /path/to/data --skip-existing
  # [v15] 多算法运行模式: 指定单模型 / 多模型选择性 / 全部模型遍历
  python scripts/run_batch_users.py --algorithms rf --algo-mode single
  python scripts/run_batch_users.py --algorithms main,v14 --algo-mode multi
  python scripts/run_batch_users.py --algo-mode all
  # (也可在 --time-filter-config JSON 中按用户配置 "algorithms": {"mode":..., "selected":[...]})
"""
import argparse
import os
import sys
import subprocess
from pathlib import Path
from datetime import datetime
import pandas as pd

# Windows GBK 控制台兼容: 强制 stdout/stderr 用 UTF-8
# 否则 print("✅ 用户切换") 等含 Unicode 符号会抛 UnicodeEncodeError
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

# [v16] 三大解耦数据模块统一接口:
#   数据输入 (发现/解析/加载) | 数据输出 (状态/汇总/归档) | 数据配置 (集中式解析)
from data_input import (parse_user_folder, discover_users, is_runnable,
                        get_execution_plan)
from data_output import (_execution_state_path, _load_execution_state,
                         _get_completed_users, _upsert_execution_state,
                         collect_skip_reasons, aggregate_metrics)
from data_config import ConfigResolver

def run_single_user(info, output_dir, skip_existing=False, log_file=None,
                    force_retrain=False,
                    train_time_filter_spec="", infer_time_filter_spec="",
                    guard_enabled="",
                    splits_time_filter_spec="",
                    common_overrides_spec="",
                    v14_flags_spec="",
                    algorithms="", algo_mode=""):
    """对单个用户调用 run_user_pipeline.py

    [v6.12.6+v6.15.0-graceful-v7] 三态返回:
      返回 (status: str, message: str)
      status ∈ {"ok", "soft_skip", "fail"}
        - "ok"        : 子进程 exit 0  (真成功, 产出模型 + 指标)
        - "soft_skip" : 子进程 exit 10 (03_train.py 数据质量门触发,
                        无模型无指标, 但有 artifacts/<user>/skip_reason.json)
        - "fail"      : 其它退出码 / 启动异常 / 超时

    [v10] force_retrain: 透传给 run_user_pipeline.py 的 --force-retrain
    [v12] train/infer_time_filter_spec: 时段过滤 JSON 字符串, 透传给 pipeline
    """
    user_id = info["folder_name"]
    # [v9 新路径] 已跳过判断改成: 训练评估目录存在且非空 (models/<u>/ 也可以,但 trains 更轻量)
    train_out = Path(output_dir) / "trains" / user_id
    if skip_existing and train_out.exists() and any(train_out.iterdir()):
        return "ok", f"已跳过 ({train_out} 已存在)"

    # 使用 sys.executable 确保跨平台兼容 (Windows 通常无 python3 命令)
    cmd = [
        sys.executable, str(SCRIPT_DIR / "run_user_pipeline.py"),
        "--user-id", user_id,
        "--target-col", info["target_col"],
        "--train-bus", str(info["train_bus"]),
        "--train-branch", str(info["train_br"]),
        "--output-dir", str(output_dir),
    ]
    # 优雅降级: infer_bus 缺失则不传 --infer-bus -> 单用户流水线会跳过 05
    if info["infer_bus"] is not None:
        cmd += ["--infer-bus", str(info["infer_bus"])]
    if info["infer_br"] is not None:
        cmd += ["--infer-branch", str(info["infer_br"])]
    # [v10] 透传 --force-retrain
    if force_retrain:
        cmd += ["--force-retrain"]
    # [v12] 透传时段过滤 spec (JSON 字符串)
    if train_time_filter_spec:
        cmd += ["--train-time-filter-spec", train_time_filter_spec]
    if infer_time_filter_spec:
        cmd += ["--infer-time-filter-spec", infer_time_filter_spec]
    # [v13] 透传用户级 d87 守卫开关
    if guard_enabled in ("true", "false"):
        cmd += ["--guard-enabled", guard_enabled]
    # [v13] 透传 per-split time_filter 规格
    if splits_time_filter_spec:
        cmd += ["--splits-time-filter-spec", splits_time_filter_spec]
    # [v13.5] 透传 8 项 common 常量覆盖
    if common_overrides_spec:
        cmd += ["--common-overrides", common_overrides_spec]
    # [v14] 透传 v14 增强配置
    if v14_flags_spec:
        cmd += ["--v14-flags", v14_flags_spec]
    # [v15] 透传多算法选择 (列表 + 运行模式)
    if algorithms:
        cmd += ["--algorithms", algorithms]
    if algo_mode:
        cmd += ["--algo-mode", algo_mode]

    # v6.12.6+v6.15.0-graceful-v3: 强制子进程 stdout/stderr 使用 UTF-8 输出,
    # 与本批处理脚本 + 子进程 reconfigure 形成"端到端 UTF-8 一致" (Windows GBK 兼容)
    sub_env = dict(os.environ)
    sub_env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        if log_file:
            with open(log_file, "a", encoding="utf-8") as lf:
                lf.write(f"\n{'='*70}\n {user_id}  ({datetime.now()})\n{'='*70}\n")
                lf.write(f"CMD: {' '.join(cmd)}\n\n")
                lf.flush()
                r = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                   cwd=PROJECT_ROOT, timeout=1200, env=sub_env)
        else:
            r = subprocess.run(cmd, cwd=PROJECT_ROOT, timeout=1200, env=sub_env)
        if r.returncode == 0:
            return "ok", "成功"
        # [v6.12.6+v6.15.0-graceful-v7] 退出码 10 = 软跳过 (数据质量门触发)
        if r.returncode == 10:
            # [v9 新路径] 读 artifacts/trains/<user>/skip_reason.json 拿具体原因
            reason = "数据质量门触发"
            try:
                import json as _json
                skip_f = Path(output_dir) / "trains" / user_id / "skip_reason.json"
                if skip_f.exists():
                    info_js = _json.loads(skip_f.read_text(encoding="utf-8"))
                    reason = info_js.get("skip_reason", reason)
                    detail = info_js.get("detail", "")
                    if detail:
                        reason = f"{reason} ({detail})"
            except Exception:
                pass
            return "soft_skip", f"软跳过: {reason}"
        # 真失败: 把日志末尾打回终端, 帮用户快速定位 (避免 "code=1" 黑盒)
        err_tail = ""
        if log_file and Path(log_file).exists():
            try:
                lines = Path(log_file).read_text(encoding="utf-8", errors="ignore").splitlines()
                # 找本次 user_id 段落以来的最后 50 行
                start = max((i for i, ln in enumerate(lines) if user_id in ln), default=0)
                tail = lines[max(start, len(lines)-50):]
                err_tail = "\n".join(tail[-50:])
            except Exception:
                pass
        msg = f"流水线返回非零 (code={r.returncode})"
        if err_tail:
            print(f"\n  ────── 子进程日志末尾 (后 50 行) ──────")
            print(err_tail)
            print(f"  ──────────────────────────────────────")
            print(f"  完整日志: {log_file}")
        return "fail", msg
    except subprocess.TimeoutExpired:
        return "fail", "超时 (>20 分钟)"
    except FileNotFoundError as e:
        # Windows 常见: 找不到 python 命令本身
        return "fail", f"FileNotFoundError: {e} (检查 Python 解释器路径)"
    except Exception as e:
        return "fail", f"异常: {type(e).__name__}: {e}"


def main():
    ap = argparse.ArgumentParser(description="批量用户训练+评估+推理流水线")
    ap.add_argument("--data-dir", default=str(PROJECT_ROOT / "data"),
                    help="用户数据根目录 (默认 data/)")
    ap.add_argument("--output-dir", default=str(PROJECT_ROOT / "artifacts"),
                    help="批量产物归档目录 (默认 artifacts/)")
    ap.add_argument("--users", nargs="*", default=None,
                    help="仅跑指定用户文件夹名 (省略 = 全部)")
    ap.add_argument("--skip-existing", action="store_true",
                    help="若 artifacts/<user>/ 已存在则跳过")
    ap.add_argument("--dry-run", action="store_true",
                    help="仅扫描+打印计划, 不实际执行")
    ap.add_argument("--continue-on-error", action="store_true", default=True,
                    help="某用户失败时继续跑其他用户 (默认 True)")
    # [v10] 模型复用控制
    ap.add_argument("--force-retrain", action="store_true",
                    help="[v10] 强制重新训练所有用户 (即使 models/<user>/ 已有完整模型);"
                         " 默认 False = 有模型就跳过训练只跑推理")
    # [v12] 时段过滤配置
    ap.add_argument("--time-filter-config", default="",
                    help="[v12] JSON 配置文件路径, 定义每用户 train/infer 的 include+exclude 时段. "
                         "结构: {user_id: {'train':{'include':[[start,end],...],'exclude':[...]}, "
                         "'infer': {...}}, '_default': {...}}. "
                         "支持任意时段 (非整天粒度), 闭区间. 未列出的用户会读 _default 键, 也可完全省略")
    # [v13.17] 断点续跑
    ap.add_argument("--resume", action="store_true",
                    help="[v13.17] 启用断点续跑: 读取 artifacts/batch_execution_state.csv, "
                         "跳过上次已完成 (ok/soft_skip) 的用户, 只跑剩余 + 上次 fail 的. "
                         "状态文件不存在或损坏时自动降级到全部重跑. "
                         "默认关闭 (与历史行为完全一致, 零回归)")
    ap.add_argument("--resume-skip-failed", action="store_true",
                    help="[v13.17] 配合 --resume 使用: 连上次 fail 的用户也跳过 (需手工删行才重试). "
                         "默认 False = fail 用户续跑时会重跑")
    ap.add_argument("--v14-flags", default="",
                    help="[v14] JSON 字符串, 透传给 run_user_pipeline.py 的 v14 开关")
    # [v15] 多算法运行模式 (优先级: CLI > time_filters 配置 algorithms 字段 > 内置默认)
    ap.add_argument("--algorithms", default="",
                    help="[v15] 逗号分隔算法列表 (main/rf/v14, 支持 'all' 别名), 覆盖 time_filters 配置")
    ap.add_argument("--algo-mode", default="",
                    choices=["", "single", "multi", "all"],
                    help="[v15] 运行模式: single=单模型 / multi=多模型选择性 / all=全部模型遍历")
    args = ap.parse_args()

    # [v12] 加载时段过滤配置
    time_filter_config = {}
    if args.time_filter_config.strip():
        from time_filter_utils import load_time_filter_config
        time_filter_config = load_time_filter_config(args.time_filter_config)
        print(f"  [v12] 已加载时段过滤配置: {args.time_filter_config}")
        print(f"        含用户级配置 {sum(1 for k in time_filter_config if not k.startswith('_'))} 条, "
              f"_default 键: {'有' if '_default' in time_filter_config else '无'}")

    # [v16] 数据配置模块统一入口: 集中式配置解析器 (配置 + CLI 覆盖 -> 每用户生效配置)
    resolver = ConfigResolver(
        config=time_filter_config or None,
        cli_algorithms=getattr(args, "algorithms", "") or "",
        cli_algo_mode=getattr(args, "algo_mode", "") or "",
        cli_v14_flags=getattr(args, "v14_flags", "") or "")

    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()
    # [v9 新结构] summary 文件直接放 artifacts/ 根目录
    summary_dir = output_dir
    # 批量级日志: logs/_batch/batch_run_<ts>.log (用户级日志在 logs/<user_id>/)
    batch_log_dir = PROJECT_ROOT / "logs" / "_batch"
    batch_log_dir.mkdir(parents=True, exist_ok=True)
    log_path = batch_log_dir / f"batch_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    print("="*70)
    print(f"  批量用户流水线 (v6.12.6+v6.15.0)")
    print(f"  data-dir   : {data_dir}  (扫描 trains/ + infers/ 子目录)")
    print(f"  output-dir : {output_dir}  (产出 trains/ infers/ summary_metrics_all_users.csv)")
    print(f"  batch log  : {log_path}")
    # [v10] 模型复用模式标识
    if args.force_retrain:
        print(f"  训练策略   : --force-retrain 强制重训所有用户")
    else:
        print(f"  训练策略   : 有完整模型则复用, 缺失则训练 (加 --force-retrain 强制重训)")
    print("="*70)

    # 1. 扫描 (v13: 传入 time_filter_config 让 parse_user_folder 优先读配置里的 target_col)
    users = discover_users(data_dir, time_filter_config=time_filter_config)
    if args.users:
        users = [u for u in users if u["folder_name"] in args.users]
    print(f"\n发现 {len(users)} 个用户文件夹:")
    print(f"{'用户ID':<40} {'target':<6} {'tr_bus':<7} {'tr_br':<7} {'inf_bus':<8} {'inf_br':<7} {'执行计划'}")
    print("-"*125)
    runnable, skipped = [], []
    for u in users:
        flags = [
            ("✓" if u["train_bus"] is not None else "✗"),
            ("✓" if u["train_br"]  is not None else "✗"),
            ("✓" if u["infer_bus"] is not None else "✗"),
            ("✓" if u["infer_br"]  is not None else "✗"),
        ]
        ok = is_runnable(u)
        plan = get_execution_plan(u)
        print(f"{u['folder_name']:<40} {u['target_col'] or '?':<6} "
              f"{flags[0]:<7} {flags[1]:<7} {flags[2]:<8} {flags[3]:<7} {plan}")
        if u["errors"]:
            for e in u["errors"]:
                print(f"    └─ {e}")
        # [v16] 扫描阶段通过数据配置模块统一接口解析并存储该用户运行配置
        if ok:
            u["run_cfg"] = resolver.resolve(u["folder_name"], verbose=True)
        (runnable if ok else skipped).append(u)

    # [v13.17] 断点续跑: 在 dry-run 之前应用, 让计划也反映真实待跑列表
    resume_completed = set()
    resume_state_df = None
    if args.resume:
        print(f"\n[v13.17 续跑] --resume 开启, 检查 {_execution_state_path(output_dir)}")
        resume_state_df = _load_execution_state(output_dir, logger_print=print)
        resume_completed = _get_completed_users(
            resume_state_df, retry_failed=not args.resume_skip_failed)
        if resume_completed:
            before_n = len(runnable)
            _kept, _skipped_resume = [], []
            for u in runnable:
                if u["folder_name"] in resume_completed:
                    _skipped_resume.append(u["folder_name"])
                else:
                    _kept.append(u)
            runnable = _kept
            policy = "只跳过 ok/soft_skip" if not args.resume_skip_failed else "跳过 ok/soft_skip/fail"
            print(f"[v13.17 续跑] 跳过策略: {policy}")
            print(f"[v13.17 续跑] 原计划 {before_n} 用户, 跳过已完成 {len(_skipped_resume)} 用户, "
                  f"实际待跑 {len(runnable)} 用户")
            if _skipped_resume:
                for uid in _skipped_resume:
                    print(f"    [SKIP-resume] {uid}")
        else:
            print(f"[v13.17 续跑] 无已完成用户可跳过, 按原计划执行 {len(runnable)} 用户")

    if args.dry_run:
        print(f"\n[dry-run] 不执行. 计划执行 {len(runnable)} 用户, 跳过 {len(skipped)} 用户")
        return 0
    if not runnable:
        print("\n无可执行用户, 退出"); return 1

    # 2. 执行
    summary_dir.mkdir(parents=True, exist_ok=True)
    results = []
    t_start = datetime.now()
    # [v13.17] 本次批处理运行 ID (供状态 CSV 追溯是哪一次跑写的)
    run_id = t_start.strftime("%Y%m%d_%H%M%S")
    # [v6.12.6+v6.15.0-graceful-v7] 三态状态符
    # ✅/❌ 这俩是 BMP 内字符通常可显示, 但 ⏭ (U+23ED) 在 Windows GBK 控制台
    # 无法 encode (即使有 stdout reconfigure 也存在转发到日志文件的双解码风险).
    # 用 [SKIP] 纯 ASCII 等宽标签, Windows / Linux / macOS 都安全.
    STATUS_ICON  = {"ok": "[OK]  ", "soft_skip": "[SKIP]", "fail": "[FAIL]"}
    STATUS_LABEL = {"ok": "成功", "soft_skip": "软跳过", "fail": "失败"}
    for i, u in enumerate(runnable, 1):
        print(f"\n{'#'*70}\n  [{i}/{len(runnable)}] {u['folder_name']} (target={u['target_col']})")
        print(f"{'#'*70}")

        # [v16] 使用扫描阶段解析好的运行配置 (数据配置模块 UserConfig 统一接口)
        _uc = u.get("run_cfg") or resolver.resolve(u["folder_name"], verbose=False)
        _train_spec_str = _uc.train_spec_cli()
        _infer_spec_str = _uc.infer_spec_cli()
        _guard_enabled = _uc.guard_cli()
        _splits_spec_str = _uc.splits_spec_cli()
        _common_overrides_str = _uc.common_overrides_cli()
        _v14_flags_str = _uc.v14_flags_cli()
        _algo_sel_names = _uc.algorithms
        _algo_mode = _uc.algo_mode
        print(_uc.plan_line())

        t0 = datetime.now()
        status, msg = run_single_user(u, output_dir, args.skip_existing, log_path,
                                       force_retrain=args.force_retrain,
                                       train_time_filter_spec=_train_spec_str,
                                       infer_time_filter_spec=_infer_spec_str,
                                       guard_enabled=_guard_enabled,
                                       splits_time_filter_spec=_splits_spec_str,
                                       common_overrides_spec=_common_overrides_str,
                                       v14_flags_spec=_v14_flags_str,
                                       algorithms=",".join(_algo_sel_names),
                                       algo_mode=_algo_mode)
        t1 = datetime.now()
        dt = (t1 - t0).total_seconds()
        icon  = STATUS_ICON.get(status, "?")
        label = STATUS_LABEL.get(status, status)
        # 单行清晰打印, 让"成功 / 软跳过 / 失败"一眼可辨
        # 若 msg 本身已含状态标签 (如"软跳过: xxx") 则不重复贴标签
        if status == "ok":
            line = f"  {icon} {u['folder_name']}: {label}  (耗时 {dt:.1f}s)"
        else:
            line = f"  {icon} {u['folder_name']}: {msg}  (耗时 {dt:.1f}s)"
        print(line)
        results.append({"user_id": u["folder_name"],
                        "status": status,         # 三态: ok / soft_skip / fail
                        "ok": (status == "ok"),    # 兼容旧字段 (仅真成功为 True)
                        "message": msg,
                        "duration_s": dt,
                        "target_col": u["target_col"]})

        # [v13.17] 每个用户完成后 立即 增量写入状态 CSV (支持崩溃恢复)
        # 原子写: .tmp + os.replace, 中断时最多丢当前正在跑的这一个用户
        try:
            _upsert_execution_state(output_dir, {
                "user_id": u["folder_name"],
                "status": status,
                "success": (status == "ok"),
                "started_at": t0.strftime("%Y-%m-%d %H:%M:%S"),
                "finished_at": t1.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_s": round(dt, 2),
                "message": (msg or "").replace("\n", " ")[:500],   # 单行且截断防超宽
                "target_col": u["target_col"] or "",
                "algorithms": ",".join(_algo_sel_names),           # [v15] 本次算法计划
                "run_id": run_id,
            }, logger_print=print)
        except Exception as _wse:
            # 状态写入失败不影响主流程, 只打印 WARN
            print(f"    [v13.17 状态] WARN: 写入状态 CSV 失败 ({_wse}), 继续下一个用户")

    # 3. 汇总指标
    print(f"\n{'='*70}\n  汇总指标到 {summary_dir}\n{'='*70}")
    written = aggregate_metrics(output_dir, summary_dir)
    for fname, n, path in written:
        print(f"  ✓ {fname:<40} {n:>5} 行 -> {path}")

    # 3b. [v6.12.6+v6.15.0-graceful-v5] 汇总软跳过原因
    skip_csv, n_skipped = collect_skip_reasons(output_dir, summary_dir)
    if skip_csv is not None:
        print(f"  ✓ {'skipped_users.csv':<40} {n_skipped:>5} 行 -> {skip_csv}")
        # 按 skip_reason 分布做一行汇总, 让用户一眼看到哪些原因占大头
        try:
            sk_df = pd.read_csv(skip_csv)
            if "skip_reason" in sk_df.columns and len(sk_df) > 0:
                dist = sk_df["skip_reason"].value_counts().to_dict()
                dist_str = ", ".join([f"{k}={v}" for k, v in dist.items()])
                print(f"    [skip 原因分布] {dist_str}")
        except Exception:
            pass

    # 4. 总结
    # [v6.12.6+v6.15.0-graceful-v7] 直接基于 results 里的 status 字段计数,
    # 不再依赖 skipped_users.csv 反推 (status 由子进程退出码 0/10/其他 决定)
    print(f"\n{'='*70}\n  批量执行总结")
    print(f"{'='*70}")
    n_ok   = sum(1 for r in results if r["status"] == "ok")
    n_soft = sum(1 for r in results if r["status"] == "soft_skip")
    n_fail = sum(1 for r in results if r["status"] == "fail")
    print(f"  总用户数              : {len(users)}")
    print(f"  可执行                : {len(runnable)}")
    print(f"  跳过 (数据缺文件)      : {len(skipped)}")
    print(f"  执行成功 (产出模型)    : {n_ok}")
    print(f"  软跳过 (数据质量门)    : {n_soft}")
    print(f"  执行失败 (真异常)      : {n_fail}")
    print(f"  总耗时                : {(datetime.now() - t_start).total_seconds():.1f}s")
    print(f"  详细日志              : {log_path}")
    print(f"  汇总指标目录          : {summary_dir}")
    # 保存执行记录: status 列直接来自子进程退出码, category 列保留兼容
    for r in results:
        r["category"] = r["status"]   # 兼容字段
    pd.DataFrame(results).to_csv(summary_dir / "batch_run_summary.csv",
                                  index=False, encoding="utf-8-sig")
    print(f"  执行记录              : {summary_dir / 'batch_run_summary.csv'}")
    # [v13.17] 状态 CSV 提示
    _state_p = _execution_state_path(output_dir)
    if _state_p.exists():
        try:
            _sdf = pd.read_csv(_state_p, encoding="utf-8-sig")
            n_all = len(_sdf)
            n_ok_state = int((_sdf["status"] == "ok").sum()) if "status" in _sdf.columns else 0
            print(f"  批量执行状态 (v13.17) : {_state_p}  ({n_all} 行, ok {n_ok_state})")
            if args.resume:
                print(f"                          续跑模式已用; 下次同命令再加 --resume 会自动跳过 ok/soft_skip")
            else:
                print(f"                          若中途中断, 下次加 --resume 可断点续跑")
        except Exception:
            print(f"  批量执行状态 (v13.17) : {_state_p}")
    # 退出码: 真异常 (fail) 才 return 2; 软跳过不影响退出码
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
