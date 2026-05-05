"""Single abstraction in front of every LLM we use.

Why: Z.AI exposes an OpenAI-compatible API at ``api.z.ai/api/paas/v4`` (and
the GOSIM proxy ``api.r9s.ai/v1`` follows the same shape), so we keep a
thin wrapper around the official ``openai`` SDK with a swappable
``base_url`` + ``model``. Same code path, different provider.

Picks Z.AI if ``ZAI_API_KEY`` is set, otherwise falls back to OpenAI for dev
sessions before the hackathon credentials are handed out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from ..config import config

# GLM-5.x exposes a "Thinking Mode" by default which prepends a chain-of-
# thought block (``thinking:\n…``) to the actual answer. We disable it via
# the ``extra_body`` channel of the OpenAI SDK (the proxy forwards the
# field straight to GLM) AND strip any leaking prefix as a belt-and-braces
# defense — different provider versions accept different field names.
_GLM_NO_THINKING_EXTRA = {
    "thinking": {"type": "disabled"},
    "enable_thinking": False,
}

_THINKING_PREFIX_RE = re.compile(
    r"^\s*(?:<thinking>.*?</thinking>\s*|thinking[:：][\s\S]*?\n\n)",
    re.IGNORECASE,
)


def _strip_thinking_prefix(text: str) -> str:
    """Best-effort scrub of leaking CoT prefixes from GLM responses."""
    if not text:
        return text
    # Cheap: drop a recognised prefix block.
    text = _THINKING_PREFIX_RE.sub("", text, count=1)
    # If the prefix wasn't recognised but the model dumped a long bullet
    # list of self-analysis without a final paragraph, return the last
    # paragraph (heuristic: most models put the final reply after the last
    # blank line).
    if text.lower().startswith(("thinking", "1.", "let me", "let's analyze")):
        last_block = text.rstrip().split("\n\n")[-1].strip()
        if last_block and last_block != text.strip():
            text = last_block
    return text.strip()


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

        # Disable GLM Thinking Mode so the chain-of-thought doesn't leak
        # into ``message.content``. Harmless no-op on non-GLM providers.
        if self.name == "zai":
            kwargs["extra_body"] = _GLM_NO_THINKING_EXTRA

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

        text = _strip_thinking_prefix(msg.content or "")
        return LLMResponse(text=text, tool_calls=tool_calls, raw=resp)

    # ── vision (screenshot reading) ───────────────────────────────────────
    def see(self, image_b64: str, prompt: str) -> str:
        """Send a screenshot (base64 PNG) + text prompt; return plain text.

        Raises ``RuntimeError`` if the configured provider has no vision
        model (e.g. the GOSIM proxy currently exposes text-only models).
        """
        if not self.vision_model:
            raise RuntimeError(
                "No vision model configured for this provider — set "
                "ZAI_VISION_MODEL or switch base_url to direct Z.AI."
            )
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
