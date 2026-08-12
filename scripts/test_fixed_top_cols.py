# -*- coding: utf-8 -*-
"""NILM_FIXED_TOP_COLS manifest 解析回归测试。"""
import importlib.util
from pathlib import Path
import sys

SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS_DIR))
spec = importlib.util.spec_from_file_location("train_step", SCRIPTS_DIR / "03_train.py")
train_step = importlib.util.module_from_spec(spec)
spec.loader.exec_module(train_step)
parse = train_step.parse_fixed_top_cols

available = ["load_iden_data1", "load_iden_data2", "load_iden_data3"]
assert parse('["load_iden_data2", "load_iden_data1"]', available) == [
    "load_iden_data2", "load_iden_data1"
]
assert parse('[" load_iden_data2 "]', available) == ["load_iden_data2"]

invalid = [
    "not-json",
    "{}",
    "[]",
    '["load_iden_data1", "load_iden_data1"]',
    '["load_iden_data404"]',
    '[1]',
    '[""]',
]
for raw in invalid:
    try:
        parse(raw, available)
    except ValueError:
        pass
    else:
        raise AssertionError(f"应拒绝非法 manifest: {raw}")

print(f"[OK] fixed manifest: 2 个合法用例 + {len(invalid)} 个非法用例")
