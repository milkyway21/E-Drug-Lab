"use client";

import { useEffect } from "react";
import { getApiBaseUrl } from "@/lib/api-client";

const HIGHLIGHT_CLASS =
  "ring-2 ring-sky-400 ring-offset-2 ring-offset-white transition-shadow duration-300";

export default function AgentUiEffects() {
  useEffect(() => {
    const onHighlight = (e: Event) => {
      const detail = (e as CustomEvent).detail as { entityId?: string };
      if (!detail?.entityId) return;
      const el = document.querySelector(`[data-entity-id="${detail.entityId}"]`);
      if (!el) return;
      el.classList.add(HIGHLIGHT_CLASS);
      window.setTimeout(() => el.classList.remove(HIGHLIGHT_CLASS), 4000);
    };

    const onStartTask = async (e: Event) => {
      const detail = (e as CustomEvent).detail as {
        apiPath?: string;
        body?: Record<string, unknown>;
      };
      if (!detail?.apiPath) return;
      try {
        const res = await fetch(`${getApiBaseUrl()}${detail.apiPath}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(detail.body ?? {}),
        });
        if (!res.ok) {
          const text = await res.text();
          window.dispatchEvent(
            new CustomEvent("edrug-agent-task-result", {
              detail: { ok: false, message: `任务失败 HTTP ${res.status}: ${text.slice(0, 160)}` },
            })
          );
          return;
        }
        window.dispatchEvent(
          new CustomEvent("edrug-agent-task-result", {
            detail: { ok: true, message: `已提交 ${detail.apiPath}` },
          })
        );
      } catch (err) {
        window.dispatchEvent(
          new CustomEvent("edrug-agent-task-result", {
            detail: {
              ok: false,
              message: `任务错误: ${err instanceof Error ? err.message : String(err)}`,
            },
          })
        );
      }
    };

    window.addEventListener("edrug-agent-highlight", onHighlight);
    window.addEventListener("edrug-agent-start-task", onStartTask);
    return () => {
      window.removeEventListener("edrug-agent-highlight", onHighlight);
      window.removeEventListener("edrug-agent-start-task", onStartTask);
    };
  }, []);

  return null;
}
