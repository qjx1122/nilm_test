# STATUS.md

## 当前目标
- 按 `BOOTSTRAP.md` 恢复会话上下文与开发环境，等待用户给出下一项具体开发任务。

## 已完成
- [x] 2026-08-12 完成开局仪式：检查 Git 状态、最近提交与当前分支。
- [x] 读取 `README.md`、历史会话纪要及 `REPORT_TEST.md`。
- [x] 确认 GitHub CLI 登录和 Git 远端访问正常。
- [x] 仓库无 `setup.sh` / `pnpm` 工程，按 README 的 pip 备选流程创建 `.venv` 并安装 `requirements.txt`。
- [x] 完成环境冒烟验证：脚本编译通过；4 个自包含测试脚本共 137 个断言通过；`time_filter_utils.py` 自测通过；v6.15 守卫压力脚本执行成功。

## 进行中
- 等待用户指定本会话的具体代码、实验或分析目标。

## 下一步（TODO）
1. 收到需求后先定位相关代码和验收口径。
2. 实施改动并运行针对性测试/回归测试。
3. 按里程碑小步提交，收尾时更新本文件和会话纪要并推送固定分支。

## 决策记录 / 踩坑
- 本会话固定在 Arena 分支 `arena/019ff3f3-nilm-test`，不另建或切换分支（优先遵守会话运行环境约束）。
- 仓库没有 `setup.sh`，也不是 pnpm 项目；因此按 `README.md` / `requirements.txt` 的 pip 备选方案恢复依赖，`.venv/` 已由 `.gitignore` 忽略。
- README 推荐 Python 3.10，当前沙箱仅提供 Python 3.11.2；固定版本依赖均成功安装且自包含测试通过，但涉及历史 pickle 模型时仍需留意 Python/sklearn 兼容性。
- `scripts/test_train_infer_symmetry.py` 不是自包含单测：它硬编码依赖 `/home/user/nilm_ac_win/results_v6_15_0/...` 历史实验产物；当前仓库缺少这些外部文件，因此报 `FileNotFoundError`，不判定为代码回归。

## 关键文件路径
- 会话协议：`BOOTSTRAP.md`
- 项目手册：`README.md`
- 当前状态：`STATUS.md`
- 历史会话纪要：`session/NILM_AC_session_complete.md`
- 专题报告：`REPORT_TEST.md`
- 核心脚本：`scripts/`
- 用户配置示例：`data/time_filters.example.json`
- 本地环境：`.venv/`（Git 忽略）
