"""Synthetic gateway responses. No live provider or credentials are used."""
import json
from datetime import datetime

import httpx
import pytest
from pydantic import BaseModel, ConfigDict

from app.llm import LLM, LLMError
from tests.test_llm_assistant import FakeLLM


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


MESSAGES = [{"role": "user", "content": "演示问题"}]


def test_missing_config_never_sends_request(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("unconfigured gateway sent an HTTP request")
    monkeypatch.setattr(httpx, "post", forbidden)
    with pytest.raises(LLMError):
        LLM(base_url="", api_key="", model="", mode="live", cache_dir=tmp_path).chat(MESSAGES)


def test_invalid_json_repairs_once(tmp_path):
    llm = FakeLLM(['{"bad": true}', '{"bad": true}'], tmp_path)
    with pytest.raises(LLMError):
        llm.chat_json(MESSAGES, Payload)
    assert len(llm.calls) == 2
    assert not list(tmp_path.glob("*.json")), "invalid output must not be recorded as successful"


def test_repaired_response_replays_under_original_request(tmp_path):
    llm = FakeLLM(["not JSON", '{"value":"修复后"}'], tmp_path)
    parsed, live = llm.chat_json(MESSAGES, Payload)
    assert parsed.value == "修复后" and live.mode == "model"
    llm.mode = "replay"
    parsed, replay = llm.chat_json(MESSAGES, Payload)
    assert parsed.value == "修复后" and replay.mode == "replay"
    assert replay.recorded_at == live.recorded_at
    assert datetime.fromisoformat(replay.recorded_at).tzinfo is not None
    assert len(llm.calls) == 2


def test_schema_is_part_of_replay_key(tmp_path):
    class Other(BaseModel):
        number: int
    llm = FakeLLM(['{"value":"ok"}'], tmp_path)
    llm.chat_json(MESSAGES, Payload)
    llm.mode = "replay"
    with pytest.raises(LLMError):
        llm.chat_json(MESSAGES, Other)


def test_case_namespace_prevents_cross_case_replay(tmp_path):
    llm = FakeLLM(["case A"], tmp_path)
    llm.chat(MESSAGES, cache_namespace="case-a")
    llm.mode = "replay"
    with pytest.raises(LLMError):
        llm.chat(MESSAGES, cache_namespace="case-b")
    assert llm.chat(MESSAGES, cache_namespace="case-a").text == "case A"


def test_corrupt_cache_is_an_llm_error(tmp_path):
    llm = FakeLLM(["hello"], tmp_path)
    llm.chat(MESSAGES)
    next(tmp_path.glob("*.json")).write_text("{broken", encoding="utf-8")
    llm.mode = "replay"
    with pytest.raises(LLMError):
        llm.chat(MESSAGES)


def test_auth_error_redacts_secret_and_does_not_retry(tmp_path):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(401, json={"error": "secret-test-token"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    llm = LLM(base_url="https://gateway.example/v1/", api_key="secret-test-token", model="m",
              mode="live", cache_dir=tmp_path, client=client)
    with pytest.raises(LLMError) as err:
        llm.chat_json(MESSAGES, Payload)
    assert "secret-test-token" not in str(err.value)
    assert err.value.code == "auth"
    assert len(requests) == 1
    assert str(requests[0].url) == "https://gateway.example/v1/chat/completions"


def test_provider_shape_and_timeout_are_safe_failures(tmp_path):
    for response in ({"choices": []}, {"choices": [{"message": {"content": None}}]}):
        client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=response)))
        llm = LLM(base_url="https://gateway.example/v1", api_key="synthetic", model="m", mode="live",
                  cache_dir=tmp_path, client=client)
        with pytest.raises(LLMError):
            llm.chat(MESSAGES)


def test_invalid_modes_and_url_credentials_rejected(tmp_path):
    for kwargs in ({"mode": "typo"}, {"base_url": "https://secret:token@example.com/v1"}):
        llm = LLM(api_key="synthetic", model="m", cache_dir=tmp_path, **kwargs)
        with pytest.raises(LLMError):
            llm.chat(MESSAGES)


def test_cache_write_failure_preserves_live_result(tmp_path, monkeypatch):
    llm = FakeLLM(["成功"], tmp_path)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(llm, "_record", fail)
    result = llm.chat(MESSAGES)
    assert result.text == "成功" and result.mode == "model"
    assert result.warnings
