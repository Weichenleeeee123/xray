"""Synthetic quote-repair regressions; no network or private material."""
import json

import pytest

from app.assistant import UNKNOWN, answer
from app.models import ChatIn
from tests.helpers import DEMO_COMPANY, make_case
from tests.test_llm_assistant import FakeLLM


LEAF = "责令改正，给予警告，并处36万元罚款"
BAD_QUOTE = "企业处罚结果：" + LEAF


@pytest.fixture
def record_case():
    case = make_case(DEMO_COMPANY, "保本保息")
    raw = next(r for r in case.raw if r.source_id == "material")
    raw.content = {"企业处罚结果": LEAF, "详情": "首部" + "完整材料" * 500 + "末尾核对标记"}
    raw.note = "此处是元数据说明，不是材料原文"
    return case, raw.id


def response(ref, quote=LEAF, text="记录写明给予警告，并处36万元罚款。", **extra):
    return json.dumps({"segments": [{"text": text, "citations": [ref],
                        "quotes": [{"ref": ref, "text": quote}]}], **extra}, ensure_ascii=False)


def test_bad_key_prefix_is_rewritten_to_leaf_with_full_context(record_case, tmp_path):
    case, ref = record_case
    before = case.model_dump_json()
    llm = FakeLLM([response(ref, BAD_QUOTE), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么", refs=[ref]), llm)
    assert not result.not_found and result.mode == "model" and result.rewrites == 1
    assert result.quotes[0].text == LEAF and BAD_QUOTE not in result.model_dump_json()
    assert result.dropped > 0 and len(llm.calls) == 2
    assert llm.calls[1][:len(llm.calls[0])] == llm.calls[0]
    assert "末尾核对标记" in json.dumps(llm.calls[1], ensure_ascii=False)
    feedback = llm.calls[1][-1]["content"]
    assert "字段名" in feedback and "note" in feedback and "数字" in feedback
    assert case.model_dump_json() == before


def test_invalid_quotes_exhaust_exactly_two_rewrites(record_case, tmp_path):
    case, ref = record_case
    llm = FakeLLM([response(ref, BAD_QUOTE)] * 3 + [response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么", refs=[ref]), llm)
    assert result.text == UNKNOWN and result.not_found and result.dropped >= 6
    assert result.rewrites == 2 and len(llm.calls) == 3 and len(llm.replies) == 1
    assert not result.quotes and not result.citations


def test_gateway_failure_after_rejected_quote_stays_unknown(record_case, tmp_path):
    case, ref = record_case
    llm = FakeLLM([response(ref, BAD_QUOTE)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么", refs=[ref]), llm)
    assert result.text == UNKNOWN and result.not_found and result.mode == "guard"
    assert result.dropped > 0 and result.rewrites == 1 and len(llm.calls) == 2
    assert not result.quotes and not result.citations


def test_explicit_unknown_is_not_rewritten(record_case, tmp_path):
    case, ref = record_case
    llm = FakeLLM([response(ref, BAD_QUOTE, not_found=True), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert result.not_found and result.dropped > 0 and result.rewrites == 0
    assert len(llm.calls) == 1


def test_partially_valid_answer_repairs_rejected_core_fact(record_case, tmp_path):
    case, ref = record_case
    before = case.model_dump_json()
    payload = json.loads(response(ref, BAD_QUOTE))
    payload["segments"].append({"text": "报告标为不合规承诺。", "citations": ["A2"]})
    llm = FakeLLM([json.dumps(payload), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert "36万元罚款" in result.text and result.quotes[0].text == LEAF
    assert not result.not_found and result.rewrites == 1 and len(llm.calls) == 2
    assert result.dropped > 0 and BAD_QUOTE not in result.model_dump_json()
    assert llm.calls[1][:len(llm.calls[0])] == llm.calls[0]
    assert case.model_dump_json() == before


@pytest.mark.parametrize("followups", ["unavailable", "invalid", "overreach", "unknown"])
def test_partial_fallback_survives_failed_repair(record_case, tmp_path, followups):
    case, ref = record_case
    payload = json.loads(response(ref, BAD_QUOTE))
    payload["segments"].append({"text": "报告标为不合规承诺。", "citations": ["A2"]})
    replies = {
        "unavailable": [],
        "invalid": [response(ref, BAD_QUOTE)] * 2,
        "overreach": [response(ref, text="钱很可能拿不回来。")] * 2,
        "unknown": ['{"not_found":true,"segments":[]}'],
    }
    llm = FakeLLM([json.dumps(payload), *replies[followups]], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert result.text == "报告标为不合规承诺。 [A2]" and not result.not_found
    assert result.citations == ["A2"] and not result.quotes and result.dropped >= 2
    assert result.mode == "model" and result.rewrites in (1, 2)
    assert len(llm.calls) == (2 if followups in ("unavailable", "unknown") else 3)


def test_partial_repair_never_exceeds_shared_budget(record_case, tmp_path):
    case, ref = record_case
    partial = json.loads(response(ref, BAD_QUOTE))
    partial["segments"].append({"text": "报告标为不合规承诺。", "citations": ["A2"]})
    llm = FakeLLM([response(ref, text="钱很可能拿不回来。"), json.dumps(partial),
                   response(ref, BAD_QUOTE), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert result.text == "报告标为不合规承诺。 [A2]" and result.rewrites == 2
    assert len(llm.calls) == 3 and len(llm.replies) == 1 and result.dropped >= 4


def test_partial_explicit_unknown_does_not_trigger_repair(record_case, tmp_path):
    case, ref = record_case
    partial = json.loads(response(ref, BAD_QUOTE, not_found=True))
    partial["segments"].append({"text": "报告标为不合规承诺。", "citations": ["A2"]})
    llm = FakeLLM([json.dumps(partial), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert result.text == "报告标为不合规承诺。 [A2]" and result.rewrites == 0
    assert len(llm.calls) == 1


def test_grounding_and_overreach_share_rewrite_budget(record_case, tmp_path):
    case, ref = record_case
    llm = FakeLLM([response(ref, text="钱很可能拿不回来。"),
                   response(ref, BAD_QUOTE), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert not result.not_found and result.rewrites == 2 and len(llm.calls) == 3
    assert result.blocked == ["很可能"] and result.dropped > 0
    assert result.quotes[0].text == LEAF


@pytest.mark.parametrize("bad_followup", [
    {"quote": "此处是元数据说明，不是材料原文"},
    {"text": "记录写明罚款99万元。"},
    {"text": "收益承诺与记录相符。"},
])
def test_rewrite_still_checks_metadata_numbers_and_rule_states(record_case, tmp_path, bad_followup):
    case, ref = record_case
    invalid = json.loads(response(ref, **bad_followup))
    invalid["segments"][0]["citations"].append("A2")
    llm = FakeLLM([response(ref, BAD_QUOTE), json.dumps(invalid), response(ref)], tmp_path)
    result = answer(case, ChatIn(text="记录写了什么"), llm)
    assert result.rewrites == 2 and len(llm.calls) == 3 and not result.not_found
    assert result.quotes[0].text == LEAF and "99" not in result.text and "与记录相符" not in result.text


def test_overreach_after_grounding_failure_cannot_return_template_as_repaired(record_case, tmp_path):
    case, ref = record_case
    llm = FakeLLM([response(ref, BAD_QUOTE)] + [response(ref, text="钱很可能拿不回来。")] * 2,
                  tmp_path)
    result = answer(case, ChatIn(text="记录写了什么", refs=[ref]), llm)
    assert result.text == UNKNOWN and result.not_found and result.mode == "guard"
    assert result.rewrites == 2 and result.dropped > 0 and len(llm.calls) == 3


def test_date_repair_feedback_identifies_exact_rejected_token_and_source_tokens(record_case, tmp_path):
    case, ref = record_case
    raw = next(r for r in case.raw if r.id == ref)
    raw.content["决定日期"] = "2024-09-13"
    raw.content["文书类别"] = "行政处罚决定"
    bad_text = "2024年9月13日作出处罚，并处36万元罚款。"
    payload = json.loads(response(ref, text=bad_text))
    payload["segments"].append({"text": "文书类别为行政处罚决定。", "citations": [ref]})
    good = response(ref, text="2024-09-13作出处罚，并处36万元罚款。")
    before = case.model_dump_json()
    llm = FakeLLM([json.dumps(payload), good], tmp_path)
    result = answer(case, ChatIn(text="哪天处罚，罚款多少"), llm)
    assert "2024-09-13" in result.text and "36万元罚款" in result.text
    assert result.rewrites == 1 and result.dropped == 1 and len(llm.calls) == 2
    feedback = llm.calls[1][-1]["content"]
    assert "程序校验诊断（JSON）：" in feedback, "repair feedback must identify the rejected numeric token"
    diagnostics = json.loads(feedback.split("程序校验诊断（JSON）：", 1)[1])
    assert diagnostics[0]["text"] == bad_text
    assert diagnostics[0]["unsupported_numbers"] == ["9"]
    assert set(diagnostics[0]["supported_numbers_by_ref"][ref]) == {"2024", "09", "13", "36"}
    assert "文书类别为行政处罚决定。" in feedback
    assert llm.calls[1][:len(llm.calls[0])] == llm.calls[0]
    assert case.model_dump_json() == before


def test_diagnostics_do_not_normalize_unsupported_date_numbers(record_case, tmp_path):
    case, ref = record_case
    next(r for r in case.raw if r.id == ref).content["决定日期"] = "2024-09-13"
    bad = response(ref, text="2024年9月13日作出处罚，并处36万元罚款。")
    llm = FakeLLM([bad] * 3, tmp_path)
    result = answer(case, ChatIn(text="哪天处罚，罚款多少"), llm)
    assert result.text == UNKNOWN and result.not_found and result.dropped == 3
    assert len(llm.calls) == 3 and result.rewrites == 2
