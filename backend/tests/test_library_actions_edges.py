"""Conflicting snapshot identities and mixed questions cannot trigger auto-save."""
import pytest

from app import config
from app.assistant import answer
from app.library_actions import save_target
from app.models import ChatIn
from tests.test_library_actions import explained, explanation, term
from tests.test_llm_assistant import FakeLLM


@pytest.mark.parametrize("second_name,second_plain", [
    ("存续", "另一条冲突的解释。"),
    ("注销", "另一条冲突的解释。"),
    ("注销", "第一条解释的原始快照。"),
])
@pytest.mark.parametrize("command", ["收藏这个词", "收藏存续", "把刚才的解释记到我的知识库里", "将存续记录到知识库中"])
def test_conflicting_duplicate_ids_never_auto_save_after_name_selection(
        second_name, second_plain, command, tmp_path):
    case = explained()
    case.chat[-1] = explanation([
        term("status", "存续", "第一条解释的原始快照。"),
        term("status", second_name, second_plain),
    ])
    original = case.model_dump_json()
    gateway = FakeLLM([], tmp_path)

    result = answer(case, ChatIn(text=command), gateway, version_no=1, max_context_chars=1)

    assert not gateway.calls
    assert case.model_dump_json() == original
    assert result.library_action is None or not result.library_action.auto_save, (
        "A shown name cannot resolve conflicting snapshots sharing the same library ID"
    )


@pytest.mark.parametrize("question", [
    "收藏实缴资本公司有没有处罚",
    "保存实缴资本企业资金链有没有问题",
    "收藏实缴资本和看看公司有没有处罚",
    "收藏实缴资本和公司风险有多大",
    "把刚才的解释记到我的知识库里，再查这家公司的处罚",
    "把实缴资本和公司风险有多大记到知识库里",
])
def test_unpunctuated_save_plus_company_question_keeps_normal_answer_route(question, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CASE_MEMORY_ENABLED", False)
    case = explained()
    original = case.model_dump_json()
    gateway = FakeLLM([], tmp_path)

    result = answer(case, ChatIn(text=question), gateway, version_no=1, max_context_chars=1)

    assert case.model_dump_json() == original
    assert result.library_action is None
    assert result.answer_kind != "library_action", (
        "The company question must not be consumed by a missing-term save response"
    )
    assert save_target(question) is None
    assert result.error_code == "context_budget" or result.answer_kind == "clarification"
