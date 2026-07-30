"use client";

import { useState } from "react";
import AgentUiEffects from "@/components/agent/AgentUiEffects";
import ScientistFloat from "@/components/agent/ScientistFloat";
import { AgentCommandProvider } from "@/lib/agent-command-context";
import { WorkflowProvider } from "@/lib/workflow-context";

export default function AppShell({ children }: { children: React.ReactNode }) {
  const [sessionId, setSessionId] = useState<string | null>(null);

  return (
    <WorkflowProvider>
      <AgentCommandProvider sessionId={sessionId} setSessionId={setSessionId}>
        <AgentUiEffects />
        {children}
        <ScientistFloat onSessionSync={setSessionId} />
      </AgentCommandProvider>
    </WorkflowProvider>
  );
}
