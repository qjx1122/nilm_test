# -*- coding: utf-8 -*-
"""
[v17] 统一阶段执行器 (StageRunner / StageResult)
================================================
各模型训练/推理功能的统一执行底座: 算法模块的 train()/evaluate()/infer()
统一访问接口通过本执行器运行阶段脚本 (子进程隔离, 保证算法间环境零污染),
并把退出码翻译为结构化结果 StageResult:

    0            -> status = "ok"          (真成功)
    11 / 12 / 13 -> status = "soft_skip"   (数据质量门软跳过, 非错误)
    其他 / 异常    -> status = "fail"        (真异常)

对外统一接口:
    SOFT_SKIP_CODES          : 软跳过退出码集合 (11=对齐过少 / 12=单类 / 13=val/test 空)
    StageResult              : 结构化阶段结果 (ok/is_soft_skip/is_fail 判定属性)
    StageRunner              : 统一阶段执行器
      .run(script, args, env, label, ...) -> StageResult

设计原则:
  - UTF-8 端到端 (PYTHONIOENCODING=utf-8 注入 + errors=replace), Windows GBK 兼容
  - 算法隔离环境: env dict 只对本阶段子进程生效, 不污染其他算法
  - 失败/软跳过均打印子进程日志末尾, 不做黑盒
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

# 软跳过退出码 (03_train.py 数据质量门): 11=对齐过少 / 12=单类标签 / 13=val/test 空
SOFT_SKIP_CODES = (11, 12, 13)


@dataclass
class StageResult:
    """一次训练/评估/推理阶段执行的结构化结果 (统一访问接口返回对象)."""
    algo: str = ""                # 算法名 (main/rf/v14; 非算法步骤可为空)
    stage: str = ""               # 阶段名: train / evaluate / inference / align
    label: str = ""               # 人类可读步骤名 (日志用)
    status: str = "fail"          # "ok" / "soft_skip" / "fail"
    exit_code: int = 1            # 子进程退出码 (soft_skip 时保留 11/12/13)
    message: str = ""             # 结果摘要 (失败原因/跳过原因)
    duration_s: float = 0.0
    stdout_tail: str = ""         # 子进程输出末尾 (诊断用)

    # ---------- 判定属性 (统一语义) ----------
    @property
    def ok(self) -> bool:
        return self.status == "ok"

    @property
    def is_soft_skip(self) -> bool:
        return self.status == "soft_skip"

    @property
    def is_fail(self) -> bool:
        return self.status == "fail"

    def summary(self) -> str:
        """单行人类可读摘要 (批量/流水线日志用)."""
        icon = "✓" if self.ok else ("◐" if self.is_soft_skip else "✗")
        tail = f" | {self.message}" if self.message else ""
        return (f"    {icon} [{self.label or f'{self.algo}/{self.stage}':<8}] "
                f"{self.status}{tail}  ({self.duration_s:.1f}s)")

    def __repr__(self):
        return (f"<StageResult algo={self.algo!r} stage={self.stage!r} "
                f"status={self.status!r} code={self.exit_code}>")


class StageRunner:
    """[v17] 统一阶段执行器: 以子进程方式运行阶段脚本并返回 StageResult.

    统一访问接口 (算法模块 train/evaluate/infer 及流水线共享步骤均经由本执行器):
      runner.run(script, args=["--a", "1"], env={"NILM_X": "1"}, label="03 训练 [main]")
    """

    def __init__(self, python: str = None, cwd: Union[str, Path] = None,
                 timeout: float = 1200.0, log_file: Union[str, Path] = None):
        """
        Args:
            python:   解释器路径 (默认 sys.executable, 跨平台兼容)
            cwd:      子进程工作目录 (默认 None = 继承当前)
            timeout:  子进程超时秒数 (默认 1200s, 与批量层一致)
            log_file: 可选, 子进程 stdout/stderr 追加写入的日志文件
        """
        self.python = python or sys.executable
        self.cwd = str(cwd) if cwd is not None else None
        self.timeout = timeout
        self.log_file = str(log_file) if log_file is not None else None

    # ---------- 统一执行入口 ----------
    def run(self, script: str, args: Optional[List[str]] = None,
            env: Optional[Dict[str, str]] = None,
            label: str = "", algo: str = "", stage: str = "",
            timeout: Optional[float] = None) -> StageResult:
        """执行一次阶段脚本, 返回结构化 StageResult (不抛异常).

        Args:
            script:  脚本文件名 (相对 cwd 或绝对路径), 如 "03_train.py"
            args:    脚本 CLI 参数列表 (不含解释器与脚本名)
            env:     该阶段隔离注入的环境变量 (只对本子进程生效)
            label:   人类可读步骤名 (日志头)
            algo:    算法名 (结果对象携带)
            stage:   阶段名 (结果对象携带)
            timeout: 覆盖默认超时
        """
        cmd = [self.python, str(script)] + [str(a) for a in (args or [])]
        label = label or f"{algo}/{stage}" if algo else (label or str(script))
        t0 = time.time()
        print(f"\n{'='*70}\n  STEP: {label}\n{'='*70}")
        print(f"  CMD: {' '.join(cmd)}")

        # UTF-8 端到端 + 算法隔离环境 (env 只对本子进程生效)
        sub_env = dict(os.environ)
        sub_env.setdefault("PYTHONIOENCODING", "utf-8")
        if env:
            sub_env.update(env)

        stdout_text, stderr_text = "", ""
        try:
            if self.log_file:
                with open(self.log_file, "a", encoding="utf-8") as lf:
                    lf.write(f"\n{'='*70}\n {label}  ({time.strftime('%Y-%m-%d %H:%M:%S')})\n{'='*70}\n")
                    lf.write(f"CMD: {' '.join(cmd)}\n\n")
                    lf.flush()
                    result = subprocess.run(
                        cmd, cwd=self.cwd, stdout=lf, stderr=subprocess.STDOUT,
                        env=sub_env, timeout=timeout or self.timeout)
            else:
                result = subprocess.run(
                    cmd, cwd=self.cwd, capture_output=True, text=True,
                    encoding="utf-8", errors="replace",
                    env=sub_env, timeout=timeout or self.timeout)
                stdout_text = result.stdout if result.stdout is not None else ""
                stderr_text = result.stderr if result.stderr is not None else ""
        except FileNotFoundError as e:
            # Windows 常见: 硬编码 "python3" 找不到 (统一接口固定用 sys.executable)
            print(f"  [FAIL] FileNotFoundError: {e}")
            print(f"     当前 Python 解释器: {self.python}")
            return StageResult(algo=algo, stage=stage, label=label, status="fail",
                               message=f"启动失败: {e}",
                               duration_s=time.time() - t0)
        except subprocess.TimeoutExpired:
            print(f"  [FAIL] 阶段超时 (>{timeout or self.timeout}s)")
            return StageResult(algo=algo, stage=stage, label=label, status="fail",
                               message=f"超时 (>{timeout or self.timeout}s)",
                               duration_s=time.time() - t0)

        rc = result.returncode
        tail = (stdout_text.strip().split("\n")[-30:] if stdout_text else [])
        dur = time.time() - t0

        # ---------- 退出码翻译 (统一语义) ----------
        if rc in SOFT_SKIP_CODES:
            # 数据质量门软跳过 (非错误): 打印最后 30 行 (含 [SKIP] 提示)
            print("\n".join(tail))
            return StageResult(algo=algo, stage=stage, label=label,
                               status="soft_skip", exit_code=rc,
                               message=f"数据质量门触发 (code={rc})",
                               duration_s=dur, stdout_tail="\n".join(tail))
        if rc != 0:
            print("STDOUT:", stdout_text[-2000:])
            print("STDERR:", stderr_text[-2000:])
            return StageResult(algo=algo, stage=stage, label=label,
                               status="fail", exit_code=rc,
                               message=f"非零退出 (code={rc})",
                               duration_s=dur, stdout_tail="\n".join(tail))
        # 成功: 仅打印最后 30 行
        print("\n".join(tail))
        return StageResult(algo=algo, stage=stage, label=label,
                           status="ok", exit_code=0,
                           message="", duration_s=dur,
                           stdout_tail="\n".join(tail))
