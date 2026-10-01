"""把散在各处的记录归进赛题的四个信号：风险、财务、信用、口碑。"""
import re
from datetime import date

from app.analysis.extract import Extraction
from app.analysis.fmt import money, months_between, wan
from app.analysis.verify import qualification_review, return_review
from app.config import LOW_PAID_RATIO, YOUNG_COMPANY_MONTHS
from app.models import (AmacHit, Assertion, ClaimKind, CompanyProfile, LicenseHit, RegistryHit, Scenario, Signal,
                        SignalItem, Status, Verdict)
from app.sources.web import WebFindings, WebHit

NO_WEB = "联网搜索没开（没配模型网关，或处于离线模式）"

# 和钱的去向有关的说法，结论同时放进风险信号
MONEY_KINDS = (ClaimKind.payee, ClaimKind.refund, ClaimKind.upfront_fee)
VERDICT_STATUS = {Verdict.mismatch: Status.bad, Verdict.redline: Status.bad, Verdict.misleading: Status.warn,
                  Verdict.attention: Status.warn, Verdict.unverifiable: Status.miss, Verdict.consistent: Status.ok}
CASH_TOPIC = re.compile(r"兑付|提现|退款|跑路|失联|拿不回")
DEAD_STATUS = re.compile(r"吊销|注销|撤销|停业|清算")
QUAL_KEYS = ["bank_list", "amac", "product_code", "scope"]


def _flags(items: list[SignalItem]) -> int:
    return sum(i.status is Status.bad for i in items)


def _not_covered(key: str) -> list[SignalItem]:
    return [SignalItem(key=key, label="登记数据", value="没查", detail="还没有这家公司的登记数据",
                       status=Status.none, source="registry")]


def _hit_item(key: str, label: str, value: str, hit: WebHit, status: Status, refs: dict[str, str],
              source: str) -> SignalItem:
    date = f"{hit.date} " if hit.date else ""
    return SignalItem(key=key, label=label, value=value, detail=f"{date}{hit.site}：{hit.title}", status=status,
                      source=source, ref=refs.get(hit.url))


def official_web_item(web: WebFindings | None, refs: dict[str, str]) -> SignalItem:
    label = "政府网站点名"
    if web is None:
        return SignalItem(key="official_web", label=label, value="没查", detail=NO_WEB, status=Status.none,
                          source="web_official")
    if not web.official and any("官方" in e for e in web.errors):
        return SignalItem(key="official_web", label=label, value="查询失败", detail="；".join(web.errors),
                          status=Status.none, source="web_official")
    # 只算它是当事人的文件；正文里顺带提到它的（比如别家公司的处罚决定里写"员工在它那里兼职"）单独说
    subject = [h for h in web.official if h.subject]
    mentioned = [h for h in web.official if not h.subject and h.category in ("penalty", "warning", "judicial")]
    also = f"；另有 {len(mentioned)} 份文件在正文里提到它，它不是当事人" if mentioned else ""
    bad = [h for h in subject if h.category in ("penalty", "warning")]
    judicial = [h for h in subject if h.category == "judicial"]
    if bad:
        kinds = "、".join(dict.fromkeys(h.category_label for h in bad))
        item = _hit_item("official_web", label, f"{len(bad)} 份文件点名了它（{kinds}）", bad[0], Status.bad, refs,
                         "web_official")
        if also:
            item.detail = (item.detail or "") + also
        return item
    if judicial:
        return _hit_item("official_web", label, f"{len(judicial)} 份法院相关文件提到它", judicial[0], Status.warn, refs,
                         "web_official")
    if mentioned:
        return _hit_item("official_web", label, f"{len(mentioned)} 份处罚或法院文件在正文里提到它（它不是当事人）",
                         mentioned[0], Status.warn, refs, "web_official")
    if web.official:
        return _hit_item("official_web", label, f"{len(web.official)} 份文件提到它，没有处罚或警示", web.official[0],
                         Status.ok, refs, "web_official")
    return SignalItem(key="official_web", label=label, value="没搜到",
                      detail="搜了监管、法院和政府网站，没找到点名它的处罚或警示；搜索覆盖有限，没搜到不等于没有",
                      status=Status.ok, source="web_official")


PF_MIN = 1_000_000  # 投资单只私募基金的最低金额


def pf_threshold_item(amac: AmacHit, amount: float | None) -> SignalItem | None:
    """它是私募基金管理人：卖的只能是私募，只能卖给合格投资者，单只起投 100 万。"""
    if not amac.registered:
        return None
    label, src = "私募门槛", "reg_pf_qualified"
    if amount is not None and amount < PF_MIN:
        return SignalItem(key="pf_threshold", label=label,
                          value=f"私募基金只能卖给合格投资者，单只至少 100 万；这笔是 {wan(amount)}，达不到",
                          detail="它登记的是私募基金管理人，不能向普通人公开推销产品", status=Status.bad, source=src)
    return SignalItem(key="pf_threshold", label=label, value="私募基金只能卖给合格投资者，单只至少 100 万",
                      detail="个人还要金融资产不低于 300 万元，或近三年年均收入不低于 50 万元", status=Status.warn, source=src)


def risk_signal(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
                scenario: Scenario, assertions: list[Assertion], others: list[RegistryHit] = (),
                web: WebFindings | None = None, refs: dict[str, str] | None = None,
                amount: float | None = None) -> Signal:
    items: list[SignalItem] = []
    warnings = [h for h in (web.official if web else []) if h.category == "warning"]
    if warnings:
        items.append(_hit_item("regulator_warning", "监管风险提示", f"{len(warnings)} 份风险提示或非法金融通报点名了它",
                               warnings[0], Status.bad, refs or {}, "web_official"))
    if scenario.license_checks or ext.is_financial or lic.found or any(h.found for h in others):
        checks, _, _ = qualification_review(ext, company, lic, amac, others)
        items += [SignalItem(key=k, label=c.label, value=c.result, status=c.status, source=c.source)
                  for k, c in zip(QUAL_KEYS, checks)]
        if "amac" in scenario.license_checks and (pf := pf_threshold_item(amac, amount)):
            items.append(pf)
    else:
        items.append(SignalItem(key="bank_list", label="金融牌照", value="你的需求和材料都不涉及理财或投资，不适用",
                                status=Status.ok, source="material"))
    for a in assertions:
        if a.kind in MONEY_KINDS:
            items.append(SignalItem(key=a.kind.value, label=a.kind_label, value=a.plain,
                                    status=VERDICT_STATUS[a.verdict], source=a.checks[0].source))

    if promise := ext.claims.get(ClaimKind.return_promise):
        checks, verdict, plain = return_review(promise)
        status = {Verdict.redline: Status.bad, Verdict.attention: Status.warn}.get(verdict, Status.ok)
        items.append(SignalItem(key="promise", label="收益承诺", value=plain, status=status, source=checks[0].source))
    elif ext.is_financial:
        items.append(SignalItem(key="promise", label="收益承诺", value="未发现保本或高收益承诺",
                                status=Status.ok, source="material"))
    if ext.benchmark_rates:
        items.append(SignalItem(key="benchmark", label="业绩比较基准",
                                value=f"{'、'.join(f'{r:g}%' for r in ext.benchmark_rates)}（是参考，不是承诺）",
                                status=Status.ok, source="material"))
    if ext.is_financial:
        items.append(SignalItem(key="disclosure", label="风险提示语",
                                value="有" if ext.has_risk_disclosure else "材料上没有任何风险提示",
                                status=Status.ok if ext.has_risk_disclosure else Status.warn, source="reg_wm_sales"))
    if ext.pressure:
        items.append(SignalItem(key="pressure", label="施压话术", value="、".join(f"\"{p}\"" for p in ext.pressure),
                                detail="制造紧迫感，让人没时间核实", status=Status.warn, source="material"))
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
    if not company.known("pledges"):
        items.append(SignalItem(key="pledges", label="股权出质", value="没查", detail="这次的数据来源不含这一项",
                                status=Status.none, source="registry"))
    elif company.pledges:
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
        if not company.known(key):
            items.append(SignalItem(key=key, label=label, value="没查", detail="这次的数据来源不含这一项",
                                    status=Status.none, source="registry"))
            continue
        items.append(SignalItem(key=key, label=label, value=f"{len(rows)} 条" if rows else "无",
                                status=bad if rows else Status.ok, source="registry"))
    return Signal(key="finance", title="财务", lede=lede, flags=_flags(items), items=items)


def credit_signal(company: CompanyProfile | None, as_of: date, web: WebFindings | None = None,
                  refs: dict[str, str] | None = None) -> Signal:
    lede = "\"没有不良记录\"只说明查过的地方没有，不等于可靠。"
    web_item = official_web_item(web, refs or {})
    if company is None:
        items = _not_covered("registry") + [web_item]
        return Signal(key="credit", title="信用", lede=lede, flags=_flags(items), items=items)
    months = months_between(company.founded, as_of)
    status = (Status.bad if DEAD_STATUS.search(company.status)
              else Status.warn if months < YOUNG_COMPANY_MONTHS else Status.ok)
    items = [SignalItem(key="status", label="登记状态", value=company.status,
                        detail=f"成立于 {company.founded}，{months // 12} 年 {months % 12} 个月", status=status, source="registry")]
    if not company.known("penalties"):
        items.append(SignalItem(key="penalties", label="行政处罚", value="没查", detail="这次的数据来源不含这一项",
                                status=Status.none, source="registry"))
    elif company.penalties:
        detail = "；".join(f"{p.date} {p.org}：{p.reason}，{p.result}" for p in company.penalties)
        items.append(SignalItem(key="penalties", label="行政处罚", value=f"{len(company.penalties)} 条", detail=detail,
                                status=Status.bad, source="registry"))
    else:
        items.append(SignalItem(key="penalties", label="行政处罚", value="无", status=Status.ok, source="registry"))
    for key, label, hit, yes, no in [("abnormal", "经营异常名录", company.abnormal, "已列入", "未列入"),
                                     ("serious_illegal", "严重违法失信名单", company.serious_illegal, "已列入", "未列入"),
                                     ("dishonest", "失信被执行人", company.dishonest, "有", "无")]:
        if not company.known(key):
            items.append(SignalItem(key=key, label=label, value="没查", detail="这次的数据来源不含这一项",
                                    status=Status.none, source="registry"))
            continue
        items.append(SignalItem(key=key, label=label, value=yes if hit else no,
                                status=Status.bad if hit else Status.ok, source="registry"))
    items.append(web_item)
    return Signal(key="credit", title="信用", lede=lede, flags=_flags(items), items=items)


def web_reputation(web: WebFindings, refs: dict[str, str], lede: str) -> Signal:
    if not web.news and any("报道" in e for e in web.errors):
        items = [SignalItem(key="web_total", label="公开报道和投诉", value="查询失败", detail="；".join(web.errors),
                            status=Status.none, source="web_news")]
        return Signal(key="reputation", title="口碑", lede=lede, flags=0, items=items)
    cash = [h for h in web.news if h.category == "cash"]
    complaint = [h for h in web.news if h.category == "complaint"]
    items = [SignalItem(key="web_total", label="网上提到它的报道和投诉", value=f"{len(web.news)} 条",
                        detail="全网搜\"公司简称 + 投诉、维权、兑付\"，只算摘要里出现全称或简称的",
                        status=Status.ok,
                        source="web_news")]
    if cash:
        items.append(_hit_item("web_cash", "说到兑付、提现、跑路", f"{len(cash)} 条", cash[0],
                               Status.bad if len(cash) >= 2 else Status.warn, refs, "web_news"))
    if complaint:
        items.append(_hit_item("web_complaint", "投诉、维权", f"{len(complaint)} 条", complaint[0], Status.warn, refs,
                               "web_news"))
    if not cash and not complaint:
        items.append(SignalItem(key="web_negative", label="负面报道", value="没搜到集中的负面",
                                detail="搜索覆盖有限，没搜到不等于没有", status=Status.ok, source="web_news"))
    extra = {"web": [{"category": h.category_label, "title": h.title, "url": h.url, "site": h.site, "date": h.date,
                      "excerpt": h.excerpt, "ref": refs.get(h.url)} for h in web.news]}
    return Signal(key="reputation", title="口碑", lede=lede, flags=_flags(items), items=items, extra=extra)


def reputation_signal(data: dict | None, web: WebFindings | None = None, refs: dict[str, str] | None = None) -> Signal:
    lede = "单条投诉不能证明什么，可能有误会或夸大。我们看的是趋势和集中的主题。"
    if data is None and web is not None:
        return web_reputation(web, refs or {}, lede)
    if data is None:
        return Signal(key="reputation", title="口碑", lede=lede, flags=0,
                      items=[SignalItem(key="complaints", label="投诉", value="没查", detail="还没有这家公司的投诉数据",
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
                  complaints: dict | None, as_of: date, scenario: Scenario,
                  assertions: list[Assertion] = (), others: list[RegistryHit] = (),
                  web: WebFindings | None = None, web_refs: dict[str, str] | None = None,
                  amount: float | None = None) -> list[Signal]:
    """四个信号的内容不随场景变；场景只改排序和开头那句话。"""
    scale = ext.claims.get(ClaimKind.scale)
    stores = scale.numbers.get("stores") if scale else None
    refs = web_refs or {}
    signals = {s.key: s for s in [risk_signal(ext, company, lic, amac, scenario, list(assertions), list(others), web, refs,
                                              amount),
                                  finance_signal(company, stores), credit_signal(company, as_of, web, refs),
                                  reputation_signal(complaints, web, refs)]}
    for key, lede in scenario.signal_ledes.items():
        if key in signals:
            signals[key].lede = lede
    return [signals[k] for k in scenario.signal_order]
