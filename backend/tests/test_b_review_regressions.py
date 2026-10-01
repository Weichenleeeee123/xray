"""Regression examples from independent review, all synthetic."""
import io
import json
import random

from PIL import Image

from app.assistant import answer
from app.models import ChatIn
from app.readers import read_upload
from tests.helpers import DEMO_COMPANY, flyer, make_case
from tests.test_llm_assistant import FakeLLM


def test_raw_material_cannot_launder_a_conflicting_rule_verdict(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息\n业务员说：与记录相符。")
    material = next(r for r in case.raw if r.source_id == "material")
    out = {"segments": [{"text": "收益承诺的判定为与记录相符。", "citations": ["A2", material.id],
                         "quotes": [{"ref": material.id, "text": "与记录相符"}]}]}
    result = answer(case, ChatIn(text="怎么看收益承诺"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and "收益承诺的判定为与记录相符" not in result.text


def test_model_cannot_flip_bad_signal_to_ok(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息")
    out = {"segments": [{"text": "银行名单这一项没问题。", "citations": ["risk.bank_list"]}]}
    result = answer(case, ChatIn(text="银行名单是什么情况"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and "这一项没问题" not in result.text


def test_invalid_segment_quote_drops_segment_even_if_citation_is_report(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息")
    material = next(r for r in case.raw if r.source_id == "material")
    out = {"segments": [{"text": "它得到过监管认可。", "citations": ["A2"],
                         "quotes": [{"ref": material.id, "text": "监管认可"}]}]}
    result = answer(case, ChatIn(text="监管是否认可"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and "得到过监管认可" not in result.text


def test_truncated_jpeg_not_sent_to_model(tmp_path):
    image = Image.frombytes("RGB", (128, 128), random.Random(42).randbytes(128 * 128 * 3))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    damaged = buffer.getvalue()[:len(buffer.getvalue()) // 2]
    # Characterize the decoder: header verification alone accepts this file.
    Image.open(io.BytesIO(damaged)).verify()
    llm = FakeLLM(["fake successful OCR"], tmp_path)
    result = read_upload("broken.jpg", damaged, llm)
    assert result.method == "failed" and not llm.calls


def test_long_legacy_sentence_fails_closed_without_exception(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息")
    out = {"answer": "文" * 3100 + " [A2]", "citations": ["A2"]}
    result = answer(case, ChatIn(text="解释这条"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and result.dropped > 0


def test_model_cannot_flip_assertion_check_status(tmp_path):
    case = make_case(DEMO_COMPANY, "正规金融，保本保息")
    a1 = next(a for a in case.versions[0].assertions if a.id == "A1")
    bad = next(check for check in a1.checks if check.status == "bad")
    out = {"segments": [{"text": f"{bad.label}这一项没问题。", "citations": ["A1"]}]}
    result = answer(case, ChatIn(text="资格是怎么判断的"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found


def test_legacy_semicolon_keeps_grounded_fact_without_invalid_neighbor(tmp_path):
    case = make_case(DEMO_COMPANY, "正规金融，保本保息")
    out = {"answer": "持牌名单里查不到它 [A1]；退款情况已经核实 [R999]。"}
    result = answer(case, ChatIn(text="核实了什么"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.citations == ["A1"] and not result.not_found
    assert "退款情况已经核实" not in result.text


def test_structured_overreach_rewrite_still_checks_authoritative_verdict(tmp_path):
    case = make_case(DEMO_COMPANY, "保本保息")
    before = case.model_dump_json()
    bad = {"segments": [{"text": "钱很可能拿不回来", "citations": ["A2"]}]}
    conflict = {"segments": [{"text": "收益承诺与记录相符", "citations": ["A2"]}]}
    fake = FakeLLM([json.dumps(bad), json.dumps(conflict)], tmp_path)
    result = answer(case, ChatIn(text="解释收益承诺"), fake)
    assert result.rewrites == 1 and result.blocked == ["很可能"]
    assert result.not_found and "与记录相符" not in result.text
    assert case.model_dump_json() == before and len(fake.calls) == 2


def test_glossary_example_cannot_supply_a_company_yield_number(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    out = {"segments": [{"text": "该公司的年化收益是 2.25%。", "citations": ["A2", "term.annualized"]}]}
    result = answer(case, ChatIn(text="年化收益是多少"), FakeLLM([json.dumps(out)], tmp_path))
    assert result.not_found and "该公司的年化收益是" not in result.text


def test_glossary_only_numeric_example_remains_available(tmp_path):
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    out = {"segments": [{"text": "年化 9% 存满一年大约多 9%，只存三个月大约只多 2.25%。",
                         "citations": ["term.annualized"]}]}
    result = answer(case, ChatIn(text="年化怎么理解"), FakeLLM([json.dumps(out)], tmp_path))
    assert not result.not_found and result.citations == ["term.annualized"] and "2.25%" in result.text
