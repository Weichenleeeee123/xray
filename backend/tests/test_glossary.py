"""名词解释：词表本身、报告覆盖、助手怎么用它。不连网。"""
import json

from fastapi.testclient import TestClient

from app.assistant import VERDICT_WORDS, answer, overreach
from app.glossary import find_terms, load_glossary
from app.main import app
from app.models import ChatIn
from tests.helpers import DEMO_COMPANY, flyer, make_case, svc
from tests.test_llm_assistant import FakeLLM, _ans

# 报告里这些标签是描述性的，不是需要解释的名词
PLAIN_LABELS = {"最近 3 个月", "近 12 个月投诉", "集中的问题", "投诉、维权", "登记数据", "网上提到它的报道和投诉",
                "说到兑付、提现、跑路", "负面报道", "收益对比（演示参数）", "会员数", "存管协议", "股东", "退款条款"}


def test_glossary_is_well_formed():
    terms = load_glossary()
    ids = [t.id for t in terms]
    names = [n for t in terms for n in (t.term, *t.aliases)]
    assert len(ids) == len(set(ids)) and len(names) == len(set(names))
    for t in terms:
        assert t.plain and (t.basis is None or t.basis in svc.sources), t.id
        assert not VERDICT_WORDS.search(t.plain + (t.why or "")), t.id     # 解释里也不许下定性


def test_longest_name_wins_and_suffixes_still_match():
    assert [t.id for t in find_terms("失信被执行人")] == ["dishonest"]
    assert [t.id for t in find_terms("严重违法失信名单")] == ["serious_illegal"]
    assert [t.id for t in find_terms("实缴资本（2025 年报）")] == ["paid_capital", "annual_report"]
    assert [t.id for t in find_terms("实缴资本：¥0（认缴 ¥5,000 万）")] == ["paid_capital", "reg_capital"]


def test_every_concept_label_in_the_demo_report_has_an_explanation():
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    v = case.versions[-1]
    labels = {i.label for s in v.signals for i in s.items} | {c.label for a in v.assertions for c in a.checks}
    labels |= {a.kind_label for a in v.assertions if a.kind_label not in {"资格", "合作机构", "背景", "规模", "注册资本"}}
    missing = sorted(lab for lab in labels - PLAIN_LABELS if not find_terms(lab))
    assert not missing, f"这些标签还没有名词解释：{missing}"


def test_glossary_endpoint():
    got = TestClient(app).get("/api/glossary").json()
    assert any(t["term"] == "实缴资本" for t in got)


def test_template_explains_terms_with_citation(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    msg = answer(case, ChatIn(text="实缴资本是什么意思"), FakeLLM([], tmp_path))
    assert msg.mode == "template" and "term.paid_capital" in msg.citations
    assert "打进公司账户" in msg.text and "finance.paid_capital" in msg.citations   # 再接上本案那一条


def test_model_sees_glossary_and_may_cite_it(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    fake = FakeLLM([_ans("实缴资本是股东实际拿出来的钱 [term.paid_capital]，它的实缴是 0 [finance.paid_capital]。")], tmp_path)
    msg = answer(case, ChatIn(text="实缴资本是什么"), fake)
    # The gateway may prepend the output schema; inspect the case message, not its index.
    case_message = next(m["content"] for m in fake.calls[0]
                        if m["role"] == "user" and m["content"].startswith("<案卷数据>"))
    ctx = json.loads(case_message.split("\n", 1)[1].rsplit("\n", 1)[0])
    assert any(e["id"] == "term.paid_capital" for e in ctx["名词解释"])
    assert msg.mode == "model" and "term.paid_capital" in msg.citations and msg.dropped == 0


def test_glossary_does_not_unlock_characterizations(tmp_path):
    # 词表里有"非法集资"，但案卷记录里没有：解释这个词可以，拿它说这家公司不行
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    data = ""
    assert overreach("非法集资是指没有经过许可、向社会公众吸收资金 [term.illegal_fundraising]", data) == []
    assert overreach("它这就是非法集资", data) == ["非法集资"]
    fake = FakeLLM([_ans("它这就是非法集资 [A1]"), _ans("持牌名单里查不到它 [A1]。")], tmp_path)
    msg = answer(case, ChatIn(text="什么是非法集资"), fake)
    assert msg.rewrites == 1 and msg.blocked == ["非法集资"]
