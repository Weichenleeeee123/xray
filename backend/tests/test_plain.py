"""一眼看懂：报告生成时一并写的短句和名词。模型只缩句、补名词，每条都由程序校验。不连网。"""
import json

import pytest

from fastapi.testclient import TestClient

from app.main import app
from app.plain import build_glance, finish_version
from tests.helpers import DEMO_COMPANY, add, flyer, make_case
from tests.test_llm_assistant import FakeLLM

GOOD = {
    "short": {
        "A1": "4 份牌照名单和私募登记都查不到",
        "A5": "实缴 0 元，5000 万只是承诺",
        "A6": "只有 3 人参保",                 # 原句是 4 人：冒出来的数字，丢掉
        "A2": "这是非法集资",                   # 越界定性，丢掉
        "Z9": "不存在的条目",                   # 没有这个 id，丢掉
    },
    "terms": [
        {"term": "定存", "plain": "定期存款的简称：存入时约定期限，到期取回本金和利息。"},
        {"term": "保本保息", "plain": "承诺不亏本。"},                        # 固定词表里已有，丢掉
        {"term": "量子理财", "plain": "一种理财。"},                          # 报告里没出现，丢掉
        {"term": "实力雄厚", "plain": f"{DEMO_COMPANY}说自己实力强。"},       # 提到这家公司，丢掉
    ],
}


def gen(tmp_path, payload=GOOD):
    return FakeLLM([json.dumps(payload, ensure_ascii=False)], tmp_path)


def test_without_model_report_still_has_first_items_and_glossary_terms(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    g, terms = build_glance(case, case.versions[-1], FakeLLM([], tmp_path))
    assert g.mode == "template" and g.short == {}
    assert g.first == ["A1", "risk.bank_list", "risk.amac", "risk.scope", "risk.product_code"]
    assert {"paid_capital", "guaranteed", "custody"} <= {t.id for t in terms}
    assert all(t.origin == "glossary" for t in terms)


def test_model_shorts_and_terms_are_checked(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    g, terms = build_glance(case, case.versions[-1], gen(tmp_path))
    assert g.mode == "model"
    assert g.short == {"A1": "4 份牌照名单和私募登记都查不到", "A5": "实缴 0 元，5000 万只是承诺"}
    model_terms = [t for t in terms if t.origin == "model"]
    assert [t.term for t in model_terms] == ["定存"] and model_terms[0].id.startswith("g")
    assert g.dropped == 6


def test_supplement_reuses_unchanged_shorts_and_terms(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    finish_version(case, gen(tmp_path / "a"))
    case = add(case, "reply", flyer("manyinghe_reply.txt"))
    fake = FakeLLM([json.dumps({"short": {"A7": "收款人是个人", "A1": "改过的说法"}, "terms": []},
                               ensure_ascii=False)], tmp_path / "b")
    finish_version(case, fake)
    v2 = case.versions[-1]
    asked = json.loads(fake.calls[0][-1]["content"])["需要缩短的条目"]
    assert "A1" not in {x["id"] for x in asked}                 # 原句没变的不再问
    assert v2.glance.short["A1"] == "4 份牌照名单和私募登记都查不到"   # 措辞跟上一版一样
    assert v2.glance.short["A7"] == "收款人是个人"
    assert "定存" in {t.term for t in v2.terms if t.origin == "model"}


def test_api_case_carries_glance_and_terms():
    client = TestClient(app)
    demo = client.get("/api/demo", params={"case": "C"}).json()
    v = client.post("/api/cases", json=demo["input"]).json()["versions"][-1]
    assert v["glance"]["first"][0] == "A1" and v["glance"]["mode"] == "template"   # 测试里不接模型
    assert any(t["term"] == "实缴资本" for t in v["terms"])


def test_short_that_drops_a_meaning_flipping_qualifier_is_rejected():
    from app.plain import _short_ok
    src = "私募基金管理人登记：未登记（它是持牌机构，不需要私募登记）"
    assert not _short_ok("未做私募管理人登记", src, "")
    assert _short_ok("持牌机构，不需要私募登记", src, "")


@pytest.mark.parametrize("changed_identity", ["case", "version"])
def test_glance_replay_stays_with_its_case_and_version(tmp_path, changed_identity):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    live, _ = build_glance(case, case.versions[0], gen(tmp_path))
    assert live.mode == "model"
    replay_llm = FakeLLM([], tmp_path)
    replay_llm.mode = "replay"
    same, _ = build_glance(case, case.versions[0], replay_llm)
    assert same.mode == "replay" and same.short == live.short
    other = case.model_copy(deep=True)
    if changed_identity == "case":
        other.id = "another-synthetic-case"
    else:
        other.current = other.versions[0].no = 2
    result, _ = build_glance(other, other.versions[0], replay_llm)
    assert result.mode == "template" and result.short == {}
    assert not replay_llm.calls


def test_short_moved_to_the_wrong_item_is_rejected():
    # 实测模型把"持牌名单"那条的短句错放到了"私募登记"那条上
    from app.plain import _short_ok
    amac_src = "私募基金管理人登记：已登记：P1021593，私募证券投资基金管理人，在管基金 21 只；协会公示了它的诚信信息"
    assert not _short_ok("四类持牌名单都没它", amac_src, "")
    assert _short_ok("已登记私募，有诚信信息", amac_src, "")
