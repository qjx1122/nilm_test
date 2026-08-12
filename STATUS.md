# STATUS.md
## 当前目标
- 维护并持续沉淀项目数据输入输出结构和用户数据配置结构功能要求说明文档

## 已完成
- [x] 按照 `BOOTSTRAP.md` 规范执行开局仪式与环境依赖检查（137 项单测全部正常通过）
- [x] 深度梳理批量训练与推理的数据输入结构（Bus CSV `RE_BUS` 命名正则、Branch CSV `RE_BR` 命名正则、v9 目录分层以及 `pA+pB` 复合分路求和物化语义）
- [x] 深度梳理生成产物与指标体系结构（`models/` 打包结构、`artifacts/` 顶层白名单保护机制、25 列每日监控指标表 `inference_daily_metrics.csv`、`min_w` 最低瞬时功率扩展等）
- [x] 规范化建档用户 JSON 配置文件（`time_filter_config`）支持的六大关键模块及三重优先级解析回退链
- [x] 在 `REPORT_TEST.md` 追加完成了《NILM 空调负荷分解 — 批量训练推理数据输入输出及用户配置规范说明书》全文

## 进行中
- 处于专题交付与收尾阶段，等待接取下一步研发需求

## 下一步（TODO）
1. 接收用户的下一步指令、实验探讨或专题研究任务
2. 遵循 BOOTSTRAP.md 工作约定与收尾协议规范，持续将各专题报告分层沉淀到 `REPORT_TEST.md`
3. 严格遵守会话纪要只追加至 `session/NILM_AC_session_complete.md` 的不爆炸治理策略

## 决策记录 / 踩坑
- [2026-08-12] 遵守 BOOTSTRAP.md“会话纪要/专题报告一律写入指定文件、只追加不新建，避免文件爆炸”规则，将全量技术要求说明书沉淀在 `REPORT_TEST.md` 首个专题章节。
- [2026-08-12] 工程约束防坑重述：单用户处理层 `run_user_pipeline.py` 在启动前清理临时产物时，必须依赖白名单 `_CLEANUP_WHITELIST`（特别是 `batch_execution_state.csv` 及其 `.tmp` 原子写入文件）以避免批量层续跑状态丢失。

## 关键文件路径
- `REPORT_TEST.md` — 专题：批量训练推理数据输入输出及用户配置规范说明书
- `STATUS.md` — 进度状态与决策记录
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
- `scripts/time_filter_utils.py` — 用户配置及公共业务常量覆盖控制解析中心
- `scripts/run_batch_users.py` / `run_user_pipeline.py` — 批量控制层与单用户任务流水线层
