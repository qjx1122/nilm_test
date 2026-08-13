# STATUS.md
## 当前目标
- [v17] 针对各模型训练推理功能继续重构代码，提供统一的访问接口：`AlgorithmModule.train/evaluate/infer` 统一训练/评估/推理接口 + `StageRunner/StageResult` 统一阶段执行器 + `train_models/evaluate_models/infer_models` 注册表级统一多模型入口；流水线不再手工拼装子进程命令，全部收敛到统一接口


## 已完成
- [x] [v15] 多算法解耦重构（详见历史 STATUS 决策记录）：`scripts/algorithms/` 统一插件框架、03_train 训练门控、04/05 `--algo` 独立路径、流水线按算法编排、批量层算法维度汇总、time_filters `algorithms` 字段三种运行模式
- [x] [v16] 三大解耦数据模块（`data_config.py` / `data_input.py` / `data_output.py`，两两零依赖）+ 编排层/阶段脚本收敛 + 全量批量验证（5/5 用户成功，产物体检 77 项通过）
- [x] [v17] 各模型训练推理功能统一访问接口：
  - `scripts/algorithms/runner.py`：`StageRunner` 统一阶段执行器（子进程隔离 + UTF-8 端到端 + 超时保护）+ `StageResult` 结构化结果（ok/soft_skip/fail 三态，`ok/is_soft_skip/is_fail/summary()` 判定接口，软跳过退出码 11/12/13 保留）
  - `base.AlgorithmModule` 新增统一接口：`train(ctx, runner=None)` / `evaluate(ctx)` / `infer(ctx)` → `StageResult`；`infer()` 自动组装 `--bus/--branch|--no-branch/--time-filter-spec` 通用参数（上下文新增 `infer_bus_staged`/`infer_branch_staged` 字段，未落地时 fail-fast）
  - `registry` 新增注册表级统一多模型入口：`train_models/evaluate_models/infer_models(names, ctx, runner)` → `dict[str, StageResult]`
  - `run_user_pipeline` 收敛：删除 `run_step` 手工命令拼装与 `_SoftSkip` 异常流，02 对齐/03 训练/04 评估/05 推理全部经由统一执行器；`StageResult` 驱动流程分支（软跳过归档 skip_reason、推理失败部分归档训练产物等语义与 v15 完全一致）
- [x] [v17] 验证：新增单测 12 项（`test_algo_runner.py`：真实子进程退出码映射/环境隔离/三算法 dispatch/推理通用参数组装/多模型入口/结果判定）全部通过；流水线 4 用例冒烟 + 软跳过路径（数据质量门 11 → 退出码 10 + skip_reason 归档）验证通过；既有 9 个单测脚本回归通过；批量层 dry-run 正常

## 进行中
- 收尾仪式：更新 STATUS / 会话纪要 / 专题报告，提交并推送远程

## 下一步（TODO）
1. 听取用户对统一训练/推理接口形态（train/evaluate/infer + StageResult）的反馈，按需调整
2. 可选：在 Word 技术方案文档中同步"各模型训练推理统一访问接口"章节
3. 可选：未来新算法接入路径已完全统一——继承 AlgorithmModule + 注册一行即可自动获得训练/推理统一接口与流水线调度能力
4. 用户 800080270778 的 main test F1=0.502 明显偏低（个体数据差异），可作后续专题排查（可选）

## 决策记录 / 踩坑
- [2026-08-13][v17] 统一接口设计：把 v15 的"配方式接口"（train_script/env/args 三件套）升级为"函数式统一访问接口"——`AlgorithmModule.train/evaluate/infer` 直接返回结构化 `StageResult`，调用方无需感知脚本名/环境变量/参数细节；`infer()` 统一组装 `--bus/--branch|--no-branch/--time-filter-spec` 通用参数，通用性收敛在基类，算法差异收敛在 `infer_args/infer_env`。
- [2026-08-13][v17] 执行与结果分离：`StageRunner`（执行底座）与 `StageResult`（结构化结果）独立成模块；退出码翻译统一（0→ok、11/12/13→soft_skip、其他→fail），子进程隔离与 UTF-8 兼容策略从流水线 run_step 原样迁移，环境注入只对本阶段子进程生效（算法间零污染契约保持）。
- [2026-08-13][v17] 异常流改结果流：流水线从 `_SoftSkip` 异常驱动改为 `StageResult` 状态驱动——软跳过/失败分支的行为语义（skip_reason 双路归档、推理失败部分归档训练产物、退出码 0/10/1 三态契约）逐一保持，但代码路径更线性、可测试（假执行器可注入验证任意状态组合）。
- [2026-08-13][v17] 可测试性：`train/evaluate/infer` 接受注入式 runner（默认按 ctx.project_root 构建），单测用假执行器录制调用即可断言脚本/参数/环境组装正确性，无需真实训练；软跳过路径用半天级小数据触发数据质量门 11 快速验证（退出码 10 + skip_reason 归档）。
- [2026-08-13][v16] 三大模块解耦口径：**两两零 import**。data_config 是配置底座（仅依赖 time_filter_utils/algorithms 实现层）；data_input 接受配置 dict 参数 + 惰性 import time_filter_utils（不 import data_config，避免模块级耦合）；data_output 接受算法模块与上下文参数 + 惰性 import algorithms.registry（只依赖 metrics_utils/common 实现层）。依赖方向严格单向：编排层 → 三大模块 → 底层实现层。
- [2026-08-13][v16] 统一接口设计：每个模块对外提供"门面函数 + 再导出"两层——门面函数承载业务语义（如 `stage_train_data`/`archive_algo_outputs`/`ConfigResolver.resolve`），再导出保证历史调用与底层实现（feature_utils/metrics_utils/time_filter_utils）零行为变化；阶段脚本切换 import 来源即可，语义完全等价。
- [2026-08-13][v16] 配置模块的序列化接口：`UserConfig.to_pipeline_cli()` 把已解析生效值统一序列化为流水线子进程 CLI 参数（时段过滤/守卫/splits/common 覆盖/v14/算法列表与模式），批量层不再手工拼接参数字典；`plan_line()` 保持扫描/执行阶段"算法计划"日志格式不变（冒烟断言兼容）。
- [2026-08-13][v16] 模型持久化接口：`save_model_bundle`（主文件 + 时间戳备份 + 滚动清理）与 `save_model_components`（组件 pkl + meta JSON）从 03_train 内联代码提炼，主模型/RF/v14 三类算法共用同一套落盘契约；备份豁免集合（主文件/v42 对照文件）与历史滚动清理行为完全一致。
- [2026-08-13][v16] 执行状态测试迁移：`test_batch_execution_state.py` 的导入源从 run_batch_users 改为 data_output（实现随模块迁移，测试断言不变），保证"批量执行状态"作为数据输出模块的标准接口被持续验证。
- [2026-08-13][v16] 语义保持原则：重构全程"只搬家、不改语义"——目标列反推链、时段过滤闭区间语义、白名单保护契约、汇总模型优选顺序（main/v14→main_final、rf→rf）、旧扁平布局兼容（algo=flat）等历史行为逐一保留，14 个冒烟用例 + 既有单测作为回归护栏。
- [2026-08-13][v16 验证测试] 批量验证执行方案：实测单用户三算法（main 234s + rf/v14 370s）合计约 10 分钟，低于批量层每用户 20 分钟超时保护，故采用单次 `--algo-mode all --force-retrain --continue-on-error` 全量执行；后台长任务运行 + 执行状态 CSV 增量监控进度。
- [2026-08-13][v16 验证测试] 验证结论：三大模块重构后全链路行为等价且功能完备——15 组模型资产契约、三分集预测、三算法推理指标、汇总/状态/记录三张批量表结构全部正确；rf 基线在 SAE 指标上显著优于主模型（test 11.8% vs 17.4%，inference 3.4% vs 17.2%），v14 相比 main F1 略升（test 0.765→0.769）且 test SAE 下降（17.4%→14.7%），但 inference SAE 略升（17.2%→18.1%），与历史"L5 切换与 OOD 场景"表现一致，属正常结果波动。

## 关键文件路径
- `scripts/algorithms/runner.py` — [v17] 统一阶段执行器（StageRunner/StageResult，各模型训练推理功能的执行底座）
- `scripts/algorithms/base.py` — 算法模块统一接口（AlgorithmModule.train/evaluate/infer 统一访问接口 + AlgoContext 上下文）
- `scripts/algorithms/registry.py` — 注册中心 + train_models/evaluate_models/infer_models 统一多模型入口
- `scripts/test_algo_runner.py` — [v17] 统一接口单测（12 项）
- `scripts/data_config.py` — 数据配置模块（统一配置访问接口：ConfigResolver / UserConfig / 环境翻译）
- `scripts/data_input.py` — 数据输入模块（统一输入访问接口：发现/解析/加载/落地/时段过滤）
- `scripts/data_output.py` — 数据输出模块（统一输出访问接口：CSV/模型资产/归档/状态/汇总）
- `scripts/test_data_config.py` / `test_data_input.py` / `test_data_output.py` — 三模块单测（27 项）
- `scripts/run_batch_users.py` / `run_user_pipeline.py` — 编排层（已收敛到算法/数据模块统一接口）
- `scripts/02_align_and_feat.py` / `03_train.py` / `04_evaluate.py` / `05_inference.py` — 阶段脚本（数据 I/O 已收敛）
- `artifacts/summary_metrics_all_users.csv` — [v16 验证] 全量批量汇总（60 行：5 用户 × 3 算法 × 4 stage）
- `artifacts/batch_execution_state.csv` — [v16 验证] 断点续跑状态（5 行全 ok）
- `artifacts/batch_run_summary.csv` — [v16 验证] 批量执行记录（5 行 ok，耗时 192~597s）
- `/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` — 技术方案 Word 文档（待后续同步统一接口章节）
- `REPORT_TEST.md` — 专题：v17 各模型训练推理统一访问接口重构报告
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
