"""Single abstraction in front of every LLM we use.

Why: Z.AI exposes an OpenAI-compatible API at ``api.z.ai/api/paas/v4``, so we
keep a thin wrapper around the official ``openai`` SDK with a swappable
``base_url`` + ``model``. Same code path, different provider.

Picks Z.AI if ``ZAI_API_KEY`` is set, otherwise falls back to OpenAI for dev
sessions before the hackathon credentials are handed out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ..config import config


@dataclass
class LLMResponse:
    text: str
    tool_calls: list[dict[str, Any]]
    raw: Any


class LLMProvider:
    """Thin sync wrapper. Async variant can be layered on later."""

    def __init__(self, name: str, client: OpenAI, model: str, vision_model: str | None = None):
        self.name = name
        self.client = client
        self.model = model
        self.vision_model = vision_model or model

    # ── chat with optional tools ──────────────────────────────────────────
    def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 1024,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = self.client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message
        tool_calls = []
        for tc in (msg.tool_calls or []):
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            )
        return LLMResponse(text=msg.content or "", tool_calls=tool_calls, raw=resp)

    # ── vision (screenshot reading) ───────────────────────────────────────
    def see(self, image_b64: str, prompt: str) -> str:
        """Send a screenshot (base64 PNG) + text prompt; return plain text."""
        resp = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
            max_tokens=512,
        )
        return resp.choices[0].message.content or ""


# ── factory ───────────────────────────────────────────────────────────────
_singleton: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Return the lazily-initialised global provider."""
    global _singleton
    if _singleton is not None:
        return _singleton

    primary = config.primary_provider()
    if primary == "zai":
        client = OpenAI(api_key=config.ZAI_API_KEY, base_url=config.ZAI_BASE_URL)
        _singleton = LLMProvider(
            name="zai",
            client=client,
            model=config.ZAI_MODEL,
            vision_model=config.ZAI_VISION_MODEL,
        )
    elif primary == "openai":
        client = OpenAI(api_key=config.OPENAI_API_KEY)
        _singleton = LLMProvider(
            name="openai",
            client=client,
            model=config.OPENAI_MODEL,
            vision_model=config.OPENAI_MODEL,
        )
    else:
        raise RuntimeError(
            "No LLM credentials. Set ZAI_API_KEY (preferred) or OPENAI_API_KEY in .env"
        )

    return _singleton
