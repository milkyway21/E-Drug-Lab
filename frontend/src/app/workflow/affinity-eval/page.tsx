import { Atom, LineChart, Waves } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";

export default function AffinityEvalPage() {
  return (
    <WorkflowShell current="/workflow/affinity-eval">
      <WorkflowHeader
        badge="Affinity"
        title="Affinity evaluation"
        description="Reserve an operating surface for MM/GBSA, molecular dynamics stability, and binding energy analysis."
      />
      <div className="grid gap-4 md:grid-cols-3">
        {[
          ["MM/GBSA", "Review binding free energy for docking candidates.", Atom],
          ["MD stability", "Track RMSD, RMSF, and key interactions.", Waves],
          ["Score profile", "Combine model scores into a confidence profile.", LineChart]
        ].map(([title, body, Icon]) => (
          <div key={title as string} className="panel p-5">
            <Icon size={20} className="text-cobalt" />
            <h2 className="mt-4 text-lg font-semibold text-ink">{title as string}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{body as string}</p>
          </div>
        ))}
      </div>
    </WorkflowShell>
  );
}
