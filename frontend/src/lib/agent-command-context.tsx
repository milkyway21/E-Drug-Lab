"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchUiCommands, type UiCommand } from "@/lib/agent-client";
import { useWorkflow } from "@/lib/workflow-context";

type AgentCommandContextValue = {
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
  lastCommandId: string | null;
};

const AgentCommandContext = createContext<AgentCommandContextValue | null>(null);

export function AgentCommandProvider({
  children,
  sessionId,
  setSessionId,
}: {
  children: React.ReactNode;
  sessionId: string | null;
  setSessionId: (id: string | null) => void;
}) {
  const router = useRouter();
  const workflow = useWorkflow();
  const lastIdRef = useRef<string | null>(null);
  const [lastCommandId, setLastCommandId] = useState<string | null>(null);

  const applyCommand = useCallback(
    (cmd: UiCommand) => {
      switch (cmd.type) {
        case "navigate":
          if (cmd.path) router.push(cmd.path);
          break;
        case "set_target":
          if (cmd.target_id) {
            workflow.setTarget({
              id: cmd.target_id,
              name: cmd.name ?? cmd.target_id,
              source: "agent",
            });
          }
          break;
        case "open_molecule":
          if (cmd.smiles) {
            workflow.addMolecules([{ smiles: cmd.smiles, name: cmd.molecule_id }], "agent");
          }
          break;
        case "highlight":
          if (typeof window !== "undefined" && cmd.entity_id) {
            window.dispatchEvent(
              new CustomEvent("edrug-agent-highlight", {
                detail: { entityType: cmd.entity_type, entityId: cmd.entity_id },
              })
            );
          }
          break;
        case "start_task":
          if (cmd.api_path) {
            window.dispatchEvent(
              new CustomEvent("edrug-agent-start-task", {
                detail: { apiPath: cmd.api_path, body: cmd.body },
              })
            );
          }
          break;
        default:
          break;
      }
      lastIdRef.current = cmd.id;
      setLastCommandId(cmd.id);
    },
    [router, workflow]
  );

  useEffect(() => {
    if (!sessionId) return;
    const tick = async () => {
      const cmds = await fetchUiCommands(sessionId, lastIdRef.current ?? undefined);
      for (const c of cmds) applyCommand(c);
    };
    void tick();
    const id = window.setInterval(tick, 800);
    return () => window.clearInterval(id);
  }, [sessionId, applyCommand]);

  return (
    <AgentCommandContext.Provider value={{ sessionId, setSessionId, lastCommandId }}>
      {children}
    </AgentCommandContext.Provider>
  );
}

export function useAgentCommands(): AgentCommandContextValue {
  const ctx = useContext(AgentCommandContext);
  if (!ctx) {
    return { sessionId: null, setSessionId: () => {}, lastCommandId: null };
  }
  return ctx;
}
