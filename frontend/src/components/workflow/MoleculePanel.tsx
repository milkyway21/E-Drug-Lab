"use client";

import { useState } from "react";
import { Trash2, Plus, ChevronDown, ChevronUp, X, Beaker } from "lucide-react";
import { getPipelineMoleculeDisplayName, useWorkflow, type PipelineMolecule } from "@/lib/workflow-context";

export function MoleculePanel() {
  const { molecules, addMolecules, removeMolecule, clearPipeline, getCounts } = useWorkflow();
  const counts = getCounts();
  const [expanded, setExpanded] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [manualSmiles, setManualSmiles] = useState("");

  const handleAddManual = () => {
    const lines = manualSmiles.split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
    if (lines.length === 0) return;
    const mols = lines.map((smi) => {
      const parts = smi.split(/\s+/);
      return { smiles: parts[0], name: parts[1] || undefined };
    });
    addMolecules(mols, "manual");
    setManualSmiles("");
    setShowAdd(false);
  };

  return (
    <aside className="panel p-4 lg:sticky lg:top-24 lg:self-start">
      <button onClick={() => setExpanded(!expanded)} className="flex w-full items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-2">
          <Beaker size={16} className="text-teal" />
          <span className="text-sm font-semibold text-ink">Pipeline</span>
          <span className="badge text-xs">{counts.total}</span>
        </div>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </button>
      {expanded && (
        <>
          <div className="flex gap-2 mb-3 text-xs">
            <span className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700">{counts.pass} pass</span>
            <span className="px-2 py-0.5 rounded bg-red-50 text-red-700">{counts.fail} fail</span>
            <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600">{counts.pending} pending</span>
          </div>
          <div className="max-h-64 overflow-y-auto space-y-1 mb-3">
            {molecules.length === 0 ? (
              <p className="text-xs text-muted py-4 text-center">No molecules in pipeline.</p>
            ) : (
              molecules.map((mol) => <MoleculeRow key={mol.id} mol={mol} onRemove={removeMolecule} />)
            )}
          </div>
          <div className="flex gap-2">
            <button onClick={() => setShowAdd(!showAdd)} className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium border border-teal text-teal rounded hover:bg-teal-50 transition">
              <Plus size={12} /> Add
            </button>
            {counts.total > 0 && (
              <button onClick={clearPipeline} className="flex items-center justify-center gap-1 px-2 py-1.5 text-xs font-medium border border-red-200 text-red-600 rounded hover:bg-red-50 transition">
                <Trash2 size={12} /> Clear
              </button>
            )}
          </div>
          {showAdd && (
            <div className="mt-3 p-3 bg-slate-50 rounded border border-slate-200">
              <textarea value={manualSmiles} onChange={(e) => setManualSmiles(e.target.value)}
                placeholder="CC(=O)Oc1ccccc1C(=O)O aspirin"
                className="w-full h-20 text-xs font-mono p-2 border border-slate-200 rounded resize-none" />
              <div className="flex gap-2 mt-2">
                <button onClick={handleAddManual} className="flex-1 px-2 py-1 text-xs font-medium bg-teal text-white rounded hover:bg-teal-600 transition">Add to Pipeline</button>
                <button onClick={() => { setShowAdd(false); setManualSmiles(""); }} className="px-2 py-1 text-xs text-muted hover:text-ink transition">Cancel</button>
              </div>
            </div>
          )}
        </>
      )}
    </aside>
  );
}

function MoleculeRow({ mol, onRemove }: { mol: PipelineMolecule; onRemove: (id: string) => void }) {
  const [showDetails, setShowDetails] = useState(false);
  const statusColor = mol.status === "pass" ? "bg-emerald-500" : mol.status === "fail" ? "bg-red-500" : "bg-slate-300";
  return (
    <div className="group">
      <div className="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-slate-50 cursor-pointer" onClick={() => setShowDetails(!showDetails)}>
        <span className={("w-2 h-2 rounded-full shrink-0 " + statusColor)} />
        <span className="flex-1 text-xs font-mono truncate text-ink">{getPipelineMoleculeDisplayName(mol)}</span>
        <span className="text-[10px] text-muted">{mol.source}</span>
        <button onClick={(e) => { e.stopPropagation(); onRemove(mol.id); }} className="opacity-0 group-hover:opacity-100 transition">
          <X size={12} className="text-muted hover:text-red-500" />
        </button>
      </div>
      {showDetails && (
        <div className="ml-6 mr-2 mb-1 p-2 bg-slate-50 rounded text-[10px] font-mono text-muted break-all">
          {mol.smiles}
        </div>
      )}
    </div>
  );
}
