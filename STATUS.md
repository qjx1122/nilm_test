# STATUS.md
## 当前目标
- [v16] 针对数据输入、数据输出与数据配置功能继续重构代码：三大模块完全解耦（两两零依赖），各自提供统一访问接口；编排层（批量调度 + 单用户流水线）与阶段脚本（02/03/04/05）的数据 I/O 与配置访问全部收敛到三大模块统一入口
- [v16 验证测试] 重构完成后，对全部 5 个真实用户数据重新执行批量训练+评估+推理全流程验证（--algo-mode all 三算法遍历）

## 已完成
- [x] [v15] 多算法解耦重构（详见历史 STATUS 决策记录）：`scripts/algorithms/` 统一插件框架、03_train 训练门控、04/05 `--algo` 独立路径、流水线按算法编排、批量层算法维度汇总、time_filters `algorithms` 字段三种运行模式
- [x] [v16] 三大解耦数据模块（`data_config.py` / `data_input.py` / `data_output.py`，两两零依赖）+ 编排层/阶段脚本收敛（详见 v16 决策记录）
- [x] [v16 验证测试] 全部 5 用户 × 3 算法（main/rf/v14）批量重跑验证：**5/5 用户成功、0 软跳过、0 失败，总耗时 1694.8s（28.2 分钟）**
  - 产物体检 77/77 项通过：15 组模型资产契约齐全、三分集预测齐全、汇总表 60 行（5 用户 × 3 算法 × 4 stage）、状态表 algorithms 列正确
  - test 集关键指标（5 用户均值）：main F1=0.765/SAE=17.4%；rf F1=0.755/SAE=11.8%；v14 F1=0.769/SAE=14.7%
  - inference 集关键指标（5 用户均值）：main F1=0.873/SAE=17.2%；rf F1=0.817/SAE=3.4%；v14 F1=0.870/SAE=18.1%
  - 单用户耗时 192s~597s（均低于批量层 20 分钟/用户超时保护）
  - 产物落盘 `artifacts/`(15M) + `models/`(204M)，均被 .gitignore 隔离，不入库

## 进行中
- 收尾仪式：更新 STATUS / 会话纪要 / 专题报告，提交并推送远程

## 下一步（TODO）
1. 听取用户对三大模块接口粒度与命名（data_input/data_output/data_config）的反馈，按需调整
2. 可选：在 Word 技术方案文档中同步"数据输入/数据输出/数据配置三大解耦模块"章节
3. 后续新功能按模块归属接入：数据读取→data_input、产物写出→data_output、配置字段→data_config + time_filter_utils 实现层
4. 用户 800080270778 的 main test F1=0.502 明显偏低（个体数据差异），可作后续专题排查（可选）

## 决策记录 / 踩坑
- [2026-08-13][v16] 三大模块解耦口径：**两两零 import**。data_config 是配置底座（仅依赖 time_filter_utils/algorithms 实现层）；data_input 接受配置 dict 参数 + 惰性 import time_filter_utils（不 import data_config，避免模块级耦合）；data_output 接受算法模块与上下文参数 + 惰性 import algorithms.registry（只依赖 metrics_utils/common 实现层）。依赖方向严格单向：编排层 → 三大模块 → 底层实现层。
- [2026-08-13][v16] 统一接口设计：每个模块对外提供"门面函数 + 再导出"两层——门面函数承载业务语义（如 `stage_train_data`/`archive_algo_outputs`/`ConfigResolver.resolve`），再导出保证历史调用与底层实现（feature_utils/metrics_utils/time_filter_utils）零行为变化；阶段脚本切换 import 来源即可，语义完全等价。
- [2026-08-13][v16] 配置模块的序列化接口：`UserConfig.to_pipeline_cli()` 把已解析生效值统一序列化为流水线子进程 CLI 参数（时段过滤/守卫/splits/common 覆盖/v14/算法列表与模式），批量层不再手工拼接参数字典；`plan_line()` 保持扫描/执行阶段"算法计划"日志格式不变（冒烟断言兼容）。
- [2026-08-13][v16] 模型持久化接口：`save_model_bundle`（主文件 + 时间戳备份 + 滚动清理）与 `save_model_components`（组件 pkl + meta JSON）从 03_train 内联代码提炼，主模型/RF/v14 三类算法共用同一套落盘契约；备份豁免集合（主文件/v42 对照文件）与历史滚动清理行为完全一致。
- [2026-08-13][v16] 执行状态测试迁移：`test_batch_execution_state.py` 的导入源从 run_batch_users 改为 data_output（实现随模块迁移，测试断言不变），保证"批量执行状态"作为数据输出模块的标准接口被持续验证。
- [2026-08-13][v16] 语义保持原则：重构全程"只搬家、不改语义"——目标列反推链、时段过滤闭区间语义、白名单保护契约、汇总模型优选顺序（main/v14→main_final、rf→rf）、旧扁平布局兼容（algo=flat）等历史行为逐一保留，14 个冒烟用例 + 既有单测作为回归护栏。
- [2026-08-13][v16 验证测试] 批量验证执行方案：实测单用户三算法（main 234s + rf/v14 370s）合计约 10 分钟，低于批量层每用户 20 分钟超时保护，故采用单次 `--algo-mode all --force-retrain --continue-on-error` 全量执行；后台长任务运行 + 执行状态 CSV 增量监控进度。
- [2026-08-13][v16 验证测试] 验证结论：三大模块重构后全链路行为等价且功能完备——15 组模型资产契约、三分集预测、三算法推理指标、汇总/状态/记录三张批量表结构全部正确；rf 基线在 SAE 指标上显著优于主模型（test 11.8% vs 17.4%，inference 3.4% vs 17.2%），v14 相比 main F1 略升（test 0.765→0.769）且 test SAE 下降（17.4%→14.7%），但 inference SAE 略升（17.2%→18.1%），与历史"L5 切换与 OOD 场景"表现一致，属正常结果波动。

## 关键文件路径
- `scripts/data_config.py` — 数据配置模块（统一配置访问接口：ConfigResolver / UserConfig / 环境翻译）
- `scripts/data_input.py` — 数据输入模块（统一输入访问接口：发现/解析/加载/落地/时段过滤）
- `scripts/data_output.py` — 数据输出模块（统一输出访问接口：CSV/模型资产/归档/状态/汇总）
- `scripts/test_data_config.py` / `test_data_input.py` / `test_data_output.py` — 三模块单测（27 项）
- `scripts/algorithms/` — [v15] 多算法统一插件框架（算法维度与数据维度正交解耦）
- `scripts/run_batch_users.py` / `run_user_pipeline.py` — 编排层（已收敛到三大模块统一接口）
- `scripts/02_align_and_feat.py` / `03_train.py` / `04_evaluate.py` / `05_inference.py` — 阶段脚本（数据 I/O 已收敛）
- `artifacts/summary_metrics_all_users.csv` — [v16 验证] 全量批量汇总（60 行：5 用户 × 3 算法 × 4 stage）
- `artifacts/batch_execution_state.csv` — [v16 验证] 断点续跑状态（5 行全 ok）
- `artifacts/batch_run_summary.csv` — [v16 验证] 批量执行记录（5 行 ok，耗时 192~597s）
- `/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` — 技术方案 Word 文档（待后续同步三模块章节）
- `REPORT_TEST.md` — 专题：v16 三大模块解耦重构 + 全量批量验证测试报告
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
