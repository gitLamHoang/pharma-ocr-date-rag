import base64
import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from pharma_dates.classify import PageClassification
from pharma_dates.claude_client import ClaudeClient, ClaudeUnavailable, make_client
from pharma_dates.config import Settings
from pharma_dates.models import Candidate
from pharma_dates.taxonomy import as_json

CREDENTIAL_VARS = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "AWS_REGION",
    "VERTEX_PROJECT_ID",
    "VERTEX_REGION",
)
CANNED = {
    "items": [
        {
            "candidate_id": "p1-c1",
            "date_type": "expiry_date",
            "qualifier": None,
            "resolved_value": None,
            "evidence": None,
            "confidence": 0.9,
            "rationale": "after 'Expiry'",
        }
    ],
    "missed_dates": [],
}


@pytest.fixture(autouse=True)
def no_credentials(monkeypatch):
    for name in CREDENTIAL_VARS:
        monkeypatch.delenv(name, raising=False)


def settings(**overrides) -> Settings:
    return Settings(_env_file=None, **({"ai_enabled": True} | overrides))


def candidate() -> Candidate:
    return Candidate(
        id="p1-c1",
        page=1,
        raw_text="31/03/2027",
        normalized="2027-03-31",
        candidates=["2027-03-31"],
        precision="day",
        char_start=7,
        char_end=17,
        bbox=None,
        context="Expiry 31/03/2027",
        rule_label="expiry",
        source="rules",
    )


def response(*blocks, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, stop_details=stop_details)


def text(value: str):
    return SimpleNamespace(type="text", text=value)


def bad_request(message="output_config.format: unsupported field"):
    request = httpx2.Request("POST", "https://example.invalid/v1/messages")
    return anthropic.BadRequestError(message, response=httpx2.Response(400, request=request), body=None)


class FakeSDK:
    """Records each `beta.messages.create` call and replays queued responses or errors."""

    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def classify(client: ClaudeClient) -> PageClassification:
    return client.classify(b"\x89PNG-bytes", "Expiry 31/03/2027", [candidate()], as_json())


def test_make_client_none_without_key():
    assert make_client(settings()) is None


def test_make_client_none_when_ai_disabled(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")  # pragma: allowlist secret
    assert make_client(settings(ai_enabled=False)) is None


def test_make_client_anthropic_with_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-not-a-key")  # pragma: allowlist secret
    client = make_client(settings())
    assert isinstance(client, ClaudeClient)
    assert client.model == "claude-opus-5-5"
    assert client.provider == "anthropic"


@pytest.mark.parametrize("from_env", [True, False])
def test_make_client_anthropic_with_auth_token(monkeypatch, from_env):
    if from_env:
        monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "test-not-a-token")  # pragma: allowlist secret
        client = make_client(settings())
    else:
        client = make_client(settings(anthropic_auth_token="test-not-a-token"))  # pragma: allowlist secret
    assert isinstance(client, ClaudeClient)
    assert client.sdk.auth_token == "test-not-a-token"  # pragma: allowlist secret


def test_make_client_bedrock_needs_region():
    assert make_client(settings(claude_provider="bedrock")) is None
    client = make_client(settings(claude_provider="bedrock", aws_region="us-east-1"))
    assert client.model == "anthropic.claude-opus-5-5"
    assert client.provider == "bedrock"


def test_make_client_vertex_needs_project():
    assert make_client(settings(claude_provider="vertex")) is None
    client = make_client(settings(claude_provider="vertex", vertex_project_id="demo-project"))
    assert client.model == "claude-opus-5-5"
    assert client.provider == "vertex"


def test_classify_request_uses_structured_output_and_fallbacks():
    sdk = FakeSDK(response(SimpleNamespace(type="thinking", thinking=""), text(json.dumps(CANNED))))
    result = classify(ClaudeClient(sdk, "claude-opus-5-5", "anthropic"))
    assert result == PageClassification.model_validate(CANNED)
    [call] = sdk.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"]["effort"] == "medium"
    schema = call["output_config"]["format"]["schema"]
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert schema["required"] == ["items", "missed_dates"]
    assert "expiry_date" in schema["properties"]["items"]["items"]["properties"]["date_type"]["enum"]
    assert call["betas"] == ["server-side-fallback-2026-07-01"]
    assert call["fallbacks"] == "default"
    assert "tools" not in call and "tool_choice" not in call
    # Stable prefix first: system prompt + taxonomy, cached.
    [system] = call["system"]
    assert system["cache_control"] == {"type": "ephemeral"}
    assert "only from the candidate ids" in system["text"]
    assert "- legal: certificate_issue_date, certificate_valid_until," in system["text"]
    [message] = call["messages"]
    image, prompt = message["content"]
    assert image["source"] == {
        "type": "base64",
        "media_type": "image/png",
        "data": base64.standard_b64encode(b"\x89PNG-bytes").decode(),
    }
    assert "Expiry 31/03/2027" in prompt["text"]
    assert '"p1-c1"' in prompt["text"]


def test_system_prompt_is_identical_across_pages():
    sdk = FakeSDK(response(text(json.dumps(CANNED))), response(text(json.dumps(CANNED))))
    client = ClaudeClient(sdk, "claude-opus-5-5", "anthropic")
    classify(client)
    client.classify(b"", "Other page", [], as_json())
    first, second = sdk.calls
    assert first["system"] == second["system"]
    assert first["output_config"] == second["output_config"]
    assert [block["type"] for block in second["messages"][0]["content"]] == ["text"]  # no image given


def test_refusal_raises_unavailable():
    sdk = FakeSDK(response(stop_reason="refusal", stop_details=SimpleNamespace(category="cyber")))
    with pytest.raises(ClaudeUnavailable, match="refus"):
        classify(ClaudeClient(sdk, "claude-opus-5-5", "anthropic"))


@pytest.mark.parametrize(
    "outcome",
    [
        response(text("{not json")),
        response(text(json.dumps({"items": "nope"}))),
        response(text('{"items": []'), stop_reason="max_tokens"),
        response(),
    ],
)
def test_bad_response_raises_unavailable(outcome):
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(FakeSDK(outcome), "claude-opus-5-5", "anthropic"))


def test_api_error_raises_unavailable():
    error = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://example.invalid"))
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(FakeSDK(error), "claude-opus-5-5", "anthropic"))


@pytest.mark.parametrize(
    "error",
    [
        RuntimeError("Could not resolve AWS credentials from session"),  # Bedrock without credentials
        type("DefaultCredentialsError", (Exception,), {})("no Google credentials"),  # Vertex likewise
    ],
)
@pytest.mark.parametrize("call", ["classify", "transcribe"])
def test_non_api_sdk_error_raises_unavailable(error, call):
    client = ClaudeClient(FakeSDK(error), "anthropic.claude-opus-5-5", "bedrock")
    with pytest.raises(ClaudeUnavailable, match=type(error).__name__):
        classify(client) if call == "classify" else client.transcribe(b"png")


def test_anthropic_bad_request_not_retried():
    sdk = FakeSDK(bad_request())
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(sdk, "claude-opus-5-5", "anthropic"))
    assert len(sdk.calls) == 1


@pytest.mark.parametrize("provider", ["bedrock", "vertex"])
def test_cloud_provider_400_retries_once_with_strict_tool(provider):
    tool_use = SimpleNamespace(type="tool_use", name="record_page_classification", input=CANNED)
    sdk = FakeSDK(bad_request(), response(tool_use, stop_reason="tool_use"))
    result = classify(ClaudeClient(sdk, "anthropic.claude-opus-5-5", provider))
    assert result == PageClassification.model_validate(CANNED)
    first, retry = sdk.calls
    assert "fallbacks" not in first and "betas" not in first
    assert "format" in first["output_config"]
    assert retry["output_config"] == {"effort": "medium"}
    assert retry["tool_choice"] == {"type": "auto"}
    [tool] = retry["tools"]
    assert tool["name"] == "record_page_classification"
    assert tool["strict"] is True
    assert tool["input_schema"] == first["output_config"]["format"]["schema"]
    assert retry["system"] == first["system"]


def test_cloud_provider_retry_without_tool_call_raises():
    sdk = FakeSDK(bad_request(), response(text("I think it is an expiry date.")))
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(sdk, "claude-opus-5-5", "vertex"))
    assert len(sdk.calls) == 2


def test_cloud_provider_retry_invalid_tool_input_raises():
    tool_use = SimpleNamespace(type="tool_use", name="record_page_classification", input={"items": 3})
    sdk = FakeSDK(bad_request(), response(tool_use, stop_reason="tool_use"))
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(sdk, "claude-opus-5-5", "bedrock"))


def test_cloud_provider_retries_only_once():
    sdk = FakeSDK(bad_request(), bad_request(), response(text(json.dumps(CANNED))))
    with pytest.raises(ClaudeUnavailable):
        classify(ClaudeClient(sdk, "claude-opus-5-5", "bedrock"))
    assert len(sdk.calls) == 2


def test_transcribe_returns_text_blocks():
    sdk = FakeSDK(
        response(SimpleNamespace(type="thinking", thinking=""), text("Line one\n"), text("Line two"))
    )
    out = ClaudeClient(sdk, "claude-opus-5-5", "anthropic").transcribe(b"png")
    assert out == "Line one\nLine two"
    [call] = sdk.calls
    assert call["thinking"] == {"type": "adaptive"}
    assert call["output_config"] == {"effort": "medium"}
    assert call["fallbacks"] == "default"
    assert call["messages"][0]["content"][0]["type"] == "image"


def test_transcribe_refusal_raises():
    sdk = FakeSDK(response(stop_reason="refusal"))
    with pytest.raises(ClaudeUnavailable):
        ClaudeClient(sdk, "claude-opus-5-5", "anthropic").transcribe(b"png")


@pytest.mark.parametrize("provider", ["anthropic", "bedrock", "vertex"])
def test_transcribe_bad_request_raises_unavailable(provider):
    sdk = FakeSDK(bad_request("image too large"))
    with pytest.raises(ClaudeUnavailable):
        ClaudeClient(sdk, "claude-opus-5-5", provider).transcribe(b"png")
    assert len(sdk.calls) == 1
