"""报告里的图：数据来自记录和规则；没查不画成 0；自然人股东不显示姓名。不连网。"""
from datetime import date

from app.analysis.charts import capital_chart, holders_chart, timeline_chart
from app.analysis.extract import RuleExtractor
from app.models import CompanyProfile, Shareholder
from tests.helpers import DEMO_COMPANY, flyer, make_case


def charts(case):
    return {c.id: c for c in case.versions[-1].charts}


def test_demo_report_has_the_comparisons_that_matter():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    got = charts(case)
    assert list(got) == ["capital", "return", "scale", "holders", "complaints", "timeline"]
    cap = got["capital"]
    assert [(p.side, p.value) for p in cap.points] == [("said", 50_000_000), ("record", 50_000_000), ("record", 0)]
    assert cap.item == "A5" and "实际交了 0 元" in cap.note
    assert [p.display for p in cap.points] == ["5000 万", "5000 万", "0 元"]
    assert [p.side for p in got["return"].points] == ["said", "reference"]
    assert [p.value for p in got["scale"].points] == [30, 0] and "4 人" in got["scale"].note


def test_capital_chart_writes_registered_and_paid_in_the_same_units():
    company = CompanyProfile(name="杭州银行股份有限公司", status="存续", founded="1996-09-25", scope="银行业务",
                             reg_capital=7_249_003_000, paid_capital=7_249_003_000)
    cap = capital_chart(RuleExtractor().extract(""), company, [], {})
    assert [p.display for p in cap.points] == ["72.49 亿", "72.49 亿"]
    assert "实际交了 72.49 亿" in cap.note


def test_every_point_and_event_points_back_to_a_record_in_the_case():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    raw_ids = {r.id for r in case.raw}
    for c in case.versions[-1].charts:
        for p in c.points:
            assert p.ref in raw_ids or p.side == "reference", (c.id, p.label)
        for e in c.events:
            assert e.ref in raw_ids, (c.id, e.label)


def test_timeline_is_sorted_and_marks_the_future_deadline():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    ev = charts(case)["timeline"].events
    assert [e.date for e in ev] == sorted(e.date for e in ev)
    assert ev[0].label == "公司成立" and ev[-1].tone == "future"


def test_natural_person_shareholders_are_not_named():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    holders = charts(case)["holders"]
    assert [p.label for p in holders.points] == ["自然人股东 A", "自然人股东 B"]
    assert "张某明" not in holders.note and "70% 股权已出质" in holders.note


def test_unchecked_paid_capital_is_not_drawn_as_zero():
    company = CompanyProfile(name="某公司", status="存续", founded="2020-01-01", reg_capital=10_000_000,
                             paid_capital=0, scope="软件开发", checked=["reg_capital", "status", "founded"])
    ext = RuleExtractor().extract("注册资本 1000 万，实力雄厚")
    cap = capital_chart(ext, company, [], {"registry": "R1"})
    paid = cap.points[-1]
    assert paid.value is None and paid.display == "没查"


def test_no_registry_data_means_no_registry_charts():
    case = make_case("杭州某某不存在科技有限公司", "保本保息，年化 8%")
    got = charts(case)
    assert "capital" not in got and "holders" not in got and "timeline" not in got
    assert got["return"].points[0].value == 8


def test_company_charts_skip_fields_the_source_did_not_give():
    company = CompanyProfile(name="某公司", status="存续", founded="2020-01-01", reg_capital=1,
                             shareholders=[Shareholder(name="某某集团", type="企业法人", pct=100)],
                             scope="", checked=["status"])
    assert holders_chart(company, [], {}) is None
    assert timeline_chart(company, None, {}, None, {}, date(2026, 10, 2)) is None


def test_timeline_keeps_only_official_events_that_matter():
    from app.sources.web import WebFindings, WebHit
    labels = {"penalty": "行政处罚 / 监管措施", "judicial": "法院文书", "other": "其他提及", "license": "许可 / 批复"}
    hit = lambda cat, title, d, subject=True, dated=True: WebHit(cat, labels[cat], True, title, f"https://x.gov.cn/{d}",
                                                                 "x", d, "", subject=subject, dated=dated)
    web = WebFindings(searched=True, official=[
        hit("penalty", "关于对某某公司采取责令改正措施的决定", "2023-02-24"),
        hit("other", "关于王某某等同志任职的通知", "2024-06-20"),           # 其他提及：不上线
        hit("judicial", "张某某与某某公司借款合同纠纷判决书", "2025-01-02"),  # 当事人姓名不上线
        hit("license", "关于某某公司开业的批复", "2021-07-05"),
        hit("penalty", "关于对某某另一家公司采取警示函措施的决定", "2022-03-31", subject=False),  # 只是顺带提到它
        hit("penalty", "行政处罚决定书[2024]35号(某某公司、王某某)_浙江监管局", "2024-09-13", dated=False)])
    tl = timeline_chart(None, web, {}, None, {}, date(2026, 10, 2))
    assert [e.label for e in tl.events] == ["许可 / 批复：关于某某公司开业的批复", "行政处罚 / 监管措施：关于对某某公司采取责令改正措施的决定",
                                          "行政处罚 / 监管措施：行政处罚决定书[2024]35号（日期是网页收录日）", "法院文书"]
    assert [e.tone for e in tl.events] == ["neutral", "bad", "bad", "warn"]    # 括号里的当事人人名不上线
