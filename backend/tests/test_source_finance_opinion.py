"""财务数据、新闻舆情（企查查）：只照抄平台给的数，负面最多"要留意"，个人名字不进案卷；进度按声明的顺序走。"""
from dataclasses import replace
from datetime import date

from app import progress
from app.analysis.pipeline import new_case
from app.models import CaseIn, Status
from app.scenarios import keyword_intake
from app.sources import finance as fin
from app.sources import news as news_src
from app.sources.qcc_agent import Call
from app.sources.registries import AMAC_ID
from tests.helpers import svc

NAME = "杭州远山股份有限公司"
WHEN = "2026-10-02T20:00:00+08:00"


def period(label, revenue, profit, yoy="1.09", debt="92.96"):
    return {"报告期": label, "披露等级": "指标丰富", "指标详情": {
        "主要财务指标": {"营业总收入": revenue, "总资产": "2000000000000"},
        "财务报表": {"利润表": {"营业总收入": revenue, "净利润": profit},
                     "资产负债表": {"资产合计": "2000000000000"}},
        "分析数据": {"成长能力": {"营业收入同比": yoy}, "偿还能力": {"资产负债率": debt},
                     "盈利能力": {"加权净资产收益率": "8.87"}}}}


FINANCE = {"企业名称": NAME, "摘要": "已检索 2024 年至今的财务数据，共 3 个报告期",
           "财务数据信息": [period("2025年年报", "38798611000", "19029250000"),
                            period("2026年中报", "21047502000", "12813493000", "4.75"),
                            period("2024年年报", "38381172000", "16982563000", "9.61")]}
NEWS = {"企业名称": NAME, "摘要": "该查询实体共有120条新闻舆情记录。", "新闻舆情信息": [
    {"标题": "行政处罚决定书（远山股份、张小明）", "情感类型": "消极", "链接": "https://example.org/1",
     "发布时间": "2026-09-20 10:00:00", "来源": "某证监局"},
    {"标题": "远山股份聘任王某某担任董事会秘书", "情感类型": "中立", "链接": "https://example.org/2",
     "发布时间": "2026-09-28 10:00:00", "来源": "凤凰网"},
    {"标题": "远山股份获评优秀企业", "情感类型": "积极", "链接": "https://example.org/3",
     "发布时间": "2026-09-30 10:00:00", "来源": "今日头条"},
]}


class FakeQcc:
    """只有财务、舆情两个工具的企查查；工商查询返回 None（当作没配工商）。"""
    def __init__(self, finance=FINANCE, news=NEWS, error=None):
        self.finance, self.news_data, self.error = finance, news, error
        self.calls = []

    def fetch(self, name):
        return None

    def financials(self, name):
        self.calls.append("financials")
        return Call(None if self.error else self.finance, self.error, False, WHEN)

    def news(self, name):
        self.calls.append("news")
        return Call(None if self.error else self.news_data, self.error, False, WHEN)


def services(qcc):
    return replace(svc, commercial=qcc, web=None, reviews=None)


def build(qcc, name=NAME):
    events = []
    with progress.reporting(events.append):
        case = new_case(CaseIn(company_name=name, need="理财"), keyword_intake("理财"), services(qcc))
    return case, events


def items(case, key):
    return {i.key: i for s in case.versions[0].signals if s.key == key for i in s.items}


def test_finance_periods_are_copied_newest_first_and_not_recomputed():
    f = fin.findings(Call(FINANCE, None, False, WHEN))
    assert f.coverage == "found"
    assert [p.label for p in f.periods] == ["2026年中报", "2025年年报", "2024年年报"]
    assert f.latest_annual.label == "2025年年报"
    assert fin.yi(f.latest_annual.revenue) == "387.99 亿元"
    assert f.latest_annual.revenue_yoy == 1.09 and f.latest.debt_ratio == 92.96


def test_finance_empty_and_failed_are_told_apart():
    empty = {"企业名称": NAME, "搜索结果": "已全量扫描该主体财务数据数据库，未发现任何记录。"}
    assert fin.findings(Call(empty, None, False, WHEN)).coverage == "not_found"
    assert fin.findings(Call(None, "查询失败：ConnectError", False, WHEN)).coverage == "failed"
    assert fin.findings(Call({"企业名称": NAME, "摘要": "数据格式变了"}, None, False, WHEN)).coverage == "failed"


def test_news_keeps_all_titles_and_scrubs_person_names():
    n = news_src.findings(Call(NEWS, None, False, WHEN), NAME)
    assert n.total == 120 and len(n.items) == 3
    assert n.counts() == {"消极": 1, "中立": 1, "积极": 1}
    assert n.negatives[0].title == "行政处罚决定书（远山股份、相关个人）"
    assert news_src.scrub_title("行政处罚决定书（巨鲸财富、张小明）", "杭州巨鲸财富管理有限公司") ==         "行政处罚决定书（巨鲸财富、相关个人）"
    assert all(i.title for i in n.items)
    assert "王某某" not in str(n.items)  # Preserve appointment news, not personal names.
    assert len(n.recent_negatives(date(2026, 10, 2))) == 1
    assert n.recent_negatives(date(2028, 1, 1)) == []


def test_case_shows_report_figures_and_news_without_judging_ratios():
    case, _ = build(FakeQcc())
    by_source = {r.source_id: r for r in case.raw}
    assert by_source["qcc_finance"].coverage == "found" and by_source["qcc_news"].coverage == "found"
    assert "张小明" not in str([r.content for r in case.raw])
    f = items(case, "finance")
    assert f["revenue"].label == "营业收入（2025年年报）"
    assert f["revenue"].value == "387.99 亿元，同比 +1.09%"
    assert f["net_profit"].status is Status.ok
    assert f["debt_ratio"].status is Status.ok  # 银行负债率高是常态，不标
    assert f["revenue"].ref == by_source["qcc_finance"].id
    rep = items(case, "reputation")
    assert rep["news"].value == "共 120 条"
    assert rep["news_negative"].status is Status.warn  # 平台标的负面，最多要留意
    assert "complaints" not in rep  # 舆情查了，就不再写"还没有投诉数据"


def test_loss_is_the_only_figure_flagged():
    loss = dict(FINANCE, 财务数据信息=[period("2025年年报", "1000000000", "-50000000")])
    f = items(build(FakeQcc(finance=loss))[0], "finance")
    assert f["net_profit"].status is Status.warn and f["net_profit"].detail == "亏损"


def test_another_companys_financials_are_not_used():
    other = dict(FINANCE, 企业名称="杭州远山控股有限公司")
    case, _ = build(FakeQcc(finance=other))
    rec = next(r for r in case.raw if r.source_id == "qcc_finance")
    assert rec.coverage == "failed" and "对不上" in rec.note
    assert "revenue" not in items(case, "finance")


def test_unlisted_company_says_no_public_financials():
    empty = {"企业名称": NAME, "搜索结果": "已全量扫描该主体财务数据数据库，未发现任何记录。"}
    case, events = build(FakeQcc(finance=empty))
    assert items(case, "finance")["reports"].value == "没有"
    done = next(e for e in events if e.get("id") == "finance" and e.get("phase") == "done")
    assert done["coverage"] == "not_found" and "非上市公司" in done["text"]


def test_failed_lookup_is_failed_not_clean():
    case, events = build(FakeQcc(error="查询失败：ConnectError"))
    assert items(case, "finance")["reports"].value == "没查成"
    assert items(case, "reputation")["news"].value == "没查成"
    done = {e["id"]: e for e in events if e.get("phase") == "done"}
    assert done["finance"]["coverage"] == "failed" and done["opinion"]["coverage"] == "failed"


def test_demo_company_skips_paid_lookups():
    qcc = FakeQcc()
    _, events = build(qcc, "杭州满盈禾康养健康咨询有限公司")
    assert qcc.calls == []
    done = {e["id"]: e for e in events if e.get("phase") == "done"}
    assert done["finance"]["coverage"] == "not_covered" and "虚构" in done["finance"]["text"]


def test_steps_follow_declared_order():
    _, events = build(FakeQcc())
    lookups = [e["id"] for e in events if e["type"] == "step" and e["phase"] == "done"
               and e["id"] in progress.LOOKUPS]
    declared = [s for s in progress.STEPS if s in progress.LOOKUPS]
    assert lookups == declared


def test_amac_fallback_progress_precedes_registry_with_and_without_pack():
    services_ = replace(svc, registries={k: v for k, v in svc.registries.items() if k != AMAC_ID},
                        commercial=None, web=None, reviews=None)
    for name in (NAME, "杭州巨鲸财富管理有限公司"):
        events = []
        with progress.reporting(events.append):
            new_case(CaseIn(company_name=name, need="理财"), keyword_intake("理财"), services_)
        sequence = [(e["id"], e["phase"]) for e in events if e["type"] == "step"]
        assert sequence[:12] == [(step, phase) for step in ("lists", "amac", "registry", "finance", "pack", "web")
                                 for phase in ("start", "done")]
