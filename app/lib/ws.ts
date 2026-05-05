"use client";

export type ServerEvent =
  | { type: "transcript"; text: string }
  | { type: "speak"; text: string }
  | { type: "confirm"; text: string }
  | { type: "skill_start"; name: string; args: Record<string, unknown> }
  | { type: "skill_result"; name: string; result: string }
  | { type: "skill_error"; name: string; error: string }
  | {
      type: "alert";
      // Backend emits the overlay-native vocabulary (phishing | suspicious
      // | clear). "warning" / "danger" are kept as legacy synonyms so a
      // mid-flight upgrade doesn't break any deployed Chrome extension.
      level?: "phishing" | "suspicious" | "clear" | "warning" | "danger";
      message: string;
    }
  // Mirrors the backend's bus.broadcast_speaking — the frontend echoes
  // its own gpt-realtime audio levels here, but listening to the WS lets
  // any other surface (cursor halo, status pill, future Tauri overlay)
  // react to the same signal without duplicating the analyser.
  | {
      type: "speaking";
      state: "start" | "stop";
      level?: number;
    }
  // Working = silent agent activity (vision call, scam analysis, AppleScript
  // automation). Distinct from speaking because Margaret should see the
  // halo even when Xiexie isn't talking. ``label`` is a short hint
  // (e.g. "looking at your screen") rendered next to the bars.
  | {
      type: "working";
      state: "start" | "stop";
      label?: string;
    }
  | { type: "done" }
  | { type: "pong" }
  | { type: "error"; message: string };

export type ClientEvent =
  | { type: "ping" }
  | {
      type: "user_text";
      text: string;
      history?: { role: "user" | "assistant"; content: string }[];
    };

export function connect(
  url: string,
  onEvent: (e: ServerEvent) => void,
  onOpen?: () => void,
  onClose?: () => void
): WebSocket {
  const ws = new WebSocket(url);
  ws.addEventListener("open", () => onOpen?.());
  ws.addEventListener("close", () => onClose?.());
  ws.addEventListener("message", (m) => {
    try {
      onEvent(JSON.parse(m.data) as ServerEvent);
    } catch {
      /* ignore */
    }
  });
  return ws;
}

export function send(ws: WebSocket, event: ClientEvent): void {
  if (ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify(event));
}
