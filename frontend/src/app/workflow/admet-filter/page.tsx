import { SlidersHorizontal } from "lucide-react";
import { WorkflowHeader, WorkflowShell } from "@/components/workflow/WorkflowLayout";

const rules = [
  ["Absorption", "Caco-2, HIA, and permeability"],
  ["Distribution", "PPB, BBB, and volume of distribution"],
  ["Metabolism", "CYP inhibition and substrate profile"],
  ["Excretion", "Clearance and half-life"],
  ["Toxicity", "hERG, Ames, and hepatotoxicity"]
];

export default function AdmetFilterPage() {
  return (
    <WorkflowShell current="/workflow/admet-filter">
      <WorkflowHeader
        badge="ADMET"
        title="ADMET filter"
        description="Filter candidate molecules by absorption, distribution, metabolism, excretion, and toxicity properties."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {rules.map(([title, body]) => (
          <div key={title} className="panel p-5">
            <SlidersHorizontal size={18} className="text-amber" />
            <h2 className="mt-3 text-lg font-semibold text-ink">{title}</h2>
            <p className="mt-2 text-sm leading-6 text-slate-600">{body}</p>
          </div>
        ))}
      </div>
    </WorkflowShell>
  );
}
