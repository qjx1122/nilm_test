# STATUS.md
## 当前目标
- [v16] 针对数据输入、数据输出与数据配置功能继续重构代码：三大模块完全解耦（两两零依赖），各自提供统一访问接口；编排层（批量调度 + 单用户流水线）与阶段脚本（02/03/04/05）的数据 I/O 与配置访问全部收敛到三大模块统一入口

## 已完成
- [x] [v15] 多算法解耦重构（详见历史 STATUS 决策记录）：`scripts/algorithms/` 统一插件框架、03_train 训练门控、04/05 `--algo` 独立路径、流水线按算法编排、批量层算法维度汇总、time_filters `algorithms` 字段三种运行模式
- [x] [v16] 新增三大解耦数据模块（两两零 import 依赖，`scripts/data_config.py` / `data_input.py` / `data_output.py`）：
  - **数据配置模块 data_config**：`ConfigResolver`（配置 + CLI 覆盖 → `UserConfig` 每用户生效配置对象）、`UserConfig`（统一序列化接口 `to_pipeline_cli()`/`plan_line()`/各 `*_cli()`）、配置→运行环境翻译接口（`common_overrides_to_env`/`guard_cli_to_env`/`v14_flags_to_env`/`splits_spec_cli_to_env`）、time_filter_utils 底层实现门面再导出
  - **数据输入模块 data_input**：命名契约 `RE_BUS/RE_BR`、`parse_data_dir`/`parse_user_folder`/`discover_users`（含配置 target_col 优先与 Ch{N} 反推链）、`is_runnable`/`get_execution_plan`、原始加载门面（load_bus_csv/load_branch_csv/resample_and_align）、运行时落地 `stage_train_data`/`stage_infer_data`/`cleanup_staged_data_files`、时段过滤统一入口 `parse_time_filter_spec`/`apply_time_filter_spec`
  - **数据输出模块 data_output**：统一 CSV 写出 `write_csv`、预测/指标写出门面（metrics_utils 再导出）、模型资产持久化（`resolve_model_path`/`load_model_bundle`/`save_model_bundle` 含备份滚动清理/`save_model_components`）、归档清理（`archive_algo_outputs`/`cleanup_artifacts_top`/`restore_algo_models_to_top`/`check_algo_model_complete`）、批量状态（执行状态 CSV 四函数）与汇总（`aggregate_metrics`/`collect_skip_reasons`）
- [x] [v16] 编排层收敛：`run_batch_users.py` 删去内联的发现/解析/状态/汇总/配置解析代码，全部走三大模块（每用户配置经 `resolver.resolve()` → `UserConfig`）；`run_user_pipeline.py` 删去内联的数据落地/归档/清理/配置翻译代码，数据落地走 data_input、归档走 data_output、配置→环境翻译走 data_config
- [x] [v16] 阶段脚本收敛：02（加载/时段过滤）、03（指标写出 + 模型 bundle/组件持久化 + 原始数据加载）、04/05（指标写出 + rf 模型路径解析 + 05 时段过滤）全部改走统一接口
- [x] [v16] 验证：新增单测 27 项（data_config 10 + data_input 8 + data_output 9）全部通过；既有单测（执行状态/复合目标列/日级原始点数/min_w 列/算法注册/配置解析）回归通过；全链路冒烟回归通过（03 训练门控 3 用例、04/05 双链路 2 用例、流水线编排 4 用例、批量层 5 用例）
- [x] 三模块解耦关系核验：两两零 import 依赖；依赖方向仅指向底层实现层（feature_utils/metrics_utils/time_filter_utils/common）

## 进行中
- 收尾仪式：更新 STATUS / 会话纪要 / 专题报告，提交并推送远程

## 下一步（TODO）
1. 听取用户对三大模块接口粒度与命名（data_input/data_output/data_config）的反馈，按需调整
2. 可选：在 Word 技术方案文档中同步“数据输入/数据输出/数据配置三大解耦模块”章节
3. 后续新功能按模块归属接入：数据读取→data_input、产物写出→data_output、配置字段→data_config + time_filter_utils 实现层

## 决策记录 / 踩坑
- [2026-08-13][v16] 三大模块解耦口径：**两两零 import**。data_config 是配置底座（仅依赖 time_filter_utils/algorithms 实现层）；data_input 接受配置 dict 参数 + 惰性 import time_filter_utils（不 import data_config，避免模块级耦合）；data_output 接受算法模块与上下文参数 + 惰性 import algorithms.registry（只依赖 metrics_utils/common 实现层）。依赖方向严格单向：编排层 → 三大模块 → 底层实现层。
- [2026-08-13][v16] 统一接口设计：每个模块对外提供"门面函数 + 再导出"两层——门面函数承载业务语义（如 `stage_train_data`/`archive_algo_outputs`/`ConfigResolver.resolve`），再导出保证历史调用与底层实现（feature_utils/metrics_utils/time_filter_utils）零行为变化；阶段脚本切换 import 来源即可，语义完全等价。
- [2026-08-13][v16] 配置模块的序列化接口：`UserConfig.to_pipeline_cli()` 把已解析生效值统一序列化为流水线子进程 CLI 参数（时段过滤/守卫/splits/common 覆盖/v14/算法列表与模式），批量层不再手工拼接参数字典；`plan_line()` 保持扫描/执行阶段"算法计划"日志格式不变（冒烟断言兼容）。
- [2026-08-13][v16] 模型持久化接口：`save_model_bundle`（主文件 + 时间戳备份 + 滚动清理）与 `save_model_components`（组件 pkl + meta JSON）从 03_train 内联代码提炼，主模型/RF/v14 三类算法共用同一套落盘契约；备份豁免集合（主文件/v42 对照文件）与历史滚动清理行为完全一致。
- [2026-08-13][v16] 执行状态测试迁移：`test_batch_execution_state.py` 的导入源从 run_batch_users 改为 data_output（实现随模块迁移，测试断言不变），保证"批量执行状态"作为数据输出模块的标准接口被持续验证。
- [2026-08-13][v16] 语义保持原则：重构全程"只搬家、不改语义"——目标列反推链、时段过滤闭区间语义、白名单保护契约、汇总模型优选顺序（main/v14→main_final、rf→rf）、旧扁平布局兼容（algo=flat）等历史行为逐一保留，14 个冒烟用例 + 既有单测作为回归护栏。

## 关键文件路径
- `scripts/data_config.py` — 数据配置模块（统一配置访问接口：ConfigResolver / UserConfig / 环境翻译）
- `scripts/data_input.py` — 数据输入模块（统一输入访问接口：发现/解析/加载/落地/时段过滤）
- `scripts/data_output.py` — 数据输出模块（统一输出访问接口：CSV/模型资产/归档/状态/汇总）
- `scripts/test_data_config.py` / `test_data_input.py` / `test_data_output.py` — 三模块单测（27 项）
- `scripts/algorithms/` — [v15] 多算法统一插件框架（算法维度与数据维度正交解耦）
- `scripts/run_batch_users.py` / `run_user_pipeline.py` — 编排层（已收敛到三大模块统一接口）
- `scripts/02_align_and_feat.py` / `03_train.py` / `04_evaluate.py` / `05_inference.py` — 阶段脚本（数据 I/O 已收敛）
- `scripts/time_filter_utils.py` — 数据配置底层实现层（字段语义与降级链）
- `scripts/feature_utils.py` / `metrics_utils.py` — 数据输入/输出底层实现层
- `/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` — 技术方案 Word 文档（待后续同步三模块章节）
- `REPORT_TEST.md` — 专题：v16 数据输入/输出/配置三大模块解耦重构报告
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
