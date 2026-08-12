# STATUS.md

## 当前目标
- 分别以 `data/time_filters-5User-v14-new.json` 与 `data/time_filters-5User-v14-new-test.json` 对 5 用户执行隔离、强制重训验证；筛选并归因所有每日 `F1 < 0.90` 或 `SAE > 0.20` 的记录，比较目标用户 `800080270789_4206680982373` 及总体变化。

## 已完成
- [x] 2026-08-12 完成开局仪式、`.venv` 依赖恢复和 GitHub/远端检查。
- [x] 完成环境基线：4 个自包含测试脚本共 137 个断言通过；`time_filter_utils.py` 自测、v6.15 守卫压力脚本及脚本编译通过。
- [x] 核验两份配置唯一差异：目标用户首段训练 include / 推理 exclude 的结束时间由 `2026-06-04` 延长至 `2026-06-06`。
- [x] 两份配置首次完整批量运行均 exit 0、各 5/5 用户状态为 `ok`，并完成每日指标初筛。
- [x] 初筛发现第二次运行的用户 `800080252844_4206894986488` 实际误读默认 `p1` 而非配置的 `p2`；定位为 `common.py` 同秒等长改写后 Python 时间戳 pyc 仍被判定有效。
- [x] 修复 `run_user_pipeline.py`：每次修改/恢复 `TARGET_COL` 后清除 `common` 字节码缓存，支持 `p1+p2` 等组合目标并校验替换成功；针对 `p2`、`p1+p2` 和恢复默认值的独立子进程回归通过。

## 进行中
- 使用修复后的流水线重新执行两份配置的完整隔离强制重训，替换受 pyc 污染的首次验证口径。

## 下一步（TODO）
1. 完成修复后的双配置批量运行，核验状态、目标列、样本覆盖和产物完整性。
2. 对每个命中阈值的用户日按全关正确（F1 不适用）、全关误报、分类/能耗偏差和数据覆盖逐日归因。
3. 比较两配置对目标用户及总体汇总的影响，将结论仅追加到 `REPORT_TEST.md`。
4. 完成全套回归检查，追加会话纪要，提交并推送固定 Arena 分支。

## 决策记录 / 踩坑
- 本会话固定在 Arena 分支 `arena/019ff3f3-nilm-test`，不另建或切换分支（优先遵守会话运行环境约束）。
- 两配置必须使用不同输出目录且启用 `--force-retrain`，避免模型复用掩盖配置差异。
- 不能仅凭批量 exit 0 判定结果可信：首次第二套运行中，用户 `800080252844_4206894986488` 的配置和输入未变，但对齐样本由 2734 降至 1152、推理 F1 由 0.9744 降至 0；对照分路能耗确认第二次实际使用了 `p1`。根因是 Python 时间戳 pyc 在源文件同一秒内由 `p1` 等长改成 `p2` 时未失效，因此先修复缓存清理并完整重跑。
- 每日 `TP=FP=FN=0` 时 sklearn 将 F1 记为 0；这些日期仍按用户阈值列出，但 F1 在无正类日不可解释，不计为模型分类失败。
- 仓库没有 `setup.sh`，也不是 pnpm 项目；按 README / `requirements.txt` 使用 `.venv`。当前 Python 3.11.2 与 README 推荐的 3.10 不同，固定依赖与现有自包含测试均已通过。
- `scripts/test_train_infer_symmetry.py` 硬编码依赖仓库外历史产物，当前缺失导致 `FileNotFoundError`，不判定为源码回归。

## 关键文件路径
- 两份配置：`data/time_filters-5User-v14-new.json`、`data/time_filters-5User-v14-new-test.json`
- 批量/单用户入口：`scripts/run_batch_users.py`、`scripts/run_user_pipeline.py`
- 隔离产物：`artifacts/validation_v14_new/`、`artifacts/validation_v14_new_test/`
- 专题报告：`REPORT_TEST.md`
- 会话纪要：`session/NILM_AC_session_complete.md`
- 本地环境：`.venv/`（Git 忽略）
