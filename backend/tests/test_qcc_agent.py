"""企查查智能体数据平台：协议解析、字段映射、隐私清理、积分上限、缓存，以及接进报告后的效果。

全部用本地假响应（httpx.MockTransport），不连网、不扣积分。公司是虚构的，股东用"甲某"这类假名。
返回结构照平台工具详情页的"示例输出"写。
"""
import json

import httpx

from app.analysis.pipeline import Services, new_case
from app.models import CaseIn, Status, Verdict
from app.scenarios import keyword_intake
from app.sources.packs import EvidencePacks
from app.sources.qcc_agent import QccAgentClient, QccError, clean, is_person, parse_response
from tests.helpers import svc

NAME = "杭州测试财富管理有限公司"
EMPTY = "经企查查底层数据库全量核查实体 {n}，当前未发现任何【{f}】记录。此项核心合规风控排查安全，允许进入下一步审计。"

REG = {"企业名称": NAME, "统一社会信用代码": "91330100TEST00000X", "法定代表人": "甲某", "登记状态": "存续",
       "成立日期": "2015-04-01", "注册资本": "2000万元", "实缴资本": "100万元", "参保人数": "5",
       "企业类型": "有限责任公司", "经营范围": "资产管理；投资管理", "企业联系电话": "0571-00000000"}
FACTORS = {"失信信息": 0, "被执行人": 12, "限制高消费": 1, "行政处罚": 1, "经营异常": 0, "严重违法": 0,
           "股权出质": 0, "动产抵押": 0, "欠税公告": 0, "裁判文书": 3}
TOOLS = {
    "get_company_registration_info": REG,
    "get_company_risk_scan": {"企业名称": NAME, "摘要": "已全量扫描。",
                              "风险因子扫描": [{"风险因子": k, "条目数": v, "明细工具": "x"} for k, v in FACTORS.items()]},
    "get_judgment_debtor_info": {"企业名称": NAME, "摘要": "该主体共有12条记录。", "提示": "该维度数据较多，已为您展示前2条。",
                                 "被执行人信息": [{"案号": "（2024）浙0100执1号", "执行标的": "50000", "执行法院": "某区人民法院",
                                                  "立案日期": "2024-03-01"},
                                                 {"案号": "（2024）浙0100执2号", "执行标的": "80000", "执行法院": "某区人民法院",
                                                  "立案日期": "2024-04-01"}]},
    "get_high_consumption_restriction": {"企业名称": NAME, "摘要": "该主体仅有1条记录。",
                                         "限制高消费信息": [{"限制法定代表人": "甲某", "申请人": "乙某", "立案日期": "2024-05-01"}]},
    "get_administrative_penalty": {"企业名称": NAME, "摘要": "该主体仅有1条记录，处罚日期为2024-09-13。",
                                   "行政处罚信息": [{"决定书文号": "某局罚〔2024〕1号", "处罚结果": "警告，罚款36万元",
                                                    "处罚金额": "360000", "处罚单位": "某监管局", "处罚日期": "2024-09-13"}]},
    "get_shareholder_info": {"企业名称": NAME, "摘要": "该查询实体共有2条股东信息记录。",
                             "股东信息": [{"股东名称": "甲某", "持股比例": "60%"}, {"股东名称": "乙某", "持股比例": "40%"}]},
    "get_branches": {"企业名称": NAME, "摘要": "该查询实体共有2条分支机构记录。",
                     "分支机构信息": [{"企业名称": "分公司一", "负责人": "丙某", "登记状态": "存续"},
                                    {"企业名称": "分公司二", "负责人": "丁某", "登记状态": "注销"}]},
    "get_listing_info": {"企业名称": NAME, "搜索结果": "已全量扫描该主体上市信息数据库，未发现任何记录。"},
}


def server(tools: dict, seen: list, sse: bool = True):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((request.url.path, body["params"]["name"], request.headers["Authorization"]))
        tool = body["params"]["name"]
        data = tools.get(tool) or {"企业名称": NAME, "摘要": EMPTY.format(n=NAME, f=tool)}
        msg = {"jsonrpc": "2.0", "id": body["id"],
               "result": {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False)}]}}
        if sse:
            return httpx.Response(200, text=f"event: message\ndata: {json.dumps(msg, ensure_ascii=False)}\n\n")
        return httpx.Response(200, json=msg)
    return httpx.MockTransport(handler)


def client(tmp_path, tools=TOOLS, seen=None, **kw):
    return QccAgentClient("Bearer K", cache_dir=tmp_path, transport=server(tools, [] if seen is None else seen), **kw)


def test_parse_response_json_sse_and_errors():
    msg = {"result": {"content": [{"type": "text", "text": "{\"企业名称\": \"X\"}"}]}}
    assert parse_response(json.dumps(msg)) == {"企业名称": "X"}
    assert parse_response(f"event: message\ndata: {json.dumps(msg)}\n\n") == {"企业名称": "X"}
    for bad in ({"error": {"code": -32001, "message": "invalid_token"}},
                {"result": {"isError": True, "content": [{"type": "text", "text": "积分不足"}]}}):
        try:
            parse_response(json.dumps(bad))
            raise AssertionError("应当报错")
        except QccError as e:
            assert str(e) in ("invalid_token", "积分不足")


def test_clean_drops_personal_info_and_judging_words():
    out = clean({"法定代表人": "甲某", "摘要": EMPTY.format(n=NAME, f="失信信息"),
                 "股东信息": [{"股东名称": "甲某", "持股比例": "60%"}, {"股东名称": "某某投资有限公司", "持股比例": "40%"}]})
    assert "法定代表人" not in out and "安全" not in out["摘要"] and "未发现" in out["摘要"]
    assert [r["股东名称"] for r in out["股东信息"]] == ["自然人股东A", "某某投资有限公司"]
    assert is_person("甲某") and not is_person("杭州市财政局") and not is_person("Commonwealth Bank of Australia")


def test_fetch_maps_fields_counts_and_privacy(tmp_path):
    seen = []
    c = client(tmp_path, seen=seen)
    r = c.fetch(NAME)
    p = r.profile
    assert seen[0][0] == "/mcp/company/stream" and seen[0][2] == "Bearer K"     # Key 前面的 Bearer 不重复
    assert (p.code, p.status, p.founded, p.reg_capital, p.paid_capital, p.insured) == \
           ("91330100TEST00000X", "存续", "2015-04-01", 2e7, 1e6, 5)
    assert p.n("executions") == 12 and len(p.executions) == 2              # 只给了前 2 条，按总数 12 算
    assert p.restricted and not p.dishonest and p.known("dishonest") and p.known("restricted")
    assert p.penalties[0].result == "警告，罚款36万元" and p.penalties[0].date == "2024-09-13"
    assert [(h.name, h.type, h.pct) for h in p.shareholders] == [("自然人股东A", "自然人", 60), ("自然人股东B", "自然人", 40)]
    assert p.branches == 1                                                  # 注销的不算
    assert p.known("listing") and p.listing is None
    text = json.dumps(r.content, ensure_ascii=False)
    assert "甲某" not in text and "乙某" not in text and "丙某" not in text and "安全" not in text
    # 有记录的才调明细：失信、经营异常这些 0 条的不调
    called = [t for _, t, _ in seen]
    assert "get_dishonest_info" not in called and "get_judgment_debtor_info" in called
    assert c.points == 3 + 5 + 3 + 3 + 3 + 20 + 5 + 1
    n = len(seen)
    again = client(tmp_path, seen=seen).fetch(NAME)                        # 新进程，读缓存
    assert len(seen) == n and again.profile.n("executions") == 12 and "缓存" in again.note


def test_name_mismatch_stops_after_first_call(tmp_path):
    seen = []
    r = client(tmp_path, seen=seen).fetch("杭州测试")
    assert r.profile is None and "对不上" in r.note and len(seen) == 1


def test_points_cap_leaves_fields_unchecked(tmp_path):
    r = client(tmp_path, max_points=8).fetch(NAME)                          # 只够工商信息 3 + 风险扫描 5
    p = r.profile
    assert p.known("penalties") and p.n("penalties") == 1 and not p.penalties
    assert not p.known("shareholders") and not p.known("listing") and "上限" in r.note


def services(tmp_path, tools=TOOLS, packs=None):
    return Services(svc.licenses, svc.registry, svc.amac, svc.complaints, packs or svc.packs, svc.extractor,
                    svc.sources, svc.registries, client(tmp_path, tools))


def make(tmp_path, text, tools=TOOLS, packs=None, name=NAME):
    need = "我妈想存 20 万理财"
    return new_case(CaseIn(company_name=name, need=need, material_text=text), keyword_intake(need),
                    services(tmp_path, tools, packs))


def test_report_uses_qcc_records(tmp_path):
    case = make(tmp_path, "公司获得国内大型综合金融集团的认可并注资。")
    v = case.versions[0]
    items = {f"{s.key}.{i.key}": i for s in v.signals for i in s.items}
    assert items["credit.restricted"].status is Status.bad and items["credit.dishonest"].value == "无"
    assert items["finance.executions"].value == "12 条" and items["credit.penalties"].value == "1 条"
    bg = next(a for a in v.assertions if a.kind.value == "background")
    assert bg.verdict is Verdict.mismatch and "没有宣传说的集团" in bg.plain
    reg = next(r for r in case.raw if r.source_id == "registry")
    assert reg.kind == "commercial" and "企查查" in reg.title and case.sources["registry"].kind == "commercial"


def test_listing_claim_checked_against_listing_info(tmp_path):
    listed = dict(TOOLS, get_listing_info={"企业名称": NAME, "上市信息": [
        {"上市交易所": "上海证券交易所", "股票代码": "600000", "股票简称": "测试银行", "上市日期": "2016-10-27"}]})
    said = "首次公开发行A股在上海证券交易所成功上市，股票代码600000。"
    bg = next(a for a in make(tmp_path / "a", said, listed).versions[0].assertions if a.kind.value == "background")
    assert bg.verdict is Verdict.consistent and "上交所上市" in bg.plain and "600000" in bg.plain
    wrong = next(a for a in make(tmp_path / "b", said.replace("600000", "600001"), listed).versions[0].assertions
                 if a.kind.value == "background")
    assert wrong.verdict is Verdict.mismatch and "股票代码" in wrong.plain
    none = next(a for a in make(tmp_path / "c", said).versions[0].assertions if a.kind.value == "background")
    assert none.verdict is Verdict.mismatch and "查不到" in none.plain


def test_pack_without_registry_still_gets_qcc_registry(tmp_path):
    pack_dir = tmp_path / "packs"
    pack_dir.mkdir()
    (pack_dir / "p.json").write_text(json.dumps({
        "company": NAME, "as_of": "2026-10-02", "note": "只摘了一份文书",
        "extra": [{"source_id": "doc1", "source": {"name": "某局文书", "url": "https://example.gov.cn/1"},
                   "title": "某局文书", "data": {"要点": "示例"}}]}, ensure_ascii=False), encoding="utf-8")
    case = make(tmp_path, "注册资本2000万元。", packs=EvidencePacks.load(pack_dir))
    assert case.sources["registry"].kind == "commercial"
    assert any(r.source_id == "doc1" for r in case.raw)                      # 证据包里的文书照样进原始数据
    assert not any(r.source_id == "registry" and r.kind == "collected" for r in case.raw)


# ---------- 同一份文书不重复计数 ----------

def _credit(items):
    from app.models import Signal
    return [Signal(key="credit", title="信用", lede="", flags=0, items=items)]


def test_pack_documents_are_not_counted_again():
    from app.analysis.signals import add_pack_items, official_web_item
    from app.models import CompanyProfile, Penalty, RawRecord, SignalItem
    from app.sources.web import WebFindings, WebHit
    url24, url23, url22 = (f"https://www.csrc.gov.cn/zhejiang/c{i}/content.shtml" for i in (1, 2, 3))
    hit = lambda u, cat, label: WebHit(cat, label, True, "决定", u, "csrc.gov.cn", "2024-09-13", "……")
    web = WebFindings(True, official=[hit(url24, "penalty", "行政处罚"), hit(url23.replace("https", "http"), "warning", "警示函"),
                                      hit(url22, "warning", "警示函")])
    records = [RawRecord(id="R1", source_id="d24", title="", kind="collected", retrieved_at="", url=url24),
               RawRecord(id="R2", source_id="d23", title="", kind="collected", retrieved_at="", url=url23)]
    pack = [SignalItem(key="p1", label="行政处罚决定（人工采集）", value="2024-09-13：罚款36万元", status=Status.bad, source="d24", ref="R1"),
            SignalItem(key="p2", label="行政监管措施（人工采集）", value="2023-12-05：警示函", status=Status.bad, source="d23", ref="R2")]
    company = CompanyProfile(name=NAME, status="存续", founded="2015-04-01", reg_capital=2e7, scope="",
                             penalties=[Penalty(date="2024-09-13", org="某局", reason="", result="罚款")],
                             counts={"penalties": 1}, checked=["penalties"])
    signals = _credit([SignalItem(key="penalties", label="行政处罚", value="1 条", status=Status.bad, source="registry"),
                       official_web_item(web, {})])
    assert signals[0].items[1].value.startswith("3 份")
    add_pack_items(signals, pack, records, company, web, {})
    credit = signals[0]
    web_item = next(i for i in credit.items if i.key == "official_web")
    assert web_item.value.startswith("另有 1 份")                    # 2024、2023 两份已在上面列出（http/https 视为同一网址）
    assert not any(i.key == "penalties" for i in credit.items)       # 商业数据里同一天的处罚不再单列
    assert credit.flags == 3


# ---------- 实测暴露的问题 ----------

def test_penalty_text_keeps_only_the_company_clause():
    from app.sources.qcc_agent import scrub_text
    text = f"一、对{NAME}责令改正，给予警告，并处36万元罚款； 二、对甲某某给予警告，并处21万元罚款。"
    assert scrub_text(text, NAME) == f"一、对{NAME}责令改正，给予警告，并处36万元罚款；"
    assert scrub_text("对甲某某给予警告", NAME) == "对相关个人给予警告"
    out = clean({"限制高消费信息": [{"案号": "（2025）浙01执1号", "限制法定代表人": "甲某", "申请人": ["华*", "某某融资租赁有限公司"]}]})
    assert out["限制高消费信息"][0] == {"案号": "（2025）浙01执1号", "申请人": ["自然人", "某某融资租赁有限公司"]}


def test_pledges_and_mortgages_where_it_is_the_creditor_do_not_count(tmp_path):
    bank = dict(TOOLS)
    bank["get_company_risk_scan"] = {"风险因子扫描": [{"风险因子": "股权出质", "条目数": 3}, {"风险因子": "动产抵押", "条目数": 2}]}
    bank["get_equity_pledge_info"] = {"企业名称": NAME, "摘要": "该查询实体共有3条股权出质记录。", "提示": "已为您展示前2条。",
                                      "股权出质信息": [{"出质人": ["某影视股份有限公司"], "质权人": [NAME], "股权数额": "100万元",
                                                      "登记日期": "2024-10-08", "标的企业": "某科技有限公司"},
                                                     {"出质人": ["乙某"], "质权人": ["某银行股份有限公司"], "股权数额": "50万元",
                                                      "登记日期": "2023-01-01", "标的企业": NAME}]}
    bank["get_chattel_mortgage_info"] = {"企业名称": NAME, "摘要": "该查询实体共有2条动产抵押记录。",
                                         "动产抵押信息": [{"抵押人": "某服饰有限公司", "抵押权人": [NAME], "登记日期": "2019-12-11"},
                                                        {"抵押人": "某服饰二有限公司", "抵押权人": [NAME], "登记日期": "2019-10-29"}]}
    p = client(tmp_path, bank).fetch(NAME).profile
    assert p.n("pledges") == 1 and p.pledges[0].pledgor == "自然人股东A" and p.pledges[0].pledgee == "某银行股份有限公司"
    assert "别人押给它" in p.facts["pledges"] and "前 2 条" in p.facts["pledges"]
    assert p.n("mortgages") == 0 and p.known("mortgages") and "抵押权人" in p.facts["mortgages"]


def test_other_risks_only_red_for_factors_that_are_its_own():
    from app.analysis.signals import other_risks_item
    assert other_risks_item({"裁判文书": 1507, "司法拍卖": 6, "违约事项": 2, "行政处罚": 5})[0].status is Status.warn
    item = other_risks_item({"终本案件": 2, "裁判文书": 8, "失信信息": 1})[0]
    assert item.status is Status.bad and item.value == "终本案件 2、裁判文书 8"
    assert other_risks_item({"裁判文书": 0, "行政处罚": 3}) == []
