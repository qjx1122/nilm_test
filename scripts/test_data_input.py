# -*- coding: utf-8 -*-
"""
[v16 数据模块解耦] 数据输入模块统一接口 单元测试
================================================
覆盖:
  1. 命名契约 RE_BUS / RE_BR (含 -1/-infer 后缀兼容)
  2. parse_data_dir (总线+分路+通道提取, 多文件取字典序最小)
  3. parse_user_folder: 配置 target_col 优先 / Ch{N} 反推 / 分路 pN 退化 / 默认 p1
  4. discover_users / is_runnable / get_execution_plan
  5. stage_train_data (含增量合并 + 标签清洗路径) / stage_infer_data /
     cleanup_staged_data_files
  6. 时段过滤统一入口 parse_time_filter_spec / apply_time_filter_spec
"""
import shutil
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from data_input import (
    RE_BUS, RE_BR, parse_data_dir, parse_user_folder, discover_users,
    is_runnable, get_execution_plan,
    stage_train_data, stage_infer_data, cleanup_staged_data_files,
    parse_time_filter_spec, apply_time_filter_spec,
)

TMP = Path("/tmp/nilm_data_input_test")


def _mk_user_layout(user="4200001", device="8000001", train=True, infer=True,
                    br_p_cols=("p1", "p2"), ch=1):
    """构造合成 data/trains|infers/<device>_<user>/ 布局, 返回根目录."""
    shutil.rmtree(TMP, ignore_errors=True)
    root = TMP
    uid = f"{device}_{user}"
    bus = pd.DataFrame({"event_time": ["2026-06-01 00:00:00", "2026-06-01 00:05:00"],
                        "load_iden_data1": [1.0, 2.0]})
    br = pd.DataFrame({"time": ["2026-06-01 00:00:00", "2026-06-01 00:15:00"]})
    for c in br_p_cols:
        br[c] = [10.0, 20.0]
    if train:
        d = root / "trains" / uid
        d.mkdir(parents=True, exist_ok=True)
        bus.to_csv(d / f"e241_{device}_{user}-Ch{ch}-250601-260630.csv", index=False)
        br.to_csv(d / f"{user}-250601-260630.csv", index=False)
    if infer:
        d = root / "infers" / uid
        d.mkdir(parents=True, exist_ok=True)
        bus.to_csv(d / f"e241_{device}_{user}-Ch{ch}-250701-260715-1.csv", index=False)
        br.to_csv(d / f"{user}-250701-260715-infer.csv", index=False)
    return root


def test_naming_contract():
    assert RE_BUS.match("e241_800_420-Ch1-250601-260630.csv")
    assert RE_BUS.match("e241_800_420-Ch12-250601-260630-1.csv")
    assert RE_BUS.match("e241_800_420-Ch1-250601-260630-infer.csv")
    assert not RE_BUS.match("420-250601-260630.csv")
    assert RE_BR.match("420-250601-260630.csv")
    assert RE_BR.match("420-250601-260630-infer.csv")
    assert not RE_BR.match("e241_800_420-Ch1-250601-260630.csv")
    # 命名分组
    m = RE_BUS.match("e241_800_420-Ch2-250601-260630.csv")
    assert m["device"] == "800" and m["user"] == "420" and m["ch"] == "2"


def test_parse_data_dir():
    root = _mk_user_layout()
    d = root / "trains" / "8000001_4200001"
    bus, br, ch_set = parse_data_dir(d)
    assert bus is not None and bus.suffix == ".csv"
    assert br is not None
    assert ch_set == {1}
    # 空目录 / 不存在
    empty = root / "trains" / "nobody"
    empty.mkdir(parents=True)
    assert parse_data_dir(empty) == (None, None, set())
    assert parse_data_dir(root / "trains" / "missing") == (None, None, set())


def test_parse_user_folder_ch_inference():
    root = _mk_user_layout(br_p_cols=("p1", "p2"), ch=2)
    info = parse_user_folder("8000001_4200001", root / "trains", root / "infers")
    assert info["device"] == "8000001" and info["user"] == "4200001"
    # 分路含 p2 -> Ch2 反推 p2
    assert info["target_col"] == "p2"
    assert info["train_bus"] is not None and info["train_br"] is not None
    assert info["infer_bus"] is not None and info["infer_br"] is not None


def test_parse_user_folder_pn_fallback_and_default():
    # Ch2 但分路只有 p1 -> 退化 p1
    root = _mk_user_layout(br_p_cols=("p1",), ch=2)
    info = parse_user_folder("8000001_4200001", root / "trains", root / "infers")
    assert info["target_col"] == "p1"
    # 无 pN 列 + 无 Ch 标识 -> 默认 p1 (构造无通道名文件)
    shutil.rmtree(TMP, ignore_errors=True)
    d = TMP / "trains" / "8000001_4200001"
    d.mkdir(parents=True)
    pd.DataFrame({"event_time": []}).to_csv(d / "e241_8000001_4200001-250601-260630.csv",
                                            index=False)
    pd.DataFrame({"time": [], "x": []}).to_csv(d / "4200001-250601-260630.csv", index=False)
    info2 = parse_user_folder("8000001_4200001", TMP / "trains", TMP / "infers")
    assert info2["target_col"] == "p1"


def test_parse_user_folder_config_target_priority():
    root = _mk_user_layout(br_p_cols=("p1", "p2"), ch=1)
    cfg = {"8000001_4200001": {"target_col": "p2"}}
    info = parse_user_folder("8000001_4200001", root / "trains", root / "infers",
                             time_filter_config=cfg)
    assert info["target_col"] == "p2"   # 配置覆盖 Ch1 反推
    # 配置 target 不在分路列 -> 回退反推
    cfg_bad = {"8000001_4200001": {"target_col": "p9"}}
    info2 = parse_user_folder("8000001_4200001", root / "trains", root / "infers",
                              time_filter_config=cfg_bad)
    assert info2["target_col"] == "p1"


def test_discover_and_runnable_plan():
    root = _mk_user_layout()
    users = discover_users(root)
    assert [u["folder_name"] for u in users] == ["8000001_4200001"]
    u = users[0]
    assert is_runnable(u) is True
    assert "全流程" in get_execution_plan(u)
    # 只有推理数据 -> 不可执行
    shutil.move(str(TMP / "trains"), str(TMP / "trains_off"))
    users2 = discover_users(TMP)
    assert not is_runnable(users2[0])
    assert "跳过" in get_execution_plan(users2[0])
    shutil.move(str(TMP / "trains_off"), str(TMP / "trains"))


def test_stage_train_and_infer_roundtrip():
    proj = TMP / "proj"
    (proj / "data").mkdir(parents=True, exist_ok=True)
    bus = pd.DataFrame({"event_time": ["2026-06-01 00:00:00"], "v": [1.0]})
    br = pd.DataFrame({"time": ["2026-06-01 00:00:00"], "p1": [10.0]})
    bus.to_csv(TMP / "b.csv", index=False)
    br.to_csv(TMP / "r.csv", index=False)
    stage_train_data("u1", TMP / "b.csv", TMP / "r.csv", proj, target_col="p1")
    assert (proj / "data" / "merged_bus.csv").exists()
    assert (proj / "data" / "merged_branch.csv").exists()
    # 增量合并
    bus2 = pd.DataFrame({"event_time": ["2026-06-02 00:00:00"], "v": [2.0]})
    br2 = pd.DataFrame({"time": ["2026-06-02 00:00:00"], "p1": [20.0]})
    bus2.to_csv(TMP / "b2.csv", index=False)
    br2.to_csv(TMP / "r2.csv", index=False)
    stage_train_data("u1", TMP / "b.csv", TMP / "r.csv", proj,
                     extra_train_bus=TMP / "b2.csv", extra_train_branch=TMP / "r2.csv")
    merged = pd.read_csv(proj / "data" / "merged_bus.csv")
    assert len(merged) == 2
    # 推理落地 (有/无分路两种形态)
    i_bus, i_br = stage_infer_data(TMP / "b.csv", TMP / "r.csv", proj)
    assert Path(i_bus).name == "infer_bus.csv" and Path(i_br).name == "infer_branch.csv"
    i_bus2, i_br2 = stage_infer_data(TMP / "b.csv", "", proj)
    assert i_br2 is None
    # 收尾清理
    cleanup_staged_data_files(proj)
    assert not (proj / "data" / "merged_bus.csv").exists()
    assert not (proj / "data" / "infer_bus.csv").exists()


def test_time_filter_unified_entry():
    df = pd.DataFrame({
        "time": pd.date_range("2026-06-01 00:00", periods=48, freq="15min"),
        "v": range(48),
    })
    spec_str = ('{"include":[["2026-06-01 00:00","2026-06-01 06:00"]],'
                '"exclude":[["2026-06-01 00:00","2026-06-01 01:00"]]}')
    out = apply_time_filter_spec(df, "time", spec_str, "t")
    # include 保留 25 步 (00:00~06:00 含端点), exclude 剔除前 5 步 (00:00~01:00)
    assert len(out) == 25 - 5
    # 空 spec -> 原样返回 (零开销)
    assert apply_time_filter_spec(df, "time", "", "t") is df
    assert apply_time_filter_spec(df, "time", None, "t") is df
    # 解析接口
    assert parse_time_filter_spec("") is None
    spec = parse_time_filter_spec('{"include":[],"exclude":[]}')
    assert spec == {"include": [], "exclude": []}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"\n{len(fns)} 项通过")
    shutil.rmtree(TMP, ignore_errors=True)
