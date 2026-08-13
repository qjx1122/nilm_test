# STATUS.md
## 当前目标
- [v15] 代码重构：各功能模块解耦隔离；新增多算法模型支撑能力（main/RF/v14 三类算法代码模块解耦隔离，统一输入输出接口）；开放配置入口支持三种自定义运行模式（指定单模型 single / 多模型选择性 multi / 全部模型遍历 all）；产物输出按算法维度子目录隔离归档

## 已完成
- [x] [v15] 新增 `scripts/algorithms/` 多算法统一插件框架：
  - `base.py`：`AlgorithmModule` 抽象基类 + `AlgoContext` 上下文（统一输入输出接口：train/eval/infer 三阶段脚本、隔离环境变量、CLI 参数、模型完整性契约、产物子目录、bundle 文件名契约）
  - `main_l4.py` / `rf_baseline.py` / `v14_enhanced.py`：三类算法模块，后续新算法仅需继承基类 + 注册即可接入
  - `registry.py`：注册表 + `resolve_algorithm_selection()` 三种运行模式统一解析（优先级：CLI > time_filters 配置 > 内置默认 main+rf）
- [x] [v15] 训练解耦门控：`03_train.py` 支持 `NILM_ALGO_SELECT`（main / rf / main+rf），主模型与 RF 基线完全独立训练；rf 产出自包含 `rf_bundle.pkl`（统一接口上下文齐备）；默认 main+rf 行为与重构前完全一致（向后兼容）
- [x] [v15] 评估/推理解耦：`04_evaluate.py` / `05_inference.py` 支持 `--algo main|rf` 独立路径 + `--no-baseline` 隔离基线对比；main-only bundle 中 `rf` 键为 None 的防御处理
- [x] [v15] v14 特征一致性契约：v14 物理指纹特征环境变量在训练/评估/推理三阶段一致注入（修复 137 vs 170 特征维度不匹配）
- [x] [v15] 流水线编排重构：`run_user_pipeline.py` 按算法序列逐个执行（训练/复用→评估→推理→按算法归档），算法间故障隔离（单算法软跳过/硬失败不阻塞其他算法；05 失败时部分归档训练侧产物），退出码 0=≥1 算法成功 / 10=全部软跳过 / 1=无算法成功
- [x] [v15] 产物输出结构：算法维度子目录隔离归档
  - `models/<user_id>/<algo>/`：各算法模型资产互不覆盖
  - `artifacts/trains/<user_id>/<algo>/`：训练评估 metrics + 预测 + plots
  - `artifacts/infers/<user_id>/<algo>/`：推理 metrics + 预测 + plots
  - 用户级数据视图（train/infer_on_periods*.csv）保持原位置；旧扁平布局聚合兼容（algo=flat）
- [x] [v15] 批量层改造：`run_batch_users.py` 新增 `--algorithms` / `--algo-mode` CLI 透传；扫描阶段即解析每用户算法计划（dry-run 可见）；`summary_metrics_all_users.csv` 新增 `algo` 列（每用户×每算法 4 行）；`skipped_users.csv` 按算法维度收集；`batch_execution_state.csv` 新增 `algorithms` 列
- [x] [v15] 配置入口：`time_filter_utils.py` 新增 `get_user_algorithms_config` / `get_user_algorithms_selection`（用户级 + `_default` 回退，与既有字段同语义）；`data/time_filters.example.json` 增加 `algorithms` 字段示例与说明
- [x] 验证：单元测试 24 项（注册框架 13 + 配置解析 11）+ 合成数据冒烟 14 用例（03 训练门控 3、04/05 双链路 2、流水线编排 4、批量层 5）全部通过；既有 4 个单测脚本无回归；真实数据 5 用户 dry-run 扫描正常

## 进行中
- 收尾仪式：更新 STATUS / 会话纪要 / 专题报告，提交并推送远程

## 下一步（TODO）
1. 听取用户对多算法重构、配置字段与产物目录结构的反馈，按需微调
2. 可选：在 Word 技术方案文档中同步“多算法运行模式与算法维度产物体系”章节
3. 后续按统一接口扩展新算法（继承 `AlgorithmModule` + 注册即可）

## 决策记录 / 踩坑
- [2026-08-13][v15] 多算法“解耦隔离”的实现口径：算法隔离落在四个层面——(1) 代码模块隔离（`scripts/algorithms/` 每算法一个模块文件）；(2) 训练门控隔离（`NILM_ALGO_SELECT` 让 03_train 只训指定算法，rf 产出独立自包含 bundle）；(3) 运行环境隔离（每算法子进程独立 env，v14 的 monkey-patch 不再泄漏到其他算法）；(4) 产物隔离（models/artifacts 按 `<algo>` 子目录归档）。这样即使 main 与 v14 共用主模型槽位，两者产物也互不覆盖。
- [2026-08-13][v15] 三种运行模式语义：`single`=selected 取第一个；`multi`=selected 列表原样执行；`all`=注册表全部算法按注册顺序遍历（忽略 selected）。优先级 CLI > time_filters `algorithms` 字段 > 内置默认（main+rf，与重构前行为一致）。无显式配置且用户 v14 增强开关开启时，默认列表自动追加 v14（兼容旧 `--v14-flags` 语义）。
- [2026-08-13][v15] 多算法顺序执行时的共享状态治理：`aligned_15min.csv` / `merged_*.csv` / `infer_*.csv` / `skip_reason.json` 从“单算法用完即清”改为“执行期保留（`_CLEANUP_WHITELIST`）+ 流水线收尾统一清理”，否则后序算法训练/推理会因共享文件被前序算法归档清理而崩溃（冒烟测试实测踩坑）。
- [2026-08-13][v15] v14 特征一致性契约：`build_features` 依赖 `NILM_V14_*` 环境变量决定是否注入物理指纹特征，若只在训练阶段注入会导致评估阶段特征维度不匹配（训练 170 维 vs 评估 137 维），故 v14 模块在 train/eval/infer 三阶段注入相同环境。
- [2026-08-13][v15] 算法间故障隔离与退出码契约：单算法失败不阻塞其他算法；流水线退出码 0=≥1 算法成功、10=全部算法软跳过（数据质量门）、1=无算法成功。批量层状态表记录本次 `algorithms` 计划，汇总表以 `algo` 列区分各算法指标（inference 阶段模型优选：main/v14→main_final，rf→rf）。

## 关键文件路径
- `scripts/algorithms/` — 多算法统一插件框架（base/registry + main_l4/rf_baseline/v14_enhanced 三个算法模块）
- `scripts/test_algorithm_registry.py` / `scripts/test_algo_config.py` — 框架与配置单测（24 项）
- `scripts/03_train.py` — 训练解耦门控 `NILM_ALGO_SELECT`（main/rf/main+rf）
- `scripts/04_evaluate.py` / `scripts/05_inference.py` — `--algo main|rf` 独立评估/推理路径
- `scripts/run_user_pipeline.py` — 多算法编排（按算法序列执行 + 故障隔离 + 按算法归档）
- `scripts/run_batch_users.py` — 批量调度（`--algorithms`/`--algo-mode` 透传 + 算法维度汇总）
- `scripts/time_filter_utils.py` — 配置引擎（新增 algorithms 字段解析）
- `data/time_filters.example.json` — 配置示例（含 algorithms 三种模式示例）
- `/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` — 技术方案 Word 文档（待后续同步多算法章节）
- `REPORT_TEST.md` — 专题：v15 多算法解耦重构专题报告
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
