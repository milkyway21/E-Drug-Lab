/** Shared helpers for pipeline docking / orthogonal ranking metrics. */

export type VinaDockStepResult = {
  affinity_kcal_mol?: number;
  method?: string;
  model?: string;
  success?: boolean;
  error?: string;
};

export type VsScreenStepResult = {
  score?: number;
  method?: string;
  model?: string;
};

const FAKE_VINA_METHODS = new Set([
  "property-estimate",
  "estimated-from-admet-props",
  "unavailable",
]);

/** True only when docking used real Vina (not property estimate or stub). */
export function isRealVinaDock(result: unknown): boolean {
  if (!result || typeof result !== "object") return false;
  const data = result as VinaDockStepResult;
  if (data.method === "vina" && data.model === "vina" && data.success !== false) {
    return typeof data.affinity_kcal_mol === "number";
  }
  if (data.model === "vina" && data.method && !FAKE_VINA_METHODS.has(data.method)) {
    return typeof data.affinity_kcal_mol === "number";
  }
  return false;
}

/** Extract VS score from step 3 (DrugCLIP / TAME-VS) when stored in stepResults. */
export function getVsScreenScore(stepResults: Record<string, unknown>): {
  score: number;
  model: string;
  methodFamily: string;
} | null {
  const drugclip = stepResults["drugclip"] as VsScreenStepResult | undefined;
  if (drugclip && typeof drugclip.score === "number") {
    return { score: drugclip.score, model: "drugclip", methodFamily: "virtual_screening" };
  }
  const tame = stepResults["tame-vs"] as VsScreenStepResult | undefined;
  if (tame && typeof tame.score === "number") {
    return { score: tame.score, model: "tame-vs", methodFamily: "virtual_screening" };
  }
  return null;
}

export function computeAdmetComposite(stepResults: Record<string, unknown>): number {
  const admet = stepResults["admet-ai"] as Record<string, unknown> | undefined;
  const props = (admet?.properties || {}) as Record<string, number>;
  const dili = props.DILI ?? 0.5;
  const herg = props.hERG ?? 0.5;
  const hia = props.HIA_Hou ?? 0.5;
  const ames = props.AMES ?? 0.5;
  const logp = props.logP ?? 2;
  return Math.max(
    0,
    Math.min(
      1,
      0.5 + (1 - dili) * 0.3 + (1 - herg) * 0.3 + (1 - ames) * 0.2 + hia * 0.1 - Math.abs(logp - 3) * 0.05
    )
  );
}

export type PrimaryMetricSource =
  | { kind: "vina"; value: number }
  | { kind: "vs"; value: number; model: string; methodFamily: string }
  | null;

/** Resolve primary ranking metric: real Vina > VS screen score > null. */
export function resolvePrimaryMetric(stepResults: Record<string, unknown>): PrimaryMetricSource {
  const vina = stepResults["vina-dock"] as VinaDockStepResult | undefined;
  if (isRealVinaDock(vina)) {
    return { kind: "vina", value: vina!.affinity_kcal_mol as number };
  }
  const vs = getVsScreenScore(stepResults);
  if (vs) {
    // VS scores are higher=better; invert sign so lower_is_better aligns with docking convention
    return { kind: "vs", value: -vs.score, model: vs.model, methodFamily: vs.methodFamily };
  }
  return null;
}

export function hasRankablePrimaryMetric(stepResults: Record<string, unknown>): boolean {
  return resolvePrimaryMetric(stepResults) !== null;
}
