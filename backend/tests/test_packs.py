"""证据包：人工采集的真实记录优先于演示数据，来源类型是 collected，原始数据带截图和采集时间。"""
from app.analysis.pipeline import Services, new_case
from app.models import CaseIn
from app.scenarios import keyword_intake
from app.sources.packs import EvidencePacks
from tests.helpers import svc

PACK = {
    "company": "测试真实有限公司",
    "aliases": ["测试真实"],
    "collected_by": "测试",
    "as_of": "2026-10-02",
    "note": "资料截至 2026-10-02；话术出自某报道",
    "registry": {"source": {"url": "https://www.gsxt.gov.cn", "retrieved_at": "2026-10-02T10:00:00",
                            "screenshot": "shots/reg.png"},
                 "data": {"name": "测试真实有限公司", "status": "存续", "founded": "2018-03-01", "reg_capital": 10000000,
                          "scope": "投资咨询；企业管理", "shareholders": [{"name": "某甲", "type": "自然人", "pct": 100}]}},
    "annual_report": {"source": {"retrieved_at": "2026-10-02T10:05:00"}, "data": {"paid_capital": 0, "insured": 3}},
    "self_description": [{"source": {"url": "https://example.com", "retrieved_at": "2026-10-02T11:00:00"},
                          "title": "官网首页", "text": "国资背景 · 年化 12% · 保本保息"}],
}


def services_with(pack: dict) -> Services:
    return Services(svc.licenses, svc.registry, svc.amac, svc.complaints, EvidencePacks([pack]), svc.extractor,
                    svc.sources)


def test_pack_feeds_registry_claims_and_raw_records():
    s = services_with(PACK)
    case = new_case(CaseIn(company_name="测试真实", need="我妈想存钱理财"), keyword_intake("我妈想存钱理财"), s)
    v = case.versions[0]
    assert case.sources["registry"].kind == "collected" and case.sources["registry"].url == "https://www.gsxt.gov.cn"
    assert v.company.paid_capital == 0 and v.company.insured == 3
    reg = next(r for r in case.raw if r.source_id == "registry")
    assert reg.kind == "collected" and reg.screenshot == "shots/reg.png" and reg.retrieved_at.startswith("2026-10-02")
    # 没给 amac、投诉：记"没查"，不当作没问题
    assert next(r for r in case.raw if r.source_id == "amac").coverage == "not_covered"
    # 公司自己的说法也能拿来对照：只输入名字就有"宣称 vs 记录"
    ids = {a.id: a.verdict.value for a in v.assertions}
    assert ids["A4"] == "mismatch" and ids["A2"] == "redline"
    selfdesc = next(r for r in case.raw if r.source_id == "self_description")
    assert selfdesc.id in next(a for a in v.assertions if a.id == "A4").refs
    assert "资料截至 2026-10-02；话术出自某报道" in v.notes
    assert not any("虚构" in n for n in v.notes)


def test_template_pack_is_skipped():
    assert "（公司全称）" not in EvidencePacks.load().names()
