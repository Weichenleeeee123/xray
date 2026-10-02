"""报告里的图。数据全部来自记录和规则，不经过模型。

- 只画有数据的。没查的值写 value=None，前端画成虚线框写"没查"，不画成 0。
- 不画风险分、雷达图、仪表盘：那等于把规则结论折成一个分数，PRD 明确不打分。
- 不同单位不放在一根轴上：门店数和分支机构数放一起，参保人数只写在读图的那句话里。
- 自然人股东不显示姓名。
"""
import re
from datetime import date

from app.analysis.extract import Extraction
from app.analysis.fmt import money, wan
from app.config import REF_DEPOSIT_RATE
from app.models import AmacHit, Assertion, Chart, ChartPoint, ClaimKind, CompanyProfile, TimelineEvent
from app.sources.amac_detail import scale_upper
from app.sources.web import WebFindings

LETTERS = "ABCDEFGH"
NEWS_MAX = 4
OFFICIAL_TONE = {"penalty": "bad", "warning": "bad", "judicial": "warn", "license": "neutral"}


def _claim(assertions: list[Assertion], kind: ClaimKind) -> Assertion | None:
    return next((a for a in assertions if a.kind == kind), None)


def capital_chart(ext: Extraction, company: CompanyProfile | None, assertions: list[Assertion],
                  refs: dict[str, str]) -> Chart | None:
    if company is None or not company.known("reg_capital"):
        return None
    a = _claim(assertions, ClaimKind.capital)
    claimed = ext.claims[ClaimKind.capital].numbers.get("capital") if ClaimKind.capital in ext.claims else None
    reg = company.reg_capital
    paid = company.paid_capital if company.known("paid_capital") else None
    points = []
    if claimed is not None:
        points.append(ChartPoint(label="宣传说的注册资本", value=claimed, display=wan(claimed), side="said",
                                 ref=a.refs[0] if a and a.refs else None, source="material"))
    points.append(ChartPoint(label="登记的注册资本（认缴）", value=reg, display=wan(reg), ref=refs.get("registry"),
                             source="registry"))
    points.append(ChartPoint(label="实缴资本（年报）", value=paid, display=money(paid) if paid is not None else "没查",
                             ref=refs.get("annual_report"), source="annual_report"))
    if paid is None and claimed is None:
        return None
    note = (f"登记的注册资本是股东承诺出的钱；实际交了 {money(paid)}，占 {paid / reg:.0%}。" if paid is not None and reg
            else "实缴资本年报没公示，实际交了多少不知道。")
    return Chart(id="capital", kind="compare", title="注册资本：说的、登记的、实际交的", note=note,
                 item=a.id if a else "finance.paid_capital", points=points)


def return_chart(ext: Extraction, assertions: list[Assertion]) -> Chart | None:
    claim = ext.claims.get(ClaimKind.return_promise)
    rate = claim.numbers.get("annual_rate") if claim else None
    if rate is None:
        return None
    a = _claim(assertions, ClaimKind.return_promise)
    ref_rate = round(REF_DEPOSIT_RATE * 100, 4)
    return Chart(id="return", kind="compare", title="它承诺的收益 vs 一年期定存",
                 note=f"约为定存的 {rate / ref_rate:.1f} 倍。收益越高，越要问清钱从哪里来。",
                 item=a.id if a else "risk.promise",
                 points=[ChartPoint(label="宣传的年化收益", value=rate, display=f"{rate:g}%", side="said",
                                    ref=a.refs[0] if a and a.refs else None, source="material"),
                         ChartPoint(label="一年期定存参考利率", value=ref_rate, display=f"{ref_rate:.2g}%",
                                    side="reference", source="param_rate")])


def scale_chart(ext: Extraction, company: CompanyProfile | None, assertions: list[Assertion],
                refs: dict[str, str]) -> Chart | None:
    claim = ext.claims.get(ClaimKind.scale)
    stores = claim.numbers.get("stores") if claim else None
    if stores is None or company is None or not company.known("branches") or company.branches is None:
        return None
    a = _claim(assertions, ClaimKind.scale)
    note = f"年报里参保 {company.insured} 人。" if company.known("insured") and company.insured is not None else None
    return Chart(id="scale", kind="compare", title="门店：说的 vs 登记的", note=note, item=a.id if a else "finance.insured",
                 points=[ChartPoint(label="宣称的门店", value=stores, display=f"{stores:g} 家", side="said",
                                    ref=a.refs[0] if a and a.refs else None, source="material"),
                         ChartPoint(label="登记的分支机构", value=company.branches, display=f"{company.branches} 家",
                                    ref=refs.get("registry"), source="registry")])


def _amac_fields(amac: AmacHit | None) -> dict:
    return ((amac.record or {}).get("detail") or {}) if amac and amac.registered else {}


def aum_chart(ext: Extraction, amac: AmacHit | None, assertions: list[Assertion], refs: dict[str, str]) -> Chart | None:
    claim = ext.claims.get(ClaimKind.scale)
    aum = claim.numbers.get("aum") if claim else None
    band = _amac_fields(amac).get("管理规模区间")
    upper = scale_upper(band)
    if aum is None or upper is None:
        return None
    a = _claim(assertions, ClaimKind.scale)
    group = "集团" if claim.numbers.get("aum_group") else ""
    return Chart(id="aum", kind="compare", title="管理资产：说的 vs 协会登记的", item=a.id if a else "finance.amac_scale",
                 note=f"宣传说的是{group}管理资产 {wan(aum)}；它自己在中基协登记的管理规模区间是 {band}（管理人自行填报）。",
                 points=[ChartPoint(label=f"宣传的{group}管理资产", value=aum, display=wan(aum), side="said",
                                    ref=a.refs[0] if a and a.refs else None, source="material"),
                         ChartPoint(label="中基协登记的管理规模（区间上限）", value=upper, display=band,
                                    ref=refs.get("amac_detail"), source="amac_detail")])


def staff_chart(ext: Extraction, amac: AmacHit | None, assertions: list[Assertion], refs: dict[str, str]) -> Chart | None:
    claim = ext.claims.get(ClaimKind.scale)
    staff = claim.numbers.get("staff") if claim else None
    n = _amac_fields(amac).get("全职员工人数", "")
    if staff is None or not n.isdigit():
        return None
    a = _claim(assertions, ClaimKind.scale)
    return Chart(id="staff", kind="compare", title="员工：说的 vs 协会登记的", item=a.id if a else "finance.amac_scale",
                 note=f"中基协登记的全职员工 {n} 人，取得基金从业资格 {_amac_fields(amac).get('取得基金从业人数', '?')} 人。",
                 points=[ChartPoint(label="宣传的公司规模（下限）", value=staff, display=f"{staff:g} 人以上", side="said",
                                    ref=a.refs[0] if a and a.refs else None, source="material"),
                         ChartPoint(label="中基协登记的全职员工", value=int(n), display=f"{n} 人",
                                    ref=refs.get("amac_detail"), source="amac_detail")])


def holders_chart(company: CompanyProfile | None, assertions: list[Assertion], refs: dict[str, str]) -> Chart | None:
    if company is None or not company.known("shareholders") or not company.shareholders:
        return None
    people = [h for h in company.shareholders if h.type == "自然人"]
    points = []
    for h in company.shareholders:
        label = h.name if h.type != "自然人" else (f"自然人股东 {LETTERS[people.index(h)]}" if len(people) > 1 else "自然人股东")
        points.append(ChartPoint(label=label, value=h.pct, display=f"{h.pct:g}%", ref=refs.get("registry"),
                                 source="registry"))
    a = _claim(assertions, ClaimKind.background)
    parts = [f"宣传说\"{a.text}\"；{a.plain}"] if a else [f"登记的股东 {len(points)} 个。"]
    if company.known("pledges") and company.pledges:
        parts.append(f"其中 {'、'.join(p.share for p in company.pledges)}已出质。")
    return Chart(id="holders", kind="share", title="谁是股东", note="".join(parts),
                 item=a.id if a else "finance.pledges", points=points)


def complaints_chart(data: dict | None, refs: dict[str, str]) -> Chart | None:
    if not data or not data.get("counts"):
        return None
    counts, months = data["counts"], data["months"]
    total, last3 = sum(counts), sum(counts[-3:])
    return Chart(id="complaints", kind="series", title="近 12 个月投诉数", item="reputation.recent",
                 note=f"共 {total} 条，最近 3 个月 {last3} 条。单条投诉不能证明什么，看的是趋势。",
                 points=[ChartPoint(label=m, value=n, display=str(n), ref=refs.get("complaints"), source="complaints")
                         for m, n in zip(months, counts)])


def timeline_chart(company: CompanyProfile | None, web: WebFindings | None, web_refs: dict[str, str],
                   complaints: dict | None, refs: dict[str, str], today: date) -> Chart | None:
    ev: list[TimelineEvent] = []
    reg = refs.get("registry")
    if company is not None:
        if company.known("founded") and company.founded:
            ev.append(TimelineEvent(date=company.founded, label="公司成立", ref=reg, item="credit.status"))
        if company.known("penalties"):
            ev += [TimelineEvent(date=p.date, label=f"行政处罚：{p.reason or p.org}", tone="bad", ref=reg, item="credit.penalties")
                   for p in company.penalties if p.date]
        if company.known("pledges") and company.n("pledges") <= 5:   # 多了只在信号里写条数，不挤时间线
            ev += [TimelineEvent(date=p.date, label=f"股权出质：{p.share}", tone="warn", ref=reg, item="finance.pledges")
                   for p in company.pledges if p.date]
        for field, label in [("dishonest", "列为失信被执行人"), ("restricted", "被限制高消费"), ("abnormal", "列入经营异常名录"),
                             ("serious_illegal", "列入严重违法失信名单")]:
            when = re.search(r"\d{4}-\d{2}-\d{2}", company.facts.get(field, ""))
            if company.known(field) and getattr(company, field) and when:
                ev.append(TimelineEvent(date=when.group(0), label=label + ("（最近一次）" if field == "restricted" and
                                                                          company.counts.get(field, 0) > 1 else ""),
                                        tone="bad", ref=reg, item=f"credit.{field}"))
        for field, label, tone in [("executions", "被执行", "bad"), ("tax_arrears", "欠税公告", "bad"),
                                   ("mortgages", "动产抵押", "warn")]:
            if company.known(field):
                ev += [TimelineEvent(date=str(r["date"]), label=label, tone=tone, ref=reg, item=f"finance.{field}")
                       for r in getattr(company, field) if isinstance(r, dict) and r.get("date")]
        if company.known("capital_due") and company.capital_due:
            ev.append(TimelineEvent(date=company.capital_due, label="认缴出资到期", tone="future",
                                    ref=reg, item="finance.paid_capital"))
    if web is not None:
        penalty_days = [date.fromisoformat(p.date) for p in (company.penalties if company is not None and
                        company.known("penalties") else []) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.date or "")]
        for h in web.official:
            if not h.date or h.category not in OFFICIAL_TONE or not h.subject:   # 其他提及、只是顺带提到它的，不上线
                continue
            # 同一份处罚决定：登记记录里已有、网页日期只差几天（网页发布晚于决定日），不再画一次
            if h.category == "penalty" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", h.date[:10]) and \
                    any(abs((date.fromisoformat(h.date[:10]) - d).days) <= 15 for d in penalty_days):
                continue
            # 法院文书的标题常带当事人姓名，只写类别；处罚决定书标题括号里列的当事人（常有人名）也去掉
            title = re.split(r"[（(_]", h.title)[0][:24]
            label = h.category_label if h.category == "judicial" else f"{h.category_label}：{title}"
            if not h.dated:
                label += "（日期是网页收录日）"
            ev.append(TimelineEvent(date=h.date[:10], label=label, tone=OFFICIAL_TONE[h.category], ref=web_refs.get(h.url),
                                    item="risk.regulator_warning" if h.category == "warning" else "credit.official_web"))
        news = sorted((TimelineEvent(date=h.date[:10], label=f"{h.category_label}：{h.title[:20]}", tone="warn",
                                     ref=web_refs.get(h.url), item=f"reputation.web_{h.category}")
                       for h in web.news if h.date and h.category in ("cash", "complaint")), key=lambda e: e.date)
        ev += news[-NEWS_MAX:]   # 报道只放最近几条，线上不至于挤满
    if complaints and complaints.get("counts"):
        counts, months = complaints["counts"], complaints["months"]
        peak = max(range(len(counts)), key=lambda i: (counts[i], i))
        if counts[peak]:
            ev.append(TimelineEvent(date=months[peak], label=f"投诉最多的月份：{counts[peak]} 条", tone="warn",
                                    ref=refs.get("complaints"), item="reputation.recent"))
    if len(ev) < 2:
        return None
    ev.sort(key=lambda e: e.date)
    return Chart(id="timeline", kind="timeline", title="时间线", events=ev,
                 note=f"截至 {today.isoformat()}。只列查到的事；没查的不在线上，不代表没发生。")


def build_charts(ext: Extraction, company: CompanyProfile | None, assertions: list[Assertion],
                 refs: dict[str, str], web: WebFindings | None, web_refs: dict[str, str],
                 complaints: dict | None, today: date, amac: AmacHit | None = None) -> list[Chart]:
    charts = [capital_chart(ext, company, assertions, refs), return_chart(ext, assertions),
              aum_chart(ext, amac, assertions, refs), staff_chart(ext, amac, assertions, refs),
              scale_chart(ext, company, assertions, refs), holders_chart(company, assertions, refs),
              complaints_chart(complaints, refs),
              timeline_chart(company, web, web_refs, complaints, refs, today)]
    return [c for c in charts if c is not None]
