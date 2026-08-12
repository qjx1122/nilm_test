# STATUS.md

## 当前目标
- 已完成：分别以 `data/time_filters-5User-v14-new.json` 与 `data/time_filters-5User-v14-new-test.json` 对 5 用户执行隔离、强制重训验证，并对所有每日 `F1 < 0.90` 或 `SAE > 0.20` 的记录完成逐日归因与配置对比。

## 已完成
- [x] 2026-08-12 完成开局仪式、`.venv` 依赖恢复和 GitHub/远端检查。
- [x] 核验两份配置唯一差异：目标用户 `800080270789_4206680982373` 首段训练 include / 推理 exclude 的结束日期由 2026-06-04 延长至 2026-06-06。
- [x] 发现并修复 `common.py` 同秒等长改写后 pyc 缓存导致子进程误读旧 `TARGET_COL` 的问题；新增子进程缓存回归测试。
- [x] 删除受污染的预跑产物，使用 `--force-retrain` 和两个隔离输出目录完整重跑：v14-new 5/5 成功、579.8 秒；v14-new-test 5/5 成功、589.0 秒；均无软跳过或失败。
- [x] 核验两套状态表各 5 行全 `ok`、汇总表各 20 行；未变化 4 用户的 8 对训练/推理每日 CSV SHA-256 全部一致。
- [x] 完成 318+318 个用户日指标筛选：v14-new 原始命中 117（有效异常 94）；v14-new-test 原始命中 119（有效异常 92）。全部命中日期及指标、覆盖和归因已追加到 `REPORT_TEST.md`。
- [x] 完成目标用户与总体对比：测试配置使目标用户推理 F1 74.39%→81.67%，但 SAE 10.30%→23.39%、MAE 344.24→378.53 W；结论为分类改善、回归退化，不能作为无条件优胜配置。
- [x] 完成最终回归：4 个自包含测试脚本共 140/140 断言通过；`time_filter_utils.py` 自测、v6.15 守卫压力脚本、`compileall` 和 `git diff --check` 均通过。

## 进行中
- 无；本次验证专题已完成并固化。

## 下一步（TODO）
1. 若继续优化目标用户，先固定 train/val/test 日期集合，再单独调优 Stage-2 功率回归，避免 `stratified_day` 重排混入 A/B 结论。
2. 优先处理用户 `800080270800_4200904302272` 的大量全关误报和推理 SAE 93.97%。
3. 考虑将无正类日的 F1 输出为 N/A，或增加 `f1_applicable` 字段，避免 `TP=FP=FN=0` 的正确全关日被机械筛为异常。

## 决策记录 / 踩坑
- 本会话固定在 Arena 分支 `arena/019ff3f3-nilm-test`，不另建或切换分支（优先遵守会话运行环境约束）。
- 两配置使用不同指标/预测输出目录且均启用 `--force-retrain`；最终结果只采用修复 pyc 缓存问题后的完整重跑。
- 不能仅凭批量 exit 0 判断有效性。首次第二套预跑中，未变化用户 `800080252844_4206894986488` 的对齐样本 2734→1152、推理 F1 97.44%→0；原始分路核对证明实际误读默认 `p1` 而非配置 `p2`。修复后两套均对齐 2734 个 `p2` 样本且结果逐字节一致。
- `TP=FP=FN=0` 时当前 CSV 将 F1 记为 0；报告保留这些阈值命中日，但明确 F1 不适用且不计为模型失败。v14-new 的 117 个原始命中含 23 个此类日期，v14-new-test 的 119 个含 27 个。
- 数据缺失不是主要异常来源：两套各仅 1 个有效异常日覆盖不足，均为用户 `800080252842_4206894986488` 的 2026-06-05 推理日（76 个对齐样本）。
- 目标用户新增两天后 `stratified_day` 还重排了 5 个既有日期的 split，因此 val/test 前后值并非固定评估集上的纯模型 A/B；推理共同 22 天对比才用于拆分口径与模型效应。
- pooled SAE 会让不同用户的正负误差抵消：测试配置 pooled 推理 SAE 看似 6.12%→5.15%，但 5 用户宏平均 SAE 实际 26.08%→28.70%，目标用户本身也明显恶化。
- 仓库没有 `setup.sh`，按 README / `requirements.txt` 使用 `.venv`。当前 Python 3.11.2 与 README 推荐 3.10 不同，固定依赖和现有自包含测试均通过。
- `scripts/test_train_infer_symmetry.py` 硬编码依赖仓库外历史产物，当前缺失导致 `FileNotFoundError`，不判定为源码回归。

## 关键文件路径
- 专题报告（含全部 236 个阈值命中行）：`REPORT_TEST.md`
- 两份配置：`data/time_filters-5User-v14-new.json`、`data/time_filters-5User-v14-new-test.json`
- 修复代码/回归：`scripts/run_user_pipeline.py`、`scripts/test_composite_target_col.py`
- 最终隔离产物：`artifacts/validation_v14_new/`、`artifacts/validation_v14_new_test/`
- 最终批量日志：`logs/_batch/batch_run_20260812_033731.log`、`logs/_batch/batch_run_20260812_034712.log`
- 会话纪要：`session/NILM_AC_session_complete.md`
- 本地环境：`.venv/`（Git 忽略）
