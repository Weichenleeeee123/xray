"""把散在各处的记录归进赛题的四个信号：风险、财务、信用、口碑。"""
import re
from datetime import date

from app.analysis.extract import Extraction
from app.analysis.fmt import money, months_between
from app.analysis.verify import qualification_review, return_review
from app.config import LOW_PAID_RATIO, YOUNG_COMPANY_MONTHS
from app.models import AmacHit, ClaimKind, CompanyProfile, LicenseHit, Signal, SignalItem, Status, Verdict

CASH_TOPIC = re.compile(r"兑付|提现|退款|跑路|失联|拿不回")
DEAD_STATUS = re.compile(r"吊销|注销|撤销|停业|清算")
QUAL_KEYS = ["bank_list", "amac", "product_code", "scope"]


def _flags(items: list[SignalItem]) -> int:
    return sum(i.status is Status.bad for i in items)


def _not_covered(key: str) -> list[SignalItem]:
    return [SignalItem(key=key, label="登记数据", value="没查", detail="演示版没有这家公司的登记数据",
                       status=Status.none, source="registry")]


def risk_signal(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit) -> Signal:
    items: list[SignalItem] = []
    if ext.is_financial or lic.found:
        checks, _, _ = qualification_review(ext, company, lic, amac)
        items += [SignalItem(key=k, label=c.label, value=c.result, status=c.status, source=c.source)
                  for k, c in zip(QUAL_KEYS, checks)]
    else:
        items.append(SignalItem(key="bank_list", label="金融牌照", value="材料不涉及理财或投资，不适用",
                                status=Status.ok, source="flyer"))

    if promise := ext.claims.get(ClaimKind.return_promise):
        checks, verdict, plain = return_review(promise)
        status = {Verdict.redline: Status.bad, Verdict.attention: Status.warn}.get(verdict, Status.ok)
        items.append(SignalItem(key="promise", label="收益承诺", value=plain, status=status, source=checks[0].source))
    elif ext.is_financial:
        items.append(SignalItem(key="promise", label="收益承诺", value="未发现保本或高收益承诺",
                                status=Status.ok, source="flyer"))
    if ext.benchmark_rates:
        items.append(SignalItem(key="benchmark", label="业绩比较基准",
                                value=f"{'、'.join(f'{r:g}%' for r in ext.benchmark_rates)}（是参考，不是承诺）",
                                status=Status.ok, source="flyer"))
    if ext.is_financial:
        items.append(SignalItem(key="disclosure", label="风险提示语",
                                value="有" if ext.has_risk_disclosure else "材料上没有任何风险提示",
                                status=Status.ok if ext.has_risk_disclosure else Status.warn, source="reg_wm_sales"))
    if ext.pressure:
        items.append(SignalItem(key="pressure", label="施压话术", value="、".join(f"\"{p}\"" for p in ext.pressure),
                                detail="制造紧迫感，让人没时间核实", status=Status.warn, source="flyer"))
    return Signal(key="risk", title="风险", lede="最关键的一条：它有没有资格收你的钱。", flags=_flags(items), items=items)


def finance_signal(company: CompanyProfile | None, claimed_stores: float | None) -> Signal:
    lede = "普通公司不公开财报。但缺钱的公司，会在登记记录里留下影子。"
    if company is None:
        return Signal(key="finance", title="财务", lede=lede, flags=0, items=_not_covered("registry"))
    items: list[SignalItem] = []
    reg, paid = company.reg_capital, company.paid_capital
    due = f"，期限 {company.capital_due}" if company.capital_due else ""
    if paid is None:
        items.append(SignalItem(key="paid_capital", label="实缴资本", value="年报未公示", detail=f"认缴 {money(reg)}{due}",
                                status=Status.none, source="annual_report"))
    else:
        items.append(SignalItem(key="paid_capital", label="实缴资本", value=money(paid), detail=f"认缴 {money(reg)}{due}",
                                status=Status.bad if paid < reg * LOW_PAID_RATIO else Status.ok, source="annual_report"))
    if company.pledges:
        detail = "；".join(f"{p.date}，{p.pledgor}把 {p.share}押给「{p.pledgee}」" for p in company.pledges)
        items.append(SignalItem(key="pledges", label="股权出质", value=f"{len(company.pledges)} 笔", detail=detail,
                                status=Status.bad, source="registry"))
    else:
        items.append(SignalItem(key="pledges", label="股权出质", value="无", status=Status.ok, source="registry"))
    if company.insured is None:
        items.append(SignalItem(key="insured", label="参保人数", value="未公示", detail="企业可选择不公示",
                                status=Status.none, source="annual_report"))
    else:
        short = claimed_stores is not None and company.insured < claimed_stores
        items.append(SignalItem(key="insured", label="参保人数", value=f"{company.insured} 人",
                                detail=f"宣称 {claimed_stores:g} 家门店" if claimed_stores is not None else None,
                                status=Status.warn if short else Status.ok, source="annual_report"))
    for key, label, rows, bad in [("mortgages", "动产抵押", company.mortgages, Status.warn),
                                  ("executions", "被执行", company.executions, Status.bad),
                                  ("tax_arrears", "欠税公告", company.tax_arrears, Status.bad)]:
        items.append(SignalItem(key=key, label=label, value=f"{len(rows)} 条" if rows else "无",
                                status=bad if rows else Status.ok, source="registry"))
    return Signal(key="finance", title="财务", lede=lede, flags=_flags(items), items=items)


def credit_signal(company: CompanyProfile | None, as_of: date) -> Signal:
    lede = "\"没有不良记录\"只说明查过的地方没有，不等于可靠。"
    if company is None:
        return Signal(key="credit", title="信用", lede=lede, flags=0, items=_not_covered("registry"))
    months = months_between(company.founded, as_of)
    status = (Status.bad if DEAD_STATUS.search(company.status)
              else Status.warn if months < YOUNG_COMPANY_MONTHS else Status.ok)
    items = [SignalItem(key="status", label="登记状态", value=company.status,
                        detail=f"成立于 {company.founded}，{months // 12} 年 {months % 12} 个月", status=status, source="registry")]
    if company.penalties:
        detail = "；".join(f"{p.date} {p.org}：{p.reason}，{p.result}" for p in company.penalties)
        items.append(SignalItem(key="penalties", label="行政处罚", value=f"{len(company.penalties)} 条", detail=detail,
                                status=Status.bad, source="registry"))
    else:
        items.append(SignalItem(key="penalties", label="行政处罚", value="无", status=Status.ok, source="registry"))
    for key, label, hit, yes, no in [("abnormal", "经营异常名录", company.abnormal, "已列入", "未列入"),
                                     ("serious_illegal", "严重违法失信名单", company.serious_illegal, "已列入", "未列入"),
                                     ("dishonest", "失信被执行人", company.dishonest, "有", "无")]:
        items.append(SignalItem(key=key, label=label, value=yes if hit else no,
                                status=Status.bad if hit else Status.ok, source="registry"))
    items.append(SignalItem(key="litigation", label="司法诉讼", value="没查", detail="演示版未接入",
                            status=Status.none, source="registry"))
    return Signal(key="credit", title="信用", lede=lede, flags=_flags(items), items=items)


def reputation_signal(data: dict | None) -> Signal:
    lede = "单条投诉不能证明什么，可能有误会或夸大。我们看的是趋势和集中的主题。"
    if data is None:
        return Signal(key="reputation", title="口碑", lede=lede, flags=0,
                      items=[SignalItem(key="complaints", label="投诉", value="没查", detail="演示版没有这家公司的投诉数据",
                                        status=Status.none, source="complaints")])
    counts = data["counts"]
    total, last3 = sum(counts), sum(counts[-3:])
    share = last3 / total if total else 0.0
    topics = sorted(data["topics"], key=lambda t: -t["n"])
    top = topics[0] if topics else None
    top_share = top["n"] / total if top and total else 0.0
    rising = total >= 10 and share >= 0.5
    items = [
        SignalItem(key="total", label="近 12 个月投诉", value=f"{total} 条",
                   status=Status.warn if rising else Status.ok, source="complaints"),
        SignalItem(key="recent", label="最近 3 个月", value=f"{last3} 条", detail=f"占全年 {share:.0%}",
                   status=Status.warn if rising else Status.ok, source="complaints"),
    ]
    if top:
        cash = CASH_TOPIC.search(top["name"]) and top_share >= 0.3
        items.append(SignalItem(key="top_topic", label="集中的问题", value=top["name"],
                                detail=f"{top['n']} 条，占 {top_share:.0%}；例：{top['quote']}",
                                status=Status.bad if cash else (Status.warn if total >= 10 else Status.ok), source="complaints"))
    extra = {"months": data["months"], "counts": counts, "topics": topics,
             "total": total, "last3": last3, "last3_share": round(share, 3), "top_share": round(top_share, 3)}
    return Signal(key="reputation", title="口碑", lede=lede, flags=_flags(items), items=items, extra=extra)


def build_signals(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
                  complaints: dict | None, as_of: date) -> list[Signal]:
    scale = ext.claims.get(ClaimKind.scale)
    stores = scale.numbers.get("stores") if scale else None
    return [risk_signal(ext, company, lic, amac), finance_signal(company, stores),
            credit_signal(company, as_of), reputation_signal(complaints)]
