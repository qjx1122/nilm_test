# -*- coding: utf-8 -*-
"""
[v16] 数据输入模块 — 统一输入访问接口
======================================
职责: 输入数据的发现、解析、加载与运行时落地。是"数据输入 / 数据输出 / 数据配置"
三大解耦模块中的输入底座, 编排层 (批量调度 + 单用户流水线) 与阶段脚本
(02/03/05) 的数据入口统一收敛到这里。

对外统一接口:
    RE_BUS / RE_BR                        : 输入文件命名契约 (总线/分路正则)
    parse_data_dir(d)                     : 解析单个数据子目录 (总线+分路+通道)
    parse_user_folder(...)                : 解析单用户全部输入链 (含 target_col 反推)
    discover_users(data_dir, config=None) : 扫描全部用户 (含配置 target_col 优先)
    is_runnable(info) / get_execution_plan(info) : 可执行性判定与计划描述
    load_bus_csv / load_branch_csv / resample_and_align : 原始数据加载统一门面
    stage_train_data(...)                 : 训练数据落地 (data/merged_*.csv)
    stage_infer_data(...)                 : 推理数据落地 (data/infer_*.csv)
    cleanup_staged_data_files(root)       : 收尾清理落地数据
    parse_time_filter_spec / apply_time_filter / apply_time_filter_spec
                                          : 时段过滤统一入口

依赖方向: 依赖底层实现层 (feature_utils / time_filter_utils), 不依赖数据输出/
数据配置模块 (配置以 dict 参数传入, 惰性 import 避免模块级耦合).
"""
import re
import sys
from pathlib import Path

import pandas as pd

# ---------- 原始数据加载底层实现门面再导出 (统一输入入口) ----------
from feature_utils import load_bus_csv, load_branch_csv, resample_and_align

# ---------- 输入文件命名契约 [v6.12.6+v6.15.0-graceful-v9 简化] ----------
# 新目录结构: data/trains/<user_id>/  +  data/infers/<user_id>/
# 因目录已区分训推, 文件名去掉 -1 / -infer 后缀:
#   总线: e241_<device>_<user>-Ch{N}-<start>-<end>.csv
#   分路: <user>-<start>-<end>.csv
# 兼容: 为支持迁移期, 仍接受历史的 -1/-infer 后缀文件名 (匹配后等效处理)
RE_BUS = re.compile(
    r"^e241_(?P<device>[^_]+)_(?P<user>[^-]+)-Ch(?P<ch>\d+)-"
    r"(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$"
)
RE_BR = re.compile(
    r"^(?P<user>[^-]+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$"
)


def parse_data_dir(d: Path):
    """[v9] 解析单个子目录 (data/trains/<u>/ 或 data/infers/<u>/),
    返回 (bus_path, br_path, ch_seen_set). 该目录下应只有 1 个总线 + 1 个分路.
    若有多个, 取字典序最小的一个 (并不报错, 但日志层可加警告).
    """
    bus = br = None
    ch_set = set()
    if not d.exists() or not d.is_dir():
        return None, None, ch_set
    csv_files = sorted([f for f in d.iterdir() if f.is_file() and f.suffix.lower() == ".csv"])
    for f in csv_files:
        if m := RE_BUS.match(f.name):
            if bus is None:
                bus = f
            ch_set.add(int(m["ch"]))
        elif m := RE_BR.match(f.name):
            if br is None:
                br = f
    return bus, br, ch_set


def parse_user_folder(folder_name: str, train_dir_root: Path, infer_dir_root: Path,
                      time_filter_config: dict = None):
    """[v9] 新解析: 从 trains/<folder_name>/ 和 infers/<folder_name>/ 提取数据.

    返回 dict:
        {folder_name, device, user, target_col, train_bus, train_br, infer_bus, infer_br}
    缺失项为 None.
    """
    info = {
        "folder_name": folder_name,
        "device": None,
        "user": None,
        "target_col": None,
        "train_bus": None,
        "train_br": None,
        "infer_bus": None,
        "infer_br": None,
        "errors": [],
    }

    # 从文件夹名解析 device_user
    parts = folder_name.split("_", 1)
    if len(parts) != 2:
        info["errors"].append(f"文件夹名 {folder_name} 不符合 <device>_<user> 格式")
        return info
    info["device"], info["user"] = parts[0], parts[1]

    # 扫训练子目录
    train_dir = train_dir_root / folder_name
    info["train_bus"], info["train_br"], ch_train = parse_data_dir(train_dir)
    # 扫推理子目录
    infer_dir = infer_dir_root / folder_name
    info["infer_bus"], info["infer_br"], ch_infer = parse_data_dir(infer_dir)

    # 通道编号 (训练优先, 训练无则用推理)
    ch_seen = ch_train if ch_train else ch_infer

    # 反推 target_col
    # [v13 新增] 优先级 0: 配置文件显式指定 (time_filter_config 中的 target_col 字段)
    # [v6.12.6+v6.15.0-graceful-v8 旧规则] 优先级 1-4:
    #   1. 从训练总线文件名 -Ch{N}- 提取 pN  (称为 ch_target, 例 Ch1 -> p1, Ch2 -> p2)
    #   2. 若 ch_target 在训练分路 CSV 列中存在 -> 用 ch_target
    #   3. 若 ch_target 不在分路列中 -> 退化到分路 CSV 中第 1 个 pN 列
    #   4. 极端兜底: 分路无任何 pN 列 / 总线无 -ChN- 标识 -> 默认 p1
    #
    # 历史背景:
    #   - 早期 v5 直接读分路 CSV 第 1 个 pN, 忽略 -Ch{N}-, 会导致某些 "Ch2 但分路含
    #     p1 p2 p3 p4" 的用户错选 p1.
    #   - v8 改为以总线 -Ch{N}- 为权威(因为这是真实测量通道编号), 但保留分路实际列
    #     存在性校验, 避免因 "Ch1 + 分路只有 p2" 这类历史用户回归 (会退到 p2).
    #   - v13 增加最高优先级 (配置文件), 覆盖场景: 数据文件命名不规范, 或用户希望
    #     覆盖默认反推 (如 Ch1 反推 p1, 但业务上要用 p2)

    # 读训练分路 CSV 的实际列, 找所有 pN 列 (给下面所有路径共用)
    br_p_cols = []
    if info["train_br"] is not None:
        try:
            br_cols = pd.read_csv(info["train_br"], nrows=1).columns.tolist()
            br_p_cols = [c for c in br_cols if re.fullmatch(r"p\d+", c.strip())]
        except Exception as e:
            info["errors"].append(f"读取分路 CSV 列名失败: {e}")

    # [v13] Step 0: 优先从配置文件读 (最高优先级)
    config_target_col = None
    if time_filter_config is not None:
        try:
            from time_filter_utils import get_user_target_col
            config_target_col = get_user_target_col(time_filter_config, folder_name)
        except Exception as e:
            info["errors"].append(f"[v13] 读配置 target_col 失败: {e}")

    if config_target_col is not None:
        # 配置存在: 宽松验证分路列
        # [v13.16] 复合列 (含 '+') 要求每个分量都在 br_p_cols 里
        if "+" in config_target_col:
            comp_parts = config_target_col.split("+")
            if br_p_cols:
                missing = [p for p in comp_parts if p not in br_p_cols]
                if not missing:
                    info["target_col"] = config_target_col
                    info["errors"].append(
                        f"[v13.16] target_col={config_target_col} 复合列来自配置 "
                        f"(所有分量 {comp_parts} 均在分路列 {br_p_cols} 中 ✓)"
                    )
                else:
                    info["errors"].append(
                        f"[v13.16 WARN] 配置复合 target_col={config_target_col} 缺分量 "
                        f"{missing} (分路实际列 {br_p_cols}), 回退到旧反推逻辑"
                    )
                    config_target_col = None
            else:
                # 分路读不到 pN 列, 但配置有值 -> 信任配置
                info["target_col"] = config_target_col
                info["errors"].append(
                    f"[v13.16 WARN] 分路 CSV 无 pN 列可校验, 直接采用配置 "
                    f"复合 target_col={config_target_col}"
                )
        elif config_target_col in br_p_cols:
            info["target_col"] = config_target_col
            info["errors"].append(
                f"[v13] target_col={config_target_col} 来自配置文件 (分路列={br_p_cols} 匹配 ✓)"
            )
        elif br_p_cols:
            # WARN: 配置指定的列不在分路中, 回退旧逻辑
            info["errors"].append(
                f"[v13 WARN] 配置指定 target_col={config_target_col} 不在分路列 {br_p_cols} 中, "
                f"回退到旧反推逻辑"
            )
            config_target_col = None  # 触发下面走旧逻辑
        else:
            # 分路读不到列, 但配置有值 -> 信任配置 (WARN)
            info["target_col"] = config_target_col
            info["errors"].append(
                f"[v13 WARN] 分路 CSV 无 pN 列可校验, 直接采用配置 target_col={config_target_col}"
            )

    if config_target_col is None:
        # [旧逻辑 v8] Step 1: 从总线名 -Ch{N}- 反推 ch_target
        ch_target = None
        if ch_seen:
            if len(ch_seen) > 1:
                info["errors"].append(f"用户 {folder_name} 含多种 Ch{ch_seen}, 仅取最小")
            ch_target = f"p{min(ch_seen)}"

        # Step 3: 按规则决定 target_col
        if ch_target and ch_target in br_p_cols:
            # 主路径: 总线通道与分路列对得上
            info["target_col"] = ch_target
        elif br_p_cols:
            # 退化 1: 总线通道在分路中无对应, 用分路里第 1 个 pN
            info["target_col"] = br_p_cols[0]
            if ch_target:
                info["errors"].append(
                    f"[警告] 总线 -Ch{min(ch_seen)}- 反推 {ch_target} 在分路中不存在 "
                    f"(分路列={br_p_cols}), 退化到 {br_p_cols[0]}"
                )
        elif ch_target:
            # 退化 2: 分路无任何 pN 列 (或分路读失败), 退到总线反推值
            info["target_col"] = ch_target
            info["errors"].append(
                f"[警告] 分路 CSV 无 pN 列, 直接用总线反推 {ch_target}"
            )
        else:
            # 兜底: 既无分路 pN 列, 也无总线 Ch{N} 标识 -> 默认 p1
            info["target_col"] = "p1"
            info["errors"].append(
                f"用户 {folder_name} 无法反推 target_col (分路无pN且总线无 -ChN-), 默认 p1"
            )

    # 缺失检查 -- 区分硬错误 (errors) 和警告 (warnings)
    if info["train_bus"] is None:
        info["errors"].append(f"缺训练总线文件 (data/trains/{folder_name}/e241_*-Ch?-*.csv)")
    if info["train_br"] is None:
        info["errors"].append(f"缺训练分路文件 (data/trains/{folder_name}/<user>-*-*.csv)")
    # 推理数据缺失只是降级, 不阻塞训练/验证/测试
    if info["infer_bus"] is None:
        info["errors"].append("[警告] 缺推理总线文件 -> 跳过 05 推理 (仍跑训练/验证/测试)")
    if info["infer_br"] is None:
        info["errors"].append("[警告] 缺推理分路文件 -> 推理仅出预测无评估指标")

    return info


def discover_users(data_dir: Path, time_filter_config: dict = None):
    """[v9/v13] 扫描 data_dir/trains/ 和 data/infers/ 取用户 ID 并集.

    新结构:
        data/trains/<user_id>/    必须存在才算"可训练"
        data/infers/<user_id>/    可选, 不存在则跳过推理

    [v13] time_filter_config: 若提供, parse_user_folder 会优先从中读 target_col

    返回所有合法用户的信息列表 (按 user_id 字典序).
    """
    train_root = data_dir / "trains"
    infer_root = data_dir / "infers"
    seen_ids = set()
    # 优先以 trains/ 下的目录为主 (只有训练数据才能跑流水线)
    if train_root.exists():
        for d in train_root.iterdir():
            if d.is_dir() and "_" in d.name:
                seen_ids.add(d.name)
    # 推理子目录补充 (若某用户只有 infers 没有 trains, 后面 is_runnable 会判为不可执行)
    if infer_root.exists():
        for d in infer_root.iterdir():
            if d.is_dir() and "_" in d.name:
                seen_ids.add(d.name)

    users = []
    for uid in sorted(seen_ids):
        users.append(parse_user_folder(uid, train_root, infer_root,
                                        time_filter_config=time_filter_config))
    return users


def is_runnable(info):
    """判断该用户是否可执行流水线 (优雅降级策略)

    必要条件 (硬要求):
      - 训练总线 + 训练分路 + target_col (用于 02->03->04)

    可选条件 (有则跑, 无则跳过对应步骤, 不阻塞):
      - infer_bus 缺失     -> 跳过 05 推理, 仅完成 train/val/test
      - infer_br  缺失     -> 跑 05 但只出预测, 无 inference 评估指标
    """
    if info["train_bus"] is None or info["train_br"] is None:
        return False
    if info["target_col"] is None:
        return False
    return True


def get_execution_plan(info):
    """返回该用户的执行计划描述 (用于扫描表展示)"""
    if not is_runnable(info):
        return "❌ 跳过 (缺训练数据)"
    if info["infer_bus"] is None:
        return "⚠️  仅训练 (无推理总线)"
    if info["infer_br"] is None:
        return "⚠️  训练+推理无评估 (无推理分路)"
    return "✅ 全流程 (训练+评估+推理)"


# ============================================================
# 运行时数据落地 (训练/推理 staging)
# ============================================================
def stage_train_data(user_id, train_bus, train_branch, project_root,
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


def stage_infer_data(infer_bus, infer_branch, project_root):
    """把用户推理数据复制到 data/infer_bus.csv + data/infer_branch.csv

    设计动机 (v6.12.6+v6.15.0):
      训推路径完全分离 -- 训练用 merged_bus.csv, 推理用 infer_bus.csv
      避免 "推理数据覆盖训练数据" 的隐患, 也让 inference_result 中 bus_csv
      字段始终是稳定的 infer_bus.csv 便于审计
    """
    data_dir = project_root / "data"
    data_dir.mkdir(exist_ok=True)

    bus_dst = data_dir / "infer_bus.csv"
    br_dst = data_dir / "infer_branch.csv"

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


def cleanup_staged_data_files(project_root):
    """[v16] 收尾清理运行时落地数据 (全部算法执行完毕后不再需要)."""
    data_dir = project_root / "data"
    for fname in ("merged_bus.csv", "merged_branch.csv",
                  "infer_bus.csv", "infer_branch.csv"):
        f = data_dir / fname
        if f.exists():
            f.unlink()


# ============================================================
# 时段过滤统一入口 (底层实现 time_filter_utils)
# ============================================================
def parse_time_filter_spec(cli_str: str):
    """把时段过滤 CLI JSON 字符串解析为 spec (空/None -> None)."""
    from time_filter_utils import cli_arg_to_spec
    return cli_arg_to_spec(cli_str)


def apply_time_filter(df, time_col, spec, label="", logger=None):
    """时段过滤底层实现门面再导出 (spec 对象形态)."""
    from time_filter_utils import apply_time_filter as _impl
    return _impl(df, time_col, spec, label, logger=logger)


def apply_time_filter_spec(df, time_col, spec_str, label="", logger=None):
    """时段过滤统一入口 (CLI 字符串形态): 解析 + 应用一步到位.

    spec_str 为空/None 时原样返回 df (零开销, 不解析).
    """
    spec = parse_time_filter_spec(spec_str)
    if spec is None:
        return df
    return apply_time_filter(df, time_col, spec, label, logger=logger)
