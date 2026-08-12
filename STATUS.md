# STATUS.md

## 当前目标
- 已完成：针对用户 `800080270789_4206680982373` 执行固定 holdout 优化验证，完成 frozen/train-only 特征、raw/L4/L5、有界 Stage-2 乘性校正和 7 月高功率标签消融；固化 train-only 特征选择/LUT 修复。联合验收仍未通过（共同推理最佳 F1 约 84.5% < 90%）。

## 已完成
- [x] 2026-08-12 完成开局仪式、`.venv` 依赖恢复和 GitHub/远端检查。
- [x] 核验两份配置唯一差异：目标用户 `800080270789_4206680982373` 首段训练 include / 推理 exclude 的结束日期由 2026-06-04 延长至 2026-06-06。
- [x] 发现并修复 `common.py` 同秒等长改写后 pyc 缓存导致子进程误读旧 `TARGET_COL` 的问题；新增子进程缓存回归测试。
- [x] 删除受污染的预跑产物，使用 `--force-retrain` 和两个隔离输出目录完整重跑：v14-new 5/5 成功、579.8 秒；v14-new-test 5/5 成功、589.0 秒；均无软跳过或失败。
- [x] 核验两套状态表各 5 行全 `ok`、汇总表各 20 行；未变化 4 用户的 8 对训练/推理每日 CSV SHA-256 全部一致。
- [x] 完成 318+318 个用户日指标筛选：v14-new 原始命中 117（有效异常 94）；v14-new-test 原始命中 119（有效异常 92）。全部命中日期及指标、覆盖和归因已追加到 `REPORT_TEST.md`。
- [x] 完成目标用户与总体对比：测试配置使目标用户推理 F1 74.39%→81.67%，但 SAE 10.30%→23.39%、MAE 344.24→378.53 W；结论为分类改善、回归退化，不能作为无条件优胜配置。
- [x] 完成最终回归：4 个自包含测试脚本共 140/140 断言通过；`time_filter_utils.py` 自测、v6.15 守卫压力脚本、`compileall` 和 `git diff --check` 均通过。
- [x] 新增 0789 固定切分反事实实验：保留两个全关 hard negative，但固定原有 30 天的 split，仅把 06-05/06-06 锚定 train；1/1 成功，耗时 111.5 秒。
- [x] 固定切分模型在共同 22 个推理日达到 F1 84.07%、SAE 11.15%、MAE 283.26 W，显著优于自动重排模型的 81.67%/23.39%/378.53 W；证明主要退化来自 split/特征/Stage-2 联动，而不是全关日不可用。
- [x] 重放原配置基线并核验训练、推理每日 CSV SHA-256 与原运行完全一致；完成 ON/OFF 能耗拆分，确认原 SAE 1.14% 是 ON 低估 -73.28 kWh 与 OFF 误报 +76.60 kWh 偶然抵消。
- [x] 定位结构性原因：新增 OFF 日使 Top-3 相关性排名翻转并替换 16 个 Stage-2 派生特征；自动切分替换 104/101 个 ON 样本；P50 树模型对 ≥1400 W OOD 功率严重压缩；L4 ±150 W 和同源 fallback 的 L5 不能稳定修复。
- [x] 在固定 val 上拟合候选乘性校正系数 1.1138；独立固定 test 的 raw SAE 8.67%→1.72%，共同推理 raw SAE 9.99%→0.25%、MAE 283.63→265.02 W。结论及实施顺序已追加到 `REPORT_TEST.md`。
- [x] 完成 E0/E1/E2/E4 固定共同 2112 点消融：final F1 为 78.66%/84.07%/83.98%/83.74%，MAE 为 325.22/283.26/285.67/273.15 W，SAE 为 1.14%/11.15%/10.80%/7.92%。
- [x] 核验冻结旧 E0 manifest 的 E2 无收益；实现并验证 E4 train-only Top-25 与 train-only 温度功率 LUT，模型元数据记录拟合来源和 20 个 train 日期。
- [x] 在固定 validation/test/common inference 上完成 raw/L4/L5 比较：L4 在拟合 val 上 MAE 193.74→144.81 W，但独立 test 反向恶化到 202.33 W；同源 L5 也无稳定收益，raw 是跨集更稳健层。
- [x] 仅用 E4 validation 拟合 `[0.85,1.15]` 有界乘数 1.1159627；test SAE 8.41%→2.21%但 MAE 198.97→201.10 W，共同 inference SAE 6.68%→4.14%、MAE 273.91→257.23 W；因 ON -46.47 kWh 与 OFF +58.47 kWh 仍抵消，未接入生产。
- [x] 完成 E3 高功率 P2：07-08~10 加入 train 后，公平 19 日 final MAE 284.22→252.32 W，高功率桶显著改善；但 F1 81.48%→81.23%、SAE 6.67%→17.47%，固定 test F1 跌至 88.03%，故朴素混入不通过。
- [x] 固化 `scripts/03_train.py` 的 train-only 特征/LUT 和严格 frozen manifest 开关；新增 `scripts/test_fixed_top_cols.py`。最终 141/141 自包含断言、编译和 diff 检查通过。

## 进行中
- 无；本轮优化验证、代码固化和专题报告已完成。

## 下一步（TODO）
1. P1：把固定 split 日期自动持久化为每用户 manifest，并将 Stage-1 全量 train 与 Stage-2 train-ON 的样本/特征视图彻底分离。
2. P1：把 `ON_energy_bias_kWh`、`OFF_false_energy_kWh`、ON-only MAE 写入标准 train/test/inference 汇总；层校正需再拆 calibration/selection validation 或交叉拟合。
3. P2：07-08~10 高功率标签只供 Stage-2，比较功率桶重加权、Huber/平方损失、独立高功率专家或单调分段校正，避免再次扰动 Stage-1 阈值。
4. P2：继续增加按 p3/p4 干扰类型平衡的 hard negatives，或引入 nuisance-load 辅助模型；当前阈值扫描 F1 上限约 84.5%，单纯调阈值无法达到 90%。
5. 后续再处理用户 `800080270800_4200904302272` 的大量全关误报和推理 SAE 93.97%。

## 决策记录 / 踩坑
- 本会话固定在 Arena 分支 `arena/019ff3f3-nilm-test`，不另建或切换分支（优先遵守会话运行环境约束）。
- 两配置使用不同指标/预测输出目录且均启用 `--force-retrain`；最终结果只采用修复 pyc 缓存问题后的完整重跑。
- 不能仅凭批量 exit 0 判断有效性。首次第二套预跑中，未变化用户 `800080252844_4206894986488` 的对齐样本 2734→1152、推理 F1 97.44%→0；原始分路核对证明实际误读默认 `p1` 而非配置 `p2`。修复后两套均对齐 2734 个 `p2` 样本且结果逐字节一致。
- `TP=FP=FN=0` 时当前 CSV 将 F1 记为 0；报告保留这些阈值命中日，但明确 F1 不适用且不计为模型失败。v14-new 的 117 个原始命中含 23 个此类日期，v14-new-test 的 119 个含 27 个。
- 数据缺失不是主要异常来源：两套各仅 1 个有效异常日覆盖不足，均为用户 `800080252842_4206894986488` 的 2026-06-05 推理日（76 个对齐样本）。
- 目标用户新增两天后 `stratified_day` 还重排了 5 个既有日期的 split，因此 val/test 前后值并非固定评估集上的纯模型 A/B；推理共同 22 天对比才用于拆分口径与模型效应。
- pooled SAE 会让不同用户的正负误差抵消：测试配置 pooled 推理 SAE 看似 6.12%→5.15%，但 5 用户宏平均 SAE 实际 26.08%→28.70%，目标用户本身也明显恶化。
- 0789 的原配置在共同推理日也存在同类抵消：真实 ON 低估 73.28 kWh、真实 OFF 误报多算 76.60 kWh，净 SAE 才呈现 1.14%。因此优化验收必须同时看 ON 能耗偏差和 OFF 虚假能耗，不能只看净 SAE。
- 06-05/06-06 是有效 hard negative：`p1+p2` 完整全零，但 p3/p4 分别消耗 5.62/13.10 与 7.51/8.61 kWh，总线信号接近真实 ON；应保留给分类器，而不是混入 Stage-2 特征选择和 ON 回归数据视图。
- 固定 split 反事实是本次核心决策：C 相比 B 在相同新增数据下只改变 split 归属，故 C→B 的 F1 -2.40pp、SAE +12.24pp、MAE +95.28 W 可归因于切分重排及其后续 Stage-2/L4 变化。
- 当前相关性 Top-K 在 split 前用全量标签拟合，新增 OFF 日使相关性排名变化并替换 16 个 Top-3 派生特征，存在标签泄漏和增量不稳定；本轮已改为先解析最终 split，再仅用 train 拟合 Top-25 和温度功率 LUT。Stage-2 ON-only 选择器仍待实现。
- 不能把旧全量相关性 manifest 当成正确答案：E2 冻结 E0 特征后 F1/MAE 均比 E1 略差。保留 frozen manifest 能力是为了可复现实验；默认生产路径采用 train-only 动态选择并持久化结果。
- 当前 L5 fallback 与 summer expert 在此用户上同源同算法（全部训练样本均为 summer），不构成真正模型多样性；E4 固定 val 的 50/50 代理位于 raw/L4 之间，独立 test/inference 仅改善 0.52/0.76 W MAE且 SAE 更差，不推荐据此启用同源混合。
- L4 使用同一 validation 拟合和报告会产生明显乐观偏差：E4 val MAE 改善 48.93 W，但独立 test 恶化 3.36 W。后续层选择必须另设 selection fold 或交叉拟合。
- 有界乘性校正只通过了独立 test 的净 SAE 验证，未通过 ON/OFF 分项验收；共同 inference 仍为 ON -46.47 kWh、OFF +58.47 kWh，故不接入 bundle。
- 高功率标签方向必要但不能朴素混入统一训练：E3 高档预测显著改善，却使固定 test F1 降至 88.03%。下一轮高功率日只允许进入 Stage-2，并进行分桶权重控制。
- 仓库没有 `setup.sh`，按 README / `requirements.txt` 使用 `.venv`。当前 Python 3.11.2 与 README 推荐 3.10 不同，固定依赖和现有自包含测试均通过。
- `scripts/test_train_infer_symmetry.py` 硬编码依赖仓库外历史产物，当前缺失导致 `FileNotFoundError`，不判定为源码回归。

## 关键文件路径
- 专题报告（含全部 236 个阈值命中行）：`REPORT_TEST.md`
- 两份配置：`data/time_filters-5User-v14-new.json`、`data/time_filters-5User-v14-new-test.json`
- 修复代码/回归：`scripts/run_user_pipeline.py`、`scripts/test_composite_target_col.py`
- 最终隔离产物：`artifacts/validation_v14_new/`、`artifacts/validation_v14_new_test/`
- 0789 因果实验（历史）：`artifacts/analysis_0789_fixed_split_alloff/`、`artifacts/analysis_0789_baseline_replay/`
- 0789 本轮优化实验：`artifacts/validation_0789_opt_baseline/`、`validation_0789_opt_fixed_split/`、`validation_0789_opt_fixed_features/`、`validation_0789_opt_train_features/`、`validation_0789_opt_high_power/`
- 本轮代码：`scripts/03_train.py`、`scripts/test_fixed_top_cols.py`
- 最终批量日志：`logs/_batch/batch_run_20260812_033731.log`、`logs/_batch/batch_run_20260812_034712.log`
- 因果实验日志：`logs/_batch/batch_run_20260812_041238.log`、`logs/_batch/batch_run_20260812_041533.log`
- 会话纪要：`session/NILM_AC_session_complete.md`
- 本地环境：`.venv/`（Git 忽略）
