"""企查查补充信息、巨潮公告、权威媒体：个人名字不进案卷；只有几种情况标"要留意"；没有一项标"有问题"。"""
import json
from dataclasses import replace
from datetime import date

import httpx

from app.analysis import signals as sig
from app.analysis.pipeline import new_case
from app.analysis.verify import background_review
from app.models import CaseIn, CompanyProfile, Status, Verdict
from app.scenarios import keyword_intake
from app.sources import qcc_more
from app.sources.cninfo import CninfoClient
from app.sources.qcc_agent import Call
from app.sources.web import redact, scrub_title
from tests.helpers import svc

NAME = "杭州远山财富管理有限公司"
WHEN = "2026-10-02T20:00:00+08:00"
TODAY = date(2026, 10, 2)

DATA = {
    "get_actual_controller": {"企业名称": NAME, "实际控制人信息": [
        {"实际控制人名称": "张小明", "总持股比例": "36.89%", "表决权比例": "68.49%"}]},
    "get_administrative_license": {"企业名称": NAME, "摘要": "该主体累计共有1条记录。", "行政许可信息": [
        {"决定文书/许可证名称": "营业执照", "许可机关": "某区市场监督管理局", "许可状态": "有效"}]},
    "get_qualifications": {"企业名称": NAME, "搜索结果": "已全量扫描该主体资质证书数据库，未发现任何记录。"},
    "get_change_records": {"企业名称": NAME, "摘要": "该主体累计共有3条记录。", "变更记录信息": [
        {"变更日期": "2026-05-01", "变更项目": "名称变更", "变更前内容": ["杭州远山投资有限公司"],
         "变更后内容": [NAME]},
        {"变更日期": "2026-04-01", "变更项目": "注册资本变更", "变更前内容": ["法定代表人（负责人）: 张小明", "1000万"],
         "变更后内容": ["500万"]},
        {"变更日期": "2019-01-18", "变更项目": "投资人变更", "变更前内容": ["王大力", "某某合伙企业"], "变更后内容": []}]},
    "get_hearing_notice": {"企业名称": NAME, "摘要": "该主体累计共有2条记录。", "开庭公告信息": [
        {"案号": "（2026）浙0106民初1号", "案由": "有限合伙纠纷",
         "当事人": {"原告": ["李某某"], "被告": [NAME, "某装备有限公司"]}, "法院": "西湖区人民法院",
         "开庭时间": "2026-02-09 16:20"},
        {"案号": "（2026）浙0106民初2号", "案由": "金融借款合同纠纷",
         "当事人": {"原告": [NAME], "被告": ["赵**"]}, "法院": "西湖区人民法院", "开庭时间": "2026-03-01 09:00"}]},
    "get_case_filing_info": {"企业名称": NAME, "摘要": "该主体累计共有1条记录。", "立案信息": [
        {"案号": "（2025）浙0106民初3号", "案由": "劳动合同纠纷", "当事人": {"原告": ["方**"], "被告": [f"{NAME}武汉分公司"]},
         "法院": "武昌区人民法院", "立案日期": "2025-03-28"}]},
    "get_service_announcement": {"企业名称": NAME, "搜索结果": "已全量扫描该主体劳动仲裁数据库，未发现任何记录。"},
    "get_recruitment_info": {"企业名称": NAME, "摘要": "该查询实体共有4条招聘信息记录。", "招聘信息": [
        {"发布日期": "2026-03-01", "招聘职位": "财富顾问", "月薪": "15-30k", "办公地点": city}
        for city in ("东莞", "大连", "武汉", "合肥")]},
}


class FakeQcc:
    def __init__(self, data=DATA, error=None):
        self.data, self.error, self.calls = data, error, []

    def call(self, server, tool, name):
        self.calls.append(tool)
        if self.error:
            return Call(None, self.error, False, WHEN)
        return Call(self.data.get(tool, {"企业名称": name, "搜索结果": "未发现任何记录"}), None, False, WHEN)


def extras(data=DATA):
    return qcc_more.fetch(FakeQcc(data), NAME)


def test_no_person_names_in_cleaned_records():
    x = extras()
    blob = json.dumps([r.content for r in qcc_more.records(x)], ensure_ascii=False)
    for name in ("张小明", "王大力", "李某某", "赵**", "方**"):
        assert name not in blob, name
    assert x.get("controller").rows[0]["名称"] == "自然人"
    changes = {r["项目"]: r for r in x.get("changes").rows}
    assert changes["名称变更"]["变更前"] == ["杭州远山投资有限公司"]
    assert changes["注册资本变更"]["变更前"] == ["1000万"]       # 带"法定代表人"的那条丢掉
    assert "变更前" not in changes["投资人变更"]                  # 投资人变更不留前后内容


def test_roles_count_branches_and_only_defendant_cases():
    cases = qcc_more.defendant_cases(extras())
    assert [c["案号"] for c in cases] == ["（2026）浙0106民初1号", "（2025）浙0106民初3号"]  # 分公司被告也算它；它当原告的不算


def test_investment_dispute_and_recent_name_change_are_the_only_warnings():
    x = extras()
    law = {i.key: i for i in sig.lawsuit_items(x, TODAY)}
    assert law["lawsuits"].status is Status.warn and "投资人" in law["lawsuits"].detail
    assert law["labor"].status is Status.warn           # 近两年有当被告的劳动官司
    assert sig.change_item(x, TODAY).status is Status.warn   # 近一年改过名
    assert sig.controller_item(x).value == "自然人（个人）"
    assert sig.license_item(x).status is Status.ok
    items = [*sig.lawsuit_items(x, TODAY), sig.change_item(x, TODAY), sig.license_item(x), sig.controller_item(x)]
    assert all(i.status is not Status.bad for i in items)


def test_bank_suing_borrowers_is_not_flagged():
    data = dict(DATA, get_hearing_notice={"企业名称": NAME, "开庭公告信息": [
        {"案号": f"（2026）浙01民初{i}号", "案由": "金融借款合同纠纷", "当事人": {"原告": [NAME], "被告": ["某**"]},
         "开庭时间": "2026-06-01"} for i in range(20)]}, get_case_filing_info={"企业名称": NAME, "搜索结果": "未发现任何记录"})
    law = {i.key: i for i in sig.lawsuit_items(extras(data), TODAY)}
    assert law["lawsuits"].status is Status.ok and law["lawsuits"].value == "近两年当被告 0 条"


def test_jobs_in_many_cities_with_tiny_payroll_is_flagged():
    company = CompanyProfile(name=NAME, status="存续", founded="2015-04-28", reg_capital=3174.0, scope="", insured=3)
    item = sig.jobs_item(extras(), company, TODAY)
    assert item.status is Status.warn and "参保只有 3 人" in item.detail
    big = company.model_copy(update={"insured": 7458})
    assert sig.jobs_item(extras(), big, TODAY).status is Status.ok


def test_state_owned_claim_against_person_controller():
    from app.analysis.extract import RawClaim
    from app.models import ClaimKind, Shareholder
    company = CompanyProfile(name=NAME, status="存续", founded="2015", reg_capital=1.0, scope="",
                             shareholders=[Shareholder(name="某某合伙企业", type="企业", pct=63.0)],
                             controller=[{"名称": "自然人", "是自然人": True, "总持股比例": "36.89%", "表决权比例": "68.49%"}])
    claim = RawClaim(kind=ClaimKind.background, quotes=["国资背景，安全放心"], words=["国资背景"])
    checks, verdict, plain = background_review(claim, company)
    assert verdict is Verdict.mismatch and "实际控制人是个人" in plain
    unknown = company.model_copy(update={"controller": None})
    assert background_review(claim, unknown)[1] is Verdict.unverifiable


def test_failed_lookups_say_so():
    x = qcc_more.fetch(FakeQcc(error="查询失败：ConnectError"), NAME)
    assert all(p.coverage == "failed" for p in x.parts.values())
    assert sig.controller_item(x).value == "没查成"


def test_case_runs_extras_only_for_a_matched_company():
    class Qcc(FakeQcc):
        def fetch(self, name):
            return None              # 工商没查到：不查补充信息
        def financials(self, name):
            return Call({"企业名称": name, "搜索结果": "未发现任何记录"}, None, False, WHEN)
        def news(self, name):
            return Call({"企业名称": name, "搜索结果": "未发现任何记录"}, None, False, WHEN)
    q = Qcc()
    new_case(CaseIn(company_name=NAME, need="理财"), keyword_intake("理财"), replace(svc, commercial=q, web=None, reviews=None))
    assert not any(t in q.calls for t in ("get_actual_controller", "get_hearing_notice"))


def test_web_titles_and_excerpts_hide_person_names():
    assert scrub_title("行政处罚决定书（巨鲸财富、倪某某）", "杭州巨鲸财富管理有限公司") == "行政处罚决定书（巨鲸财富、相关个人）"
    assert redact("爱企查法定代表人:倪某某注册资本:3,174万") == "爱企查法定代表人:（姓名略）注册资本:3,174万"
    assert redact("法定代表人变更为某公司") == "法定代表人变更为某公司"
    assert redact("与实控人倪某某收警示函") == "与实控人（姓名略）收警示函"
    assert redact("当事人:某公司,住所:杭州。倪某某,男,1980年1月出生,法定代表人") == \
        "当事人:某公司,住所:杭州。相关个人,（出生信息略）,法定代表人"


def test_cninfo_finds_latest_annual_and_risky_titles(tmp_path):
    def handler(req):
        body = dict(x.split("=", 1) for x in req.content.decode().split("&")) if req.content else {}
        if "topSearch" in str(req.url):
            return httpx.Response(200, json=[{"code": "600926", "orgId": "9900006251"}])
        if "category_ndbg" in httpx.QueryParams(req.content.decode()).get("category", ""):
            return httpx.Response(200, json={"announcements": [
                {"announcementTitle": "杭州银行2025年年度报告摘要", "adjunctUrl": "a.PDF", "announcementTime": 1776902400000},
                {"announcementTitle": "杭州银行2025年年度报告", "adjunctUrl": "b.PDF", "announcementTime": 1776902400000}]})
        return httpx.Response(200, json={"totalAnnouncement": 3, "announcements": [
            {"announcementTitle": "关于收到行政处罚决定书的公告", "adjunctUrl": "c.PDF", "announcementTime": 1788000000000},
            {"announcementTitle": "关于优先股停牌的提示性公告", "adjunctUrl": "d.PDF", "announcementTime": 1788000000000},
            {"announcementTitle": "董事会决议公告", "adjunctUrl": "e.PDF", "announcementTime": 1788000000000}]})
    client = CninfoClient(tmp_path, transport=httpx.MockTransport(handler))
    found = client.find("600926", TODAY)
    assert found.annual.title == "杭州银行2025年年度报告" and found.annual.url.endswith("b.PDF")
    assert [n.category for n in found.risky] == ["penalty"]
    fin_items, credit = sig.cninfo_items(found)
    assert credit[0].status is Status.warn and fin_items[0].key == "annual_report_pdf"
    assert client.find(None, TODAY).coverage == "not_covered"
    replay = CninfoClient(tmp_path, mode="replay", transport=httpx.MockTransport(lambda r: httpx.Response(500)))
    assert replay.find("600926", TODAY).replay is True
