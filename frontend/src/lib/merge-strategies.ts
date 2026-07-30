import type { PipelineMolecule } from "@/lib/workflow-context";
import type { MergeStrategy } from "@/lib/tool-registry";

export function mergeMoleculesUnion(
  existing: PipelineMolecule[],
  incoming: PipelineMolecule[]
): PipelineMolecule[] {
  const seen = new Set(existing.map((m) => m.smiles));
  const merged = [...existing];
  for (const mol of incoming) {
    if (!seen.has(mol.smiles)) {
      seen.add(mol.smiles);
      merged.push(mol);
    }
  }
  return merged;
}

export function mergeIntersectPass(
  before: PipelineMolecule[],
  passedIdsPerTool: string[][]
): PipelineMolecule[] {
  if (passedIdsPerTool.length === 0) return before;
  const sets = passedIdsPerTool.map((ids) => new Set(ids));
  return before.filter((m) => sets.every((s) => s.has(m.id)));
}

export function mergeAllMustPass(
  molecules: PipelineMolecule[],
  passedIdsPerTool: string[][]
): { molecules: PipelineMolecule[]; passedIds: string[]; failedIds: string[] } {
  if (passedIdsPerTool.length === 0) {
    return {
      molecules: molecules.map((m) => ({ ...m, status: "fail" as const })),
      passedIds: [],
      failedIds: molecules.map((m) => m.id),
    };
  }
  const sets = passedIdsPerTool.map((ids) => new Set(ids));
  const passedIds: string[] = [];
  const failedIds: string[] = [];
  for (const mol of molecules) {
    if (sets.every((s) => s.has(mol.id))) passedIds.push(mol.id);
    else failedIds.push(mol.id);
  }
  const updated = molecules.map((m) => ({
    ...m,
    status: passedIds.includes(m.id) ? ("pass" as const) : ("fail" as const),
  }));
  return { molecules: updated, passedIds, failedIds };
}

export function applyMergeStrategy(
  strategy: MergeStrategy,
  molecules: PipelineMolecule[],
  passedIdsPerTool: string[][] = []
): PipelineMolecule[] {
  switch (strategy) {
    case "union":
      return molecules;
    case "intersect_pass":
      return mergeIntersectPass(molecules, passedIdsPerTool);
    case "all_must_pass":
      return mergeAllMustPass(molecules, passedIdsPerTool).molecules;
    case "best_score":
    case "replace":
    case "skip":
    default:
      return molecules;
  }
}

export function withStepResult(
  molecules: PipelineMolecule[],
  id: string,
  stepKey: string,
  result: unknown
): PipelineMolecule[] {
  return molecules.map((molecule) =>
    molecule.id === id
      ? { ...molecule, stepResults: { ...molecule.stepResults, [stepKey]: result } }
      : molecule
  );
}

export function withStatuses(
  molecules: PipelineMolecule[],
  passedIds: string[],
  failedIds: string[]
): PipelineMolecule[] {
  return molecules.map((molecule) => {
    if (passedIds.includes(molecule.id)) return { ...molecule, status: "pass" as const };
    if (failedIds.includes(molecule.id)) return { ...molecule, status: "fail" as const };
    return molecule;
  });
}
