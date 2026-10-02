"""联网查证：用假网关测过滤、分类、缓存回放，以及进报告后的样子。不连网。"""
import httpx

from app.analysis.pipeline import Services, new_case
from app.assistant import answer
from app.models import CaseIn, ChatIn, Status
from app.scenarios import keyword_intake
from app.sources.web import WebClient, short_name
from tests.helpers import svc
from tests.test_llm_assistant import FakeLLM

NAME = "杭州某某理财咨询有限公司"


def bocha(pages):
    return {"code": 200, "data": {"webPages": {"value": pages}}}


OFFICIAL = bocha([
    {"name": f"关于对{NAME}的行政处罚决定书", "url": "https://www.samr.gov.cn/x/1.html", "siteName": "市场监管总局",
     "summary": f"当事人：{NAME}。你公司发布虚假广告，罚款 3 万元。", "datePublished": "2026-05-12T08:00:00+08:00"},
    {"name": "关于防范非法集资的风险提示", "url": "https://www.zj.gov.cn/art/2.html", "siteName": "浙江省人民政府",
     "summary": f"近期{NAME}以高息为诱饵向社会公众吸收资金，涉嫌非法集资。", "datePublished": "2026-08-01"},
    {"name": "无关的通知", "url": "https://www.hangzhou.gov.cn/3.html", "siteName": "杭州市政府",
     "summary": "杭州某某科技有限公司中标公告", "datePublished": "2026-01-01"},
])
NEWS = bocha([
    {"name": "某某理财咨询 提现难 维权", "url": "https://tousu.example.com/1", "siteName": "投诉网",
     "summary": "杭州某某理财咨询到期不兑付，三个月取不出来", "datePublished": "2026-09-01"},
    {"name": "某某理财咨询起诉逾期借款人", "url": "https://news.example.com/2", "siteName": "某新闻",
     "summary": "杭州某某理财咨询起诉逾期借款人", "datePublished": "2026-09-02"},
    {"name": "企业信息", "url": "https://www.tianyancha.com/company/1", "siteName": "天眼查",
     "summary": f"{NAME} 注册资本 1000 万，提现难", "datePublished": None},
])


def client(tmp_path, ok=True, mode="live"):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if not ok:
            return httpx.Response(503)
        body = request.read().decode()
        return httpx.Response(200, json=OFFICIAL if "include" in body else NEWS)

    c = WebClient(base_url="https://gw.example.com/gateway/v1", api_key="k", mode=mode, cache_dir=tmp_path,
                  transport=httpx.MockTransport(handler))
    return c, seen


def test_short_name():
    assert short_name("杭州银行股份有限公司") == "杭州银行"
    assert short_name("某某有限公司") is None


def test_filters_classifies_and_skips_aggregators(tmp_path):
    c, seen = client(tmp_path)
    web = c.findings(NAME)
    assert [h.category for h in web.official] == ["penalty", "warning"]     # 无关通知没有全称，被丢掉
    assert all(h.official for h in web.official)
    assert [h.category for h in web.news] == ["cash", "other"]               # "逾期"不算兑付问题
    assert all("tianyancha" not in h.url for h in web.news)
    assert web.news[0].by_short_name and "only" not in web.news[0].excerpt
    assert c.root == "https://gw.example.com/gateway" and len(seen) == 2


def test_replay_when_gateway_down(tmp_path):
    c, _ = client(tmp_path)
    c.findings(NAME)
    down, _ = client(tmp_path, ok=False)
    web = down.findings(NAME)
    assert web.replay and len(web.official) == 2 and not web.errors
    fresh, _ = client(tmp_path / "empty", ok=False)
    failed = fresh.findings(NAME)
    assert len(failed.errors) == 2 and not failed.official


def test_off_mode_is_not_configured(tmp_path):
    assert not WebClient(base_url="https://x/v1", api_key="k", mode="off", cache_dir=tmp_path).configured


def services(web):
    return Services(svc.licenses, svc.registry, svc.amac, svc.complaints, svc.packs, svc.extractor, svc.sources,
                    svc.registries, None, web)


def test_web_findings_flow_into_signals_raw_and_questions(tmp_path):
    c, _ = client(tmp_path)
    case = new_case(CaseIn(company_name=NAME, need="我妈想存钱理财"), keyword_intake("我妈想存钱理财"), services(c))
    v = case.versions[0]
    items = {f"{s.key}.{i.key}": i for s in v.signals for i in s.items}
    raw = {r.id: r for r in case.raw}
    official = items["credit.official_web"]
    assert official.status is Status.bad and "2 份文件" in official.value
    assert raw[official.ref].kind == "official" and raw[official.ref].url.startswith("https://www.samr.gov.cn")
    warning = items["risk.regulator_warning"]
    assert warning.status is Status.bad and raw[warning.ref].as_of == "2026-08-01"
    assert items["reputation.web_cash"].status is Status.warn
    assert "可能是同名" in raw[items["reputation.web_cash"].ref].note
    assert any("点名你们的文件" in q.ask for q in v.questions)
    assert any("搜不到不等于没有" in n for n in v.notes)


def test_fictional_demo_company_is_not_searched(tmp_path):
    c, seen = client(tmp_path)
    new_case(CaseIn(company_name="杭州满盈禾康养健康咨询有限公司", need=""), keyword_intake(""), services(c))
    assert seen == []


def test_assistant_verdict_words_then_gateway_down_falls_back_to_template(tmp_path):
    c, _ = client(tmp_path)
    case = new_case(CaseIn(company_name=NAME, need="我妈想存钱理财"), keyword_intake("我妈想存钱理财"), services(c))
    fake = FakeLLM(['{"answer": "它相对安全，可以买 [credit.official_web]", "citations": ["credit.official_web"]}'],
                   tmp_path / "llm")
    msg = answer(case, ChatIn(text="它被处罚过吗"), fake)   # 第一次越界，要它重写时网关断了，才退回模板
    assert msg.mode == "template" and "相对安全" not in msg.text and "credit.official_web" in msg.citations
    assert msg.rewrites == 1 and msg.blocked == ["相对安全"]


def test_assistant_may_relay_characterization_written_in_official_records(tmp_path):
    c, _ = client(tmp_path)
    case = new_case(CaseIn(company_name=NAME, need="我妈想存钱理财"), keyword_intake("我妈想存钱理财"), services(c))
    fake = FakeLLM(['{"answer": "浙江省政府的风险提示点名它涉嫌非法集资 [risk.regulator_warning]"}'], tmp_path / "llm")
    msg = answer(case, ChatIn(text="政府说过它什么"), fake)
    assert msg.mode == "model" and msg.rewrites == 0 and not msg.blocked


def test_doc_date_subject_and_personal_info():
    from app.sources.web import doc_date, is_subject, redact
    assert doc_date("索引号…发文日期1648688353000名称") == "2022-03-31"     # 搜索引擎给的是收录日期，以页面为准
    assert doc_date("发布日期：2024年9月13日") == "2024-09-13" and doc_date("无日期") is None
    name = "杭州某某财富管理有限公司"
    assert is_subject(f"关于对{name}采取出具警示函措施的决定", "", name)
    assert is_subject("行政处罚决定书[2024]35号(某某财富、王某)", f"当事人:{name}(以下简称某某财富)", name)
    assert not is_subject("关于对杭州某某资产管理有限公司采取出具警示函措施的决定", f"三、公司员工在{name}兼职。", name)
    assert redact("王某,男,1978年8月出生,法定代表人,住址:浙江省杭州市西湖区。") == "王某,（出生信息略）,法定代表人,住址：略。"


def test_documents_that_only_mention_it_are_not_counted_as_naming_it():
    from app.analysis.signals import official_web_item
    from app.sources.web import WebFindings, WebHit
    web = WebFindings(searched=True, official=[
        WebHit("penalty", "行政处罚 / 监管措施", True, "关于对它的决定", "https://a.gov.cn/1", "a", "2023-12-05", "", subject=True),
        WebHit("penalty", "行政处罚 / 监管措施", True, "关于对别家的决定", "https://a.gov.cn/2", "a", "2022-03-31", "", subject=False)])
    item = official_web_item(web, {})
    assert item.value.startswith("1 份文件点名了它") and "另有 1 份文件在正文里提到它" in item.detail
    only = official_web_item(WebFindings(searched=True, official=web.official[1:]), {})
    assert only.status is Status.warn and "它不是当事人" in only.value
