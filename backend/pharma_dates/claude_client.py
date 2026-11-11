"""The one adapter between the pipeline and Claude (Anthropic API, Amazon Bedrock or Vertex AI).

Every failure (no access, API error, refusal, truncated or invalid output) is raised as
`ClaudeUnavailable`, so callers fall back to rule labels. Nothing here logs keys or page text.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from typing import Any

import anthropic
from pydantic import ValidationError

from .classify import (
    TRANSCRIBE_PROMPT,
    ClaudeUnavailable,
    PageClassification,
    response_schema,
    system_prompt,
)
from .config import Settings
from .models import Candidate

__all__ = ["ClaudeClient", "ClaudeUnavailable", "make_client"]

logger = logging.getLogger(__name__)

EFFORT = "medium"
MAX_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Bedrock and Vertex have no server-side `fallbacks`; the SDK middleware retries refusals there.
CLIENT_FALLBACK_MODEL = "claude-opus-4-8"
BEDROCK_PREFIX = "anthropic."
TOOL_NAME = "record_page_classification"


def make_client(settings: Settings) -> ClaudeClient | None:
    """A client for the configured provider, or None when AI is off or no credentials are set."""
    if not settings.ai_enabled:
        return None
    provider = settings.claude_provider
    if provider == "anthropic":
        key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
        if key:
            return ClaudeClient(anthropic.Anthropic(api_key=key), settings.claude_model, provider)
        if os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return ClaudeClient(anthropic.Anthropic(), settings.claude_model, provider)
        return None
    if provider == "bedrock":
        if not settings.aws_region:
            return None
        sdk = anthropic.AnthropicBedrockMantle(
            aws_region=settings.aws_region,
            middleware=[_refusal_middleware(BEDROCK_PREFIX + CLIENT_FALLBACK_MODEL)],
        )
        model = settings.claude_model
        return ClaudeClient(
            sdk, model if model.startswith(BEDROCK_PREFIX) else BEDROCK_PREFIX + model, provider
        )
    if not settings.vertex_project_id:
        return None
    sdk = anthropic.AnthropicVertex(
        project_id=settings.vertex_project_id,
        region=settings.vertex_region,
        middleware=[_refusal_middleware(CLIENT_FALLBACK_MODEL)],
    )
    return ClaudeClient(sdk, settings.claude_model, provider)


def _refusal_middleware(model: str) -> anthropic.BetaRefusalFallbackMiddleware:
    return anthropic.BetaRefusalFallbackMiddleware([{"model": model}])


class ClaudeClient:
    def __init__(self, sdk: Any, model: str, provider: str):
        self.sdk, self.model, self.provider = sdk, model, provider

    def transcribe(self, image_png: bytes) -> str:
        """A faithful transcription of the page image."""
        response = self._create(
            system=[{"type": "text", "text": TRANSCRIBE_PROMPT}],
            messages=[{"role": "user", "content": [_image(image_png)]}],
            output_config={"effort": EFFORT},
        )
        _check_stop(response, allow_max_tokens=True)
        return "".join(block.text for block in response.content if block.type == "text")

    def classify(
        self, image_png: bytes, page_text: str, candidates: list[Candidate], taxonomy_json: list[dict]
    ) -> PageClassification:
        """Claude's labels for the page's candidates plus the dates it saw that the rules missed."""
        schema = response_schema(taxonomy_json)
        system = [
            {"type": "text", "text": system_prompt(taxonomy_json), "cache_control": {"type": "ephemeral"}}
        ]
        content = ([_image(image_png)] if image_png else []) + [
            {"type": "text", "text": _page_prompt(page_text, candidates)}
        ]
        request = {"system": system, "messages": [{"role": "user", "content": content}]}
        try:
            response = self._create(
                **request,
                output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": schema}},
            )
        except anthropic.BadRequestError:
            if self.provider == "anthropic":
                raise ClaudeUnavailable("Claude rejected the request") from None
            # Bedrock/Vertex may not accept structured output: one retry with a strict tool.
            logger.info("%s rejected structured output; retrying with a strict tool", self.provider)
            return self._classify_with_tool(request, schema)
        _check_stop(response)
        raw = "".join(block.text for block in response.content if block.type == "text")
        try:
            return PageClassification.model_validate_json(raw)
        except ValidationError:
            raise ClaudeUnavailable("Claude returned an invalid classification") from None

    def _classify_with_tool(self, request: dict, schema: dict) -> PageClassification:
        tool = {
            "name": TOOL_NAME,
            "description": "Record the labels for every candidate and the missed dates on this page.",
            "strict": True,
            "input_schema": schema,
        }
        content = request["messages"][0]["content"] + [
            {"type": "text", "text": f"Answer by calling the {TOOL_NAME} tool once."}
        ]
        try:
            response = self._create(
                system=request["system"],
                messages=[{"role": "user", "content": content}],
                output_config={"effort": EFFORT},
                tools=[tool],
                tool_choice={"type": "auto"},  # forced tool_choice is rejected on this model
            )
        except anthropic.BadRequestError:
            raise ClaudeUnavailable("Claude rejected the request") from None
        _check_stop(response, allow_tool_use=True)
        call = next((b for b in response.content if b.type == "tool_use" and b.name == TOOL_NAME), None)
        if call is None:
            raise ClaudeUnavailable("Claude did not return a classification")
        try:
            return PageClassification.model_validate(call.input)
        except ValidationError:
            raise ClaudeUnavailable("Claude returned an invalid classification") from None

    def _create(self, **kwargs: Any) -> Any:
        kwargs |= {"model": self.model, "max_tokens": MAX_TOKENS, "thinking": {"type": "adaptive"}}
        if self.provider == "anthropic":
            kwargs |= {"betas": [FALLBACK_BETA], "fallbacks": "default"}
        try:
            return self.sdk.beta.messages.create(**kwargs)
        except anthropic.BadRequestError:
            raise
        except anthropic.APIError as exc:
            raise ClaudeUnavailable(f"Claude API error ({type(exc).__name__})") from None


def _image(image_png: bytes) -> dict:
    data = base64.standard_b64encode(image_png).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": data}}


def _page_prompt(page_text: str, candidates: list[Candidate]) -> str:
    listed = [
        {"id": c.id, "raw_text": c.raw_text, "readings": c.candidates, "precision": c.precision}
        for c in candidates
    ]
    return (
        f"<page_text>\n{page_text}\n</page_text>\n\n"
        f"<candidates>\n{json.dumps(listed, ensure_ascii=False, indent=1)}\n</candidates>\n\n"
        "Label every candidate and list the missed dates."
    )


def _check_stop(response: Any, allow_max_tokens: bool = False, allow_tool_use: bool = False) -> None:
    reason = response.stop_reason
    if reason == "refusal":
        details = getattr(response, "stop_details", None)
        category = getattr(details, "category", None) or "unspecified"
        raise ClaudeUnavailable(f"Claude refused the request (category: {category})")
    allowed = {"end_turn", "stop_sequence"} | ({"max_tokens"} if allow_max_tokens else set())
    if reason not in allowed | ({"tool_use"} if allow_tool_use else set()):
        raise ClaudeUnavailable(f"Claude stopped early ({reason})")
