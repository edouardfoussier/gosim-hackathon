"use client";

export type ServerEvent =
  | { type: "transcript"; text: string }
  | { type: "speak"; text: string }
  | { type: "confirm"; text: string }
  | { type: "skill_start"; name: string; args: Record<string, unknown> }
  | { type: "skill_result"; name: string; result: string }
  | { type: "skill_error"; name: string; error: string }
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
