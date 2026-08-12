## [2026-08-12] 专题：批量训练与推理数据输入输出及用户配置功能要求说明书
- **类型**：用户专题 / 技术架构与接口规范说明文档
- **目标与假设**：
  - **目标**：对项目在批量训练和推理链路（`run_batch_users.py` ↔ `run_user_pipeline.py`）中的**数据输入结构**、**数据输出与沉淀结构**以及**用户配置格式与参数优先级语义**进行系统化梳理与规范化建档。
  - **假设**：所有用户与设备的历史多路空调电耗与环境负荷辨识场景均运行在 v6.12.6+v6.15.0/v13+ 架构下，确保配置结构解析、数据对齐与状态归档满足端到端闭环和向后兼容。
- **方法 / 数据 / 参数**：
  - **方法**：基于 `scripts/run_batch_users.py`（批量编排层）、`scripts/run_user_pipeline.py`（单用户流水线控制层）、`scripts/time_filter_utils.py`（配置解析核心工具）以及各中间处理脚本（`02_align_and_feat.py`、`03_train.py`、`05_inference.py`、`analyze_on_periods.py`、`metrics_utils.py`）的代码逻辑进行逆向分析与标准归纳。
  - **数据**：涵盖 `data/` 输入根目录双分层（`trains/`/`infers/`）及平铺文件、`models/` 模型包、`artifacts/` 产物结构。
  - **参数**：包含 JSON 用户配置文件支持的六大关键模块（全局时段过滤、复合目标分路、d87守卫开关、数据集切分级独立过滤、9项公共常量覆盖、v14架构实验开关）及环境变量映射关系。
- **结果 / 结论**：
  - 形成了《NILM 空调负荷分解 — 批量训练与推理数据输入输出及用户配置功能要求说明书》，涵盖输入命名正则、对齐规范、产物架构布局、关键 CSV 表结构（如 `n_bus_raw/n_branch_raw`、`min_w` 扩展等）及参数三级覆盖机制。
  - 明确了批量隔离清理（`_CLEANUP_WHITELIST` 白名单）与断点续跑原子持久化（`batch_execution_state.csv`）的技术边界。
- **是否进入 REPORT.md（稳定结论）**：否（本专题为工程配置与接口结构规范说明文档，作为工作手册与专题库持久沉淀在 `REPORT_TEST.md` 中；算法演进报告位于 `REPORT.md`，部署与快速使用说明见 `README.md`）。
- **遗留问题**：
  - 待后续如有新增业务字段或新版本分析模块，可按本说明文档约定的命名与类型规范在本专题下方追加增补。

---

# 《NILM 空调负荷分解 — 批量训练推理数据输入输出及用户配置规范说明书》

> **适用版本**：v6.12.6+v6.15.0（及 v13.x / v14 扩展模块）  
> **制定日期**：2026-08-12  
> **文档定位**：针对本仓库所有自动化脚本与算法组件在“批量训练”与“批量推理”模式下的数据来源架构、生成产物规范、时段过滤及业务参数配置文件功能语义进行全链路规格梳理与开发规范定义。

---

## 第一部分：体系架构与控制流概览

NILM 空调负荷分解项目采用**批量编排层（`run_batch_users.py`）**与**单用户执行流水线（`run_user_pipeline.py`）**分层解耦的架构设计：

```
+-----------------------------------------------------------------------------------------+
|                                批量编排层 (run_batch_users.py)                          |
|  - 扫描 data/ 目录识别用户与设备文件映射 (e241_<device>_<user>...)                    |
|  - 统一加载并解析 --time-filter-config 指定的用户 JSON 配置文件                        |
|  - 原子写入与维护批量执行状态表 batch_execution_state.csv (支持 --resume 断点续跑)      |
+-----------------------------------------------------------------------------------------+
                                             |
                   (多进程/逐个调起并透传时段过滤与环境变量参数)
                                             v
+-----------------------------------------------------------------------------------------+
|                           单用户流水线控制层 (run_user_pipeline.py)                      |
|  - 对齐输入输出路径，维护 artifacts/ 白名单防护 (_CLEANUP_WHITELIST)                      |
|  - 依次调用底层工作流程脚本：                                                           |
|       [Step 01] scripts/01_audit.py             => 采样率勘察与健康度检查               |
|       [Step 02] scripts/02_align_and_feat.py    => 15 分钟重采样对齐 + 特征工程          |
|       [Step 03] scripts/03_train.py             => GBDT / Isotonic / RF 模型训练        |
|       [Step 04] scripts/04_evaluate.py          => 离线全量评估与残差校正学习           |
|       [Step 05] scripts/05_inference.py         => 独立推理评估 + 日级指标与漂移分析    |
|       [Step 06] scripts/analyze_on_periods.py   => 训前/推前分路启动行为分析与每日统计   |
+-----------------------------------------------------------------------------------------+
```

---

## 第二部分：数据输入结构与文件命名规范

### 2.1 目录组织布局支持

批处理工具提供对历史平铺目录与 **v9 规范化双分层目录**的自动解析兼容：
1. **规范分层目录模式（强烈推荐）**：
   - 训练数据根目录：`data/trains/<device>_<user>/`
   - 推理数据根目录：`data/infers/<device>_<user>/`
   - *注释*：每一个 `<device>_<user>` 文件夹代表一个独立训练/推理单元，文件夹内部应放置对应的总线（Bus）CSV 和分路（Branch）CSV。
2. **平铺文件名自动提取模式（向后兼容）**：
   - 所有 CSV 均置于 `data/` 根目录。脚本基于正规表达式识别用户归属并进行关联。

### 2.2 总线数据（Bus CSV / 主干总功）格式与命名正则
- **命名正则表达式 (`RE_BUS`)**：
  ```regex
  ^e241_(?P<device>[^_]+)_(?P<user>[^-]+)-Ch(?P<ch>\d+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$
  ```
  *示例*：`e241_800080270708_4206602981958-Ch1-250710-260628.csv`
- **文件表结构要求**：
  - 必须包含时间戳列：`event_time` (或通过混合解析格式化的 ISO 时间字符串，如 `YYYY-MM-DD HH:MM:SS` 或 `YYYY/M/D H:M:S`)。
  - 必须包含功率分路或总负荷特征列：通常为 `load_iden_data0`, `load_iden_data1`, ... 或主回路功率与电压特征。

### 2.3 分路数据（Branch CSV / 空调真值）格式与命名正则
- **命名正则表达式 (`RE_BR`)**：
  ```regex
  ^(?P<user>[^-]+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$
  ```
  *示例*：`4206602981958-250710-260628.csv`
- **文件表结构与复合列支持**：
  - 必须包含时间戳列：`time`
  - 必须包含负荷分路数字功率列：`p1`, `p2`, `p3`, `p4` 等（单位：W）。
  - **复合列目标语义（v13.16 新增）**：
    - 支持使用由 `+` 连接的多个分量名表示总目标，例如 `"p1+p2"` 或 `"p1+p2+p3"`。
    - **物化机制**：加载数据时，`load_branch_csv()` 函数会校验所有输入分量是否存在，并自动增加名为复合字符串（如 `p1+p2`）的实体列；其值为按行累加分量（`skipna=False`，即任一分量为 NaN 则结果传播为 NaN，避免未采集被误作 `0W` 致使电量低估）。
    - **规范化防呆**：忽略大小写和空格（`" P1 + p2 "` → `"p1+p2"`）；禁止出现重复分量（如 `"p1+p1"` 会产生异常拒绝）。

### 2.4 中间态与多路合并数据结构
若用户存在多份输入数据或需要分集处理，会通过对齐脚本土化生成中间文件：
- `data/merged_bus.csv` 与 `data/merged_branch.csv`（训练层中间聚合产物）
- `data/infer_bus.csv` 与 `data/infer_branch.csv`（推理层中间产物，实现训推路径物理分离）
- `artifacts/<user>/aligned_15min.csv`（15 分钟等距网格重采样特征矩阵临时对齐表）

---

## 第三部分：数据输出结构与产物沉淀规范

所有产物输出严格遵守“环境与日志可追溯”、“主次产物不混杂”及“状态安全隔离”三大工程纪律。

### 3.1 产物架构总体布局
```
<workspace_root>/
 ├── models/
 │    └── <user_id>/
 │         ├── model_bundle_v6_15_0.pkl     # GBDT 主分类器+回归器+残差校正器包
 │         ├── rf_model.pkl                 # v4.2 对照组 Baseline RF 模型
 │         ├── split_dates_bundle.json      # train_dates/val_dates/test_dates 训练日白名单
 │         └── weather_cache/               # Open-Meteo 本地温度气象数据缓存
 └── artifacts/
      ├── batch_execution_state.csv         # [v13.17] 批量执行状态表 (原子续跑依据)
      ├── batch_run_summary.csv             # 批量所有用户总体 KPI 指标表
      ├── summary_metrics_all_users.csv     # 全生命周期评估报表
      ├── trains/
      │    └── <user_id>/
      │         ├── train_on_periods.csv    # 训前分路开机明细表 (含 min_w / dataset 归属)
      │         ├── train_on_periods_daily.csv # 每日开机与低谷统计 (含 OFF 天行)
      │         └── temp_power_lut.csv      # 训练侧 20 温度桶参考负荷查找表
      └── infers/
           └── <user_id>/
                ├── predictions/
                │    └── inference_result.csv # 多层级预测功率及残差明细表
                ├── metrics/
                │    ├── inference_metrics.csv
                │    ├── inference_daily_metrics.csv # 推理每日追踪指标表 (25 列)
                │    └── inference_comparison.csv    # 多模型横向比较表
                ├── infer_on_periods.csv             # 推前开机段级行为分析
                ├── infer_on_periods_daily.csv       # 推前日级功率概览
                └── inference_temp_power_actual_vs_expected.csv # 温度信号漂移监控表
```

### 3.2 预测结果 CSV (`predictions/inference_result.csv`) 表结构
| 列名 | 数据类型 | 说明 |
|---|---|---|
| `time` / `event_time` | ISO String | 15分钟粒度等间距时间戳 |
| `y_true` | Float | 真实空调功率值（W，若传入无分路测试，则列可忽略） |
| `y_pred_W_main` | Float | **最终生产输出功率（W）**：融合 L4（残差层）+ L5（自适应模型切换）后对下游输出结果 |
| `y_pred_W_main_raw` | Float | 原始主分类-分位数 GBDT 输出（不含残差修正层） |
| `y_pred_W_main_L4_calib` | Float | 仅叠加 L4 加性残差校正后的功率预测 |
| `state_pred_main` | Int (0/1) | 主模型对开机状态的 0/1 二值化判定 |
| `p_on_main` | Float (0~1) | 分类模型评估为 ON 状态的特征概率 |
| `y_pred_low_W_main` / `y_pred_high_W_main` | Float | 功率区间预测下边界与上边界 |
| `residual_W_main_raw` | Float | 原始输出残差（`y_pred_W_main_raw - y_true`） |
| `residual_W_main_L4_calib` | Float | 校正后残差（`y_pred_W_main_L4_calib - y_true`） |
| `y_pred_W_rf` / `y_pred_W_fallback` ... | Float | 各基线参考算法预测对比列 |

### 3.3 逐日质量指标表 (`train_daily_metrics.csv` / `inference_daily_metrics.csv`)
日级评估统计结果由 25 个固定顺序的字段构成（支持 `n_bus_raw` / `n_branch_raw` 原始测点探查及数据泄漏分类）：

| 序号 | 字段名称 | 数据类型 | 意义说明 |
|---|---|---|---|
| 1 | `date` | String | 统计日期 (`YYYY-MM-DD`) |
| 2 | `split` | String | 所属数据集属性（`train` / `val` / `test` / `inference`；如有交叉将自动分拆标注为 `inference_leak` 与 `inference_ood`） |
| 3 | `model` | String | 指标评估的模型来源（如 `main` / `rf`） |
| 4 | `n_samples` | Int | 重采样并时间对齐完毕后的有效 15 分钟点数 |
| 5 | **`n_bus_raw`** | Int / `""` | **[v13.16] 当天原始总线 CSV 中的真实实际记录行数**（无需对齐）；若数据缺失通常显示极低（如`<10`）导致指标退化 |
| 6 | **`n_branch_raw`** | Int / `""` | **[v13.16] 当天原始分路 CSV 中的真实实际记录行数** |
| 7~11 | `Accuracy`, `Precision`, `Recall`, `F1`, `AUC` | Float | 分类性能评价指标（4~6 位小数，缺省为空字符串） |
| 12~14 | `MAE_W`, `RMSE_W`, `SAE` | Float | 连续回归误差；`SAE` = `abs(kWh_pred - kWh_true) / max(kWh_true, 0.01)` |
| 15~17 | `kWh_true`, `kWh_pred`, `kWh_err` | Float | 日度总用电量对齐比对（真实度数 / 预测度数 / 误差差值） |
| 18~21 | `TP`, `FP`, `FN`, `TN` | Int | 混淆矩阵计数 |
| 22 | `dataset` | String | 辅助标记从切分包或白名单识别的数据源类型（如 `train`/`val`/`test`/`excluded`） |
| 23 | `on_thr_w` | Float | 评估计算 `s_true` 和指标使用的实际功率阈值（W） |

### 3.4 分路启动段级行为明细 (`<stage>_on_periods.csv`) 与日汇总表 (`<stage>_on_periods_daily.csv`)
为避免误调 `on_thr_w` 阈值引发现场异常，模型在进入训练和推理前执行自动化行为分析：
- **段级表（`<stage>_on_periods.csv`）**：
  - 核心列：`being_time`, `end_time`, `p1` (实际对应目标名), `duration_min`, **`min_w`**, `mean_w`, `peak_w`, `energy_kwh`, `dataset`。
  - **`min_w` (v13.16 增强)**：指示每段空调开启过程中的最低瞬时功率。对于变频空调可判断是否存在长期低档运行；且严格满足物理约束 `min_w <= mean_w <= peak_w`。
  - **OFF 天行 (v13.11 增强)**：对全天未触发启动的日子，系统生成专用行，其中 `duration_min=1440`，`min_w/mean_w/peak_w` 等按全天所有采样统计（精准监控日常待机功率分布）。
- **日汇总表（`<stage>_on_periods_daily.csv`）**：
  - 统计单日累计行为，字段包括 `date`, `n_segments` (开机频度，OFF 天 = 0), `total_on_min`, `total_on_hours`, `first_on_time`, `last_off_time`, `min_w`, `mean_w`, `peak_w`, `energy_kwh`。

### 3.5 温度信号参考表 (`temp_power_lut.csv`) 与实际漂移报表 (`inference_temp_power_actual_vs_expected.csv`)
为实现环境变化条件下的概念漂移监控，输出标准温度-功率查询及实测对照表：
- `temp_power_lut.csv`（训练期写入）：
  - 将温度划分为 20 个独立等间距桶（Bin 1 ~ 20）加上 `ALL_MEDIAN` 全局兜底桶，共 21 行。
  - 列定义：`bin_id`, `temp_lo`, `temp_hi`, `temp_width`, `expected_signal` (中位数), `n_samples`, `mean`, `std`, `p25`, `p75`, `signal_col`, `is_global_median`。
- `inference_temp_power_actual_vs_expected.csv`（推理期写入）：
  - 比较训练期期望负荷与实际发生功率差异。
  - 关键监测列：`abs_residual`, `rel_drift`, `drift_flag` (枚举状态：`OK`、`WARN` (绝对漂移≥15%)、`ALERT` (绝对漂移≥30%)、`NO_DATA` (无对应温区样本))。

### 3.6 批量运行断点续跑状态表 (`artifacts/batch_execution_state.csv`)
- **产生背景（v13.17）**：供批量层长时间任务异常挂断后做幂等续调支持，执行时采用“先写 `.tmp` 文件再原子 `os.replace`”的设计规避崩溃导致的文件半写损坏。
- **字段明细（9 列标准规范，UTF-8-BOM）**：
  1. `user_id`: 用户识别 ID 字符（可含中文字符）
  2. `status`: 最终执行状态（`ok` / `fail` / `soft_skip`）
  3. `success`: Bool （`True` 或 `False`）
  4. `started_at` / `finished_at`: ISO 格式的时间记录点
  5. `duration_s`: 耗时秒数（Int/Float）
  6. `message`: 异常堆栈文字摘要或处理备注
  7. `target_col`: 当前用户解析得到的辨识目标（如 `p1+p2`）
  8. `run_id`: 当前批量运行关联会话标识码

---

## 第四部分：用户数据配置结构与功能要求 (JSON 配置文件规范)

用户通过 `run_batch_users.py --time-filter-config <path_to_json>` 传入一个集中配置的 JSON 文件。系统内部通过 `scripts/time_filter_utils.py` 进行解析，且遵循统一的三重参数覆盖优先级约束。

### 4.1 层级解析规范与优先级顺序
```
优先级链条从高到低排列：
  1. config["<user_id>"]["<key>"]     (给具体用户指定的定制参数，高优生效)
  2. config["_default"]["<key>"]      (针对未特别配置的用户的全局默认兜底)
  3. common.py 或流水线硬编码系统默认值 (最低优先)
```
> *特别规则*：若以下划线开头的顶级名称（如 `_note_` / `_comment_` / `_default`）出现在 JSON 中，调度器会将其剔除，绝不作为用户数据名尝试加载。

### 4.2 完整的用户配置六大模块功能规格
在单个用户配置对象（或 `_default` 节点下）支持同时配置以下六类主要业务指令字段：

```json
{
  "800080270708_4206602981958": {
    "_note_": "配置字段参考范例",
    "target_col": "p1+p2",
    "guard_enabled": false,
    "on_thr_w": 50.0,
    "split_ratios": [0.70, 0.15, 0.15],
    "split_strategy": "global_stratified",
    "post_min_on": 2,
    "post_fill_short_off": 3,
    "weather_latitude": 30.59,
    "weather_longitude": 114.31,
    "use_weather_features": true,
    "use_temp_based_season": true,
    "train": {
      "include": [["2025-07-10", "2026-06-28"]],
      "exclude": [["2026-04-02 17:45", "2026-04-02 23:59:59"]]
    },
    "infer": {
      "exclude": [["2026-06-05", "2026-06-05"]]
    },
    "splits": {
      "train": {"exclude": [["2026-06-12", "2026-06-12"]]},
      "val":   {"include": [["2026-06-20", "2026-06-20"]]},
      "test":  {"include": [["2026-06-25", "2026-06-25"]]}
    },
    "v14_enable": true,
    "physics": true,
    "calibrate": false
  },
  "_default": {
    "on_thr_w": 10.0,
    "split_ratios": [0.6, 0.2, 0.2],
    "split_strategy": "stratified_day"
  }
}
```

#### (1) 全局时段过滤 (`train` 与 `infer` 顶层字段，v12 新增)
- **参数规格**：每个阶段支持接收包含一个 `"include"` 列表与一个 `"exclude"` 列表的字典结构。
- **时间范围语义**：
  - 子元素为双元素数组 `[start_time, end_time]`，表示**闭区间** `[s, e]`。
  - 若使用 `"YYYY-MM-DD"` 短格式，系统自动扩展为全天：起点扩为 `D 00:00:00`，终点扩为 `D 23:59:59`。
  - 允许传入精确到秒级的时间 `"YYYY-MM-DD HH:MM:SS"`（可精细剥离如数小时的采集跳变污染时间段）。
- **执行次序**：
  - 先计算并取白名单 `include` 中所有时间区间的并集（如 `include` 为空则默认选择所有有效行）。
  - 再针对保留结果对黑名单 `exclude` 中的时间区域逐步实施排除剪切（`ts >= s & ts <= e`）。

#### (2) 目标分路与复合列定义 (`target_col`，v13.4 / v13.16)
- **类型**：字符串 (String)
- **合法模式**：
  - `pN`（单分路，`N` 为非负整数，如 `"p1"`, `"p2"`）。
  - `pA+pB[+pC...]`（复合累加总负荷，如 `"p1+p2"` 或 `"p1+p2+p3"`）。
- **解析与回退链**：若此参数为空或未传入，优先读取 CSV 命名正则匹配获取到的信道值；若无法识别，则默认按首个存在的 `p*` 列推断；否则最终回退默认值 `"p1"`。

#### (3) d87 启动自适应守卫开关 (`guard_enabled`，v13.1 / v13.5)
- **类型**：布尔值 / null
- **状态行为**：
  - `true`：显式开启基于瞬时脉冲功率尖峰（`d87`）的平滑与限制守卫规则。
  - `false`：显式关闭守卫。对于待机功率或峰幅较小、无瞬时浪涌尖峰的变频小容量设备适用，消除误判导致的严重漏报（FN 降低）。
  - **未配置（`null`）或不填**：触发自适应检查逻辑。若用户训练数据中 `|d87|.max < 50W` 或者训练集中识别具有超阈值脉冲的有效日占比低于 `30%`，模型自动判定该用户不支持该机制，发出记录日志并**自动降级关闭**守卫机制。

#### (4) 数据集细粒度独立过滤 (`splits`，v13.2)
- **参数规格**：提供由 `train`、`val` 和 `test` 三级各自独立包含 `include` / `exclude` 数组的关联结构。
- **四步核心语义保证**：
  1. **原策略划分**：根据系统切分算法对全部候选训练周期完成最初始的 `train/val/test` 分布。
  2. **强制硬锚定（Include Step）**：逐条检查点，将落在 `splits.X.include` 范围内的所有时间点打标归属于该数据分区 `X`。出现交叉冲突时，按照 `train -> val -> test` 优先级先到先得。
  3. **严格保持分布形状（Reshape Balance）**：如果硬锚定使得某个集合分配到了超额的记录行，则把该分区未受硬锚定限制的普通闲散点释放给样本缺乏的其他切分集，保证各数据阶段总量和原设定百分比不变。
  4. **精确黑名单排除（Exclude Step）**：移除属于某目标分区且落在其对应 `exclude` 区间的数据点并归为重分配池；若某个点位同时被三种 partition 规则的 `exclude` 捕获，则直接以丢弃形式消除。

#### (5) 九个系统公共常量用户级强覆盖 (`common_overrides`，v13.5 / v13.13)
| JSON 字段名 | 允许的数据范围或约束 | 业务对应作用 | 异常降级策略 |
|---|---|---|---|
| `on_thr_w` | Float (`[0.001, 5000.0]`) | 空调开启判定功率阈值（W）。控制全链条标签判定同口径 | WARN 提示后回退系统设定 (`10.0W`) |
| `split_ratios` | 3 元素 Float 数组，总和=1 | 切分训练、验证、测试比例参数，自动校准规整 | 校验失败忽略并采用默认 `[0.6, 0.2, 0.2]` |
| `split_strategy` | `"stratified_day"` / `"stratified"` / `"time"` / `"global_stratified"` | 划分策略。推荐 `"global_stratified"` 实现跨月分布无零散挤压的全局分层切分 | WARN 回退至默认 `"stratified_day"` |
| `post_min_on` | Int (`>= 0`) | 推断状态后处理：最小连续 ON 的持续点数（消除杂乱尖峰） | 校验失败使用 `1` |
| `post_fill_short_off`| Int (`>= 0`) | 推断状态后处理：填补的短度 OFF 间断点数（消除不平稳突变间歇） | 校验失败使用 `3` |
| `weather_latitude` | Float (`[-90.0, 90.0]`) | 空调物理所在地经纬度数据库定位坐标 | 默认纬度 `30.59`（武汉） |
| `weather_longitude`| Float (`[-180.0, 180.0]`) | 同上 | 默认经度 `114.31` |
| `use_weather_features`| Bool (`true`/`false`) | 是否启用通过 Open-Meteo 请求的气象维度数据特征 | 默认启用 (`true`) |
| `use_temp_based_season`| Bool (`true`/`false`) | 是否启用根据当地近期日均气温自动决定模型季节划分策略 | 默认启用 (`true`) |

#### (6) v14 架构实验控制参数字段 (`v14_flags` / `get_user_v14_flags`)
针对使用扩展版 `14_train_v14.py` 执行的高阶架构功能，接收可选参数对开启：
```json
{
  "v14_enable": false,
  "physics": false,
  "focal": false,
  "ensemble": false,
  "calibrate": false,
  "auto_config": false,
  "health": false,
  "diag": false
}
```

---

## 第五部分：CLI 参数传递链路与工程保护契约

### 5.1 CLI 与环境变量透传控制链
在批量执行的上下文中，`run_batch_users.py` 对选取的某具体用户配置数据字典会转换为标准化形式后，向各个子系统进程透传：
1. **JSON 序列化参数命令传递**：
   - 过滤结构转为压缩为非换行的 JSON 字符串，传递给 `run_user_pipeline.py --train-time-filter-spec '...'` 与 `--infer-time-filter-spec '...'` 等 CLI 选项。
2. **环境变量无损映射转换**：
   - 为避免在深度调用的 `03_train.py` 与 `04_evaluate.py` 等底层中多层传参解析易出错，将 `common_overrides` 参数翻译为大写的环境变量进行环境封堵与覆盖。
   - *映射规范*：例如设定 JSON `{ "on_thr_w": 50 }` → 进程运行将拥有环境变量 `NILM_USER_ON_THR_W=50.0`。各个核心特征及脚本在初始引用常量时通过：
     ```python
     ON_THR_W = float(os.environ.get("NILM_USER_ON_THR_W", default=10.0))
     ```

### 5.2 目录清理机制与核心产物白名单 (`_CLEANUP_WHITELIST`)
单用户 `run_user_pipeline.py` 开始执行时，会自动调取 `cleanup_artifacts_top(project_root)` 对以前残留的杂散中间文件（如 `*.tmp`, `aligned_15min.csv`）做出自动出栈清洗。

为避免误伤在“批量编排执行链路（Batch-level）”下由其它用户任务或总调度生成的跨用户聚合报告，代码中严格规定了**顶层文件清理白名单契约 (`_CLEANUP_WHITELIST`)**，属于本表中的名称**绝对禁止被清删**：
- `batch_execution_state.csv`（用户断点续跑关键原子记录状态表）
- `batch_execution_state.csv.tmp`（原子写入中的备份过渡文件）
- `batch_run_summary.csv`（全员汇总总表）
- `summary_metrics_all_users.csv`（主实验性能报表）
- `skipped_users.csv`（因配置软跳过的用户汇总）
- `.gitkeep`

### 5.3 严格错误边界与异常处理准则
1. **轻量化宽容解析准则**：
   - 参数字段类型容忍格式：对能够无损强制提升为要求类型的基本数值进行智能强转（如字符串 `"50"` 会转换为 Float `50.0`；字符串 `"True"`, `"yes"`, `"1"`, `"on"` 都能正确判定为 Bool `True`）。
2. **非法输入回退告警（WARN & Fallback）**：
   - 在用户把配置中的数值填报成超出规定范围（例如 `on_thr_w: -100` 或 `split_ratios: [1, 0, 0]`）时，抛出 `UserWarning` 并将其安全抹除，直接回退为下层有效兜底值，不因单个错误传参终止整条数据辨识管道，满足持续性生产要求。
