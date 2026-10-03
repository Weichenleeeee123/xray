"""Reviewed explanations are concepts, never shortcuts to a company verdict."""
import pytest

from app.glossary import find_terms, load_glossary, term_ref


def entry(term_id):
    return next(term for term in load_glossary() if term.id == term_id)


@pytest.mark.parametrize("question", ["什么是存续", "存续是什么意思", "请解释登记状态"])
def test_registration_terms_keep_stable_reference(question):
    terms = find_terms(question)
    assert [term_ref(term) for term in terms] == ["term.status"]


def test_registration_definition_is_not_an_operating_health_claim():
    term = entry("status")
    assert "主体仍然存在" in term.plain
    assert "不等于它正在正常营业" in term.plain
    assert "不等于已经注销" in term.plain
    assert "存续是正常经营" not in term.plain
    assert "还要分别核实" in term.why
    assert term.basis == "registry" and "登记管理条例" in term.law


@pytest.mark.parametrize("question", ["裁判文书是什么意思", "什么是裁判文书", "解释司法裁判文书"])
def test_judgment_documents_have_reviewed_concept_and_reference(question):
    terms = find_terms(question)
    assert [term_ref(term) for term in terms] == ["term.judgment_document"]
    term = terms[0]
    assert "判决书" in term.plain and "裁定书" in term.plain
    assert "不等于它败诉" in term.why
    assert "当事人角色" in term.why and "生效情况" in term.why
    assert "最高人民法院" in term.law
    assert term.origin == "glossary"


def test_security_records_do_not_imply_liquidity_trouble():
    pledge, mortgage = entry("pledge"), entry("mortgage")
    assert "不能仅凭出质条数判断" in pledge.why
    assert "不等于资金紧张" in mortgage.why
    assert "其他主体" in mortgage.why
    assert "出质多，可能说明股东缺钱" not in pledge.why
    assert "抵押多，说明公司在靠借钱周转" not in mortgage.why
    assert "民法典" in pledge.law and "民法典" in mortgage.law


def test_lookup_does_not_rewrite_a_previously_saved_term():
    # Saved version content remains historical. Current glossary lookup returns
    # an independent definition; it must not mutate the version's serialized data.
    from app.models import Term

    historical = Term(id="status", term="登记状态", plain="历史版本的登记状态说明。")
    snapshot = historical.model_dump()
    current = find_terms("什么是存续")[0]
    assert current.plain != historical.plain
    assert historical.model_dump() == snapshot
