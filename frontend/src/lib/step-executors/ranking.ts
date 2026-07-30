import { apiClient, type RankingMoleculeRecord } from "@/lib/api-client";
import {
  computeAdmetComposite,
  hasRankablePrimaryMetric,
  isRealVinaDock,
  resolvePrimaryMetric,
} from "@/lib/docking-metrics";
import { withStepResult } from "@/lib/merge-strategies";
import type { StepExecutor } from "./types";

export const runRankingStep: StepExecutor = async (ctx, toolIds, params, actions) => {
  if (toolIds.length === 0) {
    return { ok: true, message: "Ranking skipped", molecules: ctx.molecules };
  }

  if (ctx.molecules.length === 0) {
    return { ok: false, message: "No molecules available for ranking" };
  }

  const pipeline = ctx.molecules;
  const rankable = pipeline.filter((molecule) => hasRankablePrimaryMetric(molecule.stepResults));
  if (rankable.length === 0) {
    return {
      ok: false,
      message: "No rankable primary metric: need Vina docking or VS scores from DrugCLIP/TAME-VS",
    };
  }

  const candidates = rankable.map((molecule) => {
    const primary = resolvePrimaryMetric(molecule.stepResults)!;
    const admetComposite = computeAdmetComposite(molecule.stepResults);
    const primaryMetricName = primary.kind === "vina" ? "docking_affinity" : "vs_screen_score";
    const primaryModel = primary.kind === "vina" ? "vina" : primary.model;
    const primaryFamily = primary.kind === "vina" ? "docking" : primary.methodFamily;

    return {
      molecule_id: molecule.id,
      name: molecule.originalName || molecule.name || molecule.smiles.slice(0, 20),
      metrics: [
        {
          metric_name: primaryMetricName,
          value: primary.value,
          model_name: primaryModel,
          method_family: primaryFamily,
          direction: "lower_is_better" as const,
          priority: 1,
        },
        {
          metric_name: "admet_composite_score",
          value: admetComposite,
          model_name: "admet-ai",
          method_family: "admet",
          direction: "higher_is_better" as const,
          priority: 2,
        },
      ],
    };
  });

  const primaryMetricForApi = rankable.some((m) => isRealVinaDock(m.stepResults["vina-dock"]))
    ? "docking_affinity"
    : "vs_screen_score";

  const moleculeRecords: RankingMoleculeRecord[] = pipeline.map((molecule) => {
    const admet = molecule.stepResults?.["admet-ai"] as Record<string, unknown> | undefined;
    const props = (admet?.properties || {}) as Record<string, number>;
    const vinaData = molecule.stepResults?.["vina-dock"] as Record<string, unknown> | undefined;
    const primary = resolvePrimaryMetric(molecule.stepResults);
    return {
      molecule_id: molecule.id,
      name: molecule.originalName || molecule.name || molecule.smiles.slice(0, 20),
      smiles: molecule.smiles,
      source: molecule.source,
      source_db_id: molecule.sourceMoleculeId,
      status: molecule.status,
      sa_score: molecule.properties?.sa_score ?? null,
      molecular_weight: molecule.properties?.molecular_weight ?? null,
      logp: molecule.properties?.logp ?? null,
      tpsa: molecule.properties?.tpsa ?? null,
      qed: molecule.properties?.qed ?? null,
      herg: props.hERG ?? null,
      dili: props.DILI ?? null,
      ames: props.AMES ?? null,
      hia: props.HIA_Hou ?? null,
      docking_affinity:
        primary?.kind === "vina"
          ? primary.value
          : typeof vinaData?.affinity_kcal_mol === "number"
            ? (vinaData.affinity_kcal_mol as number)
            : null,
      step_results: molecule.stepResults,
    };
  });

  const rank = await apiClient.orthogonalRescore({
    candidates,
    primary_metric: primaryMetricForApi,
    orthogonal_metric: "admet_composite_score",
    gap_threshold: 35.0,
    target_pdb_id: params.pdbId || ctx.target?.pdbId,
    molecule_records: moleculeRecords,
  });

  if (!rank.ok) return { ok: false, message: rank.error };

  actions.updateMoleculeNames(
    rank.data.ranked.map((item) => ({
      id: item.molecule_id,
      standardName: item.standard_name,
    }))
  );

  let updated = pipeline;
  rank.data.ranked.forEach((item) => {
    const rankResult = {
      rank: item.final_score,
      final_score: item.final_score,
      primary_value: item.primary_value,
      orthogonal_value: item.orthogonal_value,
      artifact_flag: item.artifact_flag,
    };
    actions.updateStepResult(item.molecule_id, "orthogonal-rank", rankResult);
    updated = withStepResult(updated, item.molecule_id, "orthogonal-rank", rankResult);
  });

  const rows = rank.data.ranked.map((item, index) => {
    const molecule = pipeline.find((entry) => entry.id === item.molecule_id);
    const admet = molecule?.stepResults?.["admet-ai"] as Record<string, unknown> | undefined;
    const props = (admet?.properties || {}) as Record<string, number>;
    const vinaData = molecule?.stepResults?.["vina-dock"] as Record<string, unknown> | undefined;
    return {
      rank: index + 1,
      name: item.standard_name || molecule?.originalName || item.name || item.molecule_id,
      smiles: (molecule?.smiles || "").slice(0, 40),
      admetPassed: molecule?.status === "pass",
      hERG: props.hERG ?? null,
      DILI: props.DILI ?? null,
      HIA: props.HIA_Hou ?? null,
      dockingAffinity: (() => {
        const primary = resolvePrimaryMetric(molecule?.stepResults || {});
        if (primary?.kind === "vina") return primary.value;
        const v = vinaData?.affinity_kcal_mol;
        return typeof v === "number" ? v : null;
      })(),
      finalScore: item.final_score,
      artifact: item.artifact_flag,
    };
  });

  return {
    ok: true,
    message: `${rows.length} candidates ranked`,
    molecules: updated,
    rankedRows: rows,
    summary: {
      total: rows.length,
      passed: rows.filter((r) => r.admetPassed).length,
      failed: rows.filter((r) => !r.admetPassed).length,
    },
  };
};
