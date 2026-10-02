"""把散在各处的记录归进赛题的四个信号：风险、财务、信用、口碑。"""
import re
from collections import Counter
from dataclasses import replace
from datetime import date, timedelta
from urllib.parse import urlsplit

from app.analysis.extract import Extraction
from app.analysis.fmt import money, months_between, wan
from app.analysis.verify import qualification_review, return_review
from app.config import LOW_PAID_RATIO, YOUNG_COMPANY_MONTHS
from app.models import (AmacHit, Assertion, ClaimKind, CompanyProfile, LicenseHit, RegistryHit, Scenario, Signal,
                        RawRecord, SignalItem, Status, Verdict)
from app.sources.licenses import normalize
from app.sources.web import OFFICIAL_DOMAINS, WebFindings, WebHit
from app.sources import finance as fin
from app.sources.finance import FinancialFindings
from app.sources.news import NewsFindings
from app.sources import qcc_more
from app.sources.cninfo import CninfoFindings

NO_WEB = "联网搜索没开（没配模型网关，或处于离线模式）"

# 和钱的去向有关的说法，结论同时放进风险信号
MONEY_KINDS = (ClaimKind.payee, ClaimKind.refund, ClaimKind.upfront_fee)
VERDICT_STATUS = {Verdict.mismatch: Status.bad, Verdict.redline: Status.bad, Verdict.misleading: Status.warn,
                  Verdict.attention: Status.warn, Verdict.unverifiable: Status.miss, Verdict.consistent: Status.ok}
CASH_TOPIC = re.compile(r"兑付|提现|退款|跑路|失联|拿不回")
DEAD_STATUS = re.compile(r"吊销|注销|撤销|停业|清算")
# 资格核验的检查项 → 风险信号的条目。按检查名对应，不按位置：说法核验会在前面插入"宣称的牌照"这类检查
QUAL_KEYS = {"持牌机构名单": "bank_list", "私募基金管理人登记": "amac", "理财产品登记编码": "product_code",
             "经营范围": "scope"}


def _flags(items: list[SignalItem]) -> int:
    return sum(i.status is Status.bad for i in items)


def _not_covered(key: str) -> list[SignalItem]:
    return [SignalItem(key=key, label="登记数据", value="没查", detail="还没有这家公司的登记数据",
                       status=Status.none, source="registry")]


def official_pack_items(company_name: str, records: list[RawRecord]) -> list[SignalItem]:
    """只消费服务器人工核验包的结构化文书，不把用户材料或官网网址当作核验。

    collected 类型仍保留。记录仅证明该份历史文书，不代表工商处罚全量查询或当前整改情况。
    """
    categories = {"行政处罚决定": "企业处罚结果", "行政监管措施": "措施"}
    items = []
    for record in records:
        if record.kind != "collected" or record.coverage != "found" or not isinstance(record.content, dict):
            continue
        data = record.content
        category = data.get("文书类别")
        subject = data.get("当事企业")
        if category not in categories or not isinstance(subject, str) or normalize(subject) != normalize(company_name):
            continue
        try:
            url = urlsplit(record.url or "")
            hostname = (url.hostname or "").lower()
            if url.scheme != "https" or not any(hostname == d or hostname.endswith("." + d) for d in OFFICIAL_DOMAINS):
                continue
            when = data.get("决定日期")
            if not isinstance(when, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", when):
                continue
            date.fromisoformat(when)
        except ValueError:
            continue
        result = data.get(categories[category])
        if not isinstance(result, str) or not result.strip():
            continue
        items.append(SignalItem(key=f"official_pack_{record.id.lower()}", label=f"{category}（人工采集）",
                                value=f"{when}：{result.strip()}", detail="该份历史文书摘录；不是全量查询，未核验后续整改结果",
                                status=Status.bad, source=record.source_id, ref=record.id))
    # 首条进入一页结论时先保留企业处罚结果；警示函另列为监管措施。
    return sorted(items, key=lambda item: not item.label.startswith("行政处罚决定"))


def add_pack_items(signals: list[Signal], pack_items: list[SignalItem], records: list[RawRecord],
                   company: CompanyProfile | None, web: WebFindings | None, refs: dict[str, str]) -> None:
    """证据包里的文书放进信用信号最前面，同一份文书不在别的条目里再算一次：
    政府网站搜到的同一网址不再计数；商业数据里同一天的行政处罚不再单列。"""
    if not pack_items:
        return
    credit = next(s for s in signals if s.key == "credit")
    by_id = {r.id: r for r in records}
    urls = tuple(by_id[i.ref].url for i in pack_items if i.ref in by_id and by_id[i.ref].url)
    days = {i.value.split("：", 1)[0] for i in pack_items if i.label.startswith("行政处罚")}
    items = []
    for it in credit.items:
        if it.key == "official_web":
            it = official_web_item(web, refs, urls)
        elif it.key == "penalties" and company and company.penalties and days and                 all(p.date in days for p in company.penalties) and company.n("penalties") == len(company.penalties):
            continue                     # 商业数据里的处罚就是上面那份决定书，不重复列
        items.append(it)
    credit.items = pack_items + items
    credit.flags = sum(i.status == "bad" for i in credit.items)


def _hit_item(key: str, label: str, value: str, hit: WebHit, status: Status, refs: dict[str, str],
              source: str) -> SignalItem:
    date = f"{hit.date} " if hit.date else ""
    return SignalItem(key=key, label=label, value=value, detail=f"{date}{hit.site}：{hit.title}", status=status,
                      source=source, ref=refs.get(hit.url))


def _same_url(a: str | None, b: str | None) -> bool:
    key = lambda u: re.sub(r"^https?://", "", (u or "").strip().lower()).rstrip("/")
    return bool(a and b) and key(a) == key(b)


def official_web_item(web: WebFindings | None, refs: dict[str, str], listed: tuple[str, ...] = ()) -> SignalItem:
    """listed：已经在别的条目里单独列出的文书网址（证据包摘录），这里不再重复计数。"""
    label = "政府网站点名"
    if web is None:
        return SignalItem(key="official_web", label=label, value="没查", detail=NO_WEB, status=Status.none,
                          source="web_official")
    if not web.official and any("官方" in e for e in web.errors):
        return SignalItem(key="official_web", label=label, value="查询失败", detail="；".join(web.errors),
                          status=Status.none, source="web_official")
    # 只算它是当事人的文件；正文里顺带提到它的（比如别家公司的处罚决定里写"员工在它那里兼职"）单独说
    shown = [h for h in web.official if any(_same_url(h.url, u) for u in listed)]
    if shown:
        web = replace(web, official=[h for h in web.official if h not in shown])
    subject = [h for h in web.official if h.subject]
    mentioned = [h for h in web.official if not h.subject and h.category in ("penalty", "warning", "judicial")]
    also = f"；另有 {len(mentioned)} 份文件在正文里提到它，它不是当事人" if mentioned else ""
    bad = [h for h in subject if h.category in ("penalty", "warning")]
    judicial = [h for h in subject if h.category == "judicial"]
    other = "另有 " if shown else ""
    if bad:
        kinds = "、".join(dict.fromkeys(h.category_label for h in bad))
        item = _hit_item("official_web", label, f"{other}{len(bad)} 份文件点名了它（{kinds}）", bad[0], Status.bad, refs,
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
    if shown:
        return SignalItem(key="official_web", label=label, value=f"搜到的 {len(shown)} 份都已在上面单独列出",
                          detail="搜索结果里没有别的点名它的处罚或警示；搜索覆盖有限，没搜到不等于没有",
                          status=Status.none, source="web_official", ref=refs.get(shown[0].url))
    return SignalItem(key="official_web", label=label, value="没搜到",
                      detail="搜了监管、法院和政府网站，没找到点名它的处罚或警示；搜索覆盖有限，没搜到不等于没有",
                      status=Status.ok, source="web_official")


PF_MIN = 1_000_000  # 投资单只私募基金的最低金额
# 中基协诚信信息里属于处罚、纪律处分、失联这类的，判"有问题"；信息报送异常之类判"要留意"
AMAC_SERIOUS = re.compile(r"行政处罚|纪律处分|失联|异常机构|虚假|违反.{0,4}底线|不良诚信")


def _amac_detail(amac: AmacHit) -> dict | None:
    return (amac.record or {}).get("detail") if amac.registered else None


def amac_integrity_item(amac: AmacHit) -> SignalItem | None:
    d = _amac_detail(amac)
    integ = (d or {}).get("机构诚信信息") or {}
    if not integ:
        return None
    heads = list(integ)
    serious = [h for h in heads if AMAC_SERIOUS.search(h)]
    detail = "；".join((integ[h][0] if integ[h] else h) for h in (serious or heads))
    return SignalItem(key="amac_integrity", label="中基协诚信信息", value="、".join(heads), detail=detail[:200],
                      status=Status.bad if serious else Status.warn, source="amac_detail")


def amac_tips_item(amac: AmacHit) -> SignalItem | None:
    d = _amac_detail(amac)
    tips, special = (d or {}).get("机构提示信息") or [], (d or {}).get("协会特别提示") or []
    if not tips and not special:
        return None
    value = "、".join(tips) if tips else f"{len(special)} 条特别提示"
    return SignalItem(key="amac_tips", label="中基协提示", value=value, detail="；".join(special)[:240] or None,
                      status=Status.warn, source="amac_detail")


def amac_scale_item(amac: AmacHit) -> SignalItem | None:
    f = _amac_detail(amac)
    if not f or not f.get("管理规模区间"):
        return None
    detail = f"全职员工 {f.get('全职员工人数', '?')} 人，取得基金从业资格 {f.get('取得基金从业人数', '?')} 人；"              f"实缴资本 {f.get('实缴资本(万元)(人民币)', '?')} 万元（{f.get('注册资本实缴比例', '?')}）；"              f"管理人自行填报，{f.get('机构信息最后更新时间', '')} 更新"
    return SignalItem(key="amac_scale", label="管理规模（中基协公示）", value=f.get("管理规模区间"), detail=detail,
                      status=Status.ok, source="amac_detail")


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
                  for c in checks if (k := QUAL_KEYS.get(c.label))]
        if "amac" in scenario.license_checks and (pf := pf_threshold_item(amac, amount)):
            items.append(pf)
        if tips := amac_tips_item(amac):
            items.append(tips)
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


SHOWN_NONE = "明细没取到，只知道条数"


def report_items(finance: FinancialFindings | None) -> list[SignalItem]:
    """企查查财务数据：最新年报的营收、净利润，最新一期的资产负债率。只照抄，不判断高低；只有亏损标出来。"""
    if finance is None:
        return []
    if finance.coverage != "found":
        failed = finance.coverage == "failed"
        return [SignalItem(key="reports", label="公开的财务数据", value="没查成" if failed else "没有",
                           detail=finance.error if failed else "只有上市、发债等要公开披露的公司才有财报；没有不等于经营有问题",
                           status=Status.none, source="qcc_finance")]
    annual, latest = finance.latest_annual, finance.latest
    items = []
    if annual:
        yoy = f"，同比 {fin.pct(annual.revenue_yoy, True)}" if annual.revenue_yoy is not None else ""
        items.append(SignalItem(key="revenue", label=f"营业收入（{annual.label}）", value=fin.yi(annual.revenue) + yoy,
                                detail="企查查汇总的公司定期报告数据，以公告原文为准", status=Status.ok,
                                source="qcc_finance"))
        loss = annual.net_profit is not None and annual.net_profit < 0
        items.append(SignalItem(key="net_profit", label=f"净利润（{annual.label}）", value=fin.yi(annual.net_profit),
                                detail="亏损" if loss else "只列数字，不判断高低", status=Status.warn if loss else Status.ok,
                                source="qcc_finance"))
    if latest and latest is not annual:
        loss = latest.net_profit is not None and latest.net_profit < 0
        items.append(SignalItem(key="latest_period", label=f"最新一期（{latest.label}）",
                                value=f"营收 {fin.yi(latest.revenue)}，净利润 {fin.yi(latest.net_profit)}",
                                detail=("亏损；" if loss else "") + "季报、中报是累计数，不能直接和年报比",
                                status=Status.warn if loss else Status.ok, source="qcc_finance"))
    if latest and latest.debt_ratio is not None:
        items.append(SignalItem(key="debt_ratio", label=f"资产负债率（{latest.label}）", value=fin.pct(latest.debt_ratio),
                                detail="平台算好的比率。银行、保险负债率高是常态，不同行业不能直接比",
                                status=Status.ok, source="qcc_finance"))
    return items


def report_extra(finance: FinancialFindings | None) -> dict | None:
    """近几年年报的营收、净利润，给报告页画一张小表。"""
    annual = [p for p in (finance.periods if finance else []) if p.kind == "年报"][:3]
    if not annual:
        return None
    return {"reports": [{"period": p.label, "revenue": fin.yi(p.revenue), "net_profit": fin.yi(p.net_profit),
                         "revenue_yoy": fin.pct(p.revenue_yoy, True)} for p in annual]}


def finance_signal(company: CompanyProfile | None, claimed_stores: float | None, amac: AmacHit | None = None,
                   finance: FinancialFindings | None = None) -> Signal:
    lede = "普通公司不公开财报。但缺钱的公司，会在登记记录里留下影子。"
    scale = amac_scale_item(amac) if amac else None
    if company is None:
        items = ([scale] if scale else []) + report_items(finance) + _not_covered("registry")
        return Signal(key="finance", title="财务", lede=lede, flags=_flags(items), items=items, extra=report_extra(finance))
    items: list[SignalItem] = ([scale] if scale else []) + report_items(finance)
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
    elif company.n("pledges"):
        detail = "；".join(f"{p.date}，{p.pledgor}把 {p.share}押给「{p.pledgee}」" for p in company.pledges) or SHOWN_NONE
        listed = company.known("listing") and bool(company.listing)
        if listed:
            detail = "上市公司股东众多，部分股东把手里的股份出质很常见，不说明公司本身缺钱；要看大股东质押的比例。" +                      (detail if detail != SHOWN_NONE else "")
        items.append(SignalItem(key="pledges", label="股权出质", value=f"{company.n('pledges')} 笔", detail=detail,
                                status=Status.warn if listed else Status.bad, source="registry"))
    else:
        items.append(SignalItem(key="pledges", label="股权出质", value="无", detail=company.facts.get("pledges"),
                                status=Status.ok, source="registry"))
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
        n = company.n(key)
        items.append(SignalItem(key=key, label=label, value=f"{n} 条" if n else "无", detail=company.facts.get(key),
                                status=bad if n else Status.ok, source="registry"))
    return Signal(key="finance", title="财务", lede=lede, flags=_flags(items), items=items, extra=report_extra(finance))


def credit_signal(company: CompanyProfile | None, as_of: date, web: WebFindings | None = None,
                  refs: dict[str, str] | None = None, amac: AmacHit | None = None) -> Signal:
    lede = "\"没有不良记录\"只说明查过的地方没有，不等于可靠。"
    web_item = official_web_item(web, refs or {})
    integrity = amac_integrity_item(amac) if amac else None
    if company is None:
        items = ([integrity] if integrity else []) + _not_covered("registry") + [web_item]
        return Signal(key="credit", title="信用", lede=lede, flags=_flags(items), items=items)
    months = months_between(company.founded, as_of)
    status = (Status.bad if DEAD_STATUS.search(company.status)
              else Status.warn if months < YOUNG_COMPANY_MONTHS else Status.ok)
    items = [SignalItem(key="status", label="登记状态", value=company.status,
                        detail=f"成立于 {company.founded}，{months // 12} 年 {months % 12} 个月", status=status, source="registry")]
    if not company.known("penalties"):
        items.append(SignalItem(key="penalties", label="行政处罚", value="没查", detail="这次的数据来源不含这一项",
                                status=Status.none, source="registry"))
    elif company.n("penalties"):
        detail = "；".join(f"{p.date or '日期未公示'} {p.org}：{p.reason + '，' if p.reason else ''}{p.result}"
                           for p in company.penalties[:5]) or SHOWN_NONE
        if company.n("penalties") > min(len(company.penalties), 5):
            detail += f"（共 {company.n('penalties')} 条，这里列了前 {min(len(company.penalties), 5)} 条）"
        items.append(SignalItem(key="penalties", label="行政处罚", value=f"{company.n('penalties')} 条", detail=detail,
                                status=Status.bad, source="registry"))
    else:
        items.append(SignalItem(key="penalties", label="行政处罚", value="无", status=Status.ok, source="registry"))
    for key, label, hit, yes, no in [("abnormal", "经营异常名录", company.abnormal, "已列入", "未列入"),
                                     ("serious_illegal", "严重违法失信名单", company.serious_illegal, "已列入", "未列入"),
                                     ("dishonest", "失信被执行人", company.dishonest, "有", "无"),
                                     ("restricted", "限制高消费", company.restricted, "有", "无")]:
        if not company.known(key):
            if key != "restricted":  # 限制高消费只有商业接口给，没查就不占一行
                items.append(SignalItem(key=key, label=label, value="没查", detail="这次的数据来源不含这一项",
                                        status=Status.none, source="registry"))
            continue
        n = company.counts.get(key, 0)
        items.append(SignalItem(key=key, label=label, value=(f"{yes}（{n} 条）" if n > 1 else yes) if hit else no,
                                detail=company.facts.get(key) if hit else None,
                                status=Status.bad if hit else Status.ok, source="registry"))
    if company.risk_scan:
        items += other_risks_item(company.risk_scan)
    if integrity:
        items.append(integrity)
    items.append(web_item)
    return Signal(key="credit", title="信用", lede=lede, flags=_flags(items), items=items)


# 风险扫描里已经单列成条目的因子；其余有记录的合成一行"其他风险记录"
LISTED_FACTORS = {"行政处罚", "被执行人", "失信信息", "限制高消费", "经营异常", "严重违法", "股权出质", "动产抵押", "欠税公告"}
# 这些说明欠钱还不上、税务或经营出了问题；裁判文书、开庭这类不分原告被告，只算要留意
# 只有这些条目一定是它自己出的问题（被执行人、纳税人、破产主体）。司法拍卖、违约事项这类，银行等债权人也会出现在里面，
# 风险扫描不分角色，只算要留意
SERIOUS_FACTORS = {"终本案件", "税务非正常户", "税收违法", "破产重整", "清算信息", "惩戒名单", "限制出境", "财产悬赏公告"}


def other_risks_item(scan: dict[str, int]) -> list[SignalItem]:
    hits = {k: v for k, v in scan.items() if v and k not in LISTED_FACTORS}
    if not hits:
        return []
    serious = [k for k in hits if k in SERIOUS_FACTORS]
    order = serious + [k for k in hits if k not in SERIOUS_FACTORS]
    return [SignalItem(key="other_risks", label="其他风险记录", value="、".join(f"{k} {hits[k]}" for k in order),
                       detail="商业数据风险扫描的条数，不分它是哪一方：裁判文书、立案、开庭、司法拍卖里它也可能是原告或债权人，"
                              "打官司不等于有问题。终本案件指它作为被执行人、法院没查到可执行的财产，先结束这次执行",
                       status=Status.bad if serious else Status.warn, source="registry")]


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


# ---------- 企查查补充信息、巨潮公告、权威媒体 ----------
# 都只列事实和条数；能标"要留意"的只有几种：近一年改名或换法定代表人、近两年当被告的投资类纠纷或劳动纠纷、
# 近一年交易所公告里有处罚或监管措施、权威媒体报道过它被处罚或警示。没有一项会标"有问题"。

def _part_none(key: str, label: str, part, source: str) -> SignalItem | None:
    if part.coverage == "failed":
        return SignalItem(key=key, label=label, value="没查成", detail=part.error, status=Status.none, source=source)
    return None


def controller_item(x: "qcc_more.QccExtras") -> SignalItem | None:
    p = x.get("controller")
    if p.coverage == "not_found":
        return SignalItem(key="controller", label="实际控制人", value="平台没有记录",
                          detail="股权分散或没穿透出来；不等于没有人控制", status=Status.ok, source="qcc_controller")
    if p.coverage != "found":
        return _part_none("controller", "实际控制人", p, "qcc_controller")
    c = p.rows[0]
    who = "自然人（个人）" if c.get("是自然人") else c.get("名称")
    share = "，".join(x for x in (f"持股 {c['总持股比例']}" if c.get("总持股比例") else "",
                                 f"表决权 {c['表决权比例']}" if c.get("表决权比例") else "") if x)
    return SignalItem(key="controller", label="实际控制人", value=who, detail=share or None, status=Status.ok,
                      source="qcc_controller")


def license_item(x: "qcc_more.QccExtras") -> SignalItem | None:
    lic, qual = x.get("licenses"), x.get("qualifications")
    if lic.coverage == "failed" and qual.coverage == "failed":
        return _part_none("permits", "行政许可和资质", lic, "qcc_licenses")
    fin = qcc_more.financial_licenses(x)
    value = f"行政许可 {lic.total} 条、资质证书 {qual.total} 个"
    detail = ("其中和金融有关的：" + "、".join(fin[:6])) if fin else "没有金融牌照类的资质（金融牌照以监管名单为准）"
    return SignalItem(key="permits", label="行政许可和资质", value=value, detail=detail, status=Status.ok,
                      source="qcc_qualifications" if qual.total else "qcc_licenses")


def change_item(x: "qcc_more.QccExtras", today: date) -> SignalItem | None:
    p = x.get("changes")
    if p.coverage != "found":
        return _part_none("changes", "工商变更", p, "qcc_changes")
    last = qcc_more.recent(p.rows, today, 365)
    flagged = [r for r in last if qcc_more.FLAG_CHANGE.search(r.get("项目") or "")]
    kinds = list(dict.fromkeys(re.sub(r"（.*?）|\(.*?\)", "", r.get("项目") or "") for r in last))
    detail = (f"近一年 {len(last)} 次：" + "、".join(kinds[:5])) if last else "近一年没有变更"
    if flagged:
        detail = "近一年改过名称或法定代表人。跑路前常见改名、换人，但正常经营也会改，要问清原因。" + detail
    return SignalItem(key="changes", label="工商变更", value=f"共 {p.total} 次", detail=detail,
                      status=Status.warn if flagged else Status.ok, source="qcc_changes")


def lawsuit_items(x: "qcc_more.QccExtras", today: date) -> list[SignalItem]:
    items = []
    h, f = x.get("hearings"), x.get("filings")
    if h.coverage == "found" or f.coverage == "found":
        shown = len(h.rows) + len(f.rows)
        mine = qcc_more.recent(qcc_more.defendant_cases(x), today, 730)
        invest = [r for r in mine if qcc_more.INVEST.search(r.get("案由") or "")]
        causes = Counter(r.get("案由") or "未写案由" for r in mine).most_common(3)
        detail = (f"开庭 {h.total}、立案 {f.total} 条；看了返回的最近 {shown} 条，近两年它当被告 {len(mine)} 条"
                  + (f"（{'、'.join(f'{c} {n}' for c, n in causes)}）" if causes else "") + "。打官司不等于有错，银行起诉借款人很常见")
        if invest:
            detail = f"近两年有 {len(invest)} 起投资、合伙、理财类纠纷是别人告它，可能是投资人在追钱。" + detail
        items.append(SignalItem(key="lawsuits", label="开庭和立案", value=f"近两年当被告 {len(mine)} 条",
                                detail=detail, status=Status.warn if invest else Status.ok,
                                source="qcc_hearings" if h.coverage == "found" else "qcc_filings"))
    else:
        none = _part_none("lawsuits", "开庭和立案", h, "qcc_hearings")
        items += [none] if none else []
    lab = x.get("labor")
    labor_cases = [r for r in qcc_more.defendant_cases(x) if qcc_more.LABOR.search(r.get("案由") or "")]
    labor_recent = qcc_more.recent(lab.rows, today, 730) + qcc_more.recent(labor_cases, today, 730)
    if lab.coverage == "found" or labor_cases:
        items.append(SignalItem(key="labor", label="劳动仲裁和劳动纠纷",
                                value=f"劳动仲裁 {lab.total} 条，当被告的劳动官司 {len(labor_cases)} 条",
                                detail=f"近两年 {len(labor_recent)} 条" + ("。求职前可以问问对方怎么回事" if labor_recent else ""),
                                status=Status.warn if labor_recent else Status.ok,
                                source="qcc_labor" if lab.coverage == "found" else "qcc_hearings"))
    elif lab.coverage == "not_found":
        items.append(SignalItem(key="labor", label="劳动仲裁", value="无", status=Status.ok, source="qcc_labor"))
    return items


def jobs_item(x: "qcc_more.QccExtras", company: CompanyProfile | None, today: date) -> SignalItem | None:
    p = x.get("jobs")
    if p.coverage != "found":
        return _part_none("jobs", "招聘", p, "qcc_jobs")
    cities = list(dict.fromkeys(str(r.get("地点")) for r in p.rows if r.get("地点")))
    latest = max((str(r.get("日期") or "") for r in p.rows), default="")
    pay = [str(r.get("月薪")) for r in p.rows if r.get("月薪")]
    detail = f"最近一条 {latest or '日期不详'}；招聘地点 {len(cities)} 个（{'、'.join(cities[:5])}）" + \
             (f"；月薪如 {'、'.join(dict.fromkeys(pay[:3]))}" if pay else "")
    insured = company.insured if company is not None else None
    fresh = latest >= (today - timedelta(days=3 * 365)).isoformat()
    odd = insured is not None and insured < 10 and len(cities) >= 3 and fresh
    if odd:
        detail = f"在 {len(cities)} 个城市招人，但年报里参保只有 {insured} 人，对不上，要问清楚员工归谁。" + detail
    elif insured is not None and len(cities) >= 3:
        detail += f"；年报参保 {insured} 人（招聘较早，不直接比）" if not fresh else f"；年报参保 {insured} 人"
    return SignalItem(key="jobs", label="招聘", value=f"{p.total} 条", detail=detail,
                      status=Status.warn if odd else Status.ok, source="qcc_jobs")


def cninfo_items(c: CninfoFindings | None) -> tuple[list[SignalItem], list[SignalItem]]:
    """返回（财务卡片的年报原文，信用卡片的公告）。"""
    if c is None or c.coverage == "not_covered":
        return [], []
    if c.coverage != "found":
        bad = SignalItem(key="cninfo", label="交易所公告（巨潮资讯网）", value="没查成" if c.coverage == "failed" else "没有",
                         detail=c.error, status=Status.none, source="cninfo")
        return [], [bad]
    fin_items = []
    if c.annual:
        fin_items.append(SignalItem(key="annual_report_pdf", label="最新年报原文", value=f"{c.annual.title}（{c.annual.date}）",
                                    detail="巨潮资讯网上的 PDF 原文；上面的财务数字以它为准", status=Status.ok,
                                    source="cninfo"))
    pen = [n for n in c.risky if n.category == "penalty"]
    others = [n for n in c.risky if n.category != "penalty"]
    detail = f"最近一年公告 {c.total} 条，看了 {c.scanned} 条标题"
    if c.risky:
        top = (pen or others)[0]
        detail += f"；最近一条：{top.date}《{top.title}》"
    credit = SignalItem(key="cninfo", label="交易所公告里的处罚、诉讼、问询",
                        value=(f"处罚或监管措施 {len(pen)} 条，诉讼或问询 {len(others)} 条") if c.risky else "没有",
                        detail=detail, status=Status.warn if pen else Status.ok, source="cninfo")
    return fin_items, [credit]


def media_item(web: WebFindings | None) -> SignalItem | None:
    if web is None or not web.searched:
        return None
    hits = sorted(web.media, key=lambda h: h.date or "", reverse=True)
    if not hits:
        failed = any("权威媒体" in e for e in web.errors)
        return SignalItem(key="media", label="权威媒体报道", value="没查成" if failed else "没搜到",
                          detail="只搜人民网、新华网、财新、证券时报等二十多家；没搜到不等于没有",
                          status=Status.none if failed else Status.ok, source="web_media")
    reg = [h for h in hits if h.category in ("penalty", "warning") and h.subject]
    top = (reg or hits)[0]
    detail = f"最近：{top.date or '日期不详'} {top.site}《{top.title}》"
    if reg:
        detail = f"有 {len(reg)} 篇说到它被处罚、警示或涉嫌违规。" + detail
    return SignalItem(key="media", label="权威媒体报道", value=f"{len(hits)} 篇", detail=detail,
                      status=Status.warn if reg else Status.ok, source="web_media")


def news_items(news: NewsFindings, today: date) -> list[SignalItem]:
    """企查查新闻舆情。负面是平台的模型标的：最多到"要留意"，不到"有问题"。"""
    if news.coverage != "found":
        failed = news.coverage == "failed"
        return [SignalItem(key="news", label="新闻舆情", value="没查成" if failed else "没有新闻",
                           detail=news.error if failed else "平台没有收录这家公司的新闻；没有不等于没人说过",
                           status=Status.none, source="qcc_news")]
    recent = news.recent_negatives(today)
    shown = len(news.items)
    items = [SignalItem(key="news", label="新闻舆情", value=f"共 {news.total} 条",
                        detail=f"看的是最近 {shown} 条：负面 {news.counts().get('消极', 0)}、中立 {news.counts().get('中立', 0)}、"
                               f"正面 {news.counts().get('积极', 0)}（企查查标的倾向）",
                        status=Status.ok, source="qcc_news")]
    if news.negatives:
        top = (recent or news.negatives)[0]
        items.append(SignalItem(key="news_negative", label="近一年企查查标为负面的新闻" if recent else "负面新闻（一年以前）",
                                value=f"{len(recent)} 条" if recent else f"{len(news.negatives)} 条",
                                detail=f"最近一条：{top.date or '日期不详'} {top.source}《{top.title}》",
                                status=Status.warn if recent else Status.ok, source="qcc_news"))
    return items


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


REVIEW_MIN = 3   # 少于这么多条，只作参考


def review_item(reviews: list[dict] | None) -> SignalItem | None:
    """用户评价：别人说的，未核实。差评集中才标"要留意"；好评不标绿（会刷好评的，往往正是要查的公司），
    也不标"有问题"（那是留给官方记录的）。没有评价就不出这一条。"""
    if not reviews:
        return None
    n, low = len(reviews), sum(r["stars"] <= 2 for r in reviews)
    dist = "、".join(f"{s} 星 {c} 条" for s in range(5, 0, -1) if (c := sum(r["stars"] == s for r in reviews)))
    if n < REVIEW_MIN:
        status, detail = Status.none, f"只有 {n} 条，太少，只作参考。用户自己写的，系统不判断真假"
    elif low * 2 >= n:
        status, detail = Status.warn, (f"{n} 条里有 {low} 条打了 1–2 星，差评集中。用户自己写的，没核实；"
                                       "点开看他们说的具体是什么事，再拿去问对方")
    else:
        status, detail = Status.none, "差评不集中，只作参考。好评多不代表没问题；用户自己写的，系统不判断真假"
    return SignalItem(key="user_reviews", label="用户评价（未核实）", value=f"{n} 条：{dist}", detail=detail,
                      status=status, source="user_reviews")


def build_signals(ext: Extraction, company: CompanyProfile | None, lic: LicenseHit, amac: AmacHit,
                  complaints: dict | None, as_of: date, scenario: Scenario,
                  assertions: list[Assertion] = (), others: list[RegistryHit] = (),
                  web: WebFindings | None = None, web_refs: dict[str, str] | None = None,
                  amount: float | None = None, reviews: list[dict] | None = None,
                  finance: FinancialFindings | None = None, news: NewsFindings | None = None,
                  extras: "qcc_more.QccExtras | None" = None, cninfo: CninfoFindings | None = None) -> list[Signal]:
    """四个信号的内容不随场景变；场景只改排序和开头那句话。"""
    scale = ext.claims.get(ClaimKind.scale)
    stores = scale.numbers.get("stores") if scale else None
    refs = web_refs or {}
    signals = {s.key: s for s in [risk_signal(ext, company, lic, amac, scenario, list(assertions), list(others), web, refs,
                                              amount),
                                  finance_signal(company, stores, amac, finance), credit_signal(company, as_of, web, refs, amac),
                                  reputation_signal(complaints, web, refs)]}
    fin_cn, credit_cn = cninfo_items(cninfo)
    adds: dict[str, list[SignalItem | None]] = {"finance": list(fin_cn), "credit": list(credit_cn), "risk": []}
    if extras is not None:
        adds["risk"] += [controller_item(extras), license_item(extras), change_item(extras, as_of)]
        adds["credit"] += lawsuit_items(extras, as_of)
        adds["finance"].append(jobs_item(extras, company, as_of))
    for key, new in adds.items():
        new = [i for i in new if i is not None]
        if new and key in signals:
            signals[key].items += new
            signals[key].flags = _flags(signals[key].items)
    if web is not None and (item := media_item(web)) is not None:
        signals["reputation"].items.append(item)
        if web.media:
            signals["reputation"].extra = (signals["reputation"].extra or {}) | {"media": [
                {"category": h.category_label, "title": h.title, "url": h.url, "site": h.site, "date": h.date,
                 "excerpt": h.excerpt, "ref": refs.get(h.url)} for h in sorted(web.media, key=lambda h: h.date or "", reverse=True)]}
        signals["reputation"].flags = _flags(signals["reputation"].items)
    if cninfo is not None and cninfo.coverage == "found" and cninfo.risky:
        signals["credit"].extra = (signals["credit"].extra or {}) | {"notices": [n.__dict__ for n in cninfo.risky]}
    if news is not None:
        rep = signals["reputation"]
        if rep.items and rep.items[0].key == "complaints" and rep.items[0].status is Status.none:
            rep.items = []  # "还没有投诉数据"：舆情查了，就不再说没查
        rep.items[:0] = news_items(news, as_of)
        rep.extra = (rep.extra or {}) | {"news": [{"title": i.title, "date": i.date, "source": i.source, "url": i.url}
                                                  for i in news.negatives]}
        rep.flags = _flags(rep.items)
    if item := review_item(reviews):
        rep = signals["reputation"]
        rep.items.append(item)
        rep.flags = _flags(rep.items)
    for key, lede in scenario.signal_ledes.items():
        if key in signals:
            signals[key].lede = lede
    return [signals[k] for k in scenario.signal_order]
