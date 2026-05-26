"use client";

import { useState } from "react";
import { Download, Plus, Wand2 } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { apiClient } from "@/lib/api-client";

export default function TargetPrepPage() {
  const [pdbId, setPdbId] = useState("1a2b");
  const [name, setName] = useState("Demo kinase target");
  const [message, setMessage] = useState("Waiting for a target action.");

  async function createTarget() {
    const result = await apiClient.createTarget({ pdb_id: pdbId, name });
    setMessage(result.ok ? `Created target: ${result.data.id}` : result.error);
  }

  async function downloadPdb() {
    const result = await apiClient.downloadTarget(pdbId);
    setMessage(result.ok ? `Download status: ${result.data.status}` : result.error);
  }

  return (
    <WorkflowShell current="/workflow/target-prep">
      <WorkflowHeader
        badge="Target preparation"
        title="Target preparation"
        description="Register a PDB ID or sequence source, then connect structure download, prediction, and preprocessing actions."
      />
      <div className="panel p-6">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="stat-label">PDB ID</span>
            <input value={pdbId} onChange={(event) => setPdbId(event.target.value)} className="mt-2 h-10 w-full border border-slate-200 px-3 text-sm outline-none focus:border-teal" />
          </label>
          <label className="block">
            <span className="stat-label">Target name</span>
            <input value={name} onChange={(event) => setName(event.target.value)} className="mt-2 h-10 w-full border border-slate-200 px-3 text-sm outline-none focus:border-teal" />
          </label>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          <button onClick={createTarget} className="inline-flex h-10 items-center gap-2 bg-teal px-4 text-sm font-medium text-white">
            <Plus size={16} />
            Create target
          </button>
          <button onClick={downloadPdb} className="inline-flex h-10 items-center gap-2 border border-slate-200 px-4 text-sm text-ink hover:border-teal">
            <Download size={16} />
            Download PDB
          </button>
          <button className="inline-flex h-10 items-center gap-2 border border-slate-200 px-4 text-sm text-ink hover:border-teal">
            <Wand2 size={16} />
            Preprocess
          </button>
        </div>
        <p className="mt-5 border border-slate-200 bg-mist p-3 text-sm text-slate-600">{message}</p>
      </div>
    </WorkflowShell>
  );
}
