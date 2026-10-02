"""Stage budgets use a controlled clock and a synthetic HTTP transport, never live providers."""
import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app import config, llm as llm_module
from app.intake import run_intake
from app.llm import LLM, REQUEST_DEADLINE
from app.plain import build_glance, finish_version
from app.store import CaseStore
from tests.helpers import DEMO_COMPANY, flyer, make_case


STAGES = [("intake", "INTAKE_TIMEOUT", 8.0), ("plain", "PLAIN_TIMEOUT", 12.0)]
SHORT = "4 份牌照名单和私募登记都查不到"


@pytest.fixture
def clock(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(llm_module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    token = REQUEST_DEADLINE.set(None)
    try:
        yield now
    finally:
        REQUEST_DEADLINE.reset(token)


def payload(stage):
    return ({"scenario": "savings", "focus": ["取钱"], "amount": 200000} if stage == "intake" else
            {"short": {"A1": SHORT}, "terms": []})


def response(stage):
    return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(payload(stage))}}]})


def gateway(client):
    return LLM(base_url="https://synthetic.invalid/v1", api_key="synthetic", model="m", mode="live",
               timeout=45, cache_dir=None, client=client)


def invoke(stage, llm):
    if stage == "intake":
        return run_intake("我妈想存20万理财", llm)
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    return build_glance(case, case.versions[-1], llm)[0]


def assert_fallback(stage, result):
    if stage == "intake":
        assert result.method == "keywords" and result.scenario == "savings" and result.amount == 200000
    else:
        assert result.mode == "template" and result.short == {}


@pytest.mark.parametrize("stage,setting,budget", STAGES)
@pytest.mark.parametrize("repair", [False, True])
def test_stage_first_call_and_repair_share_http_budget(monkeypatch, clock, stage, setting, budget, repair):
    monkeypatch.setattr(config, setting, budget, raising=False)
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"])
        if repair and len(timeouts) == 1:
            clock[0] += 3
            return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON"}}]})
        return response(stage)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = invoke(stage, gateway(client))

    expected = [budget, budget - 3] if repair else [budget]
    assert timeouts == [dict.fromkeys(("connect", "read", "write", "pool"), value) for value in expected]
    assert (result.method if stage == "intake" else result.mode) == "model"
    if stage == "plain":
        assert result.short == {"A1": SHORT}
    assert REQUEST_DEADLINE.get() is None


@pytest.mark.parametrize("stage,setting,budget", STAGES)
def test_stage_budget_exhaustion_prevents_json_repair(monkeypatch, clock, stage, setting, budget):
    monkeypatch.setattr(config, setting, budget, raising=False)
    calls = []

    def handler(request):
        calls.append(request)
        clock[0] += budget
        return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON"}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = invoke(stage, gateway(client))

    assert len(calls) == 1
    assert_fallback(stage, result)
    assert REQUEST_DEADLINE.get() is None


@pytest.mark.parametrize("stage,setting,budget", STAGES)
@pytest.mark.parametrize("parent_remaining", [-1, 2, 90])
def test_stage_timeout_respects_parent_and_restores_it(monkeypatch, clock, stage, setting, budget, parent_remaining):
    monkeypatch.setattr(config, setting, budget, raising=False)
    parent = clock[0] + parent_remaining
    REQUEST_DEADLINE.set(parent)
    timeouts = []

    def handler(request):
        timeouts.append(request.extensions["timeout"]["read"])
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = invoke(stage, gateway(client))

    assert timeouts == ([] if parent_remaining <= 0 else [min(parent_remaining, budget)])
    assert_fallback(stage, result)
    assert REQUEST_DEADLINE.get() == parent


def test_nested_budget_restores_context_even_for_unexpected_exception(clock):
    REQUEST_DEADLINE.set(1100.0)
    with pytest.raises(RuntimeError, match="synthetic"):
        with llm_module.request_budget(12):
            assert REQUEST_DEADLINE.get() == 1012.0
            with llm_module.request_budget(8):
                assert REQUEST_DEADLINE.get() == 1008.0
            assert REQUEST_DEADLINE.get() == 1012.0
            raise RuntimeError("synthetic")
    assert REQUEST_DEADLINE.get() == 1100.0


def test_plain_budget_fallback_preserves_saved_facts_verdicts_and_references(tmp_path, monkeypatch, clock):
    monkeypatch.setattr(config, "PLAIN_TIMEOUT", 12, raising=False)
    case = make_case(DEMO_COMPANY, flyer("manyinghe.txt"))
    before = case.model_dump(exclude={"revision", "versions"})
    version_before = case.versions[-1].model_dump(exclude={"glance", "terms"})
    calls = []

    def handler(request):
        calls.append(request)
        clock[0] += 12
        return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON"}}]})

    store = CaseStore(tmp_path / "cases")
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        store.save(finish_version(case, gateway(client)))
    saved = store.get(case.id)

    assert len(calls) == 1
    assert saved.current == 1 and saved.versions[-1].glance.mode == "template"
    assert saved.model_dump(exclude={"revision", "versions"}) == before
    assert saved.versions[-1].model_dump(exclude={"glance", "terms"}) == version_before
    assert saved.versions[-1].terms and all(t.origin == "glossary" for t in saved.versions[-1].terms)
    assert REQUEST_DEADLINE.get() is None


@pytest.mark.parametrize("setting,environment", [("INTAKE_TIMEOUT", "XRAY_INTAKE_TIMEOUT"),
                                                 ("PLAIN_TIMEOUT", "XRAY_PLAIN_TIMEOUT")])
@pytest.mark.parametrize("invalid", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_stage_timeout_settings_reject_nonpositive_or_nonfinite(monkeypatch, setting, environment, invalid):
    monkeypatch.setattr(config, setting, invalid, raising=False)
    with pytest.raises(ValueError, match=environment):
        config.validate_settings()


def test_stage_timeout_settings_read_environment_without_changing_other_budgets(monkeypatch):
    monkeypatch.setenv("XRAY_INTAKE_TIMEOUT", "3.5")
    monkeypatch.setenv("XRAY_PLAIN_TIMEOUT", "7.25")
    monkeypatch.setenv("TOKENDANCE_TIMEOUT", "45")
    monkeypatch.setenv("XRAY_CHAT_TIMEOUT", "60")
    original_read = Path.read_text

    def skip_local_env(path, *args, **kwargs):
        return "" if path.name == ".env" else original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", skip_local_env)
    settings = runpy.run_path(config.__file__)
    assert settings["INTAKE_TIMEOUT"] == 3.5 and settings["PLAIN_TIMEOUT"] == 7.25
    assert settings["LLM_TIMEOUT"] == 45 and settings["CHAT_TIMEOUT"] == 60
