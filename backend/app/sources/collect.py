"""汇集数据：查一家公司时把各个来源查一遍，每个来源写一条原始记录（RawRecord）。

顺序：先找证据包（人工采集的真实记录），再找 fixtures（虚构演示数据），都没有就记"没查"。
持牌名单是真实数据，每家公司都查。
"""
from dataclasses import dataclass, field
from datetime import date, datetime

from app.models import AmacHit, CompanyProfile, Coverage, LicenseHit, RawRecord, Source
from app.sources.packs import SECTIONS, Pack

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
    note: str | None = None              # 证据包的说明：资料截止日期、话术出处


def _raw(source_id: str, title: str, kind: str, coverage: Coverage, content=None, *, retrieved_at: str | None = None,
         as_of: str | None = None, url: str | None = None, screenshot: str | None = None,
         note: str | None = None) -> RawRecord:
    return RawRecord(id="", source_id=source_id, title=title, kind=kind, coverage=coverage,
                     retrieved_at=retrieved_at or now(), as_of=as_of, url=url, content=content,
                     screenshot=screenshot, note=note)


def _license_record(lic: LicenseHit, meta: dict) -> RawRecord:
    content = {"查询名称": lic.query, "是否收录": lic.found,
               "记录": lic.record.model_dump() if lic.record else None,
               "名称相近的机构": [s.name for s in lic.suggestions[:3]]}
    return _raw("nfra_bank_list", "银行业金融机构法人名单 · 按名称查询", "official",
                Coverage.found if lic.found else Coverage.not_found, content, as_of=meta["as_of"], url=meta["url"],
                note="只含银行业金融机构；查不到不等于没有证券、保险、私募等其他牌照")


def collect(name: str, svc) -> Collected:
    pack: Pack | None = svc.packs.get(name)
    sources = dict(svc.sources)
    lic = svc.licenses.lookup(name)
    records = [_license_record(lic, svc.licenses.meta)]

    if pack:
        return _from_pack(name, pack, lic, sources, records, svc)

    company = svc.registry.get(name)
    amac = svc.amac.lookup(name)
    complaints = svc.complaints.get(name)
    as_of = svc.registry.as_of
    if company:
        reg = company.model_dump(exclude=set(ANNUAL_FIELDS))
        annual = {k: getattr(company, k) for k in ANNUAL_FIELDS}
        records += [_raw("registry", "企业登记信息", "demo", Coverage.found, reg, as_of=as_of,
                         note="演示数据 · 公司为虚构"),
                    _raw("annual_report", "企业年度报告（摘要）", "demo", Coverage.found, annual, as_of=as_of,
                         note="演示数据 · 企业自行填报、未经审计")]
    else:
        records.append(_raw("registry", "企业登记信息", "demo", Coverage.not_covered,
                            note="没查：还没有这家公司的登记数据。真实公司要人工到国家企业信用信息公示系统查询，存进证据包"))
    records.append(_raw("amac", "私募基金管理人公示", "demo", amac.coverage,
                        {"已登记": amac.registered} if amac.coverage is not Coverage.not_covered else None,
                        as_of=svc.amac.as_of, note="演示数据" if amac.coverage is not Coverage.not_covered else
                        "没查：中基协实时查询还没接入，也没有人工查询记录"))
    records.append(_raw("complaints", "投诉平台", "demo", Coverage.found if complaints else Coverage.not_covered,
                        complaints, as_of=svc.complaints.as_of,
                        note="演示数据" if complaints else "没查：还没有这家公司的投诉数据"))
    return Collected(company=company, license=lic, amac=amac, complaints=complaints,
                     as_of=date.fromisoformat(as_of), sources=sources, records=records)


def _from_pack(name: str, pack: Pack, lic: LicenseHit, sources: dict[str, Source], records: list[RawRecord],
               svc) -> Collected:
    sec = pack.sections
    for sid, s in sec.items():
        sources[sid] = s.source
    company = None
    if "registry" in sec:
        data = dict(sec["registry"].data)
        if "annual_report" in sec:
            data |= {k: v for k, v in sec["annual_report"].data.items() if k in ANNUAL_FIELDS}
        company = CompanyProfile(**data)

    amac = AmacHit(coverage=Coverage.not_covered)
    if "amac" in sec:
        registered = bool(sec["amac"].data.get("registered"))
        amac = AmacHit(coverage=Coverage.found if registered else Coverage.not_found, registered=registered)
    complaints = sec["complaints"].data if "complaints" in sec else None

    for sid in ("registry", "annual_report", "amac", "complaints"):
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
    return Collected(company=company, license=lic, amac=amac, complaints=complaints, as_of=as_of,
                     sources=sources, records=records, note=pack.note)
