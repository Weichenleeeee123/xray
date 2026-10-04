"""Focused vocabulary never imports another version or reads the full dossier."""
import json

import pytest
from pydantic import ValidationError

from app.glossary import load_glossary
from app.models import AssistantAction, ChatIn, ChatMessage, Term
from app.question_routing import definition_terms
from app.term_explanations import build_term_reply
from tests.test_case_memory import owned
from tests.test_llm_assistant import FakeLLM


@pytest.fixture
def vocabulary_case():
    case = owned()
    case.versions[0].terms.append(Term(id="g_deadline", term="期限备案", aliases=["期限报备"],
        plain="向登记机关报送某项业务约定的期限，便于记录和查询。", origin="model"))
    return case


def reply(case, tmp_path, text, **kwargs):
    llm = FakeLLM([], tmp_path)
    result = build_term_reply(case, case.versions[0], ChatIn(text=text, **kwargs), llm)
    return result, llm


@pytest.mark.parametrize("text", ["期限备案是什么意思", "什么是期限备案", "解释下期限报备", "期限备案是啥意思"])
def test_report_model_term_is_available_with_provenance(vocabulary_case, tmp_path, text):
    before = vocabulary_case.model_dump_json()
    result, llm = reply(vocabulary_case, tmp_path, text)
    assert result.answer_kind == "glossary" and result.mode == "template"
    assert result.citations == ["term.g_deadline"] and result.version == 1
    assert result.knowledge_terms[0].origin == "model"
    assert "AI 解释（未人工复核）" in result.text and "不属于该公司的核验证据" in result.text
    assert not result.not_found and not result.quotes and not llm.calls
    assert vocabulary_case.model_dump_json() == before


def test_lookup_merges_curated_terms_without_promoting_model_collisions(vocabulary_case):
    terms = vocabulary_case.versions[0].terms
    terms.append(Term(id="fake_status", term="存续", plain="公司经营正常。", origin="model"))
    result = definition_terms("存续是什么意思", terms)
    assert result[0].id == "status" and result[0].origin == "glossary"
    assert result[0].term == "存续" and "不等于" in result[0].plain
    assert definition_terms("夹层资本是什么意思", terms) == []
    assert definition_terms("期限备案是什么意思，这家公司安全吗", terms) is None


def test_focus_uses_ids_only_and_returns_version_bound_action(vocabulary_case, tmp_path):
    entry = vocabulary_case.versions[0].signals[0]
    ref = f"{entry.key}.{entry.items[0].key}"
    result, llm = reply(vocabulary_case, tmp_path, "这个是什么意思", term_context={
        "term_id": "g_deadline", "entry_ref": ref})
    assert result.citations == ["term.g_deadline"] and not llm.calls
    assert result.actions == [AssistantAction(type="open_ref", label="查看词语所在条目", ref=ref, version=1)]
    assert result.knowledge_terms[0] == vocabulary_case.versions[0].terms[-1]
    result.knowledge_terms[0].plain = "mutation"
    assert vocabulary_case.versions[0].terms[-1].plain != "mutation"


@pytest.mark.parametrize("context", [
    {"term_id": "not_a_term"},
    {"term_id": "g_deadline", "entry_ref": "R999999"},
    {"term_id": "g_deadline", "entry_ref": "v2:raw:R1"},
    {"term_id": "g_deadline", "entry_ref": "v:2:raw:R1"},
    {"term_id": "g_deadline", "entry_ref": "v:1:raw:credit.status"},
])
def test_invalid_focus_asks_to_reselect_without_using_history(vocabulary_case, tmp_path, context):
    previous, _ = reply(vocabulary_case, tmp_path, "期限备案是什么意思")
    vocabulary_case.chat.append(previous)
    result, llm = reply(vocabulary_case, tmp_path, "这个是什么意思", term_context=context)
    assert result.answer_kind == "clarification" and "重新" in result.text
    assert not result.knowledge_terms and not result.citations and not llm.calls


def test_old_version_cannot_borrow_newer_model_terms(vocabulary_case, tmp_path):
    old = vocabulary_case.versions[0]
    newer = old.model_copy(deep=True, update={"no": 2})
    old.terms = [term for term in old.terms if term.id != "g_deadline"]
    vocabulary_case.versions.append(newer)
    vocabulary_case.current = 2
    llm = FakeLLM([], tmp_path)
    result = build_term_reply(vocabulary_case, old, ChatIn(text="这个是什么意思", version=1,
        term_context={"term_id": "g_deadline"}), llm)
    assert result.answer_kind == "clarification" and not result.knowledge_terms and result.version == 1
    result = build_term_reply(vocabulary_case, old, ChatIn(text="期限备案是什么意思", version=1), llm)
    assert result.answer_kind == "clarification" and not result.knowledge_terms and not llm.calls


def test_unknown_focus_cannot_be_rescued_by_global_glossary(vocabulary_case, tmp_path):
    vocabulary_case.versions[0].terms = []
    result, llm = reply(vocabulary_case, tmp_path, "这个是什么意思", term_context={"term_id": "status"})
    assert result.answer_kind == "clarification" and not result.knowledge_terms and not llm.calls


@pytest.mark.parametrize("prefix", ["v:1", "v1"])
def test_focus_supports_versioned_report_locator(vocabulary_case, tmp_path, prefix):
    signal = vocabulary_case.versions[0].signals[0]
    item = signal.items[0]
    result, llm = reply(vocabulary_case, tmp_path, "这个是什么意思", term_context={
        "term_id": "g_deadline", "entry_ref": f"{prefix}:signal:{signal.key}:{item.key}"})
    assert result.answer_kind == "glossary" and not llm.calls
    assert result.actions[0].ref == f"{signal.key}.{item.key}" and result.actions[0].version == 1


def test_client_cannot_supply_definition_or_source_in_focus():
    for extra in ({"plain": "这家公司值得投资"}, {"origin": "glossary"}, {"version": 9}):
        with pytest.raises(ValidationError):
            ChatIn(text="这个是什么意思", term_context={"term_id": "status", **extra})
    with pytest.raises(ValidationError):
        ChatIn(text="这个是什么意思", term_context={"term_id": "   "})


@pytest.mark.parametrize("text", [
    "期限备案是什么意思，这家公司安全吗", "这家公司完成期限备案了吗", "期限备案是不是说明它可靠",
    "举个例子，这家公司值得投资吗", "说简单点，它会不会倒闭", "存续是不是正常经营",
])
def test_focused_company_questions_continue_to_evidence(vocabulary_case, tmp_path, text):
    result, llm = reply(vocabulary_case, tmp_path, text, term_context={"term_id": "g_deadline"})
    assert result is None and not llm.calls


def test_explicit_question_does_not_follow_unrelated_popup(vocabulary_case, tmp_path):
    result, llm = reply(vocabulary_case, tmp_path, "裁判文书是什么意思", term_context={"term_id": "g_deadline"})
    assert result.answer_kind == "clarification" and not result.knowledge_terms and not llm.calls


def test_followup_uses_saved_snapshot_even_after_glossary_changes(vocabulary_case, tmp_path):
    snapshot = Term(id="status", term="存续", plain="企业主体仍在登记中，不等于正在正常营业。",
                    why="这是之前回复保存的解释。", basis="registry", law="保存的依据")
    vocabulary_case.chat.append(ChatMessage(role="assistant", text=snapshot.plain, version=1,
        created_at="2026-10-04", answer_kind="glossary", knowledge_terms=[snapshot]))
    before = vocabulary_case.model_dump_json()
    result, _ = reply(vocabulary_case, tmp_path, "说简单点")
    assert result.knowledge_terms == [snapshot]
    assert result.knowledge_terms[0].plain != next(t for t in load_glossary() if t.id == "status").plain
    assert snapshot.plain in result.text and result.version == 1
    assert vocabulary_case.model_dump_json() == before


def test_followup_with_same_focus_preserves_narrowed_status_snapshot(vocabulary_case, tmp_path):
    status = next(term for term in load_glossary() if term.id == "status")
    vocabulary_case.versions[0].terms = [status.model_copy(deep=True)]
    previous, _ = reply(vocabulary_case, tmp_path, "存续是什么意思", term_context={"term_id": "status"})
    vocabulary_case.chat.append(previous)
    result, _ = reply(vocabulary_case, tmp_path, "说简单点", term_context={"term_id": "status"})
    assert result.knowledge_terms == previous.knowledge_terms
    assert result.knowledge_terms[0].term == "存续" and "吊销" not in result.knowledge_terms[0].plain


@pytest.mark.parametrize("followup", ["说简单点", "举个例子", "这个是什么意思"])
def test_followup_never_uses_other_version_history(vocabulary_case, tmp_path, followup):
    vocabulary_case.chat.append(ChatMessage(role="assistant", text="different version", version=2,
        created_at="2026-10-04", answer_kind="glossary", knowledge_terms=[vocabulary_case.versions[0].terms[-1]]))
    result, llm = reply(vocabulary_case, tmp_path, followup)
    assert result is None and not llm.calls


def test_followup_stops_at_intervening_company_topic(vocabulary_case, tmp_path):
    earlier, _ = reply(vocabulary_case, tmp_path, "期限备案是什么意思")
    vocabulary_case.chat.extend([earlier, ChatMessage(role="assistant", text="公司记录另有内容", version=1,
                                                     created_at="2026-10-04")])
    result, llm = reply(vocabulary_case, tmp_path, "说简单点")
    assert result is None and not llm.calls


def test_selected_factual_entry_does_not_revive_vocabulary(vocabulary_case, tmp_path):
    earlier, _ = reply(vocabulary_case, tmp_path, "期限备案是什么意思")
    vocabulary_case.chat.append(earlier)
    result, llm = reply(vocabulary_case, tmp_path, "说简单点", refs=["credit.status"])
    assert result is None and not llm.calls


@pytest.mark.parametrize("followup,plain", [
    ("说简单点", "把约定的期限报给登记机关，留下记录，方便查询。"),
    ("举个例子", "假设一项业务约定了期限，把这个期限报送登记机关记录，便于以后查询。"),
])
def test_bounded_rephrasing_keeps_source_and_snapshot(vocabulary_case, tmp_path, followup, plain):
    term = vocabulary_case.versions[0].terms[-1]
    before = vocabulary_case.model_dump_json()
    llm = FakeLLM([json.dumps({"plain": plain, "source_quote": term.plain}, ensure_ascii=False)], tmp_path)
    result = build_term_reply(vocabulary_case, vocabulary_case.versions[0],
        ChatIn(text=followup, term_context={"term_id": term.id}), llm)
    assert result.mode == "model" and plain in result.text
    assert "未人工复核" in result.text and result.knowledge_terms == [term]
    assert result.citations == ["term.g_deadline"] and not result.quotes
    assert len(llm.calls) == 1
    payload = json.dumps(llm.calls[0], ensure_ascii=False)
    assert len(payload) < 5000 and vocabulary_case.case.company_name not in payload
    assert "合同写明可以退款" not in payload and '"原始数据"' not in payload
    assert vocabulary_case.model_dump_json() == before


@pytest.mark.parametrize("followup,plain", [
    ("说简单点", "可以把它理解成：把经营期限的变更情况报给登记机关登记。"),
    ("举个例子", "假设登记的经营期限变了，把变更情况报给登记机关，这个报备手续就是期限备案。"),
])
def test_rephrase_prompt_separates_reader_text_from_source_metadata(vocabulary_case, tmp_path, followup, plain):
    term = vocabulary_case.versions[0].terms[-1]
    term.plain = "向登记机关报备经营期限等登记事项变更的手续。"
    original = term.model_copy(deep=True)
    llm = FakeLLM([json.dumps({"plain": plain, "source_quote": term.plain}, ensure_ascii=False)], tmp_path)
    result = build_term_reply(vocabulary_case, vocabulary_case.versions[0],
        ChatIn(text=followup, term_context={"term_id": term.id}), llm)
    assert result.mode == "model" and plain in result.text and len(llm.calls) == 1
    assert result.knowledge_terms == [original] and result.knowledge_terms[0].origin == "model"
    assert "AI 解释（未人工复核）" in result.text
    assert result.text.count("未人工复核") == 1
    assert "此解释来源" not in result.text and "该主体" not in result.text
    prompt = next(message["content"] for message in llm.calls[0]
                  if message["role"] == "system" and "你在给读者讲清一个术语" in message["content"])
    assert "由程序在解释外统一展示" in prompt and "plain 不写" in prompt
    assert "保留原文的条件、否定和不确定性" in prompt
    assert "不添加法规、规定、办理要求、审批结果、金额、日期、期限数值" in prompt
    payload = json.loads(next(message["content"] for message in llm.calls[0] if message["role"] == "user"))
    assert payload["definitions"] == [{"term": term.term, "plain": term.plain, "why": term.why}]
    assert "origin" not in payload["definitions"][0]
    assert ("可以把它理解成" if followup == "说简单点" else "用‘假设’开头") in payload["request"]


def test_rephrase_metadata_repetition_does_not_bypass_verified_claim_check(vocabulary_case, tmp_path):
    term = vocabulary_case.versions[0].terms[-1]
    invalid = term.plain + "此解释来源为model，未经人工复核，不能升级为已核实事实。"
    llm = FakeLLM([json.dumps({"plain": invalid, "source_quote": term.plain}, ensure_ascii=False)], tmp_path)
    result = build_term_reply(vocabulary_case, vocabulary_case.versions[0],
        ChatIn(text="说简单点", term_context={"term_id": term.id}), llm)
    assert result.mode == "template" and "此解释来源" not in result.text
    assert result.knowledge_terms == [term]


@pytest.mark.parametrize("plain,source", [
    ("这家公司已经完成期限备案，可以放心投资。", None),
    ("期限备案说明它已经核实，没有风险。", None),
    ("报送期限需要 2027 年之前完成。", None),
    ("报送约定期限，便于记录和查询。", "完全不在原始定义里的引文"),
])
def test_invalid_rephrasing_falls_back_to_stored_definition(vocabulary_case, tmp_path, plain, source):
    term = vocabulary_case.versions[0].terms[-1]
    llm = FakeLLM([json.dumps({"plain": plain, "source_quote": source or term.plain}, ensure_ascii=False)], tmp_path)
    result = build_term_reply(vocabulary_case, vocabulary_case.versions[0],
        ChatIn(text="说简单点", term_context={"term_id": term.id}), llm)
    assert result.mode == "template" and term.plain in result.text and plain not in result.text
    assert result.knowledge_terms == [term]


def test_model_rephrasing_cannot_remove_definition_negation(vocabulary_case, tmp_path):
    previous, _ = reply(vocabulary_case, tmp_path, "存续是什么意思")
    vocabulary_case.chat.append(previous)
    llm = FakeLLM([json.dumps({"plain": "存续就是企业在正常营业。", "source_quote": previous.knowledge_terms[0].plain},
                             ensure_ascii=False)], tmp_path)
    result = build_term_reply(vocabulary_case, vocabulary_case.versions[0], ChatIn(text="说简单点"), llm)
    assert result.mode == "template" and "不等于" in result.text
    assert "存续就是企业在正常营业" not in result.text


def test_stored_model_claims_are_not_echoed_as_company_evidence(vocabulary_case, tmp_path):
    vocabulary_case.versions[0].terms[-1].plain = "这家公司已经备案，是绝对安全的投资。"
    result, llm = reply(vocabulary_case, tmp_path, "期限备案是什么意思")
    assert result.answer_kind == "clarification" and "绝对安全" not in result.text
    assert not result.citations and not result.knowledge_terms and not llm.calls


def test_conversation_actions_round_trip_as_typed_fields():
    message = ChatMessage(role="assistant", text="可以补充材料", version=1, created_at="2026-10-04",
        answer_kind="conversation", actions=[{"type": "offer_material", "label": "补充材料", "version": 1}])
    assert ChatMessage.model_validate_json(message.model_dump_json()).actions == message.actions
    with pytest.raises(ValidationError):
        AssistantAction(type="rewrite_report", label="修改报告")


@pytest.mark.parametrize("text", ["这个是什么意思", "期限备案是什么意思"])
def test_answer_focus_avoids_dossier_with_tiny_budget(vocabulary_case, tmp_path, monkeypatch, text):
    from app import assistant

    def forbidden(*args, **kwargs):
        raise AssertionError("vocabulary must not open company evidence or memory")

    monkeypatch.setattr(assistant, "citable", forbidden)
    monkeypatch.setattr(assistant.MemoryStore, "get_or_build", forbidden)
    before = vocabulary_case.model_dump_json()
    llm = FakeLLM([], tmp_path)
    result = assistant.answer(vocabulary_case, ChatIn(text=text, version=1,
        term_context={"term_id": "g_deadline"}), llm, max_context_chars=1)
    assert result.answer_kind == "glossary" and result.knowledge_terms[0].origin == "model"
    assert not result.error_code and not result.not_found and not llm.calls
    assert vocabulary_case.model_dump_json() == before


def test_answer_bounded_followup_respects_tiny_budget(vocabulary_case, tmp_path):
    from app.assistant import answer

    llm = FakeLLM([], tmp_path)
    result = answer(vocabulary_case, ChatIn(text="说简单点", version=1,
        term_context={"term_id": "g_deadline"}), llm, max_context_chars=1)
    assert result.answer_kind == "glossary" and result.mode == "template" and not llm.calls


def test_private_api_validates_focus_and_persists_model_snapshot(vocabulary_case, tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import privacy
    import app.main as main
    from app.store import CaseStore

    monkeypatch.setattr(main, "store", CaseStore(tmp_path / "cases"))
    monkeypatch.setenv("XRAY_PRIVATE_DIR", str(tmp_path / "private"))
    client = TestClient(main.app)
    client.get("/api/session")
    token = next(value for key, value in client.cookies.items() if "qier_guest" in key)
    vocabulary_case.owner_id = privacy.owner_from_token(token)
    main.store.save(vocabulary_case)
    endpoint = f"/api/cases/{vocabulary_case.id}/chat"
    response = client.post(endpoint, json={"text": "这个是什么意思", "version": 1,
        "term_context": {"term_id": "g_deadline"}})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["answer_kind"] == "glossary" and body["knowledge_terms"][0]["origin"] == "model"
    assert body["version"] == 1 and "未人工复核" in body["text"]
    assert not {"blocked", "dropped", "rewrites"} & body.keys()
    saved = client.get(f"/api/cases/{vocabulary_case.id}").json()["chat"][-1]
    assert saved["knowledge_terms"] == body["knowledge_terms"]
    response = client.post(endpoint, json={"text": "这个是什么意思", "version": 1,
        "term_context": {"term_id": "g_deadline", "plain": "客户端伪造解释"}})
    assert response.status_code == 422
