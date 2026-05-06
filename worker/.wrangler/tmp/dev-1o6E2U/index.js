var __defProp = Object.defineProperty;
var __name = (target, value) => __defProp(target, "name", { value, configurable: true });

// .wrangler/tmp/bundle-TbvWnp/checked-fetch.js
var urls = /* @__PURE__ */ new Set();
function checkURL(request, init) {
  const url = request instanceof URL ? request : new URL(
    (typeof request === "string" ? new Request(request, init) : request).url
  );
  if (url.port && url.port !== "443" && url.protocol === "https:") {
    if (!urls.has(url.toString())) {
      urls.add(url.toString());
      console.warn(
        `WARNING: known issue with \`fetch()\` requests to custom HTTPS ports in published Workers:
 - ${url.toString()} - the custom port will be ignored when the Worker is published using the \`wrangler deploy\` command.
`
      );
    }
  }
}
__name(checkURL, "checkURL");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    const [request, init] = argArray;
    checkURL(request, init);
    return Reflect.apply(target, thisArg, argArray);
  }
});

// .wrangler/tmp/bundle-TbvWnp/strip-cf-connecting-ip-header.js
function stripCfConnectingIPHeader(input, init) {
  const request = new Request(input, init);
  request.headers.delete("CF-Connecting-IP");
  return request;
}
__name(stripCfConnectingIPHeader, "stripCfConnectingIPHeader");
globalThis.fetch = new Proxy(globalThis.fetch, {
  apply(target, thisArg, argArray) {
    return Reflect.apply(target, thisArg, [
      stripCfConnectingIPHeader.apply(null, argArray)
    ]);
  }
});

// src/index.ts
var DEFAULT_ZAI_BASE = "https://api.z.ai/api/paas/v4";
var DEFAULT_TEXT_MODEL = "glm-4.6";
var DEFAULT_VISION_MODEL = "glm-4.5v";
var src_default = {
  async fetch(request, env) {
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
      if (url.pathname === "/chat")
        return withCors(await handleChat(request, env));
      if (url.pathname === "/tts")
        return withCors(await handleTTS(request, env));
      if (url.pathname === "/transcribe-token") {
        return withCors(await handleTranscribeToken(env));
      }
    } catch (error) {
      return errorResponse(url.pathname, error);
    }
    return new Response("Not found", { status: 404 });
  }
};
async function handleChat(request, env) {
  const incoming = await request.json();
  const isStreaming = incoming.stream === true;
  const hasImage = anyContentBlockIsImage(incoming.messages);
  const baseURL = (env.ZAI_BASE_URL || DEFAULT_ZAI_BASE).replace(/\/$/, "");
  const upstreamModel = hasImage ? env.ZAI_VISION_MODEL || DEFAULT_VISION_MODEL : env.ZAI_TEXT_MODEL || DEFAULT_TEXT_MODEL;
  const openAIBody = anthropicToOpenAI(incoming, upstreamModel, isStreaming);
  const upstreamResponse = await fetch(`${baseURL}/chat/completions`, {
    method: "POST",
    headers: {
      "authorization": `Bearer ${env.ZAI_API_KEY}`,
      "content-type": "application/json"
    },
    body: JSON.stringify(openAIBody)
  });
  if (!upstreamResponse.ok) {
    const text = await upstreamResponse.text();
    console.error(`[/chat] upstream ${upstreamResponse.status}: ${text}`);
    return new Response(text, {
      status: upstreamResponse.status,
      headers: { "content-type": "application/json" }
    });
  }
  if (isStreaming && upstreamResponse.body) {
    const anthropicStream = openAIStreamToAnthropic(upstreamResponse.body);
    return new Response(anthropicStream, {
      status: 200,
      headers: {
        "content-type": "text/event-stream",
        "cache-control": "no-cache"
      }
    });
  }
  const completion = await upstreamResponse.json();
  const anthropicLike = openAICompletionToAnthropic(completion);
  return new Response(JSON.stringify(anthropicLike), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
}
__name(handleChat, "handleChat");
async function handleTTS(request, env) {
  const body = await request.text();
  const voiceId = env.ELEVENLABS_VOICE_ID;
  const response = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": env.ELEVENLABS_API_KEY,
        "content-type": "application/json",
        accept: "audio/mpeg"
      },
      body
    }
  );
  if (!response.ok) {
    const errorBody = await response.text();
    console.error(`[/tts] ElevenLabs API error ${response.status}: ${errorBody}`);
    return new Response(errorBody, {
      status: response.status,
      headers: { "content-type": "application/json" }
    });
  }
  return new Response(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") || "audio/mpeg"
    }
  });
}
__name(handleTTS, "handleTTS");
async function handleTranscribeToken(env) {
  const response = await fetch(
    "https://streaming.assemblyai.com/v3/token?expires_in_seconds=480",
    { method: "GET", headers: { authorization: env.ASSEMBLYAI_API_KEY } }
  );
  if (!response.ok) {
    const errorBody = await response.text();
    console.error(`[/transcribe-token] AssemblyAI ${response.status}: ${errorBody}`);
    return new Response(errorBody, {
      status: response.status,
      headers: { "content-type": "application/json" }
    });
  }
  return new Response(await response.text(), {
    status: 200,
    headers: { "content-type": "application/json" }
  });
}
__name(handleTranscribeToken, "handleTranscribeToken");
function anyContentBlockIsImage(messages) {
  for (const message of messages) {
    if (Array.isArray(message.content)) {
      for (const block of message.content) {
        if (block.type === "image")
          return true;
      }
    }
  }
  return false;
}
__name(anyContentBlockIsImage, "anyContentBlockIsImage");
function anthropicToOpenAI(request, upstreamModel, isStreaming) {
  const openAIMessages = [];
  if (request.system) {
    openAIMessages.push({ role: "system", content: request.system });
  }
  for (const message of request.messages) {
    if (typeof message.content === "string") {
      openAIMessages.push({ role: message.role, content: message.content });
      continue;
    }
    const openAIContent = [];
    for (const block of message.content) {
      if (block.type === "text") {
        openAIContent.push({ type: "text", text: block.text });
      } else if (block.type === "image") {
        openAIContent.push({
          type: "image_url",
          image_url: {
            url: `data:${block.source.media_type};base64,${block.source.data}`
          }
        });
      }
    }
    openAIMessages.push({ role: message.role, content: openAIContent });
  }
  return {
    model: upstreamModel,
    max_tokens: request.max_tokens ?? 1024,
    stream: isStreaming,
    messages: openAIMessages,
    thinking: { type: "disabled" }
  };
}
__name(anthropicToOpenAI, "anthropicToOpenAI");
function openAICompletionToAnthropic(completion) {
  const text = completion.choices?.[0]?.message?.content ?? "";
  return {
    id: `msg_${Date.now()}`,
    type: "message",
    role: "assistant",
    content: [{ type: "text", text }],
    stop_reason: completion.choices?.[0]?.finish_reason ?? "end_turn"
  };
}
__name(openAICompletionToAnthropic, "openAICompletionToAnthropic");
function openAIStreamToAnthropic(upstream) {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  return new ReadableStream({
    async start(controller) {
      controller.enqueue(
        encoder.encode(
          `event: message_start
data: ${JSON.stringify({
            type: "message_start",
            message: {
              id: `msg_${Date.now()}`,
              type: "message",
              role: "assistant",
              content: []
            }
          })}

`
        )
      );
      controller.enqueue(
        encoder.encode(
          `event: content_block_start
data: ${JSON.stringify({
            type: "content_block_start",
            index: 0,
            content_block: { type: "text", text: "" }
          })}

`
        )
      );
      const reader = upstream.getReader();
      let buffer = "";
      try {
        while (true) {
          const { value, done } = await reader.read();
          if (done)
            break;
          buffer += decoder.decode(value, { stream: true });
          let separatorIndex;
          while ((separatorIndex = buffer.indexOf("\n\n")) !== -1) {
            const rawEvent = buffer.slice(0, separatorIndex);
            buffer = buffer.slice(separatorIndex + 2);
            for (const rawLine of rawEvent.split("\n")) {
              if (!rawLine.startsWith("data: "))
                continue;
              const payload = rawLine.slice("data: ".length).trim();
              if (payload === "[DONE]")
                continue;
              if (!payload)
                continue;
              try {
                const parsed = JSON.parse(payload);
                const textChunk = parsed.choices?.[0]?.delta?.content;
                if (typeof textChunk === "string" && textChunk.length > 0) {
                  controller.enqueue(
                    encoder.encode(
                      `event: content_block_delta
data: ${JSON.stringify({
                        type: "content_block_delta",
                        index: 0,
                        delta: { type: "text_delta", text: textChunk }
                      })}

`
                    )
                  );
                }
              } catch (parseError) {
                console.error(
                  `[/chat] failed to parse upstream chunk: ${payload}`,
                  parseError
                );
              }
            }
          }
        }
        if (buffer.trim().length > 0) {
          console.error(
            `[/chat] dropping unterminated upstream tail: ${buffer.slice(0, 200)}`
          );
        }
      } finally {
        controller.enqueue(
          encoder.encode(
            `event: content_block_stop
data: ${JSON.stringify({ type: "content_block_stop", index: 0 })}

`
          )
        );
        controller.enqueue(
          encoder.encode(
            `event: message_stop
data: ${JSON.stringify({ type: "message_stop" })}

`
          )
        );
        controller.close();
      }
    }
  });
}
__name(openAIStreamToAnthropic, "openAIStreamToAnthropic");
function corsHeaders() {
  return {
    "access-control-allow-origin": "*",
    "access-control-allow-methods": "GET, POST, OPTIONS",
    "access-control-allow-headers": "content-type, authorization, x-api-key"
  };
}
__name(corsHeaders, "corsHeaders");
function withCors(response) {
  const merged = new Headers(response.headers);
  for (const [key, value] of Object.entries(corsHeaders())) {
    merged.set(key, value);
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: merged
  });
}
__name(withCors, "withCors");
function errorResponse(path, error) {
  console.error(`[${path}] unhandled error:`, error);
  return new Response(JSON.stringify({ error: String(error) }), {
    status: 500,
    headers: { "content-type": "application/json", ...corsHeaders() }
  });
}
__name(errorResponse, "errorResponse");

// node_modules/wrangler/templates/middleware/middleware-ensure-req-body-drained.ts
var drainBody = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } finally {
    try {
      if (request.body !== null && !request.bodyUsed) {
        const reader = request.body.getReader();
        while (!(await reader.read()).done) {
        }
      }
    } catch (e) {
      console.error("Failed to drain the unused request body.", e);
    }
  }
}, "drainBody");
var middleware_ensure_req_body_drained_default = drainBody;

// node_modules/wrangler/templates/middleware/middleware-miniflare3-json-error.ts
function reduceError(e) {
  return {
    name: e?.name,
    message: e?.message ?? String(e),
    stack: e?.stack,
    cause: e?.cause === void 0 ? void 0 : reduceError(e.cause)
  };
}
__name(reduceError, "reduceError");
var jsonError = /* @__PURE__ */ __name(async (request, env, _ctx, middlewareCtx) => {
  try {
    return await middlewareCtx.next(request, env);
  } catch (e) {
    const error = reduceError(e);
    return Response.json(error, {
      status: 500,
      headers: { "MF-Experimental-Error-Stack": "true" }
    });
  }
}, "jsonError");
var middleware_miniflare3_json_error_default = jsonError;

// .wrangler/tmp/bundle-TbvWnp/middleware-insertion-facade.js
var __INTERNAL_WRANGLER_MIDDLEWARE__ = [
  middleware_ensure_req_body_drained_default,
  middleware_miniflare3_json_error_default
];
var middleware_insertion_facade_default = src_default;

// node_modules/wrangler/templates/middleware/common.ts
var __facade_middleware__ = [];
function __facade_register__(...args) {
  __facade_middleware__.push(...args.flat());
}
__name(__facade_register__, "__facade_register__");
function __facade_invokeChain__(request, env, ctx, dispatch, middlewareChain) {
  const [head, ...tail] = middlewareChain;
  const middlewareCtx = {
    dispatch,
    next(newRequest, newEnv) {
      return __facade_invokeChain__(newRequest, newEnv, ctx, dispatch, tail);
    }
  };
  return head(request, env, ctx, middlewareCtx);
}
__name(__facade_invokeChain__, "__facade_invokeChain__");
function __facade_invoke__(request, env, ctx, dispatch, finalMiddleware) {
  return __facade_invokeChain__(request, env, ctx, dispatch, [
    ...__facade_middleware__,
    finalMiddleware
  ]);
}
__name(__facade_invoke__, "__facade_invoke__");

// .wrangler/tmp/bundle-TbvWnp/middleware-loader.entry.ts
var __Facade_ScheduledController__ = class {
  constructor(scheduledTime, cron, noRetry) {
    this.scheduledTime = scheduledTime;
    this.cron = cron;
    this.#noRetry = noRetry;
  }
  #noRetry;
  noRetry() {
    if (!(this instanceof __Facade_ScheduledController__)) {
      throw new TypeError("Illegal invocation");
    }
    this.#noRetry();
  }
};
__name(__Facade_ScheduledController__, "__Facade_ScheduledController__");
function wrapExportedHandler(worker) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return worker;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  const fetchDispatcher = /* @__PURE__ */ __name(function(request, env, ctx) {
    if (worker.fetch === void 0) {
      throw new Error("Handler does not export a fetch() function.");
    }
    return worker.fetch(request, env, ctx);
  }, "fetchDispatcher");
  return {
    ...worker,
    fetch(request, env, ctx) {
      const dispatcher = /* @__PURE__ */ __name(function(type, init) {
        if (type === "scheduled" && worker.scheduled !== void 0) {
          const controller = new __Facade_ScheduledController__(
            Date.now(),
            init.cron ?? "",
            () => {
            }
          );
          return worker.scheduled(controller, env, ctx);
        }
      }, "dispatcher");
      return __facade_invoke__(request, env, ctx, dispatcher, fetchDispatcher);
    }
  };
}
__name(wrapExportedHandler, "wrapExportedHandler");
function wrapWorkerEntrypoint(klass) {
  if (__INTERNAL_WRANGLER_MIDDLEWARE__ === void 0 || __INTERNAL_WRANGLER_MIDDLEWARE__.length === 0) {
    return klass;
  }
  for (const middleware of __INTERNAL_WRANGLER_MIDDLEWARE__) {
    __facade_register__(middleware);
  }
  return class extends klass {
    #fetchDispatcher = (request, env, ctx) => {
      this.env = env;
      this.ctx = ctx;
      if (super.fetch === void 0) {
        throw new Error("Entrypoint class does not define a fetch() function.");
      }
      return super.fetch(request);
    };
    #dispatcher = (type, init) => {
      if (type === "scheduled" && super.scheduled !== void 0) {
        const controller = new __Facade_ScheduledController__(
          Date.now(),
          init.cron ?? "",
          () => {
          }
        );
        return super.scheduled(controller);
      }
    };
    fetch(request) {
      return __facade_invoke__(
        request,
        this.env,
        this.ctx,
        this.#dispatcher,
        this.#fetchDispatcher
      );
    }
  };
}
__name(wrapWorkerEntrypoint, "wrapWorkerEntrypoint");
var WRAPPED_ENTRY;
if (typeof middleware_insertion_facade_default === "object") {
  WRAPPED_ENTRY = wrapExportedHandler(middleware_insertion_facade_default);
} else if (typeof middleware_insertion_facade_default === "function") {
  WRAPPED_ENTRY = wrapWorkerEntrypoint(middleware_insertion_facade_default);
}
var middleware_loader_entry_default = WRAPPED_ENTRY;
export {
  __INTERNAL_WRANGLER_MIDDLEWARE__,
  middleware_loader_entry_default as default
};
//# sourceMappingURL=index.js.map
