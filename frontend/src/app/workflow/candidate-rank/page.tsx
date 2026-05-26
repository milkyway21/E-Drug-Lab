import { AlertTriangle, CheckCircle2, Medal } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";
import { apiClient } from "@/lib/api-client";

export default async function CandidateRankPage() {
  const result = await apiClient.orthogonalDemo();
  const payload = result.ok ? result.data : null;
  const ranked = payload?.ranked || [];

  return (
    <WorkflowShell current="/workflow/candidate-rank">
      <WorkflowHeader
        badge="Orthogonal rescoring"
        title="Candidate ranking"
        description="Store multiple model outputs for each metric, select one representative observed value, then rank by an independent orthogonal rescore instead of averaging."
      />

      <div className="mb-5 grid gap-4 md:grid-cols-3">
        <div className="panel p-4">
          <div className="stat-label">Metric value rule</div>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {payload?.selection_rule || "Preferred model, otherwise median observed value; never mean."}
          </p>
        </div>
        <div className="panel p-4">
          <div className="stat-label">Final score rule</div>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            {payload?.final_score_rule || "Orthogonal desirability minus artifact penalty."}
          </p>
        </div>
        <div className="panel p-4">
          <div className="stat-label">Artifact signal</div>
          <p className="mt-2 text-sm leading-6 text-slate-600">
            Strong primary score plus weak orthogonal score is flagged as a scoring-function artifact.
          </p>
        </div>
      </div>

      <div className="panel overflow-hidden">
        <table className="min-w-full divide-y divide-slate-200 text-left text-sm">
          <thead>
            <tr>
              {[
                "Rank",
                "Candidate",
                "Primary",
                "Orthogonal",
                "Gap",
                "Final",
                "Flag"
              ].map((item) => (
                <th key={item} className="px-4 py-3 font-medium text-slate-600">{item}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {ranked.map((candidate, index) => (
              <tr key={candidate.molecule_id}>
                <td className="px-4 py-3 text-ink">
                  <span className="inline-flex items-center gap-2">
                    <Medal size={15} className="text-amber" />
                    {index + 1}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{candidate.name || candidate.molecule_id}</div>
                  <div className="mt-1 text-xs text-slate-600">
                    {candidate.selected_primary_model} {"->"} {candidate.selected_orthogonal_model}
                  </div>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {candidate.primary_value.toFixed(2)}
                  <span className="ml-2 text-xs">({candidate.primary_desirability.toFixed(1)})</span>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {candidate.orthogonal_value.toFixed(2)}
                  <span className="ml-2 text-xs">({candidate.orthogonal_desirability.toFixed(1)})</span>
                </td>
                <td className="px-4 py-3 text-slate-600">{candidate.consistency_gap.toFixed(1)}</td>
                <td className="px-4 py-3 font-semibold text-ink">{candidate.final_score.toFixed(1)}</td>
                <td className="px-4 py-3">
                  {candidate.artifact_flag ? (
                    <span className="inline-flex items-center gap-2 border border-rose px-2 py-1 text-xs text-rose">
                      <AlertTriangle size={14} />
                      artifact
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-2 border border-teal px-2 py-1 text-xs text-teal">
                      <CheckCircle2 size={14} />
                      pass
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </WorkflowShell>
  );
}
