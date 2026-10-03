"""Evidence-led company headlines. No LLM, name whitelist, score or material input.

Status/counts stay in overview.py. This layer selects and explains findings; a
penalty is not a verdict on the whole company. Historical records with an `ok`
status are not automatically evidence of absence (notably labour disputes).
"""
import re

from app.models import CompanyFindingSummary, OverviewItem, Status, Version


CORE_KEYS = ("credit.status", "credit.penalties", "credit.abnormal",
             "credit.serious_illegal", "credit.dishonest")
FOCUS_KEYS = {
    "job": ("credit.labor", "finance.jobs", "finance.insured"),
    "savings": ("risk.bank_list", "risk.amac", "risk.scope"),
    "investment": ("finance.net_profit", "finance.latest_period", "finance.revenue", "finance.reports"),
    "contract": ("finance.executions", "credit.lawsuits", "credit.restricted"),
    "prepaid": ("reputation.top_topic", "reputation.web_cash", "reputation.web_complaint", "finance.executions"),
    "rental": ("reputation.top_topic", "reputation.web_complaint", "finance.executions", "credit.lawsuits"),
    "takeover": ("finance.executions", "finance.tax_arrears", "finance.pledges", "finance.mortgages"),
    "general": (),
}
PERSPECTIVES = {
    "general": "企业综合核查 · 这家公司是否值得信任",
    "job": "入职前企业核查", "savings": "存款与理财前机构核查",
    "investment": "投资前企业观察", "contract": "合作前企业核查",
    "prepaid": "预付消费前企业核查", "rental": "租房前机构核查",
    "takeover": "经营与履约核查",
}
GUIDANCE = {
    "general": "这些发现说明本次查到了什么，不对整家公司作安全保证。",
    "job": "重点看这些记录与薪酬、用工和岗位职责的关系，不据此判断一份具体 offer 的真伪。",
    "savings": "机构名单、经营范围与具体产品是不同层次，名单记录不代表对资金安全的保证。",
    "investment": "企业财务和合规记录不能直接推导投资回报，也不构成买卖建议。",
    "contract": "重点核对记录中的企业角色、履行情况及其与本次合作的关系。",
    "prepaid": "重点看公开记录是否涉及服务履行、退款或持续经营；投诉说法仍需核实。",
    "rental": "企业公开记录不等于具体房源、出租权限或租赁合同已经核实。",
    "takeover": "公开记录只提供经营与履约线索，不替代内部财务核查。",
}
# Cross-scenario priority is deliberately narrow and tied to existing record
# types. Merely having a fine, pledge or complaint never becomes a red verdict.
CRITICAL_KEYS = ("credit.status", "credit.serious_illegal", "credit.dishonest",
                 "credit.other_risks", "risk.regulator_warning")
KNOWN_FINDINGS = {
    "credit.penalties": ("发现行政处罚记录", "处罚针对具体事项；需要结合内容、时间与后续处理判断影响，不能直接等同于整家公司不可信。"),
    "credit.abnormal": ("发现经营异常名录记录", "需查看列入原因、记录时间及是否已有移出或其他后续处理。"),
    "credit.serious_illegal": ("发现严重违法失信名单记录", "这项记录需优先核实，不能用其他正常项目抵消；请查看原始记录与后续处理。"),
    "credit.dishonest": ("发现失信被执行人记录", "需优先了解记录所涉义务、时间和后续履行情况。"),
    "credit.restricted": ("发现限制高消费记录", "需核对记录的具体主体、事项及当前状态。"),
    "credit.other_risks": ("发现司法或经营相关记录", "汇总条数不等于责任认定，需区分企业在每条记录中的角色和处理结果。"),
    "credit.labor": ("发现劳动争议记录", "劳动仲裁或诉讼记录不等于企业已败诉或目前仍在欠薪；需查看争议内容、结果和时间。"),
    "credit.lawsuits": ("发现需关注的诉讼记录", "立案、开庭或作为被告不等于已经认定违约，需核对案由和处理结果。"),
    "finance.executions": ("发现被执行记录", "被执行记录需结合执行事项、金额和后续履行情况阅读，不能直接断言目前无力履约。"),
    "finance.jobs": ("招聘与参保记录存在差异", "需核对招聘信息时间、用工主体与参保统计范围，不能直接据此认定招聘不真实。"),
    "finance.insured": ("参保人数记录需进一步了解", "参保统计口径、记录期间与实际用工情况可能不同，不能将人数直接当作雇主质量。"),
    "finance.pledges": ("发现股权出质记录", "股东出质不等于公司本身缺钱，需区分出质主体、比例和时间。"),
    "finance.mortgages": ("发现动产抵押记录", "抵押记录本身不等于无法履约，需结合主体、事项和后续状态阅读。"),
    "finance.tax_arrears": ("发现欠税公告记录", "需查看公告日期、具体事项与后续处理，不能只凭条数判断当前经营状态。"),
    "risk.bank_list": ("金融机构名单核查仍有疑点", "未在已查名单中匹配到记录，不等于已经查遍全部资质或认定非法经营。"),
    "risk.amac": ("私募管理人登记核查需关注", "私募管理人登记与其他金融机构资质不同，需结合实际业务及名单覆盖范围阅读。"),
    "risk.regulator_warning": ("发现监管风险提示", "需优先查看提示的适用主体、内容、日期和后续处理。"),
}


def perspective(version: Version) -> str:
    """Refine the saved scenario, never infer a purpose from a company's name."""
    need = version.need.strip()
    if version.scenario in {"general", "contract", "prepaid"} and re.search(r"租房|租赁|租住|房租|租金|出租", need):
        return "rental"
    if version.scenario == "savings" and re.search(r"投资|认购|股票|股权|基金", need) and not re.search(r"存款|存钱|储蓄", need):
        return "investment"
    return version.scenario if version.scenario in FOCUS_KEYS else "general"


def covered(item: OverviewItem | None) -> bool:
    return item is not None and item.category != "unknown" and item.gap is None


def concerning(item: OverviewItem) -> bool:
    return item.category in {"attention", "abnormal"} or (
        item.id == "credit.labor" and covered(item) and bool(re.search(r"[1-9]\d*\s*条", item.text)))


def finding(item: OverviewItem) -> tuple[str, str]:
    if item.id == "credit.status":
        return f"登记状态：{item.text}", "登记状态是本次查询记录所示，需结合来源日期与后续变更核实。"
    if item.id.startswith("reputation."):
        if item.id == "reputation.top_topic":
            return f"投诉线索涉及「{item.text}」，说法待核实", "投诉属于投诉方陈述，不等于企业违规已被认定；需结合企业回应和独立记录核对。"
        return "发现报道或投诉线索，相关说法待核实", "报道、投诉与已经认定的违法事实不同，需查看原始内容、主体和处理结果。"
    if item.id in {"finance.net_profit", "finance.latest_period", "finance.revenue"}:
        return f"{item.label}：{item.text}", "这里列出对应报告期间的披露数字，不把利润当作可用现金，也不把单期数据推断成长期趋势。"
    return KNOWN_FINDINGS.get(item.id, (f"{item.label}：{item.text}", "该项记录需要结合具体事项、来源日期和后续处理阅读。"))


def build_company_summary(version: Version, items: list[OverviewItem]) -> tuple[str, CompanyFindingSummary]:
    by_id = {item.id: item for item in items}
    purpose = perspective(version)
    focus = FOCUS_KEYS[purpose]
    critical = [by_id[key] for key in CRITICAL_KEYS if key in by_id and by_id[key].status == Status.bad]
    critical_order = {item.id: index for index, item in enumerate(critical)}
    flags = sorted((item for item in items if concerning(item)), key=lambda item: (
        critical_order.get(item.id, len(critical)),
        focus.index(item.id) if item.id in focus else len(focus),
        0 if item.id == "credit.penalties" else 1,
        0 if item.category == "abnormal" else 1, item.id))
    scope = PERSPECTIVES[purpose]
    if purpose == "general" and version.need.strip() not in {
        "", "了解公司", "了解这家公司", "了解这家公司的公开资料", "了解这家公司的登记、资质与公开资料"}:
        scope = "围绕你的需求 · 企业公开信息核查"

    def result(headline: str, explanation: str, basis: list[str], tone: str, rule: str):
        remaining = [item for item in flags if item.id not in basis]
        if remaining:
            explanation += f"另有 {len(remaining)} 项记录需要了解，完整依据保留在下方。"
        return headline, CompanyFindingSummary(
            perspective=scope, explanation=explanation + GUIDANCE[purpose],
            basis_ids=list(dict.fromkeys(basis)), priority_ids=[item.id for item in flags], tone=tone, rule=rule)

    if critical:
        item = critical[0]
        headline, explanation = finding(item)
        return result(headline, explanation, [item.id], "critical", "critical_record")

    relevant = next((item for item in flags if item.id in focus), None)
    if relevant:
        headline, explanation = finding(relevant)
        if purpose == "job" and relevant.id == "credit.labor":
            headline += "，入职需重点了解"
        return result(headline, explanation, [relevant.id], "attention", "purpose_finding")

    # Positive phrases require the exact record, not just a green total, a
    # registration date or an unrelated source. Historical labour cases are
    # never rewritten as 'no abnormal employment records'.
    positive, positive_id, positive_note = "", "", ""
    labor = by_id.get("credit.labor")
    bank = by_id.get("risk.bank_list")
    status = by_id.get("credit.status")
    if purpose == "job" and covered(labor) and labor.status == Status.ok and labor.text == "无":
        positive, positive_id = "所查劳动仲裁未见记录", labor.id
        positive_note = "只表示本次劳动仲裁来源未返回记录，不代表全部用工情况已核实。"
    elif purpose == "savings" and covered(bank) and bank.status == Status.ok:
        positive, positive_id = "已查到金融机构名单记录", bank.id
        positive_note = "名单种类、适用主体和数据日期以对应来源为准，不能扩展为所有业务资质有效。"
    elif purpose == "investment":
        financial = next((by_id[key] for key in focus[:3] if covered(by_id.get(key))), None)
        if financial:
            headline, explanation = finding(financial)
            if flags:
                other, note = finding(flags[0])
                return result(headline + "；" + other, explanation + note,
                              [financial.id, flags[0].id], "attention", "financial_with_finding")
            return result(headline, explanation, [financial.id], "neutral", "financial_record")

    if positive:
        if flags:
            other, note = finding(flags[0])
            return result(positive + "；" + other, positive_note + note,
                          [positive_id, flags[0].id], "attention", "scoped_positive_with_finding")
        return result(positive, positive_note, [positive_id], "neutral", "scoped_positive")

    if flags:
        item = flags[0]
        headline, explanation = finding(item)
        if purpose == "job" and not covered(labor):
            headline += "，用工资料仍不充分"
        elif purpose == "investment" and not any(covered(by_id.get(key)) for key in focus[:3]):
            headline += "，财务资料仍不充分"
        elif covered(status) and status.status == Status.ok:
            return result("登记信息已核实；" + headline, explanation,
                          [status.id, item.id], "attention", "registration_with_finding")
        return result(headline, explanation, [item.id], "attention", "company_finding")

    # Clean summaries require core AND purpose-specific company coverage. No
    # material-derived scenario first_items are prerequisites for this report.
    required = set(CORE_KEYS) | set(focus)
    if all(covered(by_id.get(key)) and by_id[key].status == Status.ok for key in required):
        has_gaps = any(item.category == "unknown" for item in items)
        headline = "已查关键项目未见异常" + ("，另有资料未覆盖" if has_gaps else "")
        return result(headline, "仅限已查询的企业项目，资料未覆盖不算核验正常。",
                      sorted(required), "neutral", "covered_company_checks")
    if covered(status) and status.status == Status.ok:
        gap = {"job": "用工情况暂无充分依据", "investment": "财务资料仍不充分",
               "savings": "相关金融资质仍需核实", "contract": "履约资料仍不充分",
               "prepaid": "服务与退款记录仍不充分", "rental": "租赁相关记录仍不充分"}.get(purpose, "其他关键资料仍待核实")
        return result("登记信息已核实，" + gap, "登记信息不能替代对其他经营事项的核查。",
                      [status.id], "unknown", "registration_with_coverage_gap")
    unknown = [item.id for item in items if item.category == "unknown"]
    return result("本次企业资料尚不足以形成判断", "部分来源未覆盖、未返回或查询未完成；这不是发现企业异常。",
                  unknown, "unknown", "insufficient_company_coverage")
