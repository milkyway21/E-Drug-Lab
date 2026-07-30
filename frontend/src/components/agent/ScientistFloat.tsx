"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import {
  createAgentSession,
  fetchAgentSession,
  fetchAgentTargets,
  loadStoredSessionId,
  loadStoredTargetId,
  retargetAgentSession,
  sendAgentMessage,
  storeTargetId,
  streamAgentMessage,
} from "@/lib/agent-client";
import { useAgentCommands } from "@/lib/agent-command-context";
import { useWorkflow } from "@/lib/workflow-context";
import { useLang } from "@/lib/i18n/i18n-context";
import AgentMoodFab, { type AgentMood } from "@/components/agent/AgentMoodFab";

type ChatLine = {
  role: "user" | "assistant" | "system" | "tool" | "error";
  text: string;
  thinking?: string;
  tools?: string[];
};

const NAV_ACK_RE = /已入队 navigate\s*→\s*`([^`]+)`|UI 命令已入队\s*→\s*`([^`]+)`/;
const UNSET = "_unset_";
const OFFLINE_FALLBACK = "E-Drug Lab Scientist 未连接";

function bridgeModeLabel(mode: string): string {
  if (mode === "live-cli" || mode === "live-serve") return "Scientist";
  if (mode === "ui-intent") return "快捷操作";
  if (mode === "offline") return "离线";
  return mode;
}

function welcomeCopy(pathname: string, targetId: string | null): string {
  const hasTarget = !!targetId && targetId !== UNSET;
  let path = pathname || "/";
  if (path.length > 1 && path.endsWith("/")) path = path.slice(0, -1);

  if (!hasTarget) {
    return "你好，我是 E-Drug Lab Scientist。请先选择研究靶标，或直接提问。";
  }
  if (path.startsWith("/workflow")) {
    return `已绑定 **${targetId}**。可问当前阶段或让我打开工作流步骤。`;
  }
  return `已绑定 **${targetId}**。需要推进哪个阶段，或有什么具体问题？`;
}

function sanitizeAssistantText(text: string): string {
  if (!text) return text;
  // Collapse long "Available skills" / skill inventory dumps Hermes sometimes echoes
  let out = text.replace(
    /(?:^|\n)(?:Available skills?|技能列表|已加载技能)[^\n]*(?:\n[-*•].+){3,}/gi,
    "\n（能力清单已折叠，需要时直接告诉我你要做什么。）"
  );
  // Soften markdown bold noise in welcome-like short lines
  return out.trim();
}
function summarizeTools(tools: string[]): { summary: string; details: string[] } {
  const cleaned = tools
    .map((t) => t.replace(/^[⚙⚙️]\s*/, "").trim())
    .filter(Boolean)
    .filter((t) => !/available skills?|skill(s)?\s*(list|catalog)|loaded\s+\d+\s+skill/i.test(t))
    .filter((t) => !/^[-*•]\s/.test(t) && t.length < 120);

  const unique = Array.from(new Set(cleaned));
  if (unique.length === 0) {
    return { summary: "", details: [] };
  }
  if (unique.length === 1) {
    const name = unique[0].replace(/^using\s+/i, "").slice(0, 48);
    return { summary: `正在使用：${name}`, details: unique };
  }
  return {
    summary: `已调用 ${unique.length} 项能力`,
    details: unique.slice(0, 8),
  };
}

export default function ScientistFloat({
  onSessionSync,
}: {
  onSessionSync?: (id: string | null) => void;
}) {
  const router = useRouter();
  const pathname = usePathname() || "/";
  const { t } = useLang();
  const { target, setTarget } = useWorkflow();
  const { setSessionId: setProviderSessionId } = useAgentCommands();
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [bridgeMode, setBridgeMode] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [lines, setLines] = useState<ChatLine[]>([]);
  const [busy, setBusy] = useState(false);
  const [mood, setMood] = useState<AgentMood>("idle");
  const [error, setError] = useState<string | null>(null);
  const [targetOptions, setTargetOptions] = useState<string[]>([]);
  const [targetId, setTargetId] = useState<string | null>(null);
  const [customTarget, setCustomTarget] = useState("");
  const [showCustom, setShowCustom] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const welcomeKey = useRef("");
  const autoRetargetDone = useRef(false);
  const doneTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flashDone = useCallback(() => {
    if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    setMood("done");
    doneTimerRef.current = setTimeout(() => {
      setMood("idle");
      doneTimerRef.current = null;
    }, 2200);
  }, []);

  useEffect(() => {
    return () => {
      if (doneTimerRef.current) clearTimeout(doneTimerRef.current);
    };
  }, []);

  const syncSessionId = useCallback(
    (id: string) => {
      setSessionId(id);
      setProviderSessionId(id);
      onSessionSync?.(id);
    },
    [setProviderSessionId, onSessionSync]
  );

  const applyNavigateFromReply = useCallback(
    (text: string) => {
      const m = text.match(NAV_ACK_RE);
      const path = m?.[1] || m?.[2];
      if (path && path.startsWith("/")) router.push(path);
    },
    [router]
  );

  const welcome = useMemo(() => welcomeCopy(pathname, targetId), [pathname, targetId]);

  useEffect(() => {
    fetchAgentTargets()
      .then((t) => setTargetOptions(t.filter(Boolean)))
      .catch(() => setTargetOptions([]));
  }, []);

  useEffect(() => {
    const fromWf = target?.name || target?.id;
    if (fromWf && fromWf !== UNSET) {
      setTargetId(String(fromWf));
      return;
    }
    const stored = loadStoredTargetId();
    if (stored && stored !== UNSET) setTargetId(stored);
  }, [target?.id, target?.name]);

  // Welcome card only — never invent assistant stub answers
  useEffect(() => {
    if (!open) return;
    const key = `${pathname}|${targetId ?? UNSET}`;
    if (welcomeKey.current === key) return;
    welcomeKey.current = key;
    setLines((prev) => {
      const rest = prev.filter((l) => l.role !== "system");
      return [{ role: "system", text: welcome }, ...rest];
    });
  }, [open, welcome, pathname, targetId]);

  const ensureSession = useCallback(async () => {
    const stored = loadStoredSessionId();
    if (stored) {
      try {
        const session = await fetchAgentSession(stored);
        if (session) {
          syncSessionId(stored);
          const tid = session.target_id;
          if (tid && tid !== UNSET) {
            setTargetId(tid);
            storeTargetId(tid);
          }
          return { id: stored, target_id: tid || UNSET };
        }
      } catch {
        /* recreate */
      }
      if (typeof window !== "undefined") {
        window.localStorage.removeItem("edrug-agent-session-v1");
      }
    }
    const session = await createAgentSession(targetId ?? UNSET);
    syncSessionId(session.id);
    if (session.target_id && session.target_id !== UNSET) setTargetId(session.target_id);
    return session;
  }, [targetId, syncSessionId]);

  const onChangeTarget = async (next: string) => {
    const tid = next.trim();
    if (!tid) return;
    setError(null);
    setTargetId(tid);
    storeTargetId(tid);
    setTarget({ id: tid, name: tid, source: "agent" });
    setShowCustom(false);
    setCustomTarget("");
    try {
      if (sessionId) {
        const session = await retargetAgentSession(sessionId, tid);
        if (session.target_id) setTargetId(session.target_id);
      } else {
        const session = await createAgentSession(tid);
        syncSessionId(session.id);
      }
      setLines((prev) => [
        ...prev.filter((l) => l.role !== "system"),
        { role: "system", text: welcomeCopy(pathname, tid) },
      ]);
      welcomeKey.current = `${pathname}|${tid}`;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    if (!open) return;
    const stored = loadStoredSessionId();
    if (stored) syncSessionId(stored);
  }, [open, syncSessionId]);

  useEffect(() => {
    if (open && !sessionId) {
      ensureSession().catch((e: Error) => setError(e.message));
    }
  }, [open, sessionId, ensureSession]);

  // Local target set but BFF session still _unset_ → auto-retarget once
  useEffect(() => {
    if (!open || !sessionId || autoRetargetDone.current || busy) return;
    const local = targetId && targetId !== UNSET ? targetId : loadStoredTargetId();
    if (!local || local === UNSET) return;
    let cancelled = false;
    (async () => {
      try {
        const session = await fetchAgentSession(sessionId);
        if (cancelled || !session) return;
        if (!session.target_id || session.target_id === UNSET) {
          autoRetargetDone.current = true;
          const updated = await retargetAgentSession(sessionId, local);
          if (!cancelled) {
            setTargetId(updated.target_id);
            storeTargetId(updated.target_id);
            setLines((prev) => [
              ...prev.filter((l) => l.role !== "system"),
              { role: "system", text: welcomeCopy(pathname, updated.target_id) },
            ]);
            welcomeKey.current = `${pathname}|${updated.target_id}`;
          }
        } else {
          autoRetargetDone.current = true;
          // BFF is source of truth after session loads
          if (session.target_id !== targetId) {
            setTargetId(session.target_id);
            storeTargetId(session.target_id);
          }
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, sessionId, targetId, busy, pathname]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines, open]);

  useEffect(() => {
    const onTaskResult = (e: Event) => {
      const d = (e as CustomEvent).detail as { ok?: boolean; message?: string };
      const text = d?.message || (d?.ok ? "任务已提交。" : "任务失败。");
      setLines((prev) => [...prev, { role: "tool", text: `⚙ ${text}` }]);
    };
    window.addEventListener("edrug-agent-task-result", onTaskResult);
    return () => window.removeEventListener("edrug-agent-task-result", onTaskResult);
  }, []);

  const onSend = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setError(null);
    setBusy(true);
    setMood("waiting");
    setLines((prev) => [...prev, { role: "user", text }]);
    try {
      const ensured = await ensureSession();
      const sid = typeof ensured === "string" ? ensured : ensured.id;
      syncSessionId(sid);

      let assistant = "";
      let thinkingAcc = "";
      const toolLines: string[] = [];
      setLines((prev) => [...prev, { role: "assistant", text: "", thinking: "", tools: [] }]);

      const patchAssistant = (patch: Partial<ChatLine>) => {
        setLines((prev) => {
          const copy = [...prev];
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") {
            copy[copy.length - 1] = { ...last, ...patch };
          }
          return copy;
        });
      };

      let gotStream = false;
      let succeeded = false;
      await streamAgentMessage(sid, text, {
        onDelta: (chunk) => {
          gotStream = true;
          setMood("outputting");
          assistant += chunk;
          patchAssistant({ text: assistant, thinking: thinkingAcc, tools: [...toolLines] });
        },
        onThinking: (chunk) => {
          gotStream = true;
          setMood((m) => (m === "outputting" ? m : "thinking"));
          thinkingAcc += chunk;
          patchAssistant({ text: assistant, thinking: thinkingAcc, tools: [...toolLines] });
        },
        onTool: (line) => {
          gotStream = true;
          // Skip skill-catalog dumps; keep actionable tool names only
          if (/available skills?|skill(s)?\s*(list|catalog)|loaded\s+\d+\s+skill/i.test(line)) {
            return;
          }
          if (/^[-*•]\s/.test(line.trim()) || line.length > 120) {
            return;
          }
          setMood((m) => (m === "outputting" ? m : "waiting"));
          toolLines.push(line);
          patchAssistant({ text: assistant, thinking: thinkingAcc, tools: [...toolLines] });
        },
        onError: (msg) => {
          gotStream = true;
          setError(msg.split("\n")[0] || OFFLINE_FALLBACK);
          setLines((prev) => {
            const copy = [...prev];
            // Replace empty assistant bubble with red error line
            if (copy[copy.length - 1]?.role === "assistant" && !copy[copy.length - 1].text) {
              copy[copy.length - 1] = { role: "error", text: msg.split("\n")[0] || OFFLINE_FALLBACK };
            } else {
              copy.push({ role: "error", text: msg.split("\n")[0] || OFFLINE_FALLBACK });
            }
            return copy;
          });
        },
        onUiCommand: (cmd) => {
          if (cmd.command === "navigate" && cmd.path?.startsWith("/")) {
            router.push(cmd.path);
          }
          if (cmd.command === "set_target" && cmd.target_id) {
            setTargetId(cmd.target_id);
            storeTargetId(cmd.target_id);
            setTarget({ id: cmd.target_id, name: cmd.target_id, source: "agent" });
          }
        },
        onDone: (meta) => {
          if (meta.bridge_mode) setBridgeMode(meta.bridge_mode);
          if (meta.target_id && meta.target_id !== UNSET) {
            setTargetId(meta.target_id);
            storeTargetId(meta.target_id);
          }
          if (meta.thinking) thinkingAcc = meta.thinking;
          if (meta.reply) assistant = meta.reply;
          if (meta.error && meta.bridge_mode === "offline") {
            setError(meta.error.split("\n")[0] || OFFLINE_FALLBACK);
            if (!assistant) {
              patchAssistant({
                role: "error",
                text: meta.error.split("\n")[0] || OFFLINE_FALLBACK,
              } as Partial<ChatLine>);
              setLines((prev) => {
                const copy = [...prev];
                if (copy[copy.length - 1]?.role === "assistant" && !copy[copy.length - 1].text) {
                  copy[copy.length - 1] = {
                    role: "error",
                    text: meta.error!.split("\n")[0] || OFFLINE_FALLBACK,
                  };
                }
                return copy;
              });
              return;
            }
          }
          if (assistant) succeeded = true;
          patchAssistant({
            text: assistant,
            thinking: thinkingAcc,
            tools: [...toolLines],
          });
        },
      }, undefined, pathname);

      if (!gotStream && !assistant) {
        setMood("thinking");
        const res = await sendAgentMessage(sid, text, pathname);
        if (res.bridge_mode) setBridgeMode(res.bridge_mode);
        if (res.target_id && res.target_id !== UNSET) setTargetId(res.target_id);
        if (res.error || res.status === "offline") {
          const msg = (res.error || OFFLINE_FALLBACK).split("\n")[0];
          setError(msg);
          setLines((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = { role: "error", text: msg };
            return copy;
          });
        } else {
          assistant = res.reply;
          succeeded = !!assistant;
          if (assistant) setMood("outputting");
          setLines((prev) => {
            const copy = [...prev];
            copy[copy.length - 1] = {
              role: "assistant",
              text: assistant,
              thinking: res.thinking || "",
            };
            return copy;
          });
        }
      }
      if (assistant) applyNavigateFromReply(assistant);
      if (succeeded || assistant) flashDone();
      else setMood("idle");
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
      setLines((prev) => [...prev, { role: "error", text: `连接失败：${msg}` }]);
      setMood("idle");
    } finally {
      setBusy(false);
    }
  };

  const selectValue =
    targetId && targetOptions.includes(targetId)
      ? targetId
      : showCustom || (targetId && !targetOptions.includes(targetId))
        ? "__custom__"
        : "";

  return (
    <>
      <AgentMoodFab mood={mood} open={open} onToggle={() => setOpen((v) => !v)} />

      {open && (
        <div className="fixed bottom-24 right-6 z-[60] flex h-[min(72vh,560px)] w-[min(94vw,400px)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-lg">
          <header className="border-b border-slate-150 bg-white px-4 py-3">
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="inline-flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-slate-200 bg-white">
                  <Image
                    src="/brand/atom-scientist-fab.png"
                    alt=""
                    width={32}
                    height={32}
                    className="h-8 w-8 object-cover"
                  />
                </span>
                <div>
                  <p className="text-sm font-semibold text-ink">E-Drug Lab Scientist</p>
                  <p className="text-[10px] text-muted">{t("leadGenWorkspace")}</p>
                </div>
              </div>
              <button type="button" className="rounded-md px-1.5 py-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700" onClick={() => setOpen(false)} aria-label="关闭">
                ✕
              </button>
            </div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-wide text-slate-400">当前研究靶标</label>
            <div className="flex gap-2">
              <select
                className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1.5 text-xs text-slate-800 outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
                value={selectValue}
                onChange={(e) => {
                  const v = e.target.value;
                  if (v === "") return;
                  if (v === "__custom__") {
                    setShowCustom(true);
                    return;
                  }
                  void onChangeTarget(v);
                }}
                disabled={busy}
              >
                <option value="">请选择靶点…</option>
                {targetOptions.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
                <option value="__custom__">自定义…</option>
              </select>
                  {bridgeMode && (
                <span
                  className={`shrink-0 self-center rounded px-1.5 py-0.5 text-[10px] border ${
                    bridgeMode === "offline"
                      ? "bg-red-50 text-red-600 border-red-100"
                      : bridgeMode === "ui-intent"
                        ? "bg-slate-50 text-slate-600 border-slate-200"
                        : "bg-primary-50 text-primary border-primary-100"
                  }`}
                >
                  {bridgeModeLabel(bridgeMode)}
                </span>
              )}
            </div>
            {showCustom || (targetId && !targetOptions.includes(targetId)) ? (
              <div className="mt-2 flex gap-2">
                <input
                  className="flex-1 rounded-md border border-slate-200 bg-white px-2 py-1 text-xs text-slate-800 outline-none focus:border-primary"
                  placeholder="输入靶点 ID，如 EGFR"
                  value={customTarget || (targetId && !targetOptions.includes(targetId) ? targetId : "")}
                  onChange={(e) => setCustomTarget(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      const v = (customTarget || targetId || "").trim();
                      if (v) void onChangeTarget(v);
                    }
                  }}
                  disabled={busy}
                />
                <button
                  type="button"
                  className="rounded-md bg-primary px-2 py-1 text-xs text-white hover:bg-primary-600"
                  disabled={busy}
                  onClick={() => {
                    const v = (customTarget || targetId || "").trim();
                    if (v) void onChangeTarget(v);
                  }}
                >
                  切换
                </button>
              </div>
            ) : null}
          </header>

          <div className="flex-1 space-y-3 overflow-y-auto bg-slate-50 px-3 py-3 text-sm">
            {lines.map((ln, i) => {
              if (ln.role === "system") {
                return (
                  <div key={`s-${i}`} className="rounded-lg border border-primary-100 bg-primary-50/70 px-3 py-2 text-ink whitespace-pre-wrap">
                    {ln.text}
                  </div>
                );
              }
              if (ln.role === "user") {
                return (
                  <div key={`u-${i}`} className="ml-8 rounded-lg bg-primary-50 px-3 py-2 text-ink">
                    {ln.text}
                  </div>
                );
              }
              if (ln.role === "tool") {
                const { summary } = summarizeTools([ln.text]);
                if (!summary) return null;
                return (
                  <div key={`t-${i}`} className="px-1 text-[11px] text-slate-400">
                    {summary}
                  </div>
                );
              }
              if (ln.role === "error") {
                return (
                  <div key={`e-${i}`} className="mr-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 whitespace-pre-wrap">
                    {ln.text}
                  </div>
                );
              }
              return (
                <div key={`a-${i}`} className="mr-2 space-y-2">
                  {ln.tools && ln.tools.length > 0 ? (
                    (() => {
                      const { summary, details } = summarizeTools(ln.tools);
                      if (!summary) return null;
                      return (
                        <details className="rounded-md border border-slate-200 bg-white/80 px-2.5 py-1.5 text-xs text-slate-500">
                          <summary className="cursor-pointer select-none text-slate-500 hover:text-slate-700">
                            {summary}
                          </summary>
                          {details.length > 1 ? (
                            <ul className="mt-1.5 space-y-0.5 border-t border-slate-100 pt-1.5 text-[11px] text-slate-400">
                              {details.map((d, di) => (
                                <li key={di} className="truncate">
                                  {d}
                                </li>
                              ))}
                            </ul>
                          ) : null}
                        </details>
                      );
                    })()
                  ) : null}
                  {ln.thinking ? (
                    <details className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-500">
                      <summary className="cursor-pointer select-none text-slate-400 hover:text-slate-600">
                        思考过程（点击展开）
                      </summary>
                      <pre className="mt-2 whitespace-pre-wrap font-sans leading-relaxed">{ln.thinking}</pre>
                    </details>
                  ) : null}
                  {ln.text ? (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-800 whitespace-pre-wrap">
                      {sanitizeAssistantText(ln.text)}
                    </div>
                  ) : busy && i === lines.length - 1 ? (
                    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-slate-400 text-xs">
                      E-Drug Lab Scientist 思考中…
                    </div>
                  ) : null}
                </div>
              );
            })}
            <div ref={bottomRef} />
          </div>

          {error && <p className="px-3 py-1 text-xs text-red-600">{error}</p>}

          <footer className="border-t border-slate-150 bg-white p-3">
            <div className="flex gap-2">
              <input
                className="flex-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-primary focus:ring-2 focus:ring-primary/10"
                placeholder={targetId ? "输入消息…" : "先选靶点，或直接提问 / 导航…"}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && onSend()}
                disabled={busy}
              />
              <button
                type="button"
                onClick={onSend}
                disabled={busy}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white hover:bg-primary-600 disabled:opacity-50"
              >
                发送
              </button>
            </div>
          </footer>
        </div>
      )}
    </>
  );
}
