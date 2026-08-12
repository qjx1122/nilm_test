# -*- coding: utf-8 -*-
"""
生成项目技术方案说明书 Word 文档 (.docx) —— 通用抽象规范版
《项目通用数据输入输出、用户配置管理及算法标准产物全景架构规范说明书》
注：抽象核心业务私有算法细节，专注项目整体结构、数据输入输出和数据配置结构及通用算法输出规范。
"""

import os
from pathlib import Path
import docx
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn

def set_cell_background(cell, fill_color):
    """为单元格设置背景填充色 (#RRGGBB Hex 格式)"""
    tcPr = cell._element.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_color}"/>')
    tcPr.append(shd)

def set_cell_margins(cell, top=100, bottom=100, left=150, right=150):
    """为单元格设置内边距"""
    tcPr = cell._element.get_or_add_tcPr()
    tcMar = parse_xml(f'<w:tcMar {nsdecls("w")}><w:top w:w="{top}" w:type="dxa"/><w:bottom w:w="{bottom}" w:type="dxa"/><w:left w:w="{left}" w:type="dxa"/><w:right w:w="{right}" w:type="dxa"/></w:tcMar>')
    tcPr.append(tcMar)

def set_table_borders(table, color="D3D3D3", sz="4", val="single"):
    """设置表格四边与内部灰线边框"""
    tblPr = table._element.xpath('w:tblPr')
    if tblPr:
        borders = parse_xml(f'<w:tblBorders {nsdecls("w")}><w:top w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/><w:bottom w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/><w:insideH w:val="{val}" w:sz="{sz}" w:space="0" w:color="{color}"/><w:insideV w:val="none"/><w:left w:val="none"/><w:right w:val="none"/></w:tblBorders>')
        tblPr[0].append(borders)

def add_heading_styled(doc, text, level):
    p = doc.add_paragraph()
    p.paragraph_format.keep_with_next = True
    run = p.add_run(text)
    run.bold = True
    run.font.name = "Calibri"
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    if level == 1:
        p.paragraph_format.space_before = Pt(18)
        p.paragraph_format.space_after = Pt(8)
        run.font.size = Pt(17)
        run.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F) # 深蓝
    elif level == 2:
        p.paragraph_format.space_before = Pt(14)
        p.paragraph_format.space_after = Pt(6)
        run.font.size = Pt(13.5)
        run.font.color.rgb = RGBColor(0x2B, 0x54, 0x7E) # 中蓝
    elif level == 3:
        p.paragraph_format.space_before = Pt(10)
        p.paragraph_format.space_after = Pt(4)
        run.font.size = Pt(11.5)
        run.font.color.rgb = RGBColor(0x36, 0x64, 0x8B)
    return p

def add_para_styled(doc, text, bold_prefix=None, space_after=6, line_spacing=1.25):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = line_spacing
    if bold_prefix:
        r_pre = p.add_run(bold_prefix)
        r_pre.bold = True
        r_pre.font.name = "Calibri"
        r_pre.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        r_pre.font.size = Pt(10.5)
        r_pre.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
    run = p.add_run(text)
    run.font.name = "Calibri"
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(10.5)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    return p

def add_code_block(doc, text):
    table = doc.add_table(rows=1, cols=1)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    cell = table.cell(0, 0)
    set_cell_background(cell, "F5F7FA")
    set_cell_margins(cell, top=120, bottom=120, left=180, right=180)
    tcPr = cell._element.get_or_add_tcPr()
    borders = parse_xml(f'<w:tcBorders {nsdecls("w")}><w:top w:val="none"/><w:left w:val="single" w:sz="24" w:space="0" w:color="3B71CA"/><w:bottom w:val="none"/><w:right w:val="none"/></w:tcBorders>')
    tcPr.append(borders)
    p = cell.paragraphs[0]
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.line_spacing = 1.15
    run = p.add_run(text.strip())
    run.font.name = "Consolas"
    run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run.font.size = Pt(9.5)
    run.font.color.rgb = RGBColor(0x24, 0x29, 0x2F)
    doc.add_paragraph().paragraph_format.space_after = Pt(6)

def add_styled_table(doc, headers, rows_data, col_widths=None):
    table = doc.add_table(rows=len(rows_data) + 1, cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    set_table_borders(table, color="D0D7DE", sz="4")
    
    # Header row
    hdr_cells = table.rows[0].cells
    for i, title in enumerate(headers):
        hdr_cells[i].text = ""
        p = hdr_cells[i].paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(title)
        run.bold = True
        run.font.name = "Calibri"
        run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
        run.font.size = Pt(10)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        set_cell_background(hdr_cells[i], "2B547E")
        set_cell_margins(hdr_cells[i], top=120, bottom=120, left=100, right=100)
    
    # Data rows
    for r_idx, r_data in enumerate(rows_data):
        row_cells = table.rows[r_idx + 1].cells
        fill_color = "FFFFFF" if r_idx % 2 == 0 else "F7F9FB"
        for c_idx, val in enumerate(r_data):
            row_cells[c_idx].text = ""
            p = row_cells[c_idx].paragraphs[0]
            if c_idx == 0:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = p.add_run(str(val))
            run.font.name = "Calibri"
            run.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
            run.font.size = Pt(9.5)
            run.font.color.rgb = RGBColor(0x22, 0x22, 0x22)
            set_cell_background(row_cells[c_idx], fill_color)
            set_cell_margins(row_cells[c_idx], top=80, bottom=80, left=100, right=100)
            
    if col_widths:
        for row in table.rows:
            for idx, w in enumerate(col_widths):
                row.cells[idx].width = Inches(w)
    doc.add_paragraph().paragraph_format.space_after = Pt(8)


def create_document():
    doc = docx.Document()
    
    # 设置页边距
    for section in doc.sections:
        section.top_margin = Inches(1.0)
        section.bottom_margin = Inches(1.0)
        section.left_margin = Inches(1.0)
        section.right_margin = Inches(1.0)
        
    # 文档大标题
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_before = Pt(24)
    p_title.paragraph_format.space_after = Pt(8)
    run_t = p_title.add_run("项目技术方案说明书：\n通用数据输入输出、用户配置架构及通用算法产物全景规范")
    run_t.bold = True
    run_t.font.name = "Calibri"
    run_t.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run_t.font.size = Pt(21)
    run_t.font.color.rgb = RGBColor(0x1E, 0x3A, 0x5F)
    
    p_sub = doc.add_paragraph()
    p_sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_sub.paragraph_format.space_after = Pt(24)
    run_s = p_sub.add_run("—— 通用抽象规范版（系统架构、数据标准、配置层级与产物字典） ——")
    run_s.font.name = "Calibri"
    run_s.element.rPr.rFonts.set(qn('w:eastAsia'), '微软雅黑')
    run_s.font.size = Pt(11)
    run_s.font.color.rgb = RGBColor(0x55, 0x66, 0x77)
    
    # =========================================================================
    # 第 1 章：项目整体架构与二层解耦调度模型
    # =========================================================================
    add_heading_styled(doc, "第 1 章  项目整体结构与二层解耦调度控制模型", level=1)
    
    add_heading_styled(doc, "1.1 总体架构说明与解耦工作流", level=2)
    add_para_styled(doc, "为支持通用时序多通道数据的批量建模、离线评估与生产推理，系统设计为“批量编排调度层 (run_batch_users.py)”与“单任务流水线执行引擎 (run_user_pipeline.py)”二层解耦体系。批量调度层负责多对象的物理目录检索、配置规范统一加载及断点续跑管理；流水线层负责单任务的数据健康勘察、重采样网格对齐、通用模型构建、多阶段预测计算与自动化指标汇总说明，具备良好的高弹性与易扩展性。", bold_prefix="【架构解耦宗旨】：")
    
    arch_chart = """
+-----------------------------------------------------------------------------------------------+
|                             批量调度层 (run_batch_users.py)                                   |
|  - 自动扫描工作目录 (data/) 并解析受管理对象 (User/Device) 的输入源文件映射链                   |
|  - 统一解析外部集中式 JSON 配置文件，构建优先权参数体系并向底层进程下发                         |
|  - 原子化维护 9 列标准状态表 (batch_execution_state.csv)，支持 --resume 断点续跑               |
+-----------------------------------------------------------------------------------------------+
                                               |
         (通过序列化 JSON CLI 参数 --time-filter-spec 及环境变量 NILM_USER_* 进行环境封堵与透传)
                                               v
+-----------------------------------------------------------------------------------------------+
|                            单任务流水线引擎 (run_user_pipeline.py)                             |
|  - 执行安全清理，严格遵守 _CLEANUP_WHITELIST 顶层保护契约，绝不误删全局进度统计表              |
|  - 串行执行通用数据标准化处理与通用预测输出全链路标准脚本：                                    |
|       [Step 01] 数据勘察与健康度检查 (审计上游数据连贯性与物理步长)                          |
|       [Step 02] 等距重采样与时间网格对齐 (规范化特征-目标矩阵及辅助协变量)                   |
|       [Step 03] 通用回归/分类模型构建与评估训导 (输出训练/验证/测试各切分集预测明细)         |
|       [Step 04] 离线全量预测与系统残差校正学习 (产出全切分集预测文件及基线对比)              |
|       [Step 05] 独立生产盲测执行与差异审计 (输出生产级推导表、分部泄漏说明及指标监控)        |
|       [Step 06] 连续行为切段统计与全天静默审计 (输出事件周期统计表及全日背景卡片)            |
+-----------------------------------------------------------------------------------------------+
"""
    add_code_block(doc, arch_chart)
    
    add_heading_styled(doc, "1.2 工程运行流程与安全保护契约", level=2)
    add_para_styled(doc, "为确保批量调度的稳健运行与文件系统的整洁，系统制定了严格的工作空间管理契约：\n"
                         "• 顶层状态保护白名单契约 (_CLEANUP_WHITELIST)：单对象任务流水线启动前会自动进行空间临时表清理（如 *.tmp 或未归属中间对齐文件）；为此，项目明确规定 batch_execution_state.csv 及其临时文件、batch_run_summary.csv、summary_metrics_all_users.csv、skipped_users.csv 为全局特权表，受白名单严格豁免，任何情况下不可误删。\n"
                         "• 优雅异常告警与非侵入式降级 (WARN + Fallback)：当遇到配置文件中个别参数非规范或超出允许区间时，解析层直接通过 UserWarning 提示告警并回退采用安全通用兜底值，确保长时间的批量管线继续无损推进。", bold_prefix="【运行契约规范】：")

    # =========================================================================
    # 第 2 章：通用数据输入与用户配置规范框架
    # =========================================================================
    add_heading_styled(doc, "第 2 章  通用数据输入结构与用户配置规范框架", level=1)
    
    add_heading_styled(doc, "2.1 目录组织结构与双模式输入支持", level=2)
    add_para_styled(doc, "项目对数据读取结构支持规范双分层设计与平铺提取设计模式：\n"
                         "• 规范化双分层目录布局 (推荐)：训练输入文件存放于 data/trains/<device_id>_<user_id>/，独立盲测推理文件存放于 data/infers/<device_id>_<user_id>/，彻底做到训推空间无交叉。\n"
                         "• 根目录平铺布局 (向后兼容)：源 CSV 文件放置于 data/ 根目录下，框架调用正规匹配提取关键 ID。", bold_prefix="【输入物理结构】：")

    add_heading_styled(doc, "2.2 输入文件命名正则匹配契约 (RE_BUS / RE_BR)", level=2)
    add_para_styled(doc, "通用输入文件的命名规则和表结构规范定义见下表：", bold_prefix="【正则命名契约】：")
    
    regex_table_headers = ["文件分类", "业务作用", "文件名正规表达式匹配语法 (Regex)", "通用数据列结构要求"]
    regex_table_data = [
        ["主特征表/驱动总线\n(RE_BUS)", "连续多维度测量特征输入", r"^e241_(?P<device>[^_]+)_(?P<user>[^-]+)-Ch(?P<ch>\d+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$", "时间戳主键(event_time/time)及多通道特征数值列；支持带/不带秒及 ISO 混杂解析"],
        ["目标/真值表\n(RE_BR)", "对应需建模预测的目标序列", r"^(?P<user>[^-]+)-(?P<start>\d{6})-(?P<end>\d{6})(?P<suffix>(-1|-infer)?)\.csv$", "时间戳主键(time)与独立目标数值列 (pN, N≥0 的非负整数通道，如 p1, p2...)"],
        ["中间合并表", "处理过渡及分流产物", "data/merged_bus.csv, data/merged_branch.csv\ndata/infer_bus.csv, data/infer_branch.csv", "由流水线自动化聚合生成，独立区分训练段与推理盲测段，避免泄漏"]
    ]
    add_styled_table(doc, regex_table_headers, regex_table_data, col_widths=[1.2, 1.2, 2.3, 1.8])

    add_heading_styled(doc, "2.3 通用复合目标列动态累加物化机制 (pA+pB...)", level=2)
    add_para_styled(doc, "当被建模总目标需要由多个单独采集的子目标序列叠加构成时，系统提供实时求和与物化功能，避免手工修改源 CSV 引入操作污染：\n"
                         "• 复合表达式语法：通过 \"+\" 连接多个合规目标列，形如 \"p1+p2\" 或 \"p1+p2+p3\"。\n"
                         "• 行级动态加和与 NaN 传播防呆契约：数据引擎加载源表时自动检查并新增为该表达式文本形式的物化列；其按行求和计算必须强制设置 skipna=False 语义（即某一个分项在此处出现缺失 NaN 时，总量值一律传播为 NaN）。该契约坚决杜绝把漏采静默设为 0W 所引发的数据系统性低估偏差。\n"
                         "• 容错及去重处理：忽略大小写与首尾空格 (P1 + p2 -> p1+p2)，任何出现重复对相同列累加的形式 (p1+p1) 会立即被捕获拒绝。", bold_prefix="【动态物化规则】：")

    add_heading_styled(doc, "2.4 集中式用户配置 JSON 体系与三重优先权", level=2)
    add_para_styled(doc, "项目所有会话参数均通过 CLI --time-filter-config <path_to_json> 指定管理。解析时执行三重优先级规则：", bold_prefix="【解析优先规则】：")
    add_para_styled(doc, "1. config[\"<user_id>\"][\"<key>\"] —— 最高优先级：向指定用户定制的具体运行设定。\n"
                         "2. config[\"_default\"][\"<key>\"] —— 次高优先级：面向无特殊列出对象的统一模板兜底。\n"
                         "3. 代码内部内置系统全局常数 —— 最低优先级：保底运行。\n"
                         "注：下划线开头的顶级名称（如 _note_, _default）作为元属性，被自动过滤保护，绝当真对象处理。")
    
    add_para_styled(doc, "在单独配置字典中，支持统筹管理的六大通用配置模块详见下表：", bold_prefix="【六大用户通用配置模块】：")
    
    config_table_headers = ["配置模块名称", "JSON 参数名称与数据结构", "合法数据取值范围", "功能解释与通用控制逻辑"]
    config_table_data = [
        ["(1) 顶层训/推时段裁剪\n(v12 增强)", "train / infer 字典，含 include 与 exclude 数组", "双元素闭区间 [start, end]\n短日期 YYYY-MM-DD 或带秒 HH:MM:SS", "按闭区间先行求取 include 白名单并集（未配置代表取全集），再以 exclude 剔除黑名单。短日期自动扩展至 00:00:00~23:59:59"],
        ["(2) 目标通道指定\n(v13.4 / v13.16)", "target_col", "单通道 \"pN\" (N≥0)\n或复合表达 \"pA+pB[+pC...]\"", "向管道指定要拟合的目标真值列名；未填明则自动尝试按正则从文件推演，最后兜底回退 \"p1\""],
        ["(3) 自适应策略守卫\n(v13.1 / v13.5)", "guard_enabled", "bool (true/false) 或 null(未配置)", "控制是否应用特殊限制守卫。未声明时自动分析数据，符合条件自动降级关闭，提升通用场景表现力"],
        ["(4) 细粒度分集切区过滤\n(v13.2 细粒度)", "splits.train / splits.val / splits.test", "内部含 include / exclude 数组", "四步无偏分配：(a)初始划分 -> (b)include 硬性优先锚定(权值 train->val->test) -> (c)跨分区等比让出恒久保持分布比例不变 -> (d)exclude 剔除移出"],
        ["(5) 9 项公共常数覆盖与\n环境映射(v13.5/13.13)", "common_overrides 字典，\n涵盖阈值、比例、策略、地理坐标等", "on_thr_w: [0.001, 5000.0]\nsplit_ratios: 3元素数值和为1\nsplit_strategy: 4大通用策略\n纬度:-90~90/经度:-180~180", "提供直接覆盖公共参数机制。推荐策略为 \"global_stratified\"，消除跨月按月硬分层中小月样本强往 train 倾斜的问题。内部自动映射为带 NILM_USER_ 前缀的环境变量下发"],
        ["(6) 进阶特性控制项\n(v14 增强)", "v14_flags 字典或通用选项", "v14_enable, physics, calibrate, health, diag 等", "控制管道是否开启后处理参数优化、额外诊断监控报表等扩展辅助能力"]
    ]
    add_styled_table(doc, config_table_headers, config_table_data, col_widths=[1.3, 1.4, 1.6, 2.2])

    # =========================================================================
    # 第 3 章：通用算法输出产物体系与标准表结构全集
    # =========================================================================
    add_heading_styled(doc, "第 3 章  通用算法输出产物体系与标准表结构全集", level=1)
    add_para_styled(doc, "系统在对齐重采样、特征生成、独立分类/回归建模及推导周期内产生的成果，统一在模型资产区、任务状态表及 artifacts/trains/ 和 artifacts/infers/ 下输出，建立了完备规范的数据可追溯体系。", bold_prefix="【产物分类说明】：")

    add_heading_styled(doc, "3.1 产物目录分类体系全景树（完备涵盖全分切集预测表规范）", level=2)
    add_para_styled(doc, "产物存储在系统内的总体目录结构分层关系说明如下（在训练与离线验证产物区内，完备涵盖了主建模算法与对照组算法在 train / val / test 3 个划分集上的所有预测表文件）：")

    tree_str = """
<workspace_root>/
 ├── models/                            # [持久化模型资产区] 单任务工作流不会对本区进行回收
 │    └── <user_id>/
 │         ├── model_bundle.pkl         # 综合主包：包含归一化器、主预测回归及校正模型字典
 │         ├── baseline_model.pkl       # 参比基准对照模型包 (Baseline RF 等)
 │         ├── split_dates_bundle.json  # 划分元数据：记录具体归入 train/val/test 的自然日期序列
 │         └── weather_cache/           # 协变量气象数据的离线本地序列化缓存
 └── artifacts/                         # [运行过程产物区] 顶层表受白名单契约豁免保护；下按处理区分流
      ├── batch_execution_state.csv     # (白名单保护) 9 列标准的原子断点续跑执行进度表
      ├── batch_run_summary.csv         # (白名单保护) 批处理多对象评估汇总总卡表
      ├── summary_metrics_all_users.csv # (白名单保护) 全员各维度精度全景评估报表
      ├── skipped_users.csv             # (白名单保护) 策略判断为跳过的记录名册
      ├── trains/                       # 【训练与离线评估产物分类体系】
      │    └── <user_id>/
      │         ├── train_pred.csv      # ⭐ 主模型在训练集 (Train Split) 上的全周期逐点预测与残差
      │         ├── val_pred.csv        # ⭐ 主模型在验证集 (Val Split) 上的全周期逐点预测与残差
      │         ├── test_pred.csv       # ⭐ 主模型在测试集 (Test Split) 上的完整预测 (含后处理残差校正列)
      │         ├── train_pred_rf.csv   # ⭐ 对照模型 (Baseline RF) 在训练集上的同点比对预测
      │         ├── val_pred_rf.csv     # ⭐ 对照模型 (Baseline RF) 在验证集上的同点比对预测
      │         ├── test_pred_rf.csv    # ⭐ 对照模型 (Baseline RF) 在测试集上的同点比对预测
      │         ├── train_on_periods.csv       # 连续活动行为阶段明细表 (含 min_w 最小极值监控)
      │         ├── train_on_periods_daily.csv # 连续活动行为逐日统计表 (含静默非活动背景日)
      │         └── temp_power_lut.csv         # 训练阶段对温等协变量的 20 桶分箱参考表 (LUT)
      └── infers/                       # 【独立生产盲测推理与漂移监控产物分类体系】
           └── <user_id>/
                ├── predictions/
                │    └── inference_result.csv  # 生产盲测全周期多口径对齐横向比较表
                ├── metrics/
                │    ├── inference_metrics.csv       # 整体评估基础结果
                │    ├── inference_daily_metrics.csv # [25列标准] 逐日综合评估与源表采样条数监控表
                │    └── inference_comparison.csv    # 主预测与各基线算法横向汇总表
                ├── infer_on_periods.csv             # 推测验证段级行为明细表
                ├── infer_on_periods_daily.csv       # 推测验证日级行为卡片
                └── inference_temp_power_actual_vs_expected.csv # 协变量漂移比对与风险指示表
"""
    add_code_block(doc, tree_str)

    add_heading_styled(doc, "3.2 模型层持久化资产包详解 (models/<user_id>/)", level=2)
    add_para_styled(doc, "• model_bundle.pkl：统一持久化的字典大包，包含自适应数据标准化器 (scaler)、季节判别常数、通用分类与回归算法句柄及调准后处理学习模型。\n"
                         "• baseline_model.pkl (如 rf_model.pkl)：对应训练的独立对照参考算法句柄，为检查主建模逻辑是否带来合理的复杂度效益比提供对照点。\n"
                         "• split_dates_bundle.json：精准把每次随机划分入训练、验证、测试分区的自然日字符串列表进行持久化存储。不仅供其他脚本作同切划分零偏差还原，更是推理侧进行数据泄漏区 (leakage) 识别和盲测分离的关键基标。\n"
                         "• weather_cache/：把网络请求得来的协变量序列直接缓存本地，使下一轮训练无任何外部数据下载等待。", bold_prefix="【持久包规格说明】：")

    add_heading_styled(doc, "3.3 训练与离线评估全部分切集预测表规范 (train/val/test_pred*.csv)", level=2)
    add_para_styled(doc, "为确保在离线实验与工程验收中，对每一个划分数据区的残差分布及模型过拟合表现拥有标准的数据可追溯手段，系统对**主预测流程 (main)** 和**对照算法模型 (如 Baseline RF)** 均各自自动生成 3 份分区预测表，统一存放于 artifacts/trains/<user_id>/ 下：", bold_prefix="【6 大切分预测明细表】：")
    add_para_styled(doc, "1. train_pred.csv / val_pred.csv / test_pred.csv：保存主流程算法在对应训练集、验证集与测试集上的逐点估计值、响应态及残差序列；为支持在测试展示上进行直观校验，test_pred.csv 最右侧还会自动增补经加性校正补偿后的 2 列终态 (y_pred_W_main_L4_calib 和 residual_W_main_L4_calib)。\n"
                         "2. train_pred_rf.csv / val_pred_rf.csv / test_pred_rf.csv：在同样的时间戳和样本划分边界下，对照组参考模型计算产生的逐点估值和残差，构成了不受调参偏度影响的标准刻度线。")
    
    add_para_styled(doc, "该 6 大预测文件的通用标准化列结构规范表述如下：", bold_prefix="【全部分区集预测表字典】：")
    
    split_pred_headers = ["字段名称", "数据类型", "所属列属性", "业务含义与通用架构规则"]
    split_pred_data = [
        ["time", "ISO String", "必备列", "重采样对齐后 15 分钟等距的标准时序主键 (yyyy-MM-dd HH:MM:SS)"],
        ["y_true_W", "Float", "必备列", "系统真值输入中给定的原始真实目标标量 (W)，保留 3 位小数"],
        ["y_pred_W", "Float", "必备列", "对应工作流算法在特定分区集上计算得出的预测有效估计值 (W)"],
        ["residual_W", "Float", "必备列", "模型当前估算相对客观标准值的绝对差 (y_pred_W - y_true_W)"],
        ["state_true", "Int (0/1)", "附加列", "以业务判定阈值为基础计算所得的事件运行状态标识 (Active State)"],
        ["state_pred", "Int (0/1)", "附加列", "预测模块针对该时刻目标是否处于工作激发状态的 0/1 判定结果"],
        ["p_on", "Float (0~1)", "附加列", "分类引擎计算出的被预测对象位于启用态的数学概率评分"],
        ["y_pred_low_W /\ny_pred_high_W", "Float", "附加列", "当启用连续区间建模时产出的分布区间估测下限值与上界极限值"],
        ["y_pred_W_main_L4_calib /\nresidual_W_main_L4_calib", "Float", "仅在 test_pred.csv\n中专属扩展", "叠加后处理加性补偿层修整后输出的独立优化预测值及优化后绝对残差"]
    ]
    add_styled_table(doc, split_pred_headers, split_pred_data, col_widths=[1.5, 1.1, 1.3, 2.6])

    add_heading_styled(doc, "3.4 独立生产推理阶段对齐评估表规范 (predictions/inference_result.csv)", level=2)
    add_para_styled(doc, "针对在线应用或真正未知标签的生产盲测场景。该表格以高统一宽表形式把主推导逻辑下的三层处理结果与各对照基准合并：", bold_prefix="【独立生产盲测输出字典】：")
    
    infer_headers = ["列名字段", "数据类型", "逻辑所属分层", "通用说明与技术解读"]
    infer_data = [
        ["time / event_time", "ISO String", "基底主键", "ISO 统一时序等差时间主键"],
        ["y_true", "Float", "标尺对照", "物理标定真实值（纯线上未标记独立盲测推断场景下可自动缺省）"],
        ["y_pred_W_main", "Float", "正式终态输出", "经过回归推导、残差加性校正与动态多阶段平衡调整后的业务正式对外结果"],
        ["y_pred_W_main_raw", "Float", "基础推演口径", "未做残差回归补偿且未参与后期切换策略调整的初始模型输出，保留参考"],
        ["y_pred_W_main_L4_calib", "Float", "残差验证口径", "叠加后处理残差补偿层而未参与加权策略切换重置的单阶段优化成果"],
        ["state_pred_main / p_on_main", "Int(0/1) / Float", "分类判定", "模型计算出的目标触发二值状态以及对应置信度概率分数"],
        ["residual_W_main_raw /\nresidual_W_main_L4_calib", "Float", "残差对比列", "提供基础版模型残差与经过加性校正后预测值的双向绝对误差走势"],
        ["y_pred_W_rf ...", "Float", "基线参照组", "对照基线模型在相同时间点的参考输出列"]
    ]
    add_styled_table(doc, infer_headers, infer_data, col_widths=[1.6, 1.1, 1.3, 2.5])

    add_heading_styled(doc, "3.5 25 列逐日指标表与原始源数据采样条目监控表规范 (daily_metrics.csv)", level=2)
    add_para_styled(doc, "系统在离线与独立推理流程阶段生成 train_daily_metrics.csv 和 inference_daily_metrics.csv。本方案确立了 25 列严谨表格式；最重大的审计亮点在于增设第 5 列 n_bus_raw 与第 6 列 n_branch_raw，能够让业务方一秒定位“大残差或低评估指标，是由模型估测走样引起，还是因为源输入 CSV 中物理丢数据漏采造成”：", bold_prefix="【25 列通用逐日审计表字典】：")
    
    daily_headers = ["序号顺位", "字段列表头", "数据类型", "功能定义说明与核心物理审计逻辑"]
    daily_data = [
        ["1", "date", "String", "所属自然日文本形式 (YYYY-MM-DD)"],
        ["2", "split", "String", "记录所属数据分区性质 (train / val / test / inference)；若推理推演段与已被分配进训练集的历史日期发生重叠，程序自动以日期粒度拆写两行：inference_leak (已泄漏非合规统计) 与 inference_ood (标准有效 OOD 纯盲测统计)"],
        ["3", "model", "String", "评价算法对象名称（主处理框架命名 main，对照算法为 rf 等）"],
        ["4", "n_samples", "Int", "此统计日期在经时间戳等间隙重采样规整对齐后实际计算采用的有效行条数"],
        ["5", "n_bus_raw\n(⭐审计列)", "Int / \"\"", "主特征源表当日直接物理读取总条目数：直接从原始未对齐文件中按天数条。如小于正常标准 (如 15分钟全日 288 条)，提示本指标异动来自源头丢数缺失"],
        ["6", "n_branch_raw\n(⭐审计列)", "Int / \"\"", "目标表/分路当日直接物理读取总条目数：客观展现目标采集设备是否在线稳定"],
        ["7 ~ 11", "Accuracy, Precision,\nRecall, F1, AUC", "Float", "对于二值开闭分类响应态进行评判的核心精度矩阵，保留 4~6 位小数；缺省为空"],
        ["12 ~ 14", "MAE_W, RMSE_W,\nSAE", "Float", "连续回归标量误差；其中 SAE = abs(kWh_pred - kWh_true)/max(kWh_true,0.01)，表达了全天累积输出差相对真实累积量的分布偏度"],
        ["15 ~ 17", "kWh_true, kWh_pred,\nkWh_err", "Float", "全日累积数值积分计算 (例如总做功或总能量) 比重：真实总量 / 预估总量 / 残差差"],
        ["18 ~ 21", "TP, FP, FN, TN", "Int", "单日基于响应态的混淆矩阵事件频度技术统计 counters"],
        ["22", "dataset", "String", "标注记录样本在分划控制中所在的属性 (如 used, excluded)"],
        ["23", "on_thr_w", "Float", "运算本条各状态统计时选用的界定活动常数阈值数"]
    ]
    add_styled_table(doc, daily_headers, daily_data, col_widths=[0.8, 1.4, 1.0, 3.3])

    add_heading_styled(doc, "3.6 连续行为触发段明细与静默全天审计表规范 (<stage>_on_periods*.csv)", level=2)
    add_para_styled(doc, "面向时序序列开启段的持续时长及极值分布，系统产出连续段及日卡表：", bold_prefix="【阶段及日行为审计】：")
    add_para_styled(doc, "• <stage>_on_periods.csv (连续行为段表)：收齐全部处于触发活动运行期 (Active State Segment) 的片段。核心列包含 being_time (发生开始时戳)、end_time (终结停止时戳)、p1 (通道名称)、duration_min (持续发生分长)、mean_w (段内均值)、peak_w (最高峰幅)、energy_kwh (此连续段贡献总量)、dataset (分集归属)。最关键扩展列为第 5 列 min_w (连续有效段运行极值下界)：专门用来审计此连贯运行期内的最小表现底点，且恒等保障基本逻辑约束 min_w <= mean_w <= peak_w。同时针对全日并无任何触发动作的有效候选天数，程序会额外插入一行静默记录行 (OFF Day Row, duration_min=1440)，确保其全天背景基线平稳参数不漏落。\n"
                         "• <stage>_on_periods_daily.csv (单日行为表)：汇成单日总体概览卡片。含 date、n_segments (当天发生段频次，静默日=0)、total_on_hours、first_on_time、last_off_time 及均值汇总统计。")

    add_heading_styled(doc, "3.7 协变量基底表与实测漂移评估规范 (lut.csv & actual_vs_expected.csv)", level=2)
    add_para_styled(doc, "• 训练侧参考桶表 (temp_power_lut.csv)：系统针对温度等外部环境协变量按范围等距划分 20 个常规段桶 (Bin 1~20)，外附加一个全样本统计中位桶 ALL_MEDIAN (共 21 行)。行表列示上下边界 temp_lo/temp_hi、基调预期中位数 expected_signal、样本点 n_samples 与基础分位数等，反映对象基本特质。\n"
                         "• 推理实测漂移比对表 (inference_temp_power_actual_vs_expected.csv)：推理把测定均值和样本填入对于分箱，得出差值 abs_residual 与相对漂移值 rel_drift；生成最终评估告警枚举字段 drift_flag：\n"
                         "  ① OK —— 对比处于预设正常区间，未出现系统化分布偏差；\n"
                         "  ② WARN —— 产生可观察的分箱偏度警告（如绝对偏度 ≥15%）；\n"
                         "  ③ ALERT —— 发现严重风险漂移警报（偏离加剧，如 ≥30%），引发下游应对和模型校调；\n"
                         "  ④ NO_DATA —— 此特定环境区间并未落入测点样本，安全占位。", bold_prefix="【协变量分段审计字典】：")

    add_heading_styled(doc, "3.8 批量原子断点续跑执行表规范 (artifacts/batch_execution_state.csv)", level=2)
    add_para_styled(doc, "面对海量并发或者持续时间冗长的组批自动化调度，本执行表提供对处理状态的无损恢复：", bold_prefix="【9 列断点表写就协议】：")
    add_para_styled(doc, "• 原子写盘保护语义：管理层严令禁止向现有表作非安全的流式写追加；采取“内存运算构建生成 batch_execution_state.csv.tmp 临时文件 ➔ 调用操作系统底层核心原子更名指令 (os.replace) 一秒替换老盘表”的设计。此机制能实现即使进程在运行时任意时刻遭到强退宕机，系统盘上的主表依然保持无损一致，最高仅影响正在发生读算的唯一一笔当前数据行。\n"
                         "• 9 列表字段规范 (UTF-8-BOM)：\n"
                         "  1. user_id: 正在编排执行管理的主键 ID；\n"
                         "  2. status: 计算判定结论标签 (ok / fail / soft_skip)；\n"
                         "  3. success: Bool 布尔判定量 (True / False)；\n"
                         "  4. started_at / finished_at: 任务流水起讫标记点；\n"
                         "  5. duration_s: 本轮任务过程净消耗时分秒 Float；\n"
                         "  6. message: 执行结论备注提示，支持完整中文字符反馈堆栈内容；\n"
                         "  7. target_col: 最终确认执行的目标表达式字面量 (如 p1+p2)；\n"
                         "  8. run_id: 关联到调度引擎引发任务组运行的本次独立批次码。")

    # 保存文件
    out_path = Path("/home/user/nilm_test/项目技术方案说明书_数据架构与核心算法全景规范.docx")
    doc.save(str(out_path))
    print(f"成功更新技术方案说明 Word 文档：{out_path}，大小：{out_path.stat().st_size} 字节")

if __name__ == "__main__":
    create_document()
