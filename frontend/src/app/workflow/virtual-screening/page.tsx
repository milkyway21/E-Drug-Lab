import { Play, Timer } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";

export default function VirtualScreeningPage() {
  return (
    <WorkflowShell current="/workflow/virtual-screening">
      <WorkflowHeader
        badge="Virtual screening"
        title="Virtual screening"
        description="Prepare the docking queue, progress tracking, and result table. The screening routes still need backend registration."
      />
      <div className="grid gap-4 md:grid-cols-3">
        {["Queued", "Running", "Completed"].map((label, index) => (
          <div key={label} className="panel p-5">
            <div className="stat-label">{label}</div>
            <div className="mt-2 text-3xl font-semibold text-ink">{index === 0 ? 0 : "-"}</div>
          </div>
        ))}
      </div>
      <div className="panel mt-5 p-6">
        <div className="flex items-center gap-2">
          <Timer size={18} className="text-cobalt" />
          <h2 className="text-lg font-semibold text-ink">Screening task</h2>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Next step: fix and register combined_routes.py, then connect Celery docking tasks to AutoDock Vina.
        </p>
        <button className="mt-5 inline-flex h-10 items-center gap-2 bg-teal px-4 text-sm font-medium text-white">
          <Play size={16} />
          Start screening
        </button>
      </div>
    </WorkflowShell>
  );
}
