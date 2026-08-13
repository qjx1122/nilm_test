# -*- coding: utf-8 -*-
"""
算法模块统一接口 (AlgorithmModule / AlgoContext)
================================================
[v15 多算法重构] 每个算法模型 (main / rf / v14 / 未来新模型) 都是一个独立、解耦的
代码模块, 通过本文件的统一接口接入批量训练/评估/推理流水线:

    AlgorithmModule
      ├─ train_env(ctx)   / train_args(ctx)   -> 训练阶段命令与隔离环境
      ├─ eval_env(ctx)    / eval_args(ctx)    -> 测试集评估阶段
      ├─ infer_env(ctx)   / infer_args(ctx)   -> 独立生产推理阶段
      ├─ required_model_files                   -> 模型资产完整性契约 (复用判断)
      └─ artifact_subdir() / stage_algo_flag   -> 产物隔离子目录 / 阶段脚本 --algo 取值

扩展新算法 = 新增一个继承 AlgorithmModule 的模块文件 + 在 registry 注册,
流水线 / 批量调度 / 产物归档 / 指标汇总零改动即可生效。
"""
from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AlgoContext:
    """一次单用户流水线运行中, 算法模块构建各阶段命令所需的全部上下文。

    由 run_user_pipeline.py 组装; 算法模块只读, 不修改流水线状态。
    """
    project_root: Path
    user_id: str
    target_col: str
    output_dir: Path
    train_bus: str
    train_branch: str
    infer_bus: str = ""
    infer_branch: str = ""
    infer_bus_staged: str = ""      # [v17] 推理数据落地后的总线路径 (统一推理接口用)
    infer_branch_staged: str = ""   # [v17] 推理数据落地后的分路路径 (空 = 无标签推理)
    has_inference: bool = False
    force_retrain: bool = False
    exclude_dates: str = ""
    train_time_filter_spec: str = ""
    infer_time_filter_spec: str = ""
    guard_enabled: str = ""            # "" / "true" / "false"
    splits_time_filter_spec: str = ""
    common_overrides_spec: str = ""    # JSON 字符串
    v14_flags_spec: str = ""           # JSON 字符串 (仅 v14 模块消费)


class AlgorithmModule(ABC):
    """算法模块统一接口 (抽象基类)。

    子类只需声明下列类属性 / 覆盖少量方法即可完成接入:

    类属性 (必填):
      name                : 注册键 (与产物子目录同名), 如 "main" / "rf" / "v14"
      display_name        : 人类可读名称 (日志/文档用)
      train_script        : 训练入口脚本文件名 (相对 scripts/ 目录)
      eval_script         : 评估入口脚本文件名
      infer_script        : 推理入口脚本文件名
      required_model_files: 模型资产完整性契约 (相对 models/<user_id>/<name>/ 的相对路径)
      stage_algo_flag     : 透传给 04/05 阶段脚本的 --algo 取值 ("main" 或 "rf")

    可覆盖方法:
      train_env/eval_env/infer_env : 该算法各阶段需要隔离注入的环境变量 dict
                                     (隔离保证: 只对本算法的子进程生效, 不污染其他算法)
      train_args/eval_args/infer_args : 各阶段额外 CLI 参数
      artifact_subdir()             : 产物隔离子目录名 (默认 = name)

    统一访问接口 ([v17] 各模型训练推理功能统一入口, 直接调用, 无需手工拼装命令):
      train(ctx, runner=None)    -> StageResult   # 统一训练接口
      evaluate(ctx, runner=None) -> StageResult   # 统一评估接口
      infer(ctx, runner=None)    -> StageResult   # 统一推理接口 (自动组装 bus/branch/时段过滤)
    """

    name: str = ""
    display_name: str = ""
    train_script: str = ""
    eval_script: str = ""
    infer_script: str = ""
    required_model_files: tuple = ()
    stage_algo_flag: str = "main"

    # ---------- 产物隔离 ----------
    def artifact_subdir(self) -> str:
        """产物归档子目录名: artifacts/{trains,infers}/<user_id>/<artifact_subdir()>/"""
        return self.name

    # ============================================================
    # [v17] 统一训练/评估/推理访问接口
    # ============================================================
    def _make_runner(self, ctx: AlgoContext):
        """构建默认统一阶段执行器 (可注入自定义 runner 以便测试/扩展)."""
        from .runner import StageRunner
        return StageRunner(cwd=ctx.project_root / "scripts")

    def train(self, ctx: AlgoContext, runner=None) -> "StageResult":
        """[v17] 统一训练接口: 执行本算法训练阶段并返回结构化结果.

        内部组装: 训练脚本 + 算法隔离环境 (train_env) + 算法 CLI 参数 (train_args),
        经统一执行器运行; 返回 StageResult (ok / soft_skip(11/12/13) / fail).
        调用方无需感知脚本名 / 环境变量 / 参数细节.
        """
        from .runner import StageResult
        r = runner if runner is not None else self._make_runner(ctx)
        return r.run(self.train_script, args=self.train_args(ctx),
                     env=self.train_env(ctx),
                     label=f"03 训练 [{self.name}] ({self.display_name})",
                     algo=self.name, stage="train")

    def evaluate(self, ctx: AlgoContext, runner=None) -> "StageResult":
        """[v17] 统一评估接口: 执行本算法测试集评估阶段并返回结构化结果."""
        r = runner if runner is not None else self._make_runner(ctx)
        return r.run(self.eval_script, args=self.eval_args(ctx),
                     env=self.eval_env(ctx),
                     label=f"04 评估 [{self.name}] ({self.display_name})",
                     algo=self.name, stage="evaluate")

    def infer(self, ctx: AlgoContext, runner=None) -> "StageResult":
        """[v17] 统一推理接口: 执行本算法独立生产推理阶段并返回结构化结果.

        自动组装通用参数: --bus (落地推理总线) / --branch | --no-branch (落地分路)
        / --time-filter-spec (推理时段过滤), 再叠加本算法 infer_args 与隔离环境.
        前提: ctx.infer_bus_staged 已由流水线在数据落地后填充.
        """
        r = runner if runner is not None else self._make_runner(ctx)
        if not ctx.infer_bus_staged:
            from .runner import StageResult
            return StageResult(algo=self.name, stage="inference",
                               label=f"05 推理 [{self.name}]",
                               status="fail",
                               message="ctx.infer_bus_staged 为空 (推理数据未落地)")
        args = list(self.infer_args(ctx))
        args += ["--bus", ctx.infer_bus_staged]
        if ctx.infer_branch_staged:
            args += ["--branch", ctx.infer_branch_staged]
        else:
            args += ["--no-branch"]
        if ctx.infer_time_filter_spec.strip():
            args += ["--time-filter-spec", ctx.infer_time_filter_spec]
        return r.run(self.infer_script, args=args,
                     env=self.infer_env(ctx),
                     label=f"05 推理 [{self.name}] ({self.display_name})",
                     algo=self.name, stage="inference")

    # ---------- 阶段命令构建 (统一输入输出接口) ----------
    def train_env(self, ctx: AlgoContext) -> dict:
        return {}

    def eval_env(self, ctx: AlgoContext) -> dict:
        return {}

    def infer_env(self, ctx: AlgoContext) -> dict:
        return {}

    def train_args(self, ctx: AlgoContext) -> list:
        return []

    def eval_args(self, ctx: AlgoContext) -> list:
        return []

    def infer_args(self, ctx: AlgoContext) -> list:
        return []

    # ---------- 模型资产 ----------
    def model_dir(self, ctx: AlgoContext) -> Path:
        """该算法模型资产的归档目录: models/<user_id>/<artifact_subdir()>/"""
        return ctx.project_root / "models" / ctx.user_id / self.artifact_subdir()

    def top_model_dir(self, ctx: AlgoContext) -> Path:
        """阶段脚本实际加载模型的顶层目录: models/ (运行期临时槽位)"""
        return ctx.project_root / "models"

    def bundle_file_name(self, ctx: AlgoContext) -> str:
        """训练后位于 models/ 顶层的自包含 bundle 文件名.

        供流水线读取切分日期 / ON 阈值等统一接口上下文 (训练后 analyze、评估过滤).
        main/v14 共用主模型槽位名; rf 用自己的自包含 bundle.
        """
        return "nilm_ac_two_stage.pkl"

    def check_model_complete(self, ctx: AlgoContext):
        """按 required_model_files 契约检查该算法模型资产是否完整。

        返回 (complete: bool, missing: list[str], model_dir: Path)
        """
        model_dir = self.model_dir(ctx)
        missing = [f for f in self.required_model_files
                   if not (model_dir / f).exists()]
        if len(missing) == 0:
            return True, [], model_dir
        # 迁移兼容: main 算法也接受旧扁平布局 (models/<user_id>/ 直接放文件)
        if self.name == "main" and model_dir.exists() is False:
            flat = ctx.project_root / "models" / ctx.user_id
            missing_flat = [f for f in self.required_model_files
                            if not (flat / f).exists()]
            if len(missing_flat) == 0:
                return True, [], flat
        return False, missing, model_dir

    def __repr__(self):
        return f"<AlgorithmModule {self.name} ({self.display_name})>"
