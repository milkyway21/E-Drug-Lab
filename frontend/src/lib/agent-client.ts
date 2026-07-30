import { getApiBaseUrl } from "./api-client";

export type AgentSession = {
  id: string;
  target_id: string;
  created_at: string;
  message_count: number;
  context_summary?: string;
};

export type UiCommand = {
  id: string;
  ts: string;
  type: string;
  path?: string;
  entity_type?: string;
  entity_id?: string;
  molecule_id?: string;
  smiles?: string;
  target_id?: string;
  name?: string;
  api_path?: string;
  body?: Record<string, unknown>;
};

const AGENT_SESSION_KEY = "edrug-agent-session-v1";
const AGENT_TARGET_KEY = "edrug-agent-target-v1";

export function loadStoredSessionId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AGENT_SESSION_KEY);
}

export function storeSessionId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AGENT_SESSION_KEY, id);
}

export function loadStoredTargetId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(AGENT_TARGET_KEY);
}

export function storeTargetId(id: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AGENT_TARGET_KEY, id);
}

export async function createAgentSession(targetId = "_unset_"): Promise<AgentSession> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_id: targetId || "_unset_" }),
  });
  if (!res.ok) throw new Error(`session create failed: ${res.status}`);
  const data = (await res.json()) as { session: AgentSession };
  storeSessionId(data.session.id);
  if (data.session.target_id && data.session.target_id !== "_unset_") {
    storeTargetId(data.session.target_id);
  }
  return data.session;
}

export async function retargetAgentSession(
  sessionId: string,
  targetId: string
): Promise<AgentSession> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/session/${sessionId}/retarget`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_id: targetId }),
  });
  if (!res.ok) throw new Error(`retarget failed: ${res.status}`);
  const data = (await res.json()) as { session: AgentSession };
  storeTargetId(data.session.target_id);
  return data.session;
}

export async function fetchAgentTargets(): Promise<string[]> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/targets`);
  if (!res.ok) return ["HSD17B13"];
  const data = (await res.json()) as { targets?: string[] };
  return data.targets?.length ? data.targets : ["HSD17B13"];
}

export async function fetchAgentSession(sessionId: string): Promise<AgentSession | null> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/session/${sessionId}`);
  if (!res.ok) return null;
  const data = (await res.json()) as { session: AgentSession };
  return data.session ?? null;
}

export type ChatResponse = {
  reply: string;
  thinking?: string;
  bridge_mode?: string;
  target_id?: string;
  error?: string;
  status?: string;
};

export async function sendAgentMessage(
  sessionId: string,
  message: string,
  pagePath?: string
): Promise<ChatResponse> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, page_path: pagePath }),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  const data = (await res.json()) as {
    reply: string;
    thinking?: string;
    bridge_mode?: string;
    target_id?: string;
    error?: string;
    status?: string;
  };
  return {
    reply: data.reply,
    thinking: data.thinking,
    bridge_mode: data.bridge_mode,
    target_id: data.target_id,
    error: data.error,
    status: data.status,
  };
}

export type StreamHandlers = {
  onDelta?: (chunk: string) => void;
  onThinking?: (chunk: string) => void;
  onTool?: (line: string) => void;
  onError?: (message: string) => void;
  onUiCommand?: (cmd: { command?: string; path?: string; target_id?: string }) => void;
  onDone?: (meta: {
    bridge_mode?: string;
    thinking?: string;
    target_id?: string;
    reply?: string;
    error?: string;
  }) => void;
};

/** Scientist SSE: delta / thinking / tool / done / error (+ ui_command). */
export async function streamAgentMessage(
  sessionId: string,
  message: string,
  onDeltaOrHandlers: ((chunk: string) => void) | StreamHandlers,
  onDone?: (meta: { bridge_mode?: string; thinking?: string; target_id?: string }) => void,
  pagePath?: string
): Promise<void> {
  const handlers: StreamHandlers =
    typeof onDeltaOrHandlers === "function"
      ? { onDelta: onDeltaOrHandlers, onDone }
      : onDeltaOrHandlers;

  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message, page_path: pagePath }),
  });
  if (!res.ok || !res.body) throw new Error(`stream failed: ${res.status}`);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";
    for (const part of parts) {
      const line = part.trim();
      if (!line.startsWith("data: ")) continue;
      try {
        const payload = JSON.parse(line.slice(6)) as {
          type?: string;
          delta?: string;
          text?: string;
          message?: string;
          done?: boolean;
          bridge_mode?: string;
          thinking?: string;
          target_id?: string;
          reply?: string;
          error?: string;
          command?: string;
          path?: string;
          name?: string;
          status?: string;
        };
        const t = payload.type;
        if (t === "delta" || (!t && payload.delta)) {
          const chunk = payload.delta || payload.text || "";
          if (chunk) handlers.onDelta?.(chunk);
        } else if (t === "thinking") {
          if (payload.text) handlers.onThinking?.(payload.text);
        } else if (t === "tool") {
          const lineText = payload.text || (payload.name ? `⚙ ${payload.name}` : "");
          if (lineText) handlers.onTool?.(lineText);
        } else if (t === "error") {
          handlers.onError?.(payload.message || payload.error || "E-Drug Lab Scientist 未连接");
        } else if (t === "ui_command") {
          handlers.onUiCommand?.({
            command: payload.command,
            path: payload.path,
            target_id: payload.target_id,
          });
        }
        if (t === "done" || payload.done) {
          handlers.onDone?.({
            bridge_mode: payload.bridge_mode,
            thinking: payload.thinking,
            target_id: payload.target_id,
            reply: payload.reply,
            error: payload.error || (t === "done" && payload.bridge_mode === "offline" ? payload.error : undefined),
          });
        }
      } catch {
        /* ignore malformed SSE */
      }
    }
  }
}

export async function fetchUiCommands(sessionId: string, sinceId?: string): Promise<UiCommand[]> {
  const q = sinceId ? `?since_id=${encodeURIComponent(sinceId)}` : "";
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/ui-commands/${sessionId}${q}`);
  if (!res.ok) return [];
  const data = (await res.json()) as { commands: UiCommand[] };
  return data.commands ?? [];
}

export async function fetchMemoryPreview(targetId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${getApiBaseUrl()}/api/v1/agent/memory/${encodeURIComponent(targetId)}`);
  if (!res.ok) throw new Error(`memory preview failed: ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}
