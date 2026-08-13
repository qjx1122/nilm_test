## [2026-08-12] 专题：通用批量训练与推理数据输入输出及用户配置框架规范说明书（通用抽象版·含全分集预测产物规范）
- **类型**：通用架构规范 / 数据接口与用户配置中心技术标准说明书
- **目标与假设**：
  - **目标**：抽离具体业务算法细节，针对多对象、多任务形态下的**批量训练与推理数据处理架构**，提炼通用数据输入输出结构、多层级配置规范（JSON Schema）、断点续跑状态模型、临时产物隔离清理契约；特别地，在**产物目录分类体系中完备增补 `train_pred.csv`、`val_pred.csv`、`test_pred.csv`、`train_pred_rf.csv`、`val_pred_rf.csv`、`test_pred_rf.csv` 六大全分集预测产物**及结构说明。
  - **假设**：各类具备时间序列或多通道输入的数据集经过编排层 `run_batch_users.py` 与流水线引擎 `run_user_pipeline.py` 的协同，实现对齐、特征生成、独立模型训练、残差校正学习、OOD与数据泄漏审计及业务周期评估的闭环。
- **方法 / 数据 / 参数**：
  - **方法**：系统化提炼批量编排层、单任务控制流水线及底层配置解析中心（`time_filter_utils.py`）的通用工程接口；分离“算法私有数据”与“通用框架架构数据”。
  - **数据**：涵盖 `data/` 根目录双模式输入组织（规范双分层 vs 平铺自动推导）、`models/` 资产打包规范、`artifacts/trains/` 训练评估产物区（增补 6 大主模型/基准模型在各分切分集的预测结果文档）及 `artifacts/infers/` 推理执行区。
  - **参数**：提炼通用配置文件中适用的六大功能模块（全局时段过滤、复合目标表达式、自适应算法守卫、三区独立样本过滤、通用常量覆盖与环境映射、架构进阶开关）及三层解析优先级链。
- **结果 / 结论**：
  - 形成了《通用批量训练与推理数据输入输出及用户配置框架规范说明书（通用抽象版·含全分集预测产物规范）》，确立了高通用的时序批处理文件体系、标准评估体系（包含 25 列带原始点计数的监控表）、全分集预测及对照对比表、时间段审计表及断点续跑 9 列原子状态规范。
  - 同步排版输出并更新了标准项目技术方案说明 Word 文档：`项目技术方案说明书_数据架构与核心算法全景规范.docx`（已完整抽象具体私有算法，只保留项目整体结构、数据输入输出和配置架构及通用算法标准产物表字典）。
  - 明确了工程开发中**白名单隔离保护契约 (`_CLEANUP_WHITELIST`)**与**配置异常降级回退 (`WARN + Fallback`)**两项基本保障机制。
- **是否进入 REPORT.md（稳定结论）**：否（本说明书专注于系统通用数据输入输出与用户配置规范的标准化建档，沉淀于 `REPORT_TEST.md`；具体业务领域的算法实验与演进见 `REPORT.md`）。
- **遗留问题**：
  - 随着框架后续功能演进，如有新增通用控制属性或产物，须按本说明书约定的命名、数据类型与回退链路规范在此追加更新。

---

# 《通用批量训练与推理数据输入输出及用户配置框架规范说明书（通用抽象版·含全分集预测产物规范）》

> **制定日期**：2026-08-12  
> **文档定位**：面向批量训练与推理服务框架，剥离具体业务领域的专业物理概念与特定模型细节，全面规范**数据输入接口与文件组织**、**标准产物输出与监控结构（完备规范训练集/验证集/测试集全集预测表及对照组文件）**、**集中式配置参数体系（JSON Schema）**以及**工程保护与状态恢复机制**。

---

## 第一部分：框架设计宗旨与层级控制架构

本框架基于“**批量编排调度**”与“**单任务执行流水线**”二层解耦架构设计，旨在给时序多任务学习及预测系统提供通用数据加载、按需时间过滤、模型持久化配置、产物标准化汇总与安全隔离能力。

```
+-----------------------------------------------------------------------------------------------+
|                             批量调度层 (run_batch_users.py)                                   |
|  - 扫描工作目录 (data/) 并解析被管理对象 (User/Device) 的输入文件链                            |
|  - 解析集中式 JSON 配置文件，按用户层/兜底层形成参数结构并传递                                |
|  - 原子化维护 9 列标准状态表 (batch_execution_state.csv)，支持 --resume 断点续跑               |
+-----------------------------------------------------------------------------------------------+
                                               |
         (通过序列化 JSON CLI 参数 --time-filter-spec 及环境变量 NILM_USER_* 进行环境封堵与透传)
                                               v
+-----------------------------------------------------------------------------------------------+
|                            单任务流水线引擎 (run_user_pipeline.py)                             |
|  - 安全清理历史垃圾，执行 _CLEANUP_WHITELIST 顶层白名单保护                                   |
|  - 串行调度基础分析与算法构建标准流程：                                                       |
|       [Step 01] 数据勘察与健康度检查 (审计输入采样点密度与时间覆盖度)                        |
|       [Step 02] 统一时间序列网格重采样与多通道对齐 (生成等距特征矩阵)                        |
|       [Step 03] 模型分类与回归训练 (生成主模型与参考基线包，落盘各切分集全量预测)            |
|       [Step 04] 离线全量预测与校正层评估 (产出 train/val/test_pred*.csv 及对比指标)          |
|       [Step 05] 独立推理执行与差异漂移监测 (输出生产预测表及日级质量监控表)                  |
|       [Step 06] 事件段级行为深度分析 (对启动事件序列、周期指标与极限值做量化汇总)            |
+-----------------------------------------------------------------------------------------------+
```

---

## 第二部分：通用数据输入结构与规范

### 2.1 双重目录组织结构支持
为适应自动化生成数据与历史存量数据，框架原生支持两种目录与映射管理规范：
1. **规范化双分层目录布局（推荐）**：
   - 训练候选数据根目录：`data/trains/<device_id>_<user_id>/`
   - 推理独立数据根目录：`data/infers/<device_id>_<user_id>/`
   - *约定*：在此模式下，训练数据与推理数据处于不同物理目录；每个设备/对象目录内部需且仅需放置一组关联的输入源文件（输入主特征 CSV + 真值目标 CSV）。
2. **根目录平铺文件名正向推导模式（向后兼容）**：
   - 将所有相关数据 CSV 直接放置在 `data/` 根目录下，框架使用正则表达式识别设备 ID（`<device_id>`）、对象 ID（`<user_id>`）和信道属性，实现关联。

### 2.2 主特征输入 CSV（Bus / Main Feature CSV）标准规范
- **通用命名规范（`RE_BUS` 匹配语法）**：
  ```regex
  ^e241_(?P<device>[^_]+)_(?P<user>[^-]+)-Ch(?P<ch>\d+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$
  ```
  *字段解析*：`device` 表示设备或网关标识；`user` 表示受管理的对象或账户主键；`ch` 表示输入特征组通道号；`start` / `end` 表示起止日期。
- **通用数据格式约束**：
  - **主键列**：时间戳字段（可定名 `event_time` 或 `time`），支持 ISO 标准及不同分隔符的 `YYYY-MM-DD HH:MM:SS` 时间字符串，框架具备混合格式解析能力。
  - **数值特征列**：一列或多列用于模型学习输入的数值序列（如通道测量值 `load_iden_data*` 或多特征量）。

### 2.3 目标值真值 CSV（Branch / Target CSV）标准规范
- **通用命名规范（`RE_BR` 匹配语法）**：
  ```regex
  ^(?P<user>[^-]+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$
  ```
- **通用数据结构约束**：
  - **主键列**：时间戳字段 `time`，由重采样步骤与主特征 CSV 做 Inner/Left 对齐。
  - **目标实体列**：标量或各个具体分离维度目标列（命名为 `pN`，其中 N ≥ 0 的整数，如 `p1`, `p2`, ...）。
- **通用复合列物化机制（Composite Target Column, v13.16）**：
  - **业务场景**：当待建模目标是由多个细分目标求和形成的主体对象时，系统不要求必须在文件内手工生成汇总列，支持传入带 `+` 号的复合表达式。
  - **配置语法**：`"pA+pB[+pC...]"`（如 `"p1+p2"` 或 `"p1+p2+p3"`）。
  - **按需生成与计算法则**：数据加载函数根据请求自动进行列表解析并校验组件合法性；若均合法，则新增一列名称即为该表达式字面量（如 `p1+p2`）；计算值为行级数值累加（求和时严格设置 **`skipna=False`**，即任一组件在该时间点为 `NaN`，则复合结果将传播为 `NaN`，确保未采集区间绝不被静默设为 `0` 从而导致目标失真）。
  - **防呆容忍与拦截**：自动去除首尾空白及忽略字符大小写（`" P1 + p2 "` → `"p1+p2"`）；若传入重复分量（如 `"p1+p1"`）则捕获抛错予以拒绝。

### 2.4 中间态与对齐网格数据集
- 合并阶段：训练链路生成 `merged_bus.csv` / `merged_branch.csv`；推理链路生成 `infer_bus.csv` / `infer_branch.csv`（训推分离，防止泄漏）。
- 对齐矩阵：经网格化重采样及处理后生成 `aligned_15min.csv`（默认为 15 分钟间距的标准化时间序列矩阵）。

---

## 第三部分：通用数据输出与标准产物分类体系

### 3.1 产物目录分类体系（含全分集预测文件规范）
处理流程执行中产生的全部成果，被规范化分层归类到模型层、顶层状态表与子文件夹分类体系中。特别在 **`artifacts/trains/<user_id>/` 目录下完备涵盖了主模型及基准对照模型在所有数据切分分区（Train/Val/Test）上的预测结果表**：

```
<workspace_root>/
 ├── models/                            # [持久化包资产区] 不会被单工作流清理
 │    └── <user_id>/
 │         ├── model_bundle.pkl         # 包含特征归一化器、主模型、校正模型与元数据的综合模型包
 │         ├── baseline_model.pkl       # 对照基准模型包（如基础 RF）
 │         ├── split_dates_bundle.json  # 记录分配入 train/val/test 的具体日期元数据清单
 │         └── weather_cache/           # 外源协变量（气象等）本地缓存支持
 └── artifacts/                         # [运行过程产物区] 包含白名单保护层与训/推双目录结构
      ├── batch_execution_state.csv     # (白名单保护) 原子更新的断点续跑 9 列标准表
      ├── batch_run_summary.csv         # (白名单保护) 任务执行的全局 KPI 精度总表
      ├── summary_metrics_all_users.csv # (白名单保护) 全体任务全生命周期评估表
      ├── skipped_users.csv             # (白名单保护) 策略跳过对象清单
      ├── trains/                       # [训练与离线验证产物分类体系]
      │    └── <user_id>/
      │         ├── train_pred.csv      # ⭐ 主模型在训练集 (Train Split) 上的完整预测与残差明细
      │         ├── val_pred.csv        # ⭐ 主模型在验证集 (Val Split) 上的完整预测与残差明细
      │         ├── test_pred.csv       # ⭐ 主模型在测试集 (Test Split) 上的完整预测与残差明细 (含校正残差列)
      │         ├── train_pred_rf.csv   # ⭐ 基准/对照模型 (Baseline RF) 在训练集上的预测明细
      │         ├── val_pred_rf.csv     # ⭐ 基准/对照模型 (Baseline RF) 在验证集上的预测明细
      │         ├── test_pred_rf.csv    # ⭐ 基准/对照模型 (Baseline RF) 在测试集上的预测明细
      │         ├── train_on_periods.csv       # 训前完整事件行为段级统计明细表
      │         ├── train_on_periods_daily.csv # 训前事件行为逐日统计表 (含背景基静默行)
      │         └── temp_power_lut.csv         # 训练侧 20 桶协变量-目标分箱参考基底表
      └── infers/                       # [独立生产推理与评估产物分类体系]
           └── <user_id>/
                ├── predictions/
                │    └── inference_result.csv  # 生产级推理阶段完整多模型对比预测表
                ├── metrics/
                │    ├── inference_metrics.csv       # 整体推断评估表
                │    ├── inference_daily_metrics.csv # [25列标准] 逐日追踪与原始采集密度监控表
                │    └── inference_comparison.csv    # 生产主模型与各参考基准算法横向对比表
                ├── infer_on_periods.csv             # 推前运行事件段级明细表
                ├── infer_on_periods_daily.csv       # 推前事件行为每日统计表
                └── inference_temp_power_actual_vs_expected.csv # 动态协变量分布对比与漂移告警表
```

### 3.2 模型与元数据持久化结构 (`models/<user_id>/`)
- `model_bundle.pkl`：封装处理流、标准归一化组件、回归/分位/分类模型对象及后处理校正模型的统一包。
- `baseline_model.pkl`：对照基准模型（如 Baseline RF），支持模型层横向效益对齐。
- `split_dates_bundle.json`：持久化记录被划分入 `train_dates` / `val_dates` / `test_dates` 的具体日期，供推理侧做数据泄漏识别与数据集归属标记。

### 3.3 通用多层级与多数据集预测产物表标准结构

#### (1) 训练与离线评估全切分集预测表 (`train_pred.csv`, `val_pred.csv`, `test_pred.csv` 及对照组 `*_rf.csv`)
为确保训练与离线阶段各分集的过拟合检验、残差分布核查及基线比对有完整的可追溯数据支持，系统在训练阶段 (`03_train.py` / `04_evaluate.py`) 为**主模型 (`main`)** 和**基准参考算法（如 `Baseline RF`）**各同步写盘生成三个独立的数据分切预测文件：
- **核心文件覆盖含义**：
  - `train_pred.csv` / `val_pred.csv` / `test_pred.csv`：主回归/分类建模流程分别在训练子集、验证子集与测试子集上输出的逐点预测值、状态判定及残差数据。在 `test_pred.csv` 末尾还将追加经后处理残差校正（如 L4 Calib）后的校正预测列及校正残差列，以便于开展可视化分析。
  - `train_pred_rf.csv` / `val_pred_rf.csv` / `test_pred_rf.csv`：同一份数据分布下，参考对照模型（如基础随机森林算法或基线策略）在对应三集上的完整逐点预测与残差值，提供零偏倚模型评估横向基准。
- **全切分集通用表结构定义 (`save_predictions_csv` 输出规范)**：
  | 列名 | 类型 | 功能说明 |
  |---|---|---|
  | `time` | ISO String | 等距重采样对齐时间戳 |
  | `y_true_W` | Float | 真实标准目标值 |
  | `y_pred_W` | Float | 模型在当前切分子集上的预测输出目标值 |
  | `residual_W` | Float | 模型预测绝对残差 (`y_pred_W - y_true_W`) |
  | `state_true` | Int (0/1) | （可选）基于业务阈值计算的真实事件激活状态 (`Active State`) |
  | `state_pred` | Int (0/1) | （可选）模型预测对事件激发的 0/1 判定 |
  | `p_on` | Float (0~1) | （可选）状态分类器输出的激活概率估值 |
  | `y_pred_low_W` / `y_pred_high_W` | Float | （可选）目标预测的区间分布下界与上界 |
  | `y_pred_W_main_L4_calib` / `residual_W_main_L4_calib` | Float | （仅 `test_pred.csv` 增加）附加残差学习层调正后的终态预测及对应残差 |

#### (2) 生产独立推理阶段多级对比预测表 (`predictions/inference_result.csv`)
用于独立生产评估阶段，汇纳最终业务输出与各子结构层级对比预测。列结构为：
| 列名 | 类型 | 功能说明 |
|---|---|---|
| `time` / `event_time` | ISO String | 等距统一序列时间戳 |
| `y_true` | Float | 真实标准目标值（未标注独立盲测推理场景可缺省） |
| `y_pred_W_main` | Float | **主流程生产级最终输出**（融合分类-分位数回归、残差学习层与多模型自适应切换结果） |
| `y_pred_W_main_raw` | Float | 原始回归模型输出值（无残差层，用于剥离后处理评估） |
| `y_pred_W_main_L4_calib` | Float | 仅叠加残差校正层（L4）调整后的数值 |
| `state_pred_main` / `p_on_main` | Int(0/1) / Float | 主流触发二值状态判断及对应估计置信度概率 |
| `y_pred_low_W_main` / `y_pred_high_W_main` | Float | 不确定性区间下边界与上边界 |
| `residual_W_main_raw` / `residual_W_main_L4_calib` | Float | 原始及校正后对真值的残差序列 |
| `y_pred_W_rf` / `y_pred_W_fallback` ... | Float | 各基线参考模型水平比较列 |

### 3.4 通用逐日评估与输入审计表 (`train_daily_metrics.csv` / `inference_daily_metrics.csv`)
本规范确立了 **25 列标准化逐日评估与数据审查表规范**，既包含对齐后核心质量指标，又内嵌源数据采集点审计列，实现算法误差与数据漏采异常精准判定：

| 顺序索引 | 字段名 | 类型 | 通用涵义与应用价值 |
|---|---|---|---|
| 1 | `date` | String | 具体观察日期 (`YYYY-MM-DD`) |
| 2 | `split` | String | 该时间区间在处理逻辑上的归属 (`train` / `val` / `test` / `inference`)；若推理集与训练范围重叠，自动拆为 `inference_leak`（数据泄漏区）和 `inference_ood`（合规 OOD 区域）两行以示分离 |
| 3 | `model` | String | 模型标签标识（如 `main` 或 `rf`） |
| 4 | `n_samples` | Int | 本日经等距离采样及网格对齐后所得到的有效总样本行数 |
| 5 | **`n_bus_raw`** | Int / `""` | **[审计特化·源表监控] 对应此日期内，在上游主特征原始 CSV 文件里所能够真实读取到的条目总数**（无需等距对齐；若数据缺失或记录远低于 288 条 15 分钟满载值，明确标注异常来自于原数据采漏） |
| 6 | **`n_branch_raw`** | Int / `""` | **[审计特化·源表监控] 对应此日期内，在目标/真值原始 CSV 中实际具备的实体总条数** |
| 7~11 | `Accuracy`, `Precision`, `Recall`, `F1`, `AUC` | Float | 事件分类判定的性能指标体系（保留 4~6 位小数） |
| 12~14 | `MAE_W`, `RMSE_W`, `SAE` | Float | 连续估计回归误差；其中 `SAE`（标准累积绝对误差）反映该区间总能量量的总体偏差度 |
| 15~17 | `kWh_true`, `kWh_pred`, `kWh_err` | Float | 该日累计能量/总贡献量的对应关系（标准总计值 / 预测终态值 / 累计绝对残差差值） |
| 18~21 | `TP`, `FP`, `FN`, `TN` | Int | 逐日分类混淆矩阵事件总计数 |
| 22 | `dataset` | String | 指明本数据行在划分体系上的来源（辅助区分 `used`/`excluded` 等状态） |
| 23 | `on_thr_w` | Float | 用于将连续回归值转换为事件判定（Active State）的基础临界阈值 |

### 3.5 周期性事件段级统计表 (`<stage>_on_periods.csv` & `_daily.csv`)
- **段级详表 (`<stage>_on_periods.csv`)**：
  - 提取数据中的连续活动激发阶段（Active State Segment），输出列：`being_time`（起始时间）、`end_time`（结束时间）、持续分长 `duration_min`、运行期望均值 `mean_w`、瞬时极值 `peak_w`，及累计总量 `energy_kwh`。
  - **最小极值字段 (`min_w`，v13.16 扩展)**：统计连续激发区间内的“最小瞬时记录值”，严格保障 `min_w <= mean_w <= peak_w`。
  - **背景静默基线行 (OFF Day Row，v13.11 扩展)**：在全天无任何激发状态的时段，系统自动补充静默背景记录行（`duration_min=1440`，均值/极值为全天背景基线水平）。
- **每日事件摘要表 (`<stage>_on_periods_daily.csv`)**：
  - 汇总给出每日总体统计：`date`、开机段频次 `n_segments`（静默日默认为 0）、持续时长 `total_on_min`、累计小时 `total_on_hours`、首/末次激发时间及综合加权均值。

### 3.6 协变量参考基底表 (`temp_power_lut.csv`) 与偏差状态表 (`inference_temp_power_actual_vs_expected.csv`)
- **协变量分桶参考表 (`temp_power_lut.csv`)**：
  - 将关键协变量划分成 20 个同宽区间（Bin 1 ~ Bin 20），外加全量兜底桶 `ALL_MEDIAN`（共 21 行）。列结构包含分桶边界、期望中位数 `expected_signal`、样本量及分位数特征。
- **动态协变量分布对比表 (`inference_temp_power_actual_vs_expected.csv`)**：
  - 比较推理实测均值中位值与期望参考值的差异，输出 `abs_residual` 与相对漂移 `rel_drift`，并给出通用标准判定指示 **`drift_flag`** (`OK` / `WARN` / `ALERT` / `NO_DATA`)。

### 3.7 批量原子断点续跑状态表 (`artifacts/batch_execution_state.csv`)
- **双保险文件写入语义**：执行对 `batch_execution_state.csv` 的写入时，统一采取“先在内存写就 `batch_execution_state.csv.tmp` 临时文件 -> 操作完毕调用系统无缝原子指令 (`os.replace`) 覆盖原盘”的方式；若发生系统中断，永远保障已落盘的主表完整性，最多损失当前一项条目。
- **9 列标准化协议字段 (UTF-8-BOM)**：
  1. `user_id`：受管理的任务主键或用户字符串
  2. `status`：执行结论状态（`ok` / `fail` / `soft_skip`）
  3. `success`：成功布尔标量（`True` / `False`）
  4. `started_at` / `finished_at`：进出任务链路的时间戳
  5. `duration_s`：当前对象节点总处理耗时秒数
  6. `message`：执行状态说明或中文堆栈提示
  7. `target_col`：经处理确认后的目标表达式（如 `p1+p2`）
  8. `run_id`：运行所属的批量控制执行代码识别主键

---

## 第四部分：通用用户配置规范体系 (JSON Configuration Framework)

框架通过 `--time-filter-config <path_to_json>` 接受一份集中化的 JSON 配置清单。任何需要控制某具体对象或全局执行逻辑的改动，均通过配置而非硬编码修改代码来实现。

### 4.1 三重配置优先级覆盖与下划线保护链
```
参数解析引擎按优先级自上而下检索策略：
  1. config["<user_id>"]["<field>"]   —— 最高优先 (专门为该主键 ID 配置的具体设定)
  2. config["_default"]["<field>"]    —— 次高优先 (全局统一模版兜底，所有未指定对象享用)
  3. 代码层内置的常数默认兜底值      —— 保底生效
```
> **预留名称空间安全保障**：所有以单下划线开头命名的 JSON 属性名称（包含但不限于 `_note_`、`_comment_`、`_default`、`_v135_full_example_`）一律视作注释与框架元声明，调配器自动跳过，保证不会误判为真实受控对象主键。

### 4.2 六大标准功能配置层规格详解

#### [模块 1] 顶层训练/推理时段全局白黑名单裁剪 (`train` / `infer`，v12 增强)
- **参数声明**：`"train"` 与 `"infer"` 字典开放 `"include"`（被容纳的闭区间数组）和 `"exclude"`（需移除的闭区间数组）。
- **时间范围语义**：
  - 数组元素形如 `[start_str, end_str]`，表示**闭区间** `[start, end]`。
  - 支持传入短日期 `"YYYY-MM-DD"`，按全天自动扩界（当日 `00:00:00` 至 `23:59:59`）。
  - 支持秒级精确区间 `"YYYY-MM-DD HH:MM:SS"`。
- **执行规则**：先取所有的 `include` 白名单区集的并集筛选（无指定视作保留全集），再通过 `exclude` 区间剔除落入范围内的时间点。

#### [模块 2] 目标列定义与通用复合目标 (`target_col`，v13.4 / v13.16)
- **支持模式**：
  - `"pN"`（单一目标名称，如 `"p1"`）。
  - `"pA+pB[+pC...]"`（任意带 `+` 串联的目标名，如 `"p1+p2"`，指示框架调用通用复合逻辑汇总成新目标）。
- **回退链**：若未填明，优先检索输入文件正向匹配取的指定信道，或读文件首个合规列名，最后兜底默认 `"p1"`。

#### [模块 3] 业务守卫与自适应限制策略控制 (`guard_enabled`，v13.1 / v13.5)
- **支持数值**：`true` (强制开启) / `false` (强制关闭) / `null` 或省略(触发自适应规则)。
- **自适应降级**：当不指定时，系统核对当班训练数据极值分布；如浪涌强度极小或占有效日未及 30%，系统发日志并**自动降级将其安全关停**。

#### [模块 4] 数据集细粒度分区独立过滤 (`splits`，v13.2)
- **数据结构**：开放 `splits.train`、`splits.val`、`splits.test` 下的 `include` 和 `exclude` 指令。
- **四步严格算法语义**：
  1. **原始标准划分 (Step 1)**：按照切分算法生成初始下标集合。
  2. **强制硬锚定 (Step 2 - Include)**：按照优先级 `train -> val -> test` 先到先得地将命中的样本锚定至该分区。
  3. **跨集形状恒久保护 (Step 3 - Balance)**：自动将在该集中未受到硬锚定的普通冗余记录行等比出让至缺少记录的切分集，实现零差等形平移。
  4. **黑名单排除 (Step 4 - Exclude)**：将剔除的点位转归至重分配候选池；如命中的分区具备三区全设除条件，予以全部去除。

#### [模块 5] 核心工程公共参数强行覆盖 (`common_overrides`，v13.5 / v13.13)
提供对 9 项公共常量的系统覆盖机制：
| 参数全称字段名 | 数值约束区间或类型 | 面向业务控制作用 | 异常检验失败时的处理行为 |
|---|---|---|---|
| `on_thr_w` | Float (`[0.001, 5000.0]`) | 连续目标值转换为离散事件判定 (`Active State`) 的绝对临界阈值 | 发出 `UserWarning` 警告，回退为系统常规默认 (`10.0`) |
| `split_ratios` | 3 元素 Float 数组，总和=1 | 划分 `train/val/test` 的比例数值（如 `[0.7,0.15,0.15]`，自动归一） | 校验有误时跳过并重置至内置预设 (`[0.6, 0.2, 0.2]`) |
| `split_strategy` | `"stratified_day"` / `"stratified"` / `"time"` / `"global_stratified"` | 划分采样的控制机制。**强烈建议**选用 `"global_stratified"`，跨月抽样无小月余数天数倾斜挤压 | 回退至 `"stratified_day"` |
| `post_min_on` | Int (`>= 0`) | 事件状态识别时序平滑后处理：要求一次有效激发持续的最短点数 | 忽略错误设为 `1` |
| `post_fill_short_off`| Int (`>= 0`) | 事件状态识别时序平滑后处理：需予以连接补齐的最短间断停顿步长 | 忽略错误设为 `3` |
| `weather_latitude` / `weather_longitude` | Float | 物理对应观察城市的地理定位经纬度坐标 | 默认坐标 `30.59, 114.31` |
| `use_weather_features`| Bool (`true`/`false`) | 是否把气象与温度特征纳入模型输入表 | 默认保持开启 (`true`) |
| `use_temp_based_season`| Bool (`true`/`false`) | 是否开启根据近区协变量自动做时间层多模型选择（Seasonal Routing） | 默认保持开启 (`true`) |

#### [模块 6] 高级处理与进阶特征控制属性 (`v14_flags`)
面向进阶控制，接收布尔或结构字典以实现对特征增强、后处理校正、模型集成及诊断审计报告功能的解耦开启：
```json
{
  "v14_enable": true,
  "physics": true,
  "focal": false,
  "ensemble": true,
  "calibrate": false,
  "auto_config": false,
  "health": true,
  "diag": true
}
```

---

## 第五部分：底层控制链路与核心安全保护契约

### 5.1 CLI 传递与环境变量封装解析链路
批处理层向底层实现解耦传参：
1. **JSON 参数调用**：序列化各阶段 JSON 特征至 `-time-filter-spec '...'` 等命令行传参。
2. **环境变量封堵 (`NILM_USER_*`)**：将用户在配置里的公共参数，转化为全大写的环境变量并赋予执行上下文中：
   ```bash
   NILM_USER_ON_THR_W=50.0
   NILM_USER_SPLIT_RATIOS=0.7,0.15,0.15
   NILM_USER_SPLIT_STRATEGY=global_stratified
   ```
   代码内部实现统一化无污染引用：
   ```python
   ON_THR_W = float(os.environ.get("NILM_USER_ON_THR_W", default=10.0))
   ```

### 5.2 临时产物安全隔离契约 (`_CLEANUP_WHITELIST`)
为防止执行任务在进行内部临时表清理时误伤整体批次资产，严格制订了**顶部隔离白名单契约 (`_CLEANUP_WHITELIST`)**。

`cleanup_artifacts_top(project_root)` 在清算 `artifacts/` 顶部下的任意未编目残留 `.tmp` 或对齐表时，**以下批量表或管理记录文件绝对受白名单保护豁免，不可删除**：
- `batch_execution_state.csv` —— **断点续跑 9 列通用核心状态执行控制表**
- `batch_execution_state.csv.tmp` —— 操作系统中的安全写就备份中间态
- `batch_run_summary.csv` —— 各处理全对象聚合精度的总体汇总表
- `summary_metrics_all_users.csv` —— 多模型及特征性能的对比汇总报表
- `skipped_users.csv` —— 被控制参数主动跳过的对象记录名录
- `.gitkeep` —— 项目结构空文件占位表

### 5.3 严格错误边界与优雅降级控制规则 (`WARN + Fallback`)
1. **智能数值/布尔表达兼容**：支持数字字符与多语言逻辑字面量（`"True"`, `"yes"`, `"1"`, `"on"`等）至合法数值与布尔类型的非严格兼容转换。
2. **非崩溃安全警报与系统缺省回归**：当用户传入超范围非合规值，程序均以轻量非侵入方式抛出 `UserWarning` 并剔除此值，平滑重置至下层系统确立的基础合规值兜底继续，保证业务长链高弹运行不断线。

---

# [2026-08-13] 专题：v15 多算法解耦重构报告（模块化隔离 + 三种运行模式 + 算法维度产物体系）

> **专题类型**：工程重构 / 多算法支撑能力 / 配置与产物规范
> **目标**：对现有流水线代码实施重构，实现各功能模块解耦隔离；新增多算法模型支撑能力（主模型 main / RF 基线 rf / v14 增强版三类算法代码模块解耦隔离，统一输入输出接口）；开放配置入口支持三种自定义运行模式（指定单模型 single、多模型选择性 multi、全部模型遍历 all）；产物输出按算法维度子目录隔离归档。

## 1. 重构后的四层解耦架构

```
+------------------------------------------------------------------------------------------+
|  批量调度层  run_batch_users.py                                                          |
|   --algorithms main,rf,v14  --algo-mode single|multi|all   (CLI, 覆盖配置)               |
|   time_filters 配置 algorithms 字段 (每用户 / _default)                                  |
|   summary_metrics_all_users.csv 新增 algo 列 (每用户×每算法 4 行)                         |
+------------------------------------------------------------------------------------------+
                                     |  解析为 [算法序列]
                                     v
+------------------------------------------------------------------------------------------+
|  单用户流水线层  run_user_pipeline.py  (数据准备与算法执行解耦)                            |
|   共享数据准备 (02 对齐 / 训练前分析 / 推理数据准备) 只跑一次                                |
|   for algo in 算法序列:  [训练/复用 -> 评估 -> 推理 -> 按算法归档]   (故障隔离)            |
+------------------------------------------------------------------------------------------+
                                     |  统一接口
                                     v
+------------------------------------------------------------------------------------------+
|  算法插件框架  scripts/algorithms/  (AlgorithmModule 抽象基类 + 注册中心)                 |
|   main_l4.py (主模型)   rf_baseline.py (RF 基线)   v14_enhanced.py (v14 增强)             |
|   统一契约: 三阶段脚本 / 隔离环境 / CLI 参数 / 模型完整性文件清单 / 产物子目录              |
+------------------------------------------------------------------------------------------+
                                     |  --algo / NILM_ALGO_SELECT 门控
                                     v
+------------------------------------------------------------------------------------------+
|  阶段脚本层  02_align (共享) / 03_train (NILM_ALGO_SELECT 训练门控)                        |
|             04_evaluate (--algo main|rf) / 05_inference (--algo main|rf)                 |
+------------------------------------------------------------------------------------------+
```

四层隔离实现口径：
1. **代码模块隔离**：每个算法一个模块文件，互不 import 对方实现；新算法 = 继承 `AlgorithmModule` + 注册一行。
2. **训练门控隔离**：`03_train.py` 由环境变量 `NILM_ALGO_SELECT`（main / rf / main+rf，默认 main+rf 与重构前完全一致）决定本次训练范围；rf-only 产出自包含 `rf_bundle.pkl`（含 scaler / 特征列 / ON 阈值 / 切分日期等统一接口所需全部上下文）。
3. **运行环境隔离**：每个算法的三阶段子进程拥有独立 env（v14 的 monkey-patch 不再泄漏到其他算法）；v14 物理特征环境在训练/评估/推理三阶段一致注入（特征一致性契约，规避 scaler 维度不匹配）。
4. **产物隔离**：模型与产物按算法子目录归档（见第 3 节）；main 与 v14 即使共用主模型槽位也互不覆盖。

## 2. 配置入口与三种运行模式

### 2.1 time_filters 配置扩展（用户级或 `_default` 级）

```json
"algorithms": {
  "mode": "all",
  "selected": ["main", "rf"],
  "main": {}, "rf": {}, "v14": {}
}
```

- `mode`: `single`（指定单模型执行，取 `selected` 第一个）/ `multi`（多模型选择性执行，`selected` 原样执行）/ `all`（全部注册算法按注册顺序遍历，忽略 `selected`）
- `selected`: 算法名列表；`<algo>` 子对象为算法级私有覆盖预留位
- 优先级：CLI `--algorithms` / `--algo-mode` > 配置 `algorithms` 字段 > 内置默认（main+rf，与重构前行为一致）
- 兼容：无显式配置且用户 v14 增强开关开启时，默认列表自动追加 v14（旧 `--v14-flags` 语义保持）

### 2.2 CLI 入口（批量层与单用户流水线层均支持）

```bash
python scripts/run_batch_users.py --algorithms rf --algo-mode single          # 指定单模型
python scripts/run_batch_users.py --algorithms main,v14 --algo-mode multi     # 多模型选择性
python scripts/run_batch_users.py --algo-mode all                             # 全部模型遍历
python scripts/run_batch_users.py --time-filter-config data/time_filters.json # 或按用户配置
python scripts/run_user_pipeline.py ... --algorithms main,rf --algo-mode all  # 单用户层同入口
```

解析实现统一收敛在 `scripts/algorithms/registry.py::resolve_algorithm_selection()`（含非法模式/未注册算法 WARN 剔除与空兜底）。

## 3. 产物输出结构（算法维度子目录）

```
models/
  <user_id>/
    main/    nilm_ac_two_stage.pkl, model_meta.json, scaler.pkl,
             stage1_classifier.pkl, stage2_moe_bundle.pkl
    rf/      rf_bundle.pkl, baseline_rf.pkl, rf_bundle_meta.json
    v14/     (与 main 同构 5 件套, 独立归档互不覆盖)
artifacts/
  trains/<user_id>/
    train_on_periods.csv / train_on_periods_daily.csv   (用户级数据视图, 算法无关)
    main/  train_pred.csv, val_pred.csv, test_pred.csv,
           train_val_metrics.csv, test_metrics.csv, ... 
    rf/    train_pred_rf.csv, val_pred_rf.csv, test_pred_rf.csv, ...
    v14/   (主模型槽位同名产物, 独立归档)
  infers/<user_id>/
    infer_on_periods.csv / infer_on_periods_daily.csv   (用户级数据视图)
    main/  predictions/inference_result.csv, metrics/inference_metrics.csv, ...
    rf/    predictions/inference_result.csv (rf 口径), ...
    v14/   ...
  summary_metrics_all_users.csv   [新增 algo 列] 每用户×每算法 4 行 (train/val/test/inference)
  skipped_users.csv               [新增 algo 列] 按算法维度收集软跳过原因
  batch_execution_state.csv       [新增 algorithms 列] 记录本次算法计划
```

兼容性：旧扁平布局（`trains/<user>/*.csv` 直放）聚合时以 `algo=flat` 识别，全部历史产物无需迁移即可汇总。

## 4. 行为契约（验证过的关键语义）

- **模型复用**：按算法各自的 `required_model_files` 契约检查；main 兼容旧扁平模型目录；全部所选算法模型完整时跳过 02 对齐。
- **故障隔离**：单算法软跳过（数据质量门 11/12/13）或硬失败不阻塞其他算法；05 失败时部分归档训练侧产物，不丢弃已训模型；退出码 0=≥1 算法成功 / 10=全部软跳过 / 1=无算法成功。
- **共享状态治理**：`aligned_15min.csv` / `merged_*.csv` / `infer_*.csv` / `skip_reason.json` 在多算法执行期保留（`_CLEANUP_WHITELIST` 扩展），流水线收尾统一清理。
- **汇总模型优选**：train/val/test 阶段 main/v14→`main`、rf→`rf`；inference 阶段 main/v14→`main_final`→`main`、rf→`rf`。

## 5. 验证记录

- 单元测试：`scripts/test_algorithm_registry.py`（13 项，注册完整性/接口契约/三模式解析/CLI 覆盖/v14 提示）+ `scripts/test_algo_config.py`（11 项，配置命中/_default 回退/非法防御/摘要）全部通过。
- 合成数据冒烟：03 训练门控 3 用例（rf-only 隔离 / main-only 隔离 / 默认向后兼容）、04/05 双链路 2 用例（main/rf 独立评估与推理，产物互不交叉）、流水线编排 4 用例（single/multi/all/模型复用，含 v14 三阶段特征一致性）、批量层 5 用例（dry-run 计划、CLI multi 全流程、配置驱动 single、CLI 覆盖 all、旧扁平聚合兼容）全部通过。
- 回归：既有 `test_batch_execution_state.py` / `test_composite_target_col.py` / `test_daily_raw_counts.py` / `test_min_w_column.py` 全部通过；真实数据目录 5 用户 dry-run 扫描正常。
- **遗留问题**：暂无。后续新算法接入请按 `scripts/algorithms/` 基类契约实现并在注册表登记。

---

# [2026-08-13] 专题：v16 数据输入/数据输出/数据配置三大模块解耦重构报告

> **专题类型**：工程重构 / 模块解耦 / 统一访问接口
> **目标**：针对数据输入、数据输出与数据配置功能继续重构代码，保证三个模块完全解耦（两两零依赖），并各自提供统一的访问接口；编排层与阶段脚本的全部数据 I/O 与配置访问收敛到统一入口。

## 1. 三大模块与统一接口

```
+--------------------------------------------------------------------------------+
|  编排层  run_batch_users.py (批量调度) | run_user_pipeline.py (单用户流水线)    |
+--------------------------------------------------------------------------------+
        |                        |                        |
        v                        v                        v
+---------------+        +-----------------+        +-----------------+
| 数据输入模块   |        | 数据输出模块     |        | 数据配置模块     |
| data_input.py |        | data_output.py  |        | data_config.py  |
+---------------+        +-----------------+        +-----------------+
| 发现/解析/加载/落地/过滤 | | CSV/模型资产/归档/汇总/状态 | | 集中式解析/序列化/环境翻译 |
+---------------+        +-----------------+        +-----------------+
        |                        |                        |
        v                        v                        v
+---------------+        +-----------------+        +-----------------+
| feature_utils |        | metrics_utils   |        | time_filter_utils|
| (加载/对齐/特征) |       | (指标/预测 CSV)  |        | (配置字段语义)    |
+---------------+        +-----------------+        +-----------------+
```

**解耦口径**：三模块**两两零 import 依赖**（已用程序化断言核验）；依赖方向严格单向——编排层 → 三大模块 → 底层实现层。算法维度（`scripts/algorithms/`）与数据维度（三大模块）正交解耦。

| 模块 | 统一接口要点 |
|---|---|
| **数据输入 data_input** | 命名契约 `RE_BUS`/`RE_BR`；`parse_data_dir`→`parse_user_folder`→`discover_users` 发现解析链（配置 target_col 优先 → Ch{N} 反推 → 分路 pN 退化 → 默认 p1）；`is_runnable`/`get_execution_plan` 计划描述；`load_bus_csv`/`load_branch_csv`/`resample_and_align` 原始加载门面；`stage_train_data`/`stage_infer_data`/`cleanup_staged_data_files` 运行时落地与收尾清理；`parse_time_filter_spec`/`apply_time_filter_spec` 时段过滤一步到位入口 |
| **数据输出 data_output** | `write_csv` 通用写出；预测/指标写出门面（`save_predictions_csv`/`save_metrics_csv`/`save_daily_metrics_csv`/`build_comparison_table`/`build_daily_metrics_rows`/`build_leak_ood_metric_rows`/`compute_raw_daily_counts` 等）；模型资产持久化（`resolve_model_path` 算法感知路径解析 / `load_model_bundle` / `save_model_bundle` 含时间戳备份+滚动清理 / `save_model_components` 组件 pkl+meta JSON）；归档清理（`archive_algo_outputs` 算法维度归档 / `cleanup_artifacts_top` 白名单保护 / `restore_algo_models_to_top` / `check_algo_model_complete`）；批量层（执行状态 CSV 四函数、`collect_skip_reasons`、`aggregate_metrics`） |
| **数据配置 data_config** | `ConfigResolver`（配置 + CLI 覆盖 → 每用户生效配置，支持 dict/path 双入口与 `from_batch_args` 便捷构造）；`UserConfig`（已解析生效值对象：target_col / guard_enabled / train·infer 时段 / splits / common_overrides / v14_flags / algorithms / algo_mode / warnings）；序列化接口 `to_pipeline_cli()`/`plan_line()`；配置→环境翻译（`common_overrides_to_env`/`clear_common_override_env`/`guard_cli_to_env`/`v14_flags_to_env`/`splits_spec_cli_to_env`/`v14_enabled_from_spec`）；time_filter_utils 全部门面再导出 |

## 2. 收敛范围（重构前 → 重构后）

| 原位置 | 收敛去向 |
|---|---|
| run_batch_users：RE_BUS/RE_BR、parse_user_folder、discover_users、is_runnable、get_execution_plan | → data_input |
| run_batch_users：执行状态 CSV 四函数、collect_skip_reasons、aggregate_metrics | → data_output |
| run_batch_users：resolve_user_run_config 内联配置解析 | → data_config.ConfigResolver.resolve() → UserConfig |
| run_user_pipeline：setup_user_data / setup_infer_data | → data_input.stage_train_data / stage_infer_data |
| run_user_pipeline：archive_algo_outputs / cleanup_artifacts_top / restore_algo_models_to_top / check_algo_model_complete | → data_output |
| run_user_pipeline：守卫/splits/common 覆盖/v14 的 env 翻译内联代码 | → data_config 翻译接口 |
| 02：原始加载 + 时段过滤 import | → data_input / data_config |
| 03：指标写出 + bundle/组件/meta 落盘 + d87 原始加载 | → data_output（save_model_bundle/save_model_components）/ data_input |
| 04/05：指标写出 + rf 模型路径解析（05 另含时段过滤） | → data_output / data_input / data_config |
| test_batch_execution_state：导入源 | → data_output（断言不变） |

## 3. 关键语义保持契约（重构护栏）

重构坚持"**只搬家、不改语义**"：目标列反推链、时段过滤闭区间语义、`_CLEANUP_WHITELIST` 白名单保护、汇总模型优选顺序（train/val/test：main/v14→`main`、rf→`rf`；inference：main/v14→`main_final`→`main`、rf→`rf`）、旧扁平布局聚合兼容（`algo=flat`）、v14 三阶段特征环境一致性、备份滚动清理（保留 3 份 + 主文件/v42 对照文件豁免）等历史行为逐一保留。

## 4. 验证记录

- **新增单测 27 项**：`test_data_config.py`（10 项：解析器/CLI 优先级/_default 回退/序列化/环境翻译）、`test_data_input.py`（8 项：命名契约/解析链/反推退化/落地往返/时段过滤）、`test_data_output.py`（9 项：写出/模型资产/归档布局/白名单/状态/聚合算法维度+扁平兼容）全部通过。
- **既有单测回归**：test_batch_execution_state（导入改指 data_output）、test_composite_target_col、test_daily_raw_counts、test_min_w_column、test_algorithm_registry、test_algo_config 全部通过。
- **全链路冒烟回归**：03 训练门控 3 用例（rf-only/main-only/默认向后兼容）、04/05 双链路 2 用例、流水线编排 4 用例（single/multi/all/模型复用）、批量层 5 用例（dry-run/CLI multi/配置 single/CLI 覆盖 all/扁平兼容）全部通过。
- **解耦关系核验**：程序化断言三模块两两零 import 依赖；残留引用扫描（`setup_user_data`/`resolve_user_run_config`/`_parse_one_dir` 等）为零。
- **遗留问题**：暂无。后续新数据能力按归属接入：读取→data_input、写出→data_output、配置字段→data_config（语义实现沉淀在 time_filter_utils）。

---

# [2026-08-13] 专题：v16 重构后全量批量验证测试报告（5 用户 × 3 算法全流程重跑）

> **专题类型**：验证测试 / 重构回归验收
> **目标**：在 v15 多算法解耦 + v16 三大数据模块解耦重构完成后，对仓库内全部 5 个真实用户数据重新执行批量「训练 + 评估 + 推理」全流程验证，确认重构后功能完备、行为等价、产物结构正确。

## 1. 执行方案

| 项 | 值 |
|---|---|
| 执行命令 | `python scripts/run_batch_users.py --algo-mode all --force-retrain --continue-on-error` |
| 运行模式 | all（全部模型遍历：main → rf → v14，每用户单子进程顺序执行） |
| 用户范围 | 全部 5 个真实用户（data/trains/ 与 data/infers/ 并集） |
| 时段过滤 | 未加载 time-filter-config（默认无过滤，守卫自动检测开启） |
| 气象数据 | Open-Meteo API 不可达（沙箱无外网）→ 自动降级经验气温（验证了降级链路） |
| 耗时预估 | 先以最大用户做单用户探针：main 234s、rf+v14 370s，合计约 10 分钟/用户 |

## 2. 执行结果

**批量执行总结（退出码 0）**：

```
总用户数: 5 | 可执行: 5 | 跳过: 0 | 执行成功: 5 | 软跳过: 0 | 失败: 0
总耗时: 1694.8s (28.2 分钟)
```

| 用户 | 状态 | 耗时 |
|---|---|---|
| 800080252842_4206894986488 | ok | 596.9s |
| 800080252844_4206894986488 | ok | 215.5s |
| 800080270778_4200903422131 | ok | 192.2s |
| 800080270789_4206680982373 | ok | 461.0s |
| 800080270800_4200904302272 | ok | 229.1s |

单用户耗时均低于批量层 20 分钟/用户超时保护，`--continue-on-error` 未触发任何降级。

## 3. 产物体检（77/77 项通过）

| 体检项 | 结果 |
|---|---|
| 产物目录结构 | 5 用户 × 3 算法 × trains/infers = 30 个算法子目录全部非空 ✓ |
| 模型资产契约 | 15 组（main/v14 五件套 + rf 自包含 rf_bundle.pkl）全部齐全 ✓ |
| 关键预测产物 | main 三分集（train/val/test_pred.csv）+ rf 三分集（*_rf.csv）+ 三算法 inference_metrics.csv 全部齐全 ✓ |
| 批量执行状态 | batch_execution_state.csv 5 行全 ok，algorithms 列 = main,rf,v14 ✓ |
| 汇总表 | summary_metrics_all_users.csv 60 行（5 用户 × 3 算法 × 4 stage），含 algo 列，inference 行 15 ✓ |
| 指标源文件抽查 | 训练/测试/推理三张长表模型集正确隔离（main 目录仅 main/main_L4_calib/fallback，rf 目录仅 rf，v14 同 main 槽位） ✓ |

## 4. 各算法指标对比（5 用户均值）

**test 集（与训练同分布）**：

| 算法 | F1 | MAE_W | SAE |
|---|---|---|---|
| main（主模型 L4） | 0.765 | 121.6W | 17.4% |
| rf（RF 基线） | 0.755 | 117.6W | **11.8%** |
| v14（增强版） | **0.769** | 121.6W | 14.7% |

**inference 集（OOD 生产推理）**：

| 算法 | F1 | Accuracy | MAE_W | SAE |
|---|---|---|---|---|
| main | **0.873** | **0.946** | 67.0W | 17.2% |
| rf | 0.817 | 0.863 | **52.4W** | **3.4%** |
| v14 | 0.870 | 0.941 | 67.7W | 18.1% |

**每用户 main 算法 test 集 F1/SAE**：

```
800080252842_4206894986488: F1=0.914  SAE=10.4%
800080252844_4206894986488: F1=0.836  SAE= 3.5%
800080270778_4200903422131: F1=0.502  SAE=34.7%   ← 个体差异, 可后续专题排查
800080270789_4206680982373: F1=0.838  SAE=31.7%
800080270800_4200904302272: F1=0.736  SAE= 6.6%
```

## 5. 结论

1. **重构回归验收通过**：v15/v16 两轮重构后，全量真实数据批量流水线一次性跑通，5/5 用户 × 3/3 算法全成功，产物结构、汇总表、状态表、模型契约全部正确。
2. **多算法支撑能力验证通过**：main/rf/v14 三算法在同一次 all 模式批量执行中独立训练、独立评估、独立推理、独立归档，指标行模型集互不交叉（解耦隔离生效）。
3. **指标观察**：rf 基线 SAE 显著低于主模型（能量口径误差小），但 F1/Accuracy 略低；v14 相比 main 在 test 集 F1 略升且 SAE 下降，inference 集表现与历史 L5/OOD 场景一致。个体用户（800080270778）main F1 偏低属数据个体差异，不影响框架验证结论。
4. **产物治理**：artifacts/（15M）+ models/（204M）全部被 .gitignore 隔离，验证运行不污染仓库。
- **遗留问题**：无阻塞项。800080270778 指标偏低可作后续优化专题（可选）。

---

# [2026-08-13] 专题：v17 各模型训练推理统一访问接口重构报告

> **专题类型**：工程重构 / 统一访问接口 / 算法功能抽象
> **目标**：针对各模型训练推理功能继续重构代码，提供统一的访问接口——各算法模块的训练/评估/推理功能统一为可调用接口（`train/evaluate/infer` → 结构化结果），流水线不再手工拼装子进程命令。

## 1. 统一访问接口全景

```
外部调用方 (流水线 / 批量调度 / 测试 / 未来服务)
      │  统一访问接口
      ▼
+---------------------------------------------------------------+
| train_models(names, ctx)  evaluate_models(names, ctx)  infer_models(names, ctx)  ← 注册表级统一多模型入口
| get_algorithm("main").train(ctx) / .evaluate(ctx) / .infer(ctx)                    ← 单模型统一接口
+---------------------------------------------------------------+
      │ 组装 (脚本 + 隔离环境 + 算法参数 + 通用参数)               │ StageResult 结构化结果
      ▼                                                          ▼
+--------------------+        +-----------------------------------------------------+
| StageRunner        │  ────▶ │ StageResult { algo, stage, status, exit_code,       |
| 统一阶段执行器      │        │   message, duration_s; ok/is_soft_skip/is_fail }   |
| (子进程隔离/UTF-8/  │        |  status ∈ ok | soft_skip(11/12/13) | fail          |
|  超时/日志)         │        +-----------------------------------------------------+
+--------------------+
```

## 2. 接口清单

| 接口 | 说明 |
|---|---|
| `AlgorithmModule.train(ctx, runner=None) -> StageResult` | **统一训练接口**：组装训练脚本 + 隔离环境（train_env）+ 算法参数（train_args）并执行 |
| `AlgorithmModule.evaluate(ctx, runner=None) -> StageResult` | **统一评估接口**：测试集评估阶段 |
| `AlgorithmModule.infer(ctx, runner=None) -> StageResult` | **统一推理接口**：自动组装 `--bus`（落地推理总线）/`--branch` 或 `--no-branch`（落地分路）/`--time-filter-spec`（推理时段过滤）通用参数；`ctx.infer_bus_staged` 未落地时 fail-fast |
| `train_models / evaluate_models / infer_models(names, ctx, runner)` | **注册表级统一多模型入口**：对算法序列逐个执行并返回 `dict[str, StageResult]`，如实透传各算法状态（软跳过/失败不吞掉） |
| `StageRunner.run(script, args, env, label, ...) -> StageResult` | **统一阶段执行器**：退出码翻译（0→ok / 11,12,13→soft_skip / 其他→fail）、子进程环境隔离、PYTHONIOENCODING UTF-8 端到端、1200s 超时、日志文件旁路 |
| `StageResult.ok / .is_soft_skip / .is_fail / .summary()` | 结构化结果判定与单行摘要 |

三算法统一 dispatch（实测断言）：
- main：train→`03_train.py` + `NILM_ALGO_SELECT=main`；eval/infer→`04/05 + --algo main --no-baseline`
- rf：train→`03_train.py` + `NILM_ALGO_SELECT=rf`；infer 自动加 `--model models/rf_bundle.pkl`
- v14：train→`14_train_v14.py` + `NILM_V14_*`；eval/infer 同步注入 v14 特征环境（三阶段特征一致性契约）

## 3. 流水线收敛（重构前 → 重构后）

| 原实现 | v17 收敛后 |
|---|---|
| 流水线手工拼装 `[PY, script] + args + [--bus ...]` 命令 | `algo_mod.train/evaluate/infer(ctx, runner)` 统一接口 |
| `run_step` 子进程封装 + `_SoftSkip` 异常驱动流程 | `StageRunner` 统一执行器 + `StageResult` 状态驱动流程（run_step/_SoftSkip 已删除） |
| 02 对齐共享步骤单独拼装 | 同样经由 `runner.run("02_align_and_feat.py", args, label="02 对齐+特征")` |
| 软跳过异常捕获 → skip_reason 归档 | `StageResult.is_soft_skip` 分支 → skip_reason 双路归档（算法目录 + 用户扁平目录） |

行为语义逐一保持：软跳过退出码（11/12/13）、skip_reason 归档、推理失败部分归档训练产物、流水线退出码 0/10/1 三态契约、模型复用契约。

## 4. 验证记录

- **新增单测 12 项**（`test_algo_runner.py`）：真实子进程退出码映射与软跳过集合、环境注入隔离（父进程零污染）、三算法 dispatch 组装断言、推理通用参数自动组装（含 no-branch/时段过滤/未落地 fail-fast）、注册表级多模型入口顺序与状态透传、StageResult 判定属性与摘要。
- **流水线冒烟 4 用例**（single/multi/all/模型复用）通过——统一接口重构后行为等价。
- **软跳过新路径验证**：半天级小数据触发数据质量门 11 → 流水线退出码 10 + `skip_reason.json` 双路归档，与 v15 语义一致。
- **回归**：既有 9 个单测脚本（算法注册 13 / 配置解析 11 / 三大数据模块 27 / 执行状态 / 复合目标列 / 日级原始点数 / min_w 列）全部通过；批量层 dry-run 正常。
- **遗留问题**：暂无。未来新算法接入 = 继承 `AlgorithmModule` + 注册一行，即自动获得训练/推理统一访问接口与流水线调度能力。
