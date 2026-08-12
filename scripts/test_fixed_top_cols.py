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
parse_dates = train_step.parse_json_dates

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

assert parse_dates('["2026-07-08", "2026-07-09"]', "DATES") == {
    "2026-07-08", "2026-07-09"
}
for raw in ['{}', '["2026-07-08", "2026-07-08"]', '[1]', 'not-json']:
    try:
        parse_dates(raw, "DATES")
    except ValueError:
        pass
    else:
        raise AssertionError(f"应拒绝非法日期 manifest: {raw}")

print(f"[OK] manifest: 3 个合法用例 + {len(invalid) + 4} 个非法用例")
