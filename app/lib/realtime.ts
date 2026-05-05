"use client";

/**
 * Browser-side glue for the OpenAI Realtime continuous voice loop.
 *
 * Architecture (matches backend `xiexie/voice/realtime.py`):
 *
 *   1. Hit `POST /voice/session` on our backend to get a short-lived
 *      `client_secret` + the chosen model name. The long-lived
 *      `OPENAI_API_KEY` never reaches the browser.
 *   2. Open an `RTCPeerConnection` straight to OpenAI:
 *      `https://api.openai.com/v1/realtime?model=<model>`. We attach
 *      the local mic track and a hidden `<audio>` element for the
 *      remote (model) audio playback.
 *   3. The peer connection exposes a `oai-events` data channel that
 *      streams the same JSON event stream the backend WS would see.
 *      We surface a curated subset to the page via the `events`
 *      callback (transcript, tool starts/finishes, errors).
 *   4. When the model emits a `response.function_call_arguments.done`
 *      event we forward the call to our backend `/voice/tool` endpoint.
 *      Once that returns, we send a `conversation.item.create`
 *      (`function_call_output`) + `response.create` back through the
 *      data channel so the model can fold the tool result into its
 *      next spoken turn.
 *
 * If the backend reports `continuous: false` (no `OPENAI_API_KEY`),
 * `RealtimeClient.start` rejects and the page falls back to the
 * click-mic Whisper flow that already works.
 */

export type RealtimeEvent =
  | { type: "user_transcript"; text: string }
  | { type: "assistant_transcript"; text: string; partial?: boolean }
  | { type: "tool_start"; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: string; ok: boolean }
  | { type: "model_audio_started" }
  | { type: "model_audio_stopped" }
  | { type: "error"; message: string };

export interface RealtimeCapabilities {
  continuous: boolean;
  model: string;
  voice: string;
}

export interface RealtimeStartOptions {
  backendUrl: string;
  onEvent?: (event: RealtimeEvent) => void;
}

interface SessionTokenResponse {
  client_secret: string;
  session_id: string;
  model: string;
  voice: string;
  expires_at?: number;
}

interface DataChannelEvent {
  type?: string;
  transcript?: string;
  delta?: string;
  name?: string;
  call_id?: string;
  arguments?: string | Record<string, unknown>;
  error?: { message?: string } | string;
  response?: { output?: Array<Record<string, unknown>> };
}

const OPENAI_REALTIME_BASE = "https://api.openai.com/v1/realtime";

export async function fetchVoiceCapabilities(
  backendUrl: string
): Promise<RealtimeCapabilities> {
  try {
    const res = await fetch(`${backendUrl}/voice/capabilities`);
    if (!res.ok) {
      return { continuous: false, model: "gpt-realtime", voice: "marin" };
    }
    const data = (await res.json()) as Partial<RealtimeCapabilities>;
    return {
      continuous: Boolean(data.continuous),
      model: data.model ?? "gpt-realtime",
      voice: data.voice ?? "marin",
    };
  } catch {
    return { continuous: false, model: "gpt-realtime", voice: "marin" };
  }
}

export class RealtimeClient {
  private pc: RTCPeerConnection | null = null;
  private dc: RTCDataChannel | null = null;
  private localStream: MediaStream | null = null;
  private remoteAudio: HTMLAudioElement | null = null;
  private backendUrl = "";
  private model = "gpt-realtime";
  private onEvent: (event: RealtimeEvent) => void = () => {};
  private connected = false;

  isConnected(): boolean {
    return this.connected;
  }

  /**
   * Open the peer connection. Resolves when the SDP exchange is done and
   * the data channel is ready to ferry events.
   */
  async start(options: RealtimeStartOptions): Promise<void> {
    if (this.connected) return;
    this.backendUrl = options.backendUrl;
    this.onEvent = options.onEvent ?? (() => {});

    const token = await this.mintToken();
    this.model = token.model || this.model;

    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
      throw new Error("getUserMedia is not available in this browser");
    }
    if (typeof RTCPeerConnection === "undefined") {
      throw new Error("WebRTC is not supported in this browser");
    }

    const pc = new RTCPeerConnection();
    this.pc = pc;

    // Hidden <audio> element so the model's voice is actually audible.
    // Autoplay only works once the user has interacted with the page;
    // the mic-button click that triggers `start` covers that constraint.
    const audio = document.createElement("audio");
    audio.autoplay = true;
    audio.style.display = "none";
    document.body.appendChild(audio);
    this.remoteAudio = audio;

    pc.ontrack = (ev) => {
      const [stream] = ev.streams;
      if (stream && this.remoteAudio) {
        this.remoteAudio.srcObject = stream;
        this.onEvent({ type: "model_audio_started" });
      }
    };

    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    this.localStream = stream;
    for (const track of stream.getAudioTracks()) {
      pc.addTrack(track, stream);
    }

    // OpenAI exposes a single bidirectional data channel called
    // ``oai-events`` for the JSON event stream.
    const dc = pc.createDataChannel("oai-events");
    this.dc = dc;
    dc.onopen = () => {
      this.connected = true;
    };
    dc.onclose = () => {
      this.connected = false;
      this.onEvent({ type: "model_audio_stopped" });
    };
    dc.onerror = () => {
      this.onEvent({
        type: "error",
        message: "data channel error — voice loop may be degraded",
      });
    };
    dc.onmessage = (ev) => {
      void this.handleDataChannelMessage(ev.data);
    };

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const sdpResponse = await fetch(`${OPENAI_REALTIME_BASE}?model=${this.model}`, {
      method: "POST",
      body: offer.sdp,
      headers: {
        Authorization: `Bearer ${token.client_secret}`,
        "Content-Type": "application/sdp",
        "OpenAI-Beta": "realtime=v1",
      },
    });
    if (!sdpResponse.ok) {
      const detail = await sdpResponse.text().catch(() => "");
      throw new Error(`OpenAI SDP exchange failed (${sdpResponse.status}): ${detail}`);
    }
    const answerSdp = await sdpResponse.text();
    await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });
  }

  /** Tear down the peer connection and release the mic. Idempotent. */
  stop(): void {
    this.connected = false;
    try {
      this.dc?.close();
    } catch {
      /* ignore */
    }
    this.dc = null;

    try {
      this.pc?.close();
    } catch {
      /* ignore */
    }
    this.pc = null;

    if (this.localStream) {
      for (const track of this.localStream.getTracks()) track.stop();
      this.localStream = null;
    }

    if (this.remoteAudio) {
      this.remoteAudio.pause();
      this.remoteAudio.srcObject = null;
      this.remoteAudio.remove();
      this.remoteAudio = null;
    }
  }

  /** Inject a typed message into the live voice conversation. */
  sendText(text: string): void {
    const trimmed = text.trim();
    if (!trimmed || !this.dc || this.dc.readyState !== "open") return;
    this.dc.send(
      JSON.stringify({
        type: "conversation.item.create",
        item: {
          type: "message",
          role: "user",
          content: [{ type: "input_text", text: trimmed }],
        },
      })
    );
    this.dc.send(JSON.stringify({ type: "response.create" }));
  }

  // ── private ───────────────────────────────────────────────────────────

  private async mintToken(): Promise<SessionTokenResponse> {
    const res = await fetch(`${this.backendUrl}/voice/session`, { method: "POST" });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(`/voice/session failed (${res.status}): ${detail}`);
    }
    const data = (await res.json()) as Partial<SessionTokenResponse>;
    if (!data.client_secret) {
      throw new Error("/voice/session response missing client_secret");
    }
    return {
      client_secret: data.client_secret,
      session_id: data.session_id ?? "",
      model: data.model ?? "gpt-realtime",
      voice: data.voice ?? "marin",
      expires_at: data.expires_at,
    };
  }

  private async handleDataChannelMessage(raw: unknown): Promise<void> {
    if (typeof raw !== "string") return;
    let event: DataChannelEvent;
    try {
      event = JSON.parse(raw) as DataChannelEvent;
    } catch {
      return;
    }

    switch (event.type) {
      case "conversation.item.input_audio_transcription.completed": {
        if (event.transcript) {
          this.onEvent({ type: "user_transcript", text: event.transcript });
        }
        return;
      }
      case "response.audio_transcript.delta": {
        if (event.delta) {
          this.onEvent({
            type: "assistant_transcript",
            text: event.delta,
            partial: true,
          });
        }
        return;
      }
      case "response.audio_transcript.done": {
        if (event.transcript) {
          this.onEvent({ type: "assistant_transcript", text: event.transcript });
        }
        return;
      }
      case "response.function_call_arguments.done": {
        await this.relayFunctionCall(event);
        return;
      }
      case "error": {
        const msg =
          typeof event.error === "string"
            ? event.error
            : event.error?.message ?? "unknown realtime error";
        this.onEvent({ type: "error", message: msg });
        return;
      }
      default:
        return;
    }
  }

  /**
   * Forward a model-emitted function call to our backend tool runner,
   * then send the textual result back into the realtime conversation
   * so the model can speak it. Falls back to a JSON error if the
   * backend rejects.
   */
  private async relayFunctionCall(event: DataChannelEvent): Promise<void> {
    const name = event.name ?? "";
    const callId = event.call_id ?? "";
    if (!name || !callId) return;

    let parsedArgs: Record<string, unknown> = {};
    try {
      parsedArgs =
        typeof event.arguments === "string"
          ? (JSON.parse(event.arguments) as Record<string, unknown>)
          : event.arguments ?? {};
    } catch {
      parsedArgs = {};
    }

    this.onEvent({ type: "tool_start", name, args: parsedArgs });

    let output = "";
    let ok = false;
    try {
      const res = await fetch(`${this.backendUrl}/voice/tool`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, arguments: parsedArgs, call_id: callId }),
      });
      if (!res.ok) {
        const detail = await res.text().catch(() => "");
        output = JSON.stringify({ error: `backend ${res.status}: ${detail}` });
      } else {
        const data = (await res.json()) as { ok?: boolean; output?: string };
        ok = Boolean(data.ok);
        output = data.output ?? "";
      }
    } catch (err) {
      output = JSON.stringify({
        error: err instanceof Error ? err.message : "tool relay failed",
      });
    }

    this.onEvent({ type: "tool_result", name, result: output, ok });

    if (this.dc?.readyState === "open") {
      this.dc.send(
        JSON.stringify({
          type: "conversation.item.create",
          item: {
            type: "function_call_output",
            call_id: callId,
            output,
          },
        })
      );
      this.dc.send(JSON.stringify({ type: "response.create" }));
    }
  }
}
