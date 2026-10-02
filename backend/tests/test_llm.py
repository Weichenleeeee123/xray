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


@pytest.mark.parametrize("setting,expected", [(None, False), ("0", False), ("1", True), ("", None)])
@pytest.mark.parametrize("vision", [False, True])
def test_thinking_setting_controls_actual_gateway_payload(tmp_path, monkeypatch, setting, expected, vision):
    if setting is None:
        monkeypatch.delenv("TOKENDANCE_ENABLE_THINKING", raising=False)
    else:
        monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", setting)
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"value":"ok"}'}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        llm = LLM(base_url="https://gateway.example/v1", api_key="synthetic", model="qwen3.8-max",
                  vision_model="qwen3.8-max", mode="live", cache_dir=tmp_path, json_mode=True, client=client)
        parsed, reply = llm.chat_json(MESSAGES, Payload, vision=vision)
    assert parsed.value == "ok" and reply.mode == "model"
    assert len(requests) == 1
    assert requests[0]["model"] == "qwen3.8-max"
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert "extra_body" not in requests[0], "raw HTTP parameters must not use the SDK wrapper"
    if expected is None:
        assert "enable_thinking" not in requests[0]
    else:
        assert requests[0].get("enable_thinking") is expected


@pytest.mark.parametrize("other_setting", ["1", ""])
def test_thinking_modes_cannot_replay_each_others_recordings(tmp_path, monkeypatch, other_setting):
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", "0")
    llm = FakeLLM(["original answer"], tmp_path)
    live = llm.chat(MESSAGES)
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", other_setting)
    other = FakeLLM([], tmp_path)
    other.mode = "replay"
    with pytest.raises(LLMError) as error:
        other.chat(MESSAGES)
    assert error.value.code == "replay_miss"
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", "0")
    same = FakeLLM([], tmp_path)
    same.mode = "replay"
    replay = same.chat(MESSAGES)
    assert replay.mode == "replay" and replay.text == live.text
    assert replay.recorded_at == live.recorded_at


@pytest.mark.parametrize("setting", ["false", "2", "synthetic-secret-config"])
def test_invalid_thinking_config_fails_without_network_or_value_leak(tmp_path, monkeypatch, setting):
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", setting)

    def forbidden(request):
        pytest.fail("invalid thinking configuration reached the network")

    with httpx.Client(transport=httpx.MockTransport(forbidden)) as client:
        llm = LLM(base_url="https://gateway.example/v1", api_key="synthetic", model="m",
                  mode="live", cache_dir=tmp_path, client=client)
        with pytest.raises(LLMError) as error:
            llm.chat(MESSAGES)
    assert error.value.code == "config"
    assert setting not in str(error.value)


def test_json_repair_keeps_thinking_disabled(tmp_path, monkeypatch):
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", "0")
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        content = '{"bad":true}' if len(requests) == 1 else '{"value":"repaired"}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        llm = LLM(base_url="https://gateway.example/v1", api_key="synthetic", model="m",
                  mode="live", cache_dir=tmp_path, client=client)
        parsed, _ = llm.chat_json(MESSAGES, Payload)
    assert parsed.value == "repaired" and len(requests) == 2
    assert all(payload.get("enable_thinking") is False for payload in requests)


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
