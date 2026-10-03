"""Context prevents mentions and incomplete dates from becoming company-wide claims."""
from datetime import date

import pytest

from app.analysis.extract import RuleExtractor
from app.analysis.signals import change_item, news_items, official_web_item, risk_signal
from app.models import AmacHit, LicenseHit, Status
from app.scenarios import get_scenario
from app.sources.news import NewsFindings, NewsItem
from app.sources.qcc_more import Part, QccExtras
from app.sources.web import WebFindings, WebHit


TODAY = date(2026, 10, 3)


def warning(subject, url):
    return WebHit("warning", "监管风险提示", True, "监管提示文书", url, "监管网站", "2026-09-01", "", subject=subject)


def risk_items(web):
    result = risk_signal(RuleExtractor().extract(""), None,
                         LicenseHit(query="被查询的公司", found=False), AmacHit(coverage="not_covered"),
                         get_scenario("general"), [], web=web,
                         refs={hit.url: f"raw-{i}" for i, hit in enumerate(web.official)})
    return {item.key: item for item in result.items}


def test_warning_about_another_company_does_not_create_own_regulatory_warning():
    web = WebFindings(searched=True, official=[warning(False, "https://example.gov.cn/other")])
    assert "regulator_warning" not in risk_items(web)
    # The mention stays available, with its role, instead of being erased.
    mention = official_web_item(web, {})
    assert mention.status is Status.warn
    assert "它不是当事人" in mention.value


def test_own_warning_stays_bad_and_does_not_count_other_company_mentions():
    web = WebFindings(searched=True, official=[
        warning(False, "https://example.gov.cn/other"),
        warning(True, "https://example.gov.cn/own"),
    ])
    item = risk_items(web)["regulator_warning"]
    assert item.status is Status.bad
    assert item.value.startswith("1 份")
    assert item.ref == "raw-1"


def negative(when):
    return NewsItem(when, "消极", "新闻来源", "https://example.com/news", "新闻标题")


@pytest.mark.parametrize("when", [None, "", "日期待定", "2026-02-30"])
def test_undated_negative_news_stays_pending_attention_not_historical_clear(when):
    item = news_items(NewsFindings("found", 1, [negative(when)]), TODAY)[1]
    assert item.status is Status.warn
    assert "时间待核实" in item.label
    assert "1 条发布日期待核实" in item.detail
    assert "一年以前" not in item.label


def test_recent_and_undated_news_are_both_described_without_claiming_unknown_dates():
    item = news_items(NewsFindings("found", 3, [negative("2026-09-01"), negative(None), negative("2020-01-01")]), TODAY)[1]
    assert item.status is Status.warn
    assert item.value == "1 条"
    assert "近一年" in item.label
    assert "另有 1 条发布日期待核实" in item.detail


def test_only_dated_historical_news_keeps_its_historical_context():
    item = news_items(NewsFindings("found", 1, [negative("2020-01-01")]), TODAY)[1]
    assert item.status is Status.ok
    assert item.label == "负面新闻（一年以前）"
    assert "2020-01-01" in item.detail


def test_company_change_remains_visible_without_implying_intent_to_flee():
    extras = QccExtras("被查询的公司", {"changes": Part("found", 1, [{"日期": "2026-09-01", "项目": "名称变更"}])})
    item = change_item(extras, TODAY)
    assert item.status is Status.warn
    assert item.value == "共 1 次"
    assert "名称变更" in item.detail
    assert "变更本身不代表经营异常" in item.detail
    assert "核实变更原因" in item.detail
    assert "跑路" not in item.detail
