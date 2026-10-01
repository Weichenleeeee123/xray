"""官方名单（真实数据）和商业接口（用假网关，不花钱）。"""
import csv
import hashlib
import json

import httpx
import pytest

from app.analysis.pipeline import Services, new_case
from app.models import CaseIn, Coverage, Status, Verdict
from app.scenarios import keyword_intake
from app.sources.commercial import CommercialClient, parse_money, to_profile
from app.sources.registries import REGISTRY_DIR
from tests.helpers import DEMO_COMPANY, flyer, make_case, svc


def a1(case):
    return next(a for a in case.versions[0].assertions if a.id == "A1")


def amac_row(pred):
    with open(REGISTRY_DIR / "amac_managers.csv", encoding="utf-8-sig") as f:
        return next(r for r in csv.DictReader(f) if pred(r))


def test_official_lists_loaded_with_official_counts():
    counts = {rid: idx.meta["count"] for rid, idx in svc.registries.items()}
    assert counts["nfra_insurance"] == 238 and counts["csrc_futures"] == 150
    assert counts["pbc_payment"] >= 150 and counts["amac_managers"] >= 18000
    assert svc.sources["amac"].kind == "official" and svc.sources["nfra_insurance"].kind == "official"


def test_every_list_lookup_is_a_raw_record():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    by_source = {r.source_id: r for r in case.raw}
    for sid in ("nfra_bank_list", "nfra_insurance", "csrc_futures", "pbc_payment", "amac"):
        assert by_source[sid].kind == "official" and by_source[sid].coverage is Coverage.not_found
    a = a1(case)
    assert a.verdict is Verdict.mismatch and "4 份持牌名单" in a.plain
    assert "18,396" in a.checks[1].result


def test_insurer_is_licensed_and_needs_no_private_fund_registration():
    a = a1(make_case("中国人民财产保险股份有限公司", "正规理财，安全稳健"))
    assert a.verdict is Verdict.consistent
    assert a.checks[0].source == "nfra_insurance" and a.checks[1].status is Status.ok


def test_payment_license_is_not_a_license_to_sell_wealth_products():
    a = a1(make_case("支付宝支付科技有限公司", "正规理财，年化 4%"))
    assert a.verdict is Verdict.attention and "不能卖理财" in a.plain
    assert a.checks[0].source == "pbc_payment"


def test_private_fund_manager_with_and_without_credit_tips():
    clean = amac_row(lambda r: r["credit_tips"] == "0" and r["special_tips"] == "0")
    a = a1(make_case(clean["name"], "正规理财"))
    assert a.verdict is Verdict.attention and a.checks[1].status is Status.ok and clean["register_no"] in a.checks[1].result
    assert a.checks[0].status is Status.warn
    flagged = amac_row(lambda r: r["credit_tips"] == "1")
    a = a1(make_case(flagged["name"], "正规理财"))
    assert a.checks[1].status is Status.warn and "诚信信息" in a.plain


def test_securities_like_name_is_not_judged_without_securities_list():
    assert a1(make_case("某某证券股份有限公司", "正规理财")).verdict is Verdict.unverifiable


# ---------- 商业接口 ----------

QCC_OK = {"Status": "200", "Message": "查询成功",
          "Result": {"Name": "杭州测试科技有限公司", "CreditCode": "91330100TEST000001", "Status": "存续",
                     "StartDate": "2019-05-20 00:00:00", "RegistCapi": "1000万元人民币", "RecCap": "50万元人民币",
                     "Scope": "技术开发；投资咨询", "OperName": "某甲"}}


def fake(responses: list, seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        body = responses.pop(0)
        return body if isinstance(body, httpx.Response) else httpx.Response(200, json=body)
    return httpx.MockTransport(handler)


def qcc(tmp_path, responses, seen, **kw):
    return CommercialClient("qcc", qcc_key="K", qcc_secret="S", cache_dir=tmp_path, transport=fake(responses, seen), **kw)


def test_parse_money_and_profile_mapping():
    assert parse_money("5000万元人民币") == 5e7 and parse_money("1.2亿") == 1.2e8 and parse_money("") is None
    p = to_profile("qcc", QCC_OK["Result"])
    assert p.reg_capital == 1e7 and p.paid_capital == 5e5 and p.founded == "2019-05-20"
    assert not p.known("penalties") and p.known("paid_capital")
    t = to_profile("tianyancha", {"name": "X公司", "regStatus": "存续", "estiblishTime": 1558281600000,
                                  "regCapital": "1000万人民币", "actualCapital": "", "businessScope": "", "socialStaffNum": 12})
    assert t.founded == "2019-05-20" and t.insured == 12 and t.paid_capital is None


def test_qcc_signs_request_caches_and_respects_budget(tmp_path):
    seen = []
    client = qcc(tmp_path, [QCC_OK, QCC_OK], seen, max_calls=1)
    r = client.fetch("杭州测试科技有限公司")
    ts = seen[0].headers["Timespan"]
    assert seen[0].headers["Token"] == hashlib.md5(("K" + ts + "S").encode()).hexdigest().upper()
    assert r.profile and not r.cached
    again = client.fetch("杭州测试科技有限公司")
    assert again.cached and len(seen) == 1                 # 缓存命中，不重复计费
    over = client.fetch("另一家有限公司")
    assert over.profile is None and "上限" in over.note and len(seen) == 1


def test_name_mismatch_is_not_adopted(tmp_path):
    r = qcc(tmp_path, [QCC_OK], []).fetch("杭州测试")
    assert r.profile is None and "对不上" in r.note and r.record["Name"] == "杭州测试科技有限公司"


def test_failure_and_no_result(tmp_path):
    r = qcc(tmp_path, [httpx.Response(500)], []).fetch("某公司")
    assert r.profile is None and "失败" in r.note
    r = qcc(tmp_path / "b", [{"Status": "201", "Message": "查询无结果"}], []).fetch("某公司")
    assert r.profile is None and "没有这家公司" in r.note


def test_commercial_profile_flows_into_report_and_unknown_fields_stay_unchecked(tmp_path):
    services = Services(svc.licenses, svc.registry, svc.amac, svc.complaints, svc.packs, svc.extractor, svc.sources,
                        svc.registries, qcc(tmp_path, [QCC_OK], []))
    case = new_case(CaseIn(company_name="杭州测试科技有限公司", need="我妈想存钱理财", material_text="注册资本 1000 万"),
                    keyword_intake("我妈想存钱理财"), services)
    v = case.versions[0]
    assert case.sources["registry"].kind == "commercial"
    reg = next(r for r in case.raw if r.source_id == "registry")
    assert reg.kind == "commercial" and reg.content["CreditCode"] == "91330100TEST000001"
    assert any("商业数据" in n for n in v.notes)
    items = {f"{s.key}.{i.key}": i for s in v.signals for i in s.items}
    assert items["finance.paid_capital"].value == "¥50 万"
    assert items["credit.penalties"].status is Status.none and items["finance.pledges"].value == "没查"
    assert next(a for a in v.assertions if a.id == "A5").verdict is Verdict.misleading  # 认缴 1000 万，实缴 50 万
