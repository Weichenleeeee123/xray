"""不知道的条目要说清为什么不知道："没查成"（查询出错、额度用完）和"没查"、"待补材料"、"不适用"分开。
企查查全部用本地假响应，不连网、不扣积分。"""
import json
from datetime import datetime, timedelta

import httpx

from app.analysis.pipeline import Services, new_case
from app.models import CaseIn, Status
from app.scenarios import keyword_intake
from app.sources.qcc_agent import QccAgentClient
from tests.helpers import DEMO_COMPANY, make_case, svc
from tests.test_qcc_agent import NAME, TOOLS, client, make, server

NEED = "我妈想存 20 万理财"


def items(case):
    return {f"{s.key}.{i.key}": i for s in case.versions[-1].signals for i in s.items}


def unexplained(case):
    return [k for k, i in items(case).items() if i.status is Status.none and i.gap is None]


def with_client(c, name=NAME):
    services = Services(svc.licenses, svc.registry, svc.amac, svc.complaints, svc.packs, svc.extractor,
                        svc.sources, svc.registries, c)
    return new_case(CaseIn(company_name=name, need=NEED), keyword_intake(NEED), services)


def test_registry_failure_is_failed_with_its_reason_not_unchecked(tmp_path):
    case = with_client(client(tmp_path, max_points=0))
    got = items(case)
    for key in ("finance.registry", "credit.registry", "risk.scope"):
        assert got[key].gap == "failed" and got[key].value == "没查成", key
        assert "额度用完" in got[key].detail, key
    assert any("没查成" in n for n in case.versions[-1].notes)
    assert not unexplained(case)


def test_short_name_says_the_name_did_not_match(tmp_path):
    case = with_client(client(tmp_path), name="杭州测试")
    reg = items(case)["finance.registry"]
    assert reg.gap == "not_found" and reg.value == "名字对不上" and "全称" in reg.detail


def test_every_unknown_item_says_why():
    assert not unexplained(make_case(DEMO_COMPANY))


def test_every_unknown_item_says_why_with_commercial_data(tmp_path):
    assert not unexplained(make(tmp_path, "公司获得国内大型综合金融集团的认可并注资。"))


def test_fictional_company_is_not_searched_on_purpose():
    web = items(make_case(DEMO_COMPANY))["credit.official_web"]
    assert web.gap == "not_applicable" and web.value == "不适用" and "虚构" in web.detail


def test_product_code_waits_for_material_instead_of_unchecked():
    code = items(make_case(DEMO_COMPANY))["risk.product_code"]
    assert code.gap == "needs_input" and "补充材料" in code.value


def test_fictional_company_never_queries_commercial_data(tmp_path):
    seen = []
    case = with_client(QccAgentClient("Bearer K", cache_dir=tmp_path, transport=server(TOOLS, seen)), name=DEMO_COMPANY)
    got = items(case)
    assert not seen and case.sources["registry"].kind == "demo"
    assert not [k for k, i in got.items() if i.gap == "failed"]
    assert got["credit.official_web"].gap == "not_applicable"


def test_saved_response_backs_up_a_failed_live_query(tmp_path):
    client(tmp_path).call("company", "get_company_registration_info", NAME)
    path = next(tmp_path.glob("*.json"))
    saved = json.loads(path.read_text(encoding="utf-8"))
    saved["retrieved_at"] = (datetime.now() - timedelta(days=3)).isoformat(timespec="seconds")
    path.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")

    def offline(request):
        raise httpx.ConnectError("断网")
    c = QccAgentClient("Bearer K", cache_dir=tmp_path, transport=httpx.MockTransport(offline))
    got = c.call("company", "get_company_registration_info", NAME)
    assert got.data and got.data["企业名称"] == NAME and got.error is None and "ConnectError" in got.stale
    capped = QccAgentClient("Bearer K", cache_dir=tmp_path, transport=httpx.MockTransport(offline), max_points=0)
    assert capped.call("company", "get_company_registration_info", NAME).stale.startswith("服务进程已花")


def test_a_network_blip_is_retried_once(tmp_path):
    seen, ok = [], server(TOOLS, [])
    def flaky(request):
        seen.append(1)
        if len(seen) == 1:
            raise httpx.ConnectTimeout("抖了一下")
        return ok.handle_request(request)
    c = QccAgentClient("Bearer K", cache_dir=tmp_path, transport=httpx.MockTransport(flaky))
    got = c.call("company", "get_company_registration_info", NAME)
    assert got.error is None and got.data["企业名称"] == NAME and len(seen) == 2
