from app import deployment
from app.llm import LLM


def test_release_reports_only_bounded_identifier_and_asset_fingerprints(monkeypatch):
    monkeypatch.setenv("XRAY_RELEASE_ID", "895bcf0")
    result = deployment.status()
    assert result["release_id"] == "895bcf0"
    assert len(result["report_asset"]) == 16
    monkeypatch.setenv("XRAY_RELEASE_ID", "/private/config?secret=value")
    assert deployment.status()["release_id"] is None


def test_llm_status_exposes_effective_models_and_thinking_not_credentials(monkeypatch):
    monkeypatch.setenv("TOKENDANCE_ENABLE_THINKING", "0")
    status = LLM(api_key="private-test-secret", model="qwen3.8-max", vision_model="qwen3.8-max").status()
    assert status["enable_thinking"] is False
    assert status["model"] == status["vision_model"] == "qwen3.8-max"
    assert "private-test-secret" not in str(status)
