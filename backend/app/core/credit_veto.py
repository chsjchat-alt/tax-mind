"""
纳税信用D级 / 涉税犯罪一票否决解析（单一事实源）

依据（官方明文，见《风险评分与风险等级优化建议说明书》§9.1 / §9.3）：
- 《纳税缴费信用管理办法》国家税务总局公告 2025 年第 12 号 第十八条：
  偷税金额≥10万元且占比≥10%、未按期足额缴清处理结论款项、优惠申报材料虚假、
  涉案重大税收违法等情形直接判定为 D 级。
- 《中华人民共和国刑法》第二百零一条：逃税罪（数额较大且占应纳税额 10% 以上）。

本模块为确定性纯函数（同输入必同输出），供两套引擎（risk_engine /
tax_risk_engine）与合规调整模块共用，保证一票否决口径全局一致。
"""

from __future__ import annotations

# 直接判 D 级（2025 年第 12 号官方明文）对应的标志值
D_CREDIT_LEVEL = "D"


def resolve_tax_credit_veto(
    tax_credit_level: str | None = None,
    tax_crime_convicted: bool = False,
) -> str | None:
    """解析纳税信用 / 涉税犯罪一票否决。

    Args:
        tax_credit_level: 纳税信用等级 A/B/C/D（None 或空串表示未评级）
        tax_crime_convicted: 是否因涉税犯罪（《刑法》第 201 条）被生效判决

    Returns:
        触发则返回否决原因（非空字符串），否则返回 None。
    """
    if tax_crime_convicted:
        return (
            "涉税犯罪：因逃税等涉税犯罪被生效判决（《刑法》第 201 条），"
            "触发一票否决"
        )
    if tax_credit_level and str(tax_credit_level).strip().upper() == D_CREDIT_LEVEL:
        return (
            "纳税信用等级为 D 级（《纳税缴费信用管理办法》2025 年第 12 号直接判级），"
            "触发一票否决"
        )
    return None
