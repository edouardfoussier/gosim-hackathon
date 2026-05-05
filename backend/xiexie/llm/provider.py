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

# GLM-5.x defaults to a "Thinking Mode" that bleeds chain-of-thought into
# ``message.content``. The proxy doesn't forward our extra_body fields
# reliably, so we layer three defenses:
#   (1) extra_body hint (no-op when ignored)
#   (2) a system-message directive prepended to *every* call
#   (3) post-process strip that recovers a quoted final answer when the
#       model dumps a long self-analysis instead of an answer.
_GLM_NO_THINKING_EXTRA = {
    "thinking": {"type": "disabled"},
    "enable_thinking": False,
    "thinking_mode": False,
    "do_sample": True,
}

_NO_COT_DIRECTIVE = (
    "OUTPUT FORMAT (non-negotiable): respond with the final answer ONLY. "
    "Do not narrate your reasoning, do not enumerate steps, do not write "
    "'Let me think' or 'First I will…'. No bullet lists of self-analysis. "
    "Skip preambles. If the user asks a question, answer in at most 2 short "
    "sentences unless they explicitly request more. If they ask for "
    "structured output (JSON, table, code), produce ONLY that structure."
)

_THINKING_TAG_RE = re.compile(
    r"<thinking>.*?</thinking>\s*",
    re.IGNORECASE | re.DOTALL,
)
_THINKING_PREFIX_LITERAL_RE = re.compile(
    r"^\s*thinking[:：]\s*",
    re.IGNORECASE,
)


def _strip_thinking_prefix(text: str, *, json_mode: bool = False) -> str:
    """Conservatively scrub leaking CoT from GLM responses.

    Two safe operations only:
      1. Remove any ``<thinking>…</thinking>`` block (XML-style markers).
      2. Strip a literal ``thinking:`` prefix at the start.

    No paragraph splitting, no quote recovery, no truncation. If the model
    dumps CoT the caller sees it (and the system directive plus optional
    ``json_mode`` are the levers that force a clean answer upstream).
    """
    if not text:
        return text
    text = _THINKING_TAG_RE.sub("", text)
    if not json_mode:
        text = _THINKING_PREFIX_LITERAL_RE.sub("", text, count=1)
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
        json_mode: bool = False,
    ) -> LLMResponse:
        # On GLM, prepend an explicit "no chain-of-thought" directive into
        # the system message (or create one if absent). This is the
        # strongest signal we have to suppress Thinking Mode and survives
        # even when ``extra_body`` fields are stripped by the GOSIM proxy.
        if self.name == "zai":
            messages = list(messages)  # don't mutate the caller's list
            if messages and messages[0].get("role") == "system":
                head = messages[0]
                messages[0] = {
                    **head,
                    "content": _NO_COT_DIRECTIVE + "\n\n" + (head.get("content") or ""),
                }
            else:
                messages.insert(0, {"role": "system", "content": _NO_COT_DIRECTIVE})

        kwargs: dict[str, Any] = dict(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        if json_mode:
            # Honoured by GLM-5.x via the OpenAI-compatible field, OpenAI
            # ``gpt-4o``, and the GOSIM proxy. Forces ``message.content`` to
            # parse cleanly as JSON so ``analyze_email.parse_verdict`` sees
            # a strict object instead of a markdown analysis block.
            kwargs["response_format"] = {"type": "json_object"}

        # Disable GLM Thinking Mode so the chain-of-thought doesn't leak
        # into ``message.content``. Harmless no-op on non-GLM providers.
        if self.name == "zai":
            kwargs["extra_body"] = _GLM_NO_THINKING_EXTRA

        try:
            resp = self.client.chat.completions.create(**kwargs)
        except TypeError:
            # Older SDKs / proxies without ``response_format`` support — drop
            # the field and retry. We still rely on ``parse_verdict`` to
            # rescue narrative output downstream.
            kwargs.pop("response_format", None)
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

        text = _strip_thinking_prefix(msg.content or "", json_mode=json_mode)
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
