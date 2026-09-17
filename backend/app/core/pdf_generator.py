"""
PDF 报告生成器

使用 fpdf2 将报告内容渲染为中文 PDF，供财务人员与老板阅读。
自动检测当前操作系统的中文字体路径，支持 Windows / macOS / Linux。
"""
import io
import platform
import pathlib
from datetime import datetime

from fpdf import FPDF


def _find_chinese_font() -> str:
    """跨平台自动检测中文字体路径"""
    system = platform.system()

    if system == "Windows":
        candidates = [
            "C:/Windows/Fonts/simhei.ttf",
            "C:/Windows/Fonts/msyh.ttc",
            "C:/Windows/Fonts/simsun.ttc",
        ]
    elif system == "Darwin":
        candidates = [
            "/System/Library/Fonts/PingFang.ttc",
            "/System/Library/Fonts/STHeiti Light.ttc",
            "/Library/Fonts/Arial Unicode.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        ]

    for path in candidates:
        if pathlib.Path(path).exists():
            return path

    raise RuntimeError(
        "未找到可用的中文字体。请安装中文字体后重试：\n"
        "  Windows: 确保 C:/Windows/Fonts/simhei.ttf 存在\n"
        "  macOS: 系统自带 PingFang 字体\n"
        "  Linux: apt install fonts-wqy-zenhei 或 apt install fonts-noto-cjk"
    )


_FONT_PATH = _find_chinese_font()

# ── 风险等级配色 ──
_RISK_COLORS = {
    "critical": (220, 38, 38),
    "high": (239, 68, 68),
    "medium": (245, 158, 11),
    "medium_high": (234, 88, 12),
    "low": (16, 185, 129),
}
_RISK_LABELS = {
    "critical": "严重风险",
    "high": "高风险",
    "medium": "中风险",
    "medium_high": "中高风险",
    "low": "低风险",
}


class ReportPDF(FPDF):
    """中文报告 PDF 基类"""

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.add_font("zh", "", _FONT_PATH, uni=True)
        self.add_font("zh", "B", _FONT_PATH, uni=True)
        self.set_auto_page_break(True, 20)

    def header(self):
        if self.page_no() == 1:
            return  # 封面不显示页眉
        self.set_font("zh", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 5, "蒙牛全产业链 AI 内生合规决策大脑 — 财税合规风险评估报告", align="L")
        self.cell(0, 5, "内部资料 · 注意保密", align="R", new_x="LMARGIN", new_y="NEXT")
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(4)

    def footer(self):
        if self.page_no() == 1:
            return
        self.set_y(-15)
        self.set_font("zh", "", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"第 {self.page_no()} 页", align="C")

    def cover_page(self, enterprise_name: str, risk_level: str, score: float, date_str: str):
        """封面页"""
        self.add_page()
        # 顶部色条
        r, g, b = _RISK_COLORS.get(risk_level, (100, 100, 100))
        self.set_fill_color(r, g, b)
        self.rect(0, 0, 210, 8, "F")

        self.ln(40)

        # 主标题
        self.set_font("zh", "B", 28)
        self.set_text_color(r, g, b)
        self.cell(0, 14, "财税合规风险评估报告", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)
        self.set_draw_color(r, g, b)
        self.set_line_width(0.6)
        y = self.get_y()
        self.line(50, y, 160, y)
        self.ln(8)

        # 企业名称
        self.set_font("zh", "B", 20)
        self.set_text_color(50, 50, 50)
        self.cell(0, 12, enterprise_name, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(12)

        # 风险等级 / 评分
        self.set_font("zh", "", 12)
        self.set_text_color(80, 80, 80)
        self.cell(0, 8, f"风险等级：{_RISK_LABELS.get(risk_level, risk_level)}", align="C",
                  new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, f"综合评分：{score:.1f} / 100", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(6)

        # 风险等级视觉指示器
        bar_w = 80
        bar_x = (210 - bar_w) / 2
        self.set_fill_color(220, 220, 220)
        self.rect(bar_x, self.get_y() + 2, bar_w, 10, "F")
        fill_w = bar_w * min(score / 100, 1)
        self.set_fill_color(r, g, b)
        self.rect(bar_x, self.get_y() + 2, fill_w, 10, "F")
        self.ln(18)

        # 日期
        self.set_font("zh", "", 11)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"生成日期：{date_str}", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(30)

        # 底部警示
        self.set_font("zh", "", 9)
        self.set_text_color(180, 180, 180)
        self.cell(0, 6, "本报告基于模拟数据生成，仅供演示参考，不构成任何税务或法律建议。", align="C")

    def section_title(self, title: str):
        """章节标题"""
        self.set_font("zh", "B", 14)
        self.set_text_color(30, 30, 30)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(59, 130, 246)  # blue
        self.set_line_width(0.5)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(4)

    def sub_title(self, title: str):
        """子标题"""
        self.set_font("zh", "B", 11)
        self.set_text_color(60, 60, 60)
        self.cell(0, 8, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text: str, indent: bool = False):
        """正文多行文本"""
        self.set_font("zh", "", 9)
        self.set_text_color(70, 70, 70)
        x = self.l_margin + (8 if indent else 0)
        self.set_x(x)
        self.multi_cell(self.w - self.r_margin - x, 5.5, text)
        self.ln(1)

    def key_value(self, key: str, value: str):
        """键值对行"""
        self.set_font("zh", "", 9)
        self.set_text_color(100, 100, 100)
        self.cell(35, 6, key)
        self.set_text_color(50, 50, 50)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")

    def bullet_item(self, text: str, color: tuple = (220, 38, 38)):
        """带圆点的列表项"""
        self.set_font("zh", "", 8)
        self.set_text_color(*color)
        x0 = self.l_margin + 4
        self.set_x(x0)
        self.cell(4, 5, "●")
        self.set_text_color(70, 70, 70)
        self.multi_cell(self.w - self.r_margin - x0 - 4, 5, text)
        self.ln(0.5)


def generate_report_pdf(report_content: dict) -> bytes:
    """
    将报告内容 dict 渲染为 PDF 字节流。
    """

    def _s(val, default="") -> str:
        """安全转字符串，防御 bytearray / bytes 等非预期类型"""
        if isinstance(val, (bytes, bytearray)):
            return val.decode("utf-8", errors="replace")
        if not isinstance(val, str):
            return str(val) if val else default
        return val

    # ── 解析报告内容 ──
    pdf = ReportPDF()
    ent = report_content.get("enterprise", {})
    risk = report_content.get("risk_assessment") or {}
    disclaimer = report_content.get("disclaimer", "")

    ent_name = _s(ent.get("name"), "未知企业")
    risk_level = risk.get("level", "low")
    risk_score = risk.get("score", 0)
    date_str = _s(risk.get("date", "")) or datetime.now().strftime("%Y-%m-%d")

    # ── 封面 ──
    pdf.cover_page(ent_name, risk_level, risk_score, date_str)

    # ═══════════════════════════════════════
    # 一、企业基本信息
    # ═══════════════════════════════════════
    pdf.add_page()
    pdf.section_title("一、企业基本信息")
    pdf.key_value("企业名称", _s(ent.get("name"), "-"))
    pdf.key_value("所属行业", _s(ent.get("industry"), "-"))
    rev = ent.get("revenue_annual", 0)
    pdf.key_value("年营业收入", f"{rev / 10000:.1f} 万元")
    pdf.key_value("员工人数", f"{ent.get('employee_count', '-')} 人")
    pdf.ln(4)

    # ═══════════════════════════════════════
    # 二、风险评估结果
    # ═══════════════════════════════════════
    if risk:
        pdf.section_title("二、风险评估结果")
        pdf.sub_title("2.1 综合评级")
        pdf.key_value("风险等级", _RISK_LABELS.get(risk_level, risk_level))
        pdf.key_value("综合评分", f"{risk_score:.1f} / 100")
        pdf.ln(2)

        pdf.sub_title("2.2 核心指标")
        pdf.key_value("四流匹配度", f"{risk.get('four_flow_match', 0):.1f}%")
        pdf.key_value("私卡收款占比", f"{risk.get('private_card_ratio', 0) * 100:.2f}%")
        cost_dev = risk.get('cost_deviation', 0)
        pdf.key_value("成本费用偏离", f"{cost_dev:.1f} 个百分点")
        pdf.ln(4)

        # ── 风险标记 ──
        recs_data = risk.get("recommendations", {})
        flags = recs_data.get("flags", []) if isinstance(recs_data, dict) else []
        recs = recs_data.get("recommendations", []) if isinstance(recs_data, dict) else []

        if flags:
            pdf.sub_title(f"2.3 风险发现（{len(flags)} 项）")
            for flag in flags[:50]:
                flag_str = _s(flag)
                if flag_str:
                    pdf.bullet_item(flag_str)
            if len(flags) > 50:
                pdf.body_text(f"... 共 {len(flags)} 项，以上仅展示前 50 项")
            pdf.ln(2)

        # ── 整改建议 ──
        if recs:
            pdf.sub_title(f"2.4 整改建议（{len(recs)} 条）")
            for rec in recs:
                rec_str = _s(rec)
                if rec_str:
                    pdf.bullet_item(rec_str, color=(16, 185, 129))
            pdf.ln(2)
        elif flags:
            pdf.body_text("提示：已识别出多项风险特征，建议进行深入自查并咨询注册税务师。", indent=True)

    # ═══════════════════════════════════════
    # 三、免责声明
    # ═══════════════════════════════════════
    pdf.add_page()
    pdf.section_title("三、免责声明")
    pdf.body_text(_s(disclaimer) or "本报告基于模拟数据生成，仅供演示参考，不构成任何税务或法律建议。")
    pdf.ln(6)
    pdf.set_font("zh", "", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.multi_cell(0, 5,
        "本报告由「蒙牛全产业链 AI 内生合规决策大脑」系统自动生成，数据来源于企业内部财务系统及模拟数据。\n"
        "报告中的风险评级、合规发现及整改建议均为系统基于预设规则的自动分析结果，\n"
        "不构成具有法律效力的专业意见。企业应根据实际情况咨询注册税务师或律师。\n"
        "系统运营方不对因使用本报告而产生的任何直接或间接损失承担责任。"
    )

    return pdf.output()
