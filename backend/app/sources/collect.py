"""汇集数据：查一家公司时把各个来源查一遍，每个来源写一条原始记录（RawRecord）。

官方名单（真实，每家公司都查）：银行业、保险、期货、支付机构名单，中基协私募管理人名单。
企业登记按顺序找：证据包（人工采集的官方记录）→ 商业接口（企查查/天眼查，配置了才用）→ 演示数据 → 记"没查"。
企查查补充信息（配置了才查）：实际控制人、行政许可和资质、变更记录、开庭和立案、劳动仲裁、招聘。
财务数据、新闻舆情：企查查（上市、发债的公司才有财报）；上市公司再到巨潮资讯网取年报原文和最近一年的公告。
联网搜索（配了模型网关才搜）：政府网站点名它的文件；网上的投诉、维权帖和报道；权威媒体的报道。
用户评价：有就记一条快照（别人说的，未核实）；没有不记。

步骤顺序（和 progress.STEPS 一致）：持牌名单 → 中基协 → 工商 → 财务 → 证据包 → 政府网站 → 舆情 → 本站评价。
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from app import progress
from app.models import AmacHit, CompanyProfile, Coverage, LicenseHit, RawRecord, RegistryHit, Source
from app.reviews import review_record
from app.sources.amac_detail import summary as amac_summary
from app.sources import finance as fin
from app.sources import qcc_more
from app.sources.cninfo import CninfoFindings
from app.sources import news as news_src
from app.sources.finance import FinancialFindings
from app.sources.licenses import normalize
from app.sources.news import NewsFindings
from app.sources.packs import SECTIONS, Pack
from app.sources.registries import AMAC_ID, LICENSE_LISTS
from app.sources.web import WebFindings

ANNUAL_FIELDS = ("paid_capital", "insured")
QCC_SITE = "https://agent.qcc.com"


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Collected:
    company: CompanyProfile | None
    license: LicenseHit
    amac: AmacHit
    complaints: dict | None
    as_of: date                          # 登记数据的截止日，用来算"成立多久"
    sources: dict[str, Source]
    records: list[RawRecord] = field(default_factory=list)  # id 留空，由案卷分配
    others: list[RegistryHit] = field(default_factory=list)  # 银行业以外的持牌名单
    note: str | None = None              # 证据包的说明：资料截止日期、话术出处
    web: WebFindings | None = None       # 联网查证；没开或是虚构公司时为 None
    finance: FinancialFindings | None = None   # 企查查财务数据；没查时为 None
    news: NewsFindings | None = None           # 企查查新闻舆情；没查时为 None
    extras: "qcc_more.QccExtras | None" = None  # 企查查补充信息；没查时为 None
    cninfo: CninfoFindings | None = None       # 巨潮资讯网公告（上市公司）
    reviews: list[dict] = field(default_factory=list)  # 用户评价（含作者哈希，只在后端用；原始数据里不带）


def _raw(source_id: str, title: str, kind: str, coverage: Coverage, content=None, *, retrieved_at: str | None = None,
         as_of: str | None = None, url: str | None = None, screenshot: str | None = None,
         note: str | None = None) -> RawRecord:
    return RawRecord(id="", source_id=source_id, title=title, kind=kind, coverage=coverage,
                     retrieved_at=retrieved_at or now(), as_of=as_of, url=url, content=content,
                     screenshot=screenshot, note=note)


def _hit_content(query: str, found: bool, record, suggestions: list[str]) -> dict:
    return {"查询名称": query, "是否收录": found, "记录": record, "名称相近的机构": suggestions[:3]}


def _license_record(lic: LicenseHit, meta: dict) -> RawRecord:
    content = _hit_content(lic.query, lic.found, lic.record.model_dump() if lic.record else None,
                           [s.name for s in lic.suggestions])
    return _raw("nfra_bank_list", "银行业金融机构法人名单 · 按名称查询", "official",
                Coverage.found if lic.found else Coverage.not_found, content, as_of=meta["as_of"], url=meta["url"],
                note=f"共 {meta['count']:,} 家；只含银行业金融机构，查不到不等于没有其他牌照")


def _official_lists(name: str, svc) -> tuple[list[RegistryHit], list[RawRecord]]:
    hits, records = [], []
    for rid in LICENSE_LISTS:
        index = svc.registries.get(rid)
        if index is None:
            continue
        hit = index.lookup(name)
        hits.append(hit)
        url = (hit.record or {}).get("url") or index.meta.get("url")
        records.append(_raw(rid, f"{hit.title} · 按名称查询", "official",
                            Coverage.found if hit.found else Coverage.not_found,
                            _hit_content(name, hit.found, hit.record, hit.suggestions), as_of=hit.as_of, url=url,
                            note=f"{index.meta.get('publisher', '')}公布，共 {hit.count:,} 家"))
    return hits, records


def _real_amac(name: str, svc) -> tuple[AmacHit, list[RawRecord]] | None:
    index = svc.registries.get(AMAC_ID)
    if index is None:
        return None
    progress.start("amac")
    hit = index.lookup(name)
    amac = AmacHit(coverage=Coverage.found if hit.found else Coverage.not_found, registered=hit.found,
                   record=hit.record, as_of=hit.as_of, count=hit.count)
    url = (hit.record or {}).get("detail_url") or index.meta.get("url")
    records = [_raw("amac", "私募基金管理人公示 · 按名称查询", "official", amac.coverage,
                    _hit_content(name, hit.found, hit.record, hit.suggestions), as_of=hit.as_of, url=url,
                    note=f"中基协公示的全部 {hit.count:,} 家私募基金管理人；special_tips/credit_tips 为 1 表示协会有特别提示/诚信信息")]
    detail_url = (hit.record or {}).get("detail_url")
    client = getattr(svc, "amac_detail", None)
    if hit.found and detail_url and client:
        detail, when, cached = client.fetch(detail_url)
        if detail:
            s = amac_summary(detail)
            amac.record = {**hit.record, "detail": s}
            records.append(_raw("amac_detail", "中基协公示详情页：规模、员工、诚信信息、处罚", "official", Coverage.found, s,
                                retrieved_at=when, as_of=s.get("机构信息最后更新时间"), url=detail_url,
                                note="中基协公示页面摘录：管理规模、员工人数、资本由管理人自行填报，诚信信息、处罚和提示由协会公示" +
                                     ("；网络不通，用的是之前缓存的页面" if cached else "")))
        else:
            records.append(_raw("amac_detail", "中基协公示详情页", "official", Coverage.failed, url=detail_url,
                                note="详情页没取到（网络不通，也没有缓存）"))
    return amac, records


def _web_records(web: WebFindings) -> list[RawRecord]:
    records = []
    for hits, sid, label, tag in ((web.official, "web_official", "监管、法院、政府网站", "官方"),
                                  (web.news, "web_news", "网上的投诉和报道", "报道"),
                                  (web.media, "web_media", "权威媒体报道", "权威媒体")):
        for h in hits:
            records.append(_raw(sid, h.title or h.site, "official" if h.official else "web", Coverage.found,
                                {"类别": h.category_label, "网站": h.site, "命中原文": h.excerpt}, as_of=h.date,
                                url=h.url, note=("联网搜索找到，摘要里只有简称，可能是同名的别家，要点开原文确认"
                                                 if h.by_short_name else "联网搜索找到，已核对摘要里有这家公司的全称") +
                                                ("；离线回放的搜索结果" if web.replay else "")))
        if not hits:
            failed = any(tag in e for e in web.errors)
            records.append(_raw(sid, f"{label}（联网搜索）", "web", Coverage.failed if failed else Coverage.not_found,
                                {"搜索词": web.queries}, note="搜索失败" if failed else
                                "搜了，没找到点名这家公司的页面；搜索覆盖有限，没搜到不等于没有"))
    return records


def _web_part(web: WebFindings, sid: str) -> list[RawRecord]:
    return [r for r in _web_records(web) if r.source_id == sid]


def _qcc(svc):
    """有企查查智能体平台才查财务、舆情（别的商业接口没这两项）。"""
    c = getattr(svc, "commercial", None)
    return c if c is not None and hasattr(c, "financials") else None


def _extras(name: str, svc, company: CompanyProfile | None, records: list[RawRecord]) -> "qcc_more.QccExtras | None":
    """企查查补充信息：只在企查查查到了这家公司时才查（名字对不上、虚构公司都不查）。实控人写进公司记录给核验用。"""
    qcc = _qcc(svc)
    if qcc is None or company is None or company.name != name and normalize(company.name) != normalize(name):
        return None
    extras = qcc_more.fetch(qcc, company.name)
    records.extend(qcc_more.records(extras))
    ctrl = extras.get("controller")
    if ctrl.coverage in ("found", "not_found"):
        company.controller = ctrl.rows
        if company.checked is not None and "controller" not in company.checked:
            company.checked.append("controller")
    return extras


def _cninfo_record(c: CninfoFindings) -> RawRecord:
    if c.coverage == "found":
        content = {"股票代码": c.code, "最新年度报告": c.annual.__dict__ if c.annual else None,
                   "最近一年公告总数": c.total, "看了标题的条数": c.scanned,
                   "标题带处罚、诉讼、问询等字样的": [n.__dict__ for n in c.risky]}
        return _raw("cninfo", "巨潮资讯网 · 公告", "official", Coverage.found, content,
                    url=c.annual.url if c.annual else "http://www.cninfo.com.cn", as_of=c.annual.date if c.annual else None,
                    note="证监会指定的上市公司信息披露网站；按标题关键词分类，标题不等于结论，点开原文看" +
                         ("；离线回放" if c.replay else ""))
    return _raw("cninfo", "巨潮资讯网 · 公告", "official",
                Coverage.failed if c.coverage == "failed" else Coverage(c.coverage), {"股票代码": c.code},
                url="http://www.cninfo.com.cn", note=c.error or "查了，巨潮没有这只股票")


def _finance_step(name: str, svc, records: list[RawRecord], *, is_demo: bool,
                  company: CompanyProfile | None = None) -> tuple[FinancialFindings | None, CninfoFindings | None]:
    qcc = _qcc(svc)
    if qcc is None or is_demo:
        progress.skip("finance", "没查：虚构的演示公司" if is_demo else "没查：没配企查查")
        return None, None
    progress.start("finance")
    cninfo = None
    code = str((company.listing or {}).get("股票代码") or "") if company is not None and company.listing else ""
    if code and getattr(svc, "cninfo", None) is not None:
        cninfo = svc.cninfo.find(code, date.today())
        records.append(_cninfo_record(cninfo))
    call = qcc.financials(name)
    found = fin.findings(call)
    who = (call.data or {}).get("企业名称")
    if found.coverage == "found" and who and normalize(who) != normalize(name):
        found = FinancialFindings("failed", retrieved_at=call.retrieved_at,
                                  error=f"返回的是\"{who}\"，和查询的公司对不上，没有采用")
    records.append(_finance_record(found))
    progress.done("finance", records)
    return found, cninfo


def _finance_record(f: FinancialFindings) -> RawRecord:
    note = "第三方商业数据，汇总自公司公开披露的定期报告；比率是平台算好的，照抄未重算；有出入以公司公告原文为准"
    if f.coverage == "found":
        content = {"报告期": [{"报告期": p.label, "营业总收入": fin.yi(p.revenue), "净利润": fin.yi(p.net_profit),
                              "总资产": fin.yi(p.total_assets), "营业收入同比": fin.pct(p.revenue_yoy, True),
                              "资产负债率": fin.pct(p.debt_ratio), "加权净资产收益率": fin.pct(p.roe)}
                             for p in f.periods[:8]],
                   "说明": f.summary}
        return _raw("qcc_finance", "财务数据（企查查）", "commercial", Coverage.found, content,
                    retrieved_at=f.retrieved_at, as_of=f.latest.label if f.latest else None, url=QCC_SITE, note=note)
    if f.coverage == "not_found":
        return _raw("qcc_finance", "财务数据（企查查）", "commercial", Coverage.not_found, {"说明": f.summary or None},
                    retrieved_at=f.retrieved_at, url=QCC_SITE,
                    note="查了，没有公开的财务数据。只有上市、发债等要公开披露的公司才有，没有不等于经营有问题")
    return _raw("qcc_finance", "财务数据（企查查）", "commercial", Coverage.failed, None, retrieved_at=f.retrieved_at,
                url=QCC_SITE, note=f"没查成：{f.error}")


def _news_record(n: NewsFindings) -> RawRecord:
    note = "第三方商业数据；\"负面/中立/正面\"是企查查的模型标的，不是我们的判断。只存负面新闻的标题，其余只记日期和来源"
    if n.coverage == "found":
        content = {"平台记录总数": n.total, "返回的最近几条": len(n.items), "倾向分布（返回的这几条）": n.counts(),
                   "负面新闻": [{"标题": i.title, "日期": i.date, "来源": i.source, "链接": i.url} for i in n.negatives]}
        return _raw("qcc_news", "新闻舆情（企查查）", "commercial", Coverage.found, content, retrieved_at=n.retrieved_at,
                    as_of=n.items[0].date if n.items else None, url=QCC_SITE, note=note)
    if n.coverage == "not_found":
        return _raw("qcc_news", "新闻舆情（企查查）", "commercial", Coverage.not_found, None, retrieved_at=n.retrieved_at,
                    url=QCC_SITE, note="查了，平台没有这家公司的新闻；没有不等于没人说过")
    return _raw("qcc_news", "新闻舆情（企查查）", "commercial", Coverage.failed, None, retrieved_at=n.retrieved_at,
                url=QCC_SITE, note=f"没查成：{n.error}")


def _network_steps(name: str, svc, records: list[RawRecord], *, is_demo: bool,
                   complaints: dict | None = None) -> tuple[WebFindings | None, NewsFindings | None]:
    """政府网站（联网搜索）→ 舆情（企查查新闻 + 联网搜投诉）。"""
    web_on = svc.web is not None and not is_demo
    why = "虚构的演示公司" if is_demo else "没配模型网关，或处于离线模式"
    official = None
    if web_on:
        progress.start("web")
        official = svc.web.find_official(name)
        records.extend(_web_part(official, "web_official"))
        progress.done("web", records)
    else:
        progress.skip("web", f"没联网搜：{why}")

    qcc = None if is_demo else _qcc(svc)
    if not web_on and qcc is None and not complaints:
        progress.skip("opinion", "没查：" + ("虚构的演示公司" if is_demo else "没配企查查，也没联网搜"))
        return None, None
    progress.start("opinion")
    news = None
    if qcc is not None:
        news = news_src.findings(qcc.news(name), name)
        records.append(_news_record(news))
    web = official
    if web_on:
        talk = svc.web.find_complaints(name)
        records.extend(_web_part(talk, "web_news"))
        media = svc.web.find_media(name)
        records.extend(_web_part(media, "web_media"))
        web = WebFindings(searched=True, official=official.official, news=talk.news, media=media.media,
                          queries=official.queries + talk.queries + media.queries,
                          errors=official.errors + talk.errors + media.errors,
                          replay=official.replay or talk.replay or media.replay)
    progress.done("opinion", records)
    return web, news


def collect(name: str, svc) -> Collected:
    collected = _collect(name, svc)
    store = getattr(svc, "reviews", None)
    if store is not None:
        progress.start("reviews")
        collected.reviews = store.all(name)
        if record := review_record(collected.reviews):
            collected.records.append(record)
        progress.done("reviews", collected.records, coverage=None if collected.reviews else Coverage.not_found)
    else:
        progress.skip("reviews", "评价功能没开")
    return collected


def _collect(name: str, svc) -> Collected:
    sources = dict(svc.sources)
    progress.start("lists")
    lic = svc.licenses.lookup(name)
    others, list_records = _official_lists(name, svc)
    records = [_license_record(lic, svc.licenses.meta), *list_records]
    progress.done("lists", records)
    pack: Pack | None = svc.packs.get(name)
    real_amac = _real_amac(name, svc)
    if real_amac:
        progress.done("amac", real_amac[1])
        amac, amac_records = real_amac
    else:
        progress.start("amac")
        if pack and "amac" in pack.sections:
            section = pack.sections["amac"]
            registered = bool(section.data.get("registered"))
            amac = AmacHit(coverage=Coverage.found if registered else Coverage.not_found, registered=registered)
            amac_records = [_raw("amac", section.title or "私募基金管理人公示", "collected", amac.coverage,
                                 section.data, retrieved_at=section.retrieved_at, as_of=section.source.as_of,
                                 url=section.source.url, note=section.source.note)]
        else:
            amac = svc.amac.lookup(name)
            amac_records = [_raw("amac", "私募基金管理人公示", "demo", amac.coverage,
                                 {"已登记": amac.registered} if amac.coverage is not Coverage.not_covered else None,
                                 as_of=svc.amac.as_of, note="演示数据" if amac.coverage is not Coverage.not_covered else
                                 "没查：中基协名单还没下载，也没有人工查询记录")]
        progress.done("amac", amac_records)

    progress.start("registry")  # 企查查要查好几秒，算在这一步里
    # 证据包里有人工采集的登记信息就用它；没有（只摘了几份文书）才查商业接口。
    # 虚构的演示公司（fixtures 里的）不查：商业接口查不到它，查了还会把登记来源换成商业数据，
    # 它就不再被当作演示公司，接着去查财务、新闻、政府网站，全是"没查成"
    fictional = svc.registry.get(name) is not None
    commercial = (svc.commercial.fetch(name) if svc.commercial and not fictional
                  and not (pack and "registry" in pack.sections) else None)
    if pack:
        return _from_pack(pack, lic, others, amac, amac_records, sources, records, svc, commercial)

    company, as_of, note = None, svc.registry.as_of, None
    if commercial is not None:
        company = _use_commercial(commercial, sources, records)
        if company:
            as_of = commercial.retrieved_at[:10]
    if company is None and (fixture := svc.registry.get(name)):
        company = fixture
        records += [_raw("registry", "企业登记信息", "demo", Coverage.found,
                         fixture.model_dump(exclude={*ANNUAL_FIELDS, "checked"}), as_of=as_of,
                         note="演示数据 · 公司为虚构"),
                    _raw("annual_report", "企业年度报告（摘要）", "demo", Coverage.found,
                         {k: getattr(fixture, k) for k in ANNUAL_FIELDS}, as_of=as_of,
                         note="演示数据 · 企业自行填报、未经审计")]
    elif company is None and commercial is None:
        records.append(_raw("registry", "企业登记信息", "demo", Coverage.not_covered,
                            note="没查：还没有这家公司的登记数据。真实公司要人工到国家企业信用信息公示系统查询，存进证据包，"
                                 "或者配置商业接口"))
    is_demo = company is not None and sources["registry"].kind == "demo"
    extras = None if is_demo or commercial is None else _extras(name, svc, company, records)
    progress.done("registry", records)
    finance, cninfo = _finance_step(name, svc, records, is_demo=is_demo, company=company)
    progress.skip("pack", "没有人工摘录的材料")

    records.extend(amac_records)

    complaints = svc.complaints.get(name)
    if complaints:
        records.append(_raw("complaints", "投诉平台", "demo", Coverage.found, complaints, as_of=svc.complaints.as_of,
                            note="演示数据"))
    elif svc.web is None or is_demo:  # 联网搜索开着时，投诉由搜索那条记录说
        records.append(_raw("complaints", "投诉平台", "demo", Coverage.not_covered,
                            note="没查：还没有这家公司的投诉数据，联网搜索也没开"))
    web, news = _network_steps(name, svc, records, is_demo=is_demo, complaints=complaints)
    return Collected(company=company, license=lic, amac=amac, complaints=complaints, as_of=date.fromisoformat(as_of),
                     sources=sources, records=records, others=others, note=note, web=web, finance=finance, news=news,
                     extras=extras, cninfo=cninfo)


def _use_commercial(commercial, sources: dict[str, Source], records: list[RawRecord]) -> CompanyProfile | None:
    """商业接口的结果：换掉登记、年报两个来源，记原始数据，返回公司记录（名称对不上或没查到是 None）。"""
    src = commercial.source
    sources["registry"] = src
    sources["annual_report"] = src.model_copy(update={"id": "annual_report"})
    records += commercial.records()
    return commercial.profile


def _from_pack(pack: Pack, lic: LicenseHit, others: list[RegistryHit], amac: AmacHit, amac_records: list[RawRecord], sources: dict[str, Source],
               records: list[RawRecord], svc, commercial=None) -> Collected:
    sec = pack.sections
    for sid, s in sec.items():
        sources[sid] = s.source
    company = None
    if commercial is not None:
        company = _use_commercial(commercial, sources, records)
    if "registry" in sec:
        data = dict(sec["registry"].data)
        if "annual_report" in sec:
            data |= {k: v for k, v in sec["annual_report"].data.items() if k in ANNUAL_FIELDS}
        # 证据包里没填的字段就是没查，不能当作"无"
        data["checked"] = [k for k in data if k != "checked"]
        company = CompanyProfile(**data)

    records.extend(amac_records)
    complaints = sec["complaints"].data if "complaints" in sec else None

    for sid in ("registry", "annual_report", "amac", "complaints"):
        if sid == "amac" or sid in ("registry", "annual_report") and commercial is not None:
            continue
        if sid in sec:
            s = sec[sid]
            records.append(_raw(sid, s.title or s.source.name, "collected", Coverage.found, s.data,
                                retrieved_at=s.retrieved_at, as_of=s.source.as_of, url=s.source.url,
                                screenshot=s.screenshot, note=s.source.note))
        else:
            sources[sid] = Source(id=sid, name=SECTIONS[sid], kind="collected", note="证据包里没有这一项")
            records.append(_raw(sid, SECTIONS[sid], "collected", Coverage.not_covered,
                                note="没查：证据包里没有这一项"))
    extras = _extras(pack.company, svc, company, records) if commercial is not None else None
    progress.done("registry", records)
    finance, cninfo = _finance_step(pack.company, svc, records, is_demo=False, company=company)
    for s in pack.self_description:
        records.append(_raw("self_description", s.title or "公司自己的公开说法", "web", Coverage.found, s.data,
                            retrieved_at=s.retrieved_at, url=s.source.url, screenshot=s.screenshot,
                            note="公司自己说的，只当作宣称"))
    for s in pack.extra:
        sources.setdefault(s.source.id, s.source)
        records.append(_raw(s.source.id, s.title or s.source.name, "collected", Coverage.found, s.data,
                            retrieved_at=s.retrieved_at, as_of=s.source.as_of, url=s.source.url,
                            screenshot=s.screenshot, note=s.source.note))
    progress.start("pack")
    progress.done("pack", records)
    as_of = date.fromisoformat((pack.as_of or now())[:10])
    web, news = _network_steps(pack.company, svc, records, is_demo=False, complaints=complaints)
    return Collected(company=company, license=lic, amac=amac, complaints=complaints, as_of=as_of,
                     sources=sources, records=records, others=others, note=pack.note, web=web, finance=finance, news=news,
                     extras=extras, cninfo=cninfo)
