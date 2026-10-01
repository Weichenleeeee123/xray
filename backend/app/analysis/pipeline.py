from collections import Counter
from dataclasses import dataclass
from datetime import date

from app.analysis.extract import ClaimExtractor, RuleExtractor
from app.analysis.signals import build_signals
from app.analysis.verify import verify
from app.models import CaseIn, CaseOut, Source
from app.sources.catalog import build_sources
from app.sources.fixtures import FixtureAmac, FixtureComplaints, FixtureRegistry
from app.sources.licenses import LicenseIndex


@dataclass
class Services:
    licenses: LicenseIndex
    registry: FixtureRegistry
    amac: FixtureAmac
    complaints: FixtureComplaints
    extractor: ClaimExtractor
    sources: dict[str, Source]


def load_services() -> Services:
    licenses, registry = LicenseIndex.load(), FixtureRegistry.load()
    amac, complaints = FixtureAmac.load(), FixtureComplaints.load()
    sources = build_sources(licenses.meta, registry.as_of, amac.as_of, complaints.as_of)
    return Services(licenses, registry, amac, complaints, RuleExtractor(), sources)


def analyze(case: CaseIn, svc: Services, case_id: str) -> CaseOut:
    text = case.flyer_text or ""
    ext = svc.extractor.extract(text)
    company = svc.registry.get(case.company_name)
    lic = svc.licenses.lookup(case.company_name)
    amac = svc.amac.lookup(case.company_name)

    assertions, missing = verify(ext, company, lic, amac, svc.licenses)
    signals = build_signals(ext, company, lic, amac, svc.complaints.get(case.company_name),
                            date.fromisoformat(svc.registry.as_of))

    colors = Counter(a.color for a in assertions)
    tally = {c: colors.get(c, 0) for c in ("red", "amber", "grey", "green")} | {"missing": len(missing)}

    notes = []
    if company is None:
        notes.append("演示版没有这家公司的登记数据：股东、资本、处罚等核验会显示为\"没查\"。持牌名单是真实数据，照常核验。")
    if not text.strip():
        notes.append("没有提供宣传材料，只做了企业记录检查。")
    elif not ext.claims:
        notes.append("材料里没有识别到需要核验的说法。")

    return CaseOut(id=case_id, version="v1", case=case, company=company, license=lic, amac=amac,
                   assertions=assertions, missing=missing, signals=signals, tally=tally, notes=notes,
                   sources=svc.sources)
