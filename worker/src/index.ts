/**
 * Xiexie Proxy Worker (forked from Clicky)
 *
 * Holds API keys as Cloudflare secrets so they never ship in the Mac
 * app binary. The Swift app talks ONLY to this Worker; the Worker
 * fans out to the upstream model + voice providers.
 *
 * Routes:
 *   POST /chat              → Z.AI GLM-4.6 / GLM-4.5V (translates the
 *                              app's Anthropic Messages payload into
 *                              OpenAI ChatCompletions, re-emits the
 *                              upstream stream back as Anthropic SSE
 *                              so the Swift caller stays unchanged)
 *   POST /tts               → ElevenLabs TTS (untouched from Clicky)
 *   GET  /transcribe-token  → AssemblyAI streaming token (untouched)
 *
 * Why Z.AI: Xiexie targets the Z.AI Innovation Award at GOSIM 2026.
 * GLM-4.6 handles tool-calling and conversational steering; GLM-4.5V
 * is auto-selected whenever the request carries at least one image
 * block (the Swift app sends labelled screenshots for the scam-shield
 * vision path).
 */

interface Env {
  // ── Z.AI GLM (replaces ANTHROPIC_API_KEY) ─────────────────────────
  ZAI_API_KEY: string;
  // Optional: override the upstream Z.AI base. Defaults to direct
  // ``api.z.ai/api/paas/v4`` (vision + audio capable). Set to
  // ``https://api.r9s.ai/v1`` to route through the GOSIM proxy.
  ZAI_BASE_URL?: string;
  // Optional: model override per request. Defaults to ``glm-4.6`` for
  // text-only and ``glm-4.5v`` for image-bearing requests.
  ZAI_TEXT_MODEL?: string;
  ZAI_VISION_MODEL?: string;

  // ── voice (untouched from Clicky) ─────────────────────────────────
  ELEVENLABS_API_KEY: string;
  ELEVENLABS_VOICE_ID: string;
  ASSEMBLYAI_API_KEY: string;
}

const DEFAULT_ZAI_BASE = "https://api.z.ai/api/paas/v4";
const DEFAULT_TEXT_MODEL = "glm-4.6";
const DEFAULT_VISION_MODEL = "glm-4.5v";

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders() });
    }

    if (url.pathname === "/transcribe-token" && request.method === "GET") {
      try {
        return withCors(await handleTranscribeToken(env));
      } catch (error) {
        return errorResponse(url.pathname, error);
      }
    }

    if (request.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    try {
      if (url.pathname === "/chat") return withCors(await handleChat(request, env));
      if (url.pathname === "/tts") return withCors(await handleTTS(request, env));
      if (url.pathname === "/transcribe-token") {
        // Some clients POST with an empty body even on GET-only endpoints.
        return withCors(await handleTranscribeToken(env));
      }
    } catch (error) {
      return errorResponse(url.pathname, error);
    }

    return new Response("Not found", { status: 404 });
  },
};

// ───────────────────────────────────────────────────────────────────
// /chat — Anthropic ↔ OpenAI translation, streaming both directions
// ───────────────────────────────────────────────────────────────────
async function handleChat(request: Request, env: Env): Promise<Response> {
  const incoming = (await request.json()) as AnthropicMessagesRequest;
  const isStreaming = incoming.stream === true;
  const hasImage = anyContentBlockIsImage(incoming.messages);

  const baseURL = (env.ZAI_BASE_URL || DEFAULT_ZAI_BASE).replace(/\/$/, "");
  const upstreamModel = hasImage
    ? env.ZAI_VISION_MODEL || DEFAULT_VISION_MODEL
    : env.ZAI_TEXT_MODEL || DEFAULT_TEXT_MODEL;

  const openAIBody = anthropicToOpenAI(incoming, upstreamModel, isStreaming);

  const upstreamResponse = await fetch(`${baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      "authorization": `Bearer ${env.ZAI_API_KEY}`,
      "content-type": "application/json",
    },
    body: JSON.stringify(openAIBody),
  });

  if (!upstreamResponse.ok) {
    const text = await upstreamResponse.text();
    console.error(`[/chat] upstream ${upstreamResponse.status}: ${text}`);
    return new Response(text, {
      status: upstreamResponse.status,
      headers: { "content-type": "application/json" },
    });
  }

  if (isStreaming && upstreamResponse.body) {
    const anthropicStream = openAIStreamToAnthropic(upstreamResponse.body);
    return new Response(anthropicStream, {
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache",
      },
    });
  }

  // Non-streaming path: translate the single OpenAI completion into
  // an Anthropic Messages-shaped body so ``ClaudeAPI.analyzeImage``
  // (the non-streaming fallback) can parse the same fields it always
  // has (``content[*].text``).
  const completion = (await upstreamResponse.json()) as OpenAIChatCompletion;
  const anthropicLike = openAICompletionToAnthropic(completion);
  return new Response(JSON.stringify(anthropicLike), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

// ───────────────────────────────────────────────────────────────────
// /tts — ElevenLabs (Clicky's original implementation, retained)
// ───────────────────────────────────────────────────────────────────
async function handleTTS(request: Request, env: Env): Promise<Response> {
  const body = await request.text();
  const voiceId = env.ELEVENLABS_VOICE_ID;
  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": env.ELEVENLABS_API_KEY,
        "content-type": "application/json",
        accept: "audio/mpeg",
      },
      body,
    },
  );

  if (!response.ok) {
    const errorBody = await response.text();
    console.error(`[/tts] ElevenLabs API error ${response.status}: ${errorBody}`);
    return new Response(errorBody, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  }

  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "audio/mpeg",
    },
  });
}

// ───────────────────────────────────────────────────────────────────
// /transcribe-token — AssemblyAI (Clicky's original, retained)
// ───────────────────────────────────────────────────────────────────
async function handleTranscribeToken(env: Env): Promise<Response> {
  const response = await fetch(
    "https://streaming.assemblyai.com/v3/token?expires_in_seconds=480",
    { method: "GET", headers: { authorization: env.ASSEMBLYAI_API_KEY } },
  );
  if (!response.ok) {
    const errorBody = await response.text();
    console.error(`[/transcribe-token] AssemblyAI ${response.status}: ${errorBody}`);
    return new Response(errorBody, {
      status: response.status,
      headers: { "content-type": "application/json" },
    });
  }
  return new Response(await response.text(), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

// ───────────────────────────────────────────────────────────────────
// Anthropic ↔ OpenAI translation primitives
// ───────────────────────────────────────────────────────────────────

interface AnthropicMessagesRequest {
  model?: string;
  max_tokens?: number;
  stream?: boolean;
  system?: string;
  messages: Array<{
    role: "user" | "assistant";
    content: string | Array<AnthropicContentBlock>;
  }>;
}

type AnthropicContentBlock =
  | { type: "text"; text: string }
  | {
      type: "image";
      source: { type: "base64"; media_type: string; data: string };
    };

interface OpenAIChatCompletion {
  choices: Array<{
    message?: { content?: string };
    delta?: { content?: string };
    finish_reason?: string | null;
  }>;
}

function anyContentBlockIsImage(
  messages: AnthropicMessagesRequest["messages"],
): boolean {
  for (const message of messages) {
    if (Array.isArray(message.content)) {
      for (const block of message.content) {
        if (block.type === "image") return true;
      }
    }
  }
  return false;
}

function anthropicToOpenAI(
  request: AnthropicMessagesRequest,
  upstreamModel: string,
  isStreaming: boolean,
): Record<string, unknown> {
  const openAIMessages: Array<Record<string, unknown>> = [];

  if (request.system) {
    openAIMessages.push({ role: "system", content: request.system });
  }

  for (const message of request.messages) {
    if (typeof message.content === "string") {
      openAIMessages.push({ role: message.role, content: message.content });
      continue;
    }

    // Translate Anthropic content blocks to OpenAI content blocks.
    // Anthropic image blocks: {type:"image",source:{type:"base64",media_type,data}}
    // OpenAI image blocks  : {type:"image_url",image_url:{url:"data:<mt>;base64,<d>"}}
    const openAIContent: Array<Record<string, unknown>> = [];
    for (const block of message.content) {
      if (block.type === "text") {
        openAIContent.push({ type: "text", text: block.text });
      } else if (block.type === "image") {
        openAIContent.push({
          type: "image_url",
          image_url: {
            url: `data:${block.source.media_type};base64,${block.source.data}`,
          },
        });
      }
    }
    openAIMessages.push({ role: message.role, content: openAIContent });
  }

  // Suppress GLM-4.6's "thinking mode" — without this, every reply
  // burns ~300 tokens on chain-of-thought prefixed in the
  // ``reasoning_content`` field, which our Anthropic translation
  // ignores. Result: truncated empty replies on small max_tokens.
  // ``thinking: { type: "disabled" }`` is the canonical Z.AI knob;
  // ``extra_body`` is OpenAI's escape hatch the Z.AI proxy honours.
  return {
    model: upstreamModel,
    max_tokens: request.max_tokens ?? 1024,
    stream: isStreaming,
    messages: openAIMessages,
    thinking: { type: "disabled" },
  };
}

function openAICompletionToAnthropic(
  completion: OpenAIChatCompletion,
): Record<string, unknown> {
  const text = completion.choices?.[0]?.message?.content ?? "";
  return {
    id: `msg_${Date.now()}`,
    type: "message",
    role: "assistant",
    content: [{ type: "text", text }],
    stop_reason: completion.choices?.[0]?.finish_reason ?? "end_turn",
  };
}

/**
 * Translates an OpenAI ChatCompletions SSE stream into the Anthropic
 * Messages SSE shape that ``ClaudeAPI.analyzeImageStreaming`` already
 * parses.
 *
 * OpenAI stream events look like::
 *   data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}
 *   data: {"choices":[{"delta":{},"finish_reason":"stop"}]}
 *   data: [DONE]
 *
 * Anthropic stream events look like::
 *   event: message_start
 *   data: {"type":"message_start","message":{...}}
 *
 *   event: content_block_start
 *   data: {"type":"content_block_start","index":0,
 *          "content_block":{"type":"text","text":""}}
 *
 *   event: content_block_delta
 *   data: {"type":"content_block_delta","index":0,
 *          "delta":{"type":"text_delta","text":"hello"}}
 *
 *   event: content_block_stop
 *   data: {"type":"content_block_stop","index":0}
 *
 *   event: message_stop
 *   data: {"type":"message_stop"}
 *
 * The Swift parser in ``ClaudeAPI.swift`` only inspects
 * ``content_block_delta`` → ``delta.type === "text_delta"`` →
 * ``delta.text``, which is the only event we need to fully populate.
 * The other events are emitted as no-op envelopes so the Anthropic-
 * shaped consumer doesn't choke on missing framing.
 */
function openAIStreamToAnthropic(
  upstream: ReadableStream<Uint8Array>,
): ReadableStream<Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();

  return new ReadableStream<Uint8Array>({
    async start(controller) {
      // Open the Anthropic-shaped stream with the framing events the
      // Swift parser tolerates.
      controller.enqueue(
        encoder.encode(
          `event: message_start\n` +
            `data: ${JSON.stringify({
              type: "message_start",
              message: {
                id: `msg_${Date.now()}`,
                type: "message",
                role: "assistant",
                content: [],
              },
            })}\n\n`,
        ),
      );
      controller.enqueue(
        encoder.encode(
          `event: content_block_start\n` +
            `data: ${JSON.stringify({
              type: "content_block_start",
              index: 0,
              content_block: { type: "text", text: "" },
            })}\n\n`,
        ),
      );

      const reader = upstream.getReader();
      let buffer = "";

      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          // OpenAI SSE chunks are separated by "\n\n"; loop through
          // every complete event in the buffer.
          let separatorIndex: number;
          while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
            const rawEvent = buffer.slice(0, separatorIndex);
            buffer = buffer.slice(separatorIndex + 2);

            for (const rawLine of rawEvent.split("\n")) {
              if (!rawLine.startsWith("data: ")) continue;
              const payload = rawLine.slice("data: ".length).trim();
              if (payload === "[DONE]") continue;
              if (!payload) continue;

              try {
                const parsed = JSON.parse(payload) as OpenAIChatCompletion;
                const textChunk = parsed.choices?.[0]?.delta?.content;
                if (typeof textChunk === "string" && textChunk.length > 0) {
                  controller.enqueue(
                    encoder.encode(
                      `event: content_block_delta\n` +
                        `data: ${JSON.stringify({
                          type: "content_block_delta",
                          index: 0,
                          delta: { type: "text_delta", text: textChunk },
                        })}\n\n`,
                    ),
                  );
                }
              } catch (parseError) {
                console.error(
                  `[/chat] failed to parse upstream chunk: ${payload}`,
                  parseError,
                );
              }
            }
          }
        }

        // Flush any trailing partial text — usually empty.
        if (buffer.trim().length > 0) {
          console.error(
            `[/chat] dropping unterminated upstream tail: ${buffer.slice(0, 200)}`,
          );
        }
      } finally {
        controller.enqueue(
          encoder.encode(
            `event: content_block_stop\n` +
              `data: ${JSON.stringify({ type: "content_block_stop", index: 0 })}\n\n`,
          ),
        );
        controller.enqueue(
          encoder.encode(
            `event: message_stop\n` +
              `data: ${JSON.stringify({ type: "message_stop" })}\n\n`,
          ),
        );
        controller.close();
      }
    },
  });
}

// ───────────────────────────────────────────────────────────────────
// Tiny utilities (CORS so wrangler dev can serve the local Mac app)
// ───────────────────────────────────────────────────────────────────
function corsHeaders(): Record<string, string> {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type, authorization, x-api-key",
  };
}

function withCors(response: Response): Response {
  const merged = new Headers(response.headers);
  for (const [key, value] of Object.entries(corsHeaders())) {
    merged.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: merged,
  });
}

function errorResponse(path: string, error: unknown): Response {
  console.error(`[${path}] unhandled error:`, error);
  return new Response(JSON.stringify({ error: String(error) }), {
    status: 500,
    headers: { "content-type": "application/json", ...corsHeaders() },
  });
}
