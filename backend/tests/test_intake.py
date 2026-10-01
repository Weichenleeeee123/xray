import json

import pytest

from app.intake import run_intake
from tests.test_llm_assistant import FakeLLM


@pytest.mark.parametrize("amount", [-1, 0, "NaN", float("inf"), True])
def test_invalid_amount_falls_back_to_keywords(tmp_path, amount):
    response = json.dumps({"scenario": "prepaid", "amount": amount})
    result = run_intake("我妈想存20万理财", FakeLLM([response, response], tmp_path))
    assert result.method == "keywords" and result.scenario == "savings" and result.amount == 200000


def test_unknown_amount_stays_none_not_model_default(tmp_path):
    response = '{"scenario":"job","amount":200000}'
    result = run_intake("我收到这个公司的offer", FakeLLM([response], tmp_path))
    assert result.amount is None


def test_explicit_scenario_skips_model(tmp_path):
    llm = FakeLLM(["not called"], tmp_path)
    result = run_intake("我妈想存20万理财", llm, scenario="job")
    assert result.scenario == "job" and result.method == "user" and not llm.calls


def test_model_cannot_add_verdict_to_intake(tmp_path):
    response = '{"scenario":"prepaid","verdict":"safe"}'
    result = run_intake("我要找工作", FakeLLM([response, response], tmp_path))
    assert result.method == "keywords" and result.scenario == "job"
