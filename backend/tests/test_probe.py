from tools.probe_tokendance import run_probe
from tests.test_llm_assistant import FakeLLM


def test_probe_requires_explicit_live_and_search_protocol(tmp_path):
    llm = FakeLLM(["企鹅"], tmp_path)
    assert run_probe(llm, "text")["status"] == "not_tested"
    assert not llm.calls
    assert run_probe(llm, "search", live=True)["status"] == "blocked_protocol"
    assert run_probe(llm, "reader", live=True)["status"] == "blocked_protocol"
    assert not llm.calls
    assert run_probe(llm, "text", live=True)["status"] == "tested"


def test_probe_does_not_treat_replay_as_live_test(tmp_path):
    llm = FakeLLM(["企鹅"], tmp_path)
    assert run_probe(llm, "text", live=True)["status"] == "tested"
    llm.mode = "replay"
    assert run_probe(llm, "text", live=True)["status"] == "replay_only"
