import json

import pytest

from app.assistant import answer, citable, context
from app.models import ChatIn
from tests.helpers import DEMO_COMPANY, add, make_case
from tests.test_llm_assistant import FakeLLM


@pytest.fixture
def case():
    return make_case(DEMO_COMPANY, "保本保息\n年化 9%\n随时可退")


def test_unknown_record_drops_fact_not_just_footnote(case, tmp_path):
    out = {"answer": "它上过新闻 [R999]。", "citations": ["R999"]}
    result = answer(case, ChatIn(text="它上过新闻吗"), FakeLLM([json.dumps(out)], tmp_path))
    assert "它上过新闻" not in result.text
    assert result.not_found and result.suggest


def test_fake_quote_drops_associated_fact(case, tmp_path):
    raw = next(r for r in case.raw if r.source_id == "material")
    out = {"answer": f"央行批准 [{raw.id}]。", "citations": [raw.id],
           "quotes": [{"ref": raw.id, "text": "央行批准"}]}
    result = answer(case, ChatIn(text="有没有批准"), FakeLLM([json.dumps(out)], tmp_path))
    assert "央行批准" not in result.text and result.not_found


def test_quote_must_be_verbatim_not_whitespace_normalized(case, tmp_path):
    raw = next(r for r in case.raw if r.source_id == "material")
    out = {"answer": f"材料里这样写 [{raw.id}]。", "citations": [raw.id],
           "quotes": [{"ref": raw.id, "text": "保本 保息"}]}
    result = answer(case, ChatIn(text="材料说了什么"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and not result.quotes


def test_selected_old_version_is_not_replaced(case, tmp_path):
    old = case.versions[0].no
    updated = add(case, "reply", "请转账到个人账户，户名：张某明")
    result = answer(updated, ChatIn(text="这条什么意思", refs=[f"v:{old}:assertion:A2"]), FakeLLM([], tmp_path))
    assert result.version == old and "A2" in result.citations


def test_invalid_or_mixed_version_refs_are_not_silently_ignored(case, tmp_path):
    updated = add(case, "reply", "户名：张某明")
    llm = FakeLLM(["not called"], tmp_path)
    result = answer(updated, ChatIn(text="解释它", refs=["v:99:assertion:A2"]), llm)
    assert result.not_found and not llm.calls and result.mode == "guard"
    result = answer(updated, ChatIn(text="解释它", refs=["v:1:assertion:A2", "v:2:assertion:A2"]), llm)
    assert result.not_found and not llm.calls


def test_context_does_not_silently_truncate_raw(case):
    raw = next(r for r in case.raw if r.source_id == "material")
    raw.content = "开头" + "很长的材料" * 1000 + "末尾关键条款"
    assert "末尾关键条款" in json.dumps(context(case, case.versions[0]), ensure_ascii=False)


def test_source_catalog_alone_is_not_raw_evidence(case, tmp_path):
    assert "registry" not in citable(case, case.versions[0])
    result = answer(case, ChatIn(text="它有处罚吗"), FakeLLM([
        '{"answer":"它已被罚款 [registry]。","citations":["registry"]}'], tmp_path))
    assert result.not_found and "已被罚款" not in result.text


def test_signal_keys_are_namespaced():
    unknown = make_case("合成未知企业有限公司", "")
    valid = citable(unknown, unknown.versions[0])
    assert "registry" not in valid
    assert "finance.registry" in valid and "credit.registry" in valid


def test_valid_quote_cannot_override_rule_verdict(case, tmp_path):
    out = {"answer": "收益承诺与记录相符，年化 99% [A2]。", "citations": ["A2"]}
    result = answer(case, ChatIn(text="收益承诺如何"), FakeLLM([json.dumps(out)], tmp_path))
    assert "年化 99%" not in result.text and "收益承诺与记录相符" not in result.text
    assert result.not_found


def test_segment_schema_drops_only_unsupported_segment(case, tmp_path):
    out = {"segments": [
        {"text": "报告标为不合规承诺。", "citations": ["A2"]},
        {"text": "公司老板在国外。", "citations": ["R999"]}]}
    result = answer(case, ChatIn(text="有什么发现"), FakeLLM([json.dumps(out)], tmp_path))
    assert "不合规承诺" in result.text and "老板在国外" not in result.text
    assert "A2" in result.citations and result.dropped > 0


def test_context_budget_does_not_send_incomplete_case(case, tmp_path):
    llm = FakeLLM(['{"answer":"fake"}'], tmp_path)
    result = answer(case, ChatIn(text="它靠谱吗"), llm, max_context_chars=10)
    assert result.not_found and not llm.calls and "超出" in result.text
