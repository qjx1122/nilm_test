# STATUS.md
## 当前目标
- 抽离具体业务算法细节，维护适用于通用批量模型训练与推理服务框架的数据输入输出规范、用户配置架构及核心算法流程说明，并全功能生成标准项目技术方案说明 Word 文档 (`.docx`)

## 已完成
- [x] 按照 `BOOTSTRAP.md` 规范执行开局仪式与环境依赖检查
- [x] 抽离算法私有定义，深度抽象通用的双模式数据输入结构（主特征表 `RE_BUS`、真值目标表 `RE_BR`、v9 分层输入目录架构及 `pA+pB` 通用复合列物化机制）
- [x] 梳理标准通用产物分层与评估审计体系（`models/` 模型包规范、`artifacts/` 过程产物白名单保护、25 列每日监控表 `inference_daily_metrics.csv`、及分集预测表 `train_pred.csv`, `val_pred.csv`, `test_pred.csv`, `train_pred_rf.csv`, `val_pred_rf.csv`, `test_pred_rf.csv`）
- [x] 系统归纳提炼配置文件（`time_filter_config`）中六大核心参数模块（时段白黑名单裁剪、目标表达式、业务守卫开关、独立分集过滤、公共常量覆盖及环境变量透传、进阶架构开关）与三重优先级覆盖法则
- [x] 排版生成并输出项目技术方案说明 Word 文档：`/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` (55.6 KB，内含表格、着色标题与架构流程图)
- [x] 在指定专题文档 `REPORT_TEST.md` 中完成了全文同步更新沉淀

## 进行中
- 已排版生成 Word 文档并同步更新了 REPORT_TEST.md 专题报表，进入会话收尾仪式

## 下一步（TODO）
1. 听取用户针对 Word 技术方案说明文档或框架规范内容的讨论与反馈
2. 继续遵循 BOOTSTRAP.md 文档与会话纪要“只追加不新建”的约束规范沉淀历史
3. 配合后续批量训练/推理通用流水线的新增功能扩展与参数审计建档

## 决策记录 / 踩坑
- [2026-08-12] 响应用户关于“输出到项目技术方案说明 word 文档中”的要求，基于 python-docx 编写排版生成脚本 `scripts/generate_tech_spec_docx.py`，输出了高精排版的 `项目技术方案说明书_数据架构与核心算法全景规范.docx`，满足文档正式交付要求。
- [2026-08-12] 坚持工程保护白名单契约 `_CLEANUP_WHITELIST` 与无抛错降级 `WARN + Fallback` 体系，保证单任务回收不影响批处理全局状态表，保证非法配置输入不断任务，提高服务弹性。

## 关键文件路径
- `/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx` — 技术方案说明 Word 文档
- `REPORT_TEST.md` — 专题：通用批量训练与推理数据输入输出及用户配置框架规范说明书（通用抽象版·含全分集预测产物规范）
- `STATUS.md` — 项目当前状态与决策记录
- `session/NILM_AC_session_complete.md` — 全会话历史纪要
- `scripts/time_filter_utils.py` — 通用用户配置管理与时段过滤中心引擎
- `scripts/run_batch_users.py` / `run_user_pipeline.py` — 批量调度层与流水线执行引擎
