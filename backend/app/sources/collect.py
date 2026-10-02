"""汇集数据：查一家公司时把各个来源查一遍，每个来源写一条原始记录（RawRecord）。

官方名单（真实，每家公司都查）：银行业、保险、期货、支付机构名单，中基协私募管理人名单。
企业登记按顺序找：证据包（人工采集的官方记录）→ 商业接口（企查查/天眼查，配置了才用）→ 演示数据 → 记"没查"。
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from app.models import AmacHit, CompanyProfile, Coverage, LicenseHit, RawRecord, RegistryHit, Source
from app.sources.amac_detail import summary as amac_summary
from app.sources.packs import SECTIONS, Pack
from app.sources.registries import AMAC_ID, LICENSE_LISTS
from app.sources.web import WebFindings

ANNUAL_FIELDS = ("paid_capital", "insured")


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
                                  (web.news, "web_news", "公开报道和投诉", "报道")):
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


def collect(name: str, svc) -> Collected:
    sources = dict(svc.sources)
    lic = svc.licenses.lookup(name)
    others, list_records = _official_lists(name, svc)
    records = [_license_record(lic, svc.licenses.meta), *list_records]
    real_amac = _real_amac(name, svc)

    pack: Pack | None = svc.packs.get(name)
    if pack:
        return _from_pack(pack, lic, others, real_amac, sources, records, svc)

    company, as_of, note = None, svc.registry.as_of, None
    commercial = svc.commercial.fetch(name) if svc.commercial else None
    if commercial is not None:
        company = commercial.profile
        src = commercial.source
        sources["registry"] = src
        sources["annual_report"] = src.model_copy(update={"id": "annual_report"})
        records.append(_raw("registry", src.name, "commercial",
                            Coverage.found if company else (Coverage.failed if not commercial.response
                                                            else Coverage.not_found),
                            commercial.record or commercial.response or None, retrieved_at=commercial.retrieved_at,
                            as_of=commercial.retrieved_at[:10], url=src.url, note=commercial.note))
        if company:
            as_of = commercial.retrieved_at[:10]
            records.append(_raw("annual_report", "实缴资本、参保人数（商业接口）", "commercial", Coverage.found,
                                {k: getattr(company, k) for k in ANNUAL_FIELDS}, retrieved_at=commercial.retrieved_at,
                                url=src.url, note="来自同一次商业接口查询"))
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

    if real_amac:
        amac, amac_records = real_amac
        records += amac_records
    else:
        amac = svc.amac.lookup(name)
        amac_record = _raw("amac", "私募基金管理人公示", "demo", amac.coverage,
                           {"已登记": amac.registered} if amac.coverage is not Coverage.not_covered else None,
                           as_of=svc.amac.as_of, note="演示数据" if amac.coverage is not Coverage.not_covered else
                           "没查：中基协名单还没下载，也没有人工查询记录")
        records.append(amac_record)

    complaints = svc.complaints.get(name)
    if complaints:
        records.append(_raw("complaints", "投诉平台", "demo", Coverage.found, complaints, as_of=svc.complaints.as_of,
                            note="演示数据"))
    web = None
    is_demo = company is not None and sources["registry"].kind == "demo"
    if svc.web and not is_demo:  # 虚构公司不联网搜，搜了也是空的
        web = svc.web.findings(name)
        records += _web_records(web)
    elif not complaints:
        records.append(_raw("complaints", "投诉平台", "demo", Coverage.not_covered,
                            note="没查：还没有这家公司的投诉数据，联网搜索也没开"))
    return Collected(company=company, license=lic, amac=amac, complaints=complaints, as_of=date.fromisoformat(as_of),
                     sources=sources, records=records, others=others, note=note, web=web)


def _from_pack(pack: Pack, lic: LicenseHit, others: list[RegistryHit], real_amac, sources: dict[str, Source],
               records: list[RawRecord], svc) -> Collected:
    sec = pack.sections
    for sid, s in sec.items():
        sources[sid] = s.source
    company = None
    if "registry" in sec:
        data = dict(sec["registry"].data)
        if "annual_report" in sec:
            data |= {k: v for k, v in sec["annual_report"].data.items() if k in ANNUAL_FIELDS}
        # 证据包里没填的字段就是没查，不能当作"无"
        data["checked"] = [k for k in data if k != "checked"]
        company = CompanyProfile(**data)

    # 中基协的官方名单和详情页优先；证据包里人工填的私募登记，只在没有官方数据时才用
    if real_amac:
        amac, amac_records = real_amac
        records += amac_records
    elif "amac" in sec:
        registered = bool(sec["amac"].data.get("registered"))
        amac = AmacHit(coverage=Coverage.found if registered else Coverage.not_found, registered=registered)
    else:
        amac = AmacHit(coverage=Coverage.not_covered)
    complaints = sec["complaints"].data if "complaints" in sec else None

    for sid in ("registry", "annual_report", "amac", "complaints"):
        if sid == "amac" and real_amac:
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
    for s in pack.self_description:
        records.append(_raw("self_description", s.title or "公司自己的公开说法", "web", Coverage.found, s.data,
                            retrieved_at=s.retrieved_at, url=s.source.url, screenshot=s.screenshot,
                            note="公司自己说的，只当作宣称"))
    for s in pack.extra:
        sources.setdefault(s.source.id, s.source)
        records.append(_raw(s.source.id, s.title or s.source.name, "collected", Coverage.found, s.data,
                            retrieved_at=s.retrieved_at, as_of=s.source.as_of, url=s.source.url,
                            screenshot=s.screenshot, note=s.source.note))
    as_of = date.fromisoformat((pack.as_of or now())[:10])
    web = svc.web.findings(pack.company) if svc.web else None
    if web:
        records += _web_records(web)
    return Collected(company=company, license=lic, amac=amac, complaints=complaints, as_of=as_of,
                     sources=sources, records=records, others=others, note=pack.note, web=web)
