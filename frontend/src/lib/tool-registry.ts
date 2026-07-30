import type { TranslationKey } from "@/lib/i18n/translations";

export type ModelStatus = "implemented" | "partial" | "placeholder";
export type ExecutionMode = "sync" | "async_job" | "vav1_orchestrator";
export type MergeStrategy =
  | "replace"
  | "union"
  | "intersect_pass"
  | "all_must_pass"
  | "best_score"
  | "skip";
export type ResourceTag = "cpu" | "gpu" | "docker" | "api" | "hpc" | "rl" | "workflow";

export const STEP_ID_TARGET_PREP = "target_prep";
export const STEP_ID_LIBRARY_BUILD = "library_build";
export const STEP_ID_VIRTUAL_SCREEN = "virtual_screen";
export const STEP_ID_ADMET = "admet";
export const STEP_ID_AFFINITY = "affinity";
export const STEP_ID_RANKING = "ranking";
export const STEP_ID_RL_TRAIN = "rl_train";
export const STEP_ID_VAV1_RL = "vav1_rl";

export interface ToolSpec {
  id: string;
  stepId: string;
  name: string;
  description: string;
  apiRoute: string;
  outputKey: string;
  execution?: ExecutionMode;
  mergeStrategy?: MergeStrategy;
  inputKeys?: string[];
  requires?: string[];
  status: ModelStatus;
  resourceTag?: ResourceTag;
  tag?: string;
}

export interface StepSpec {
  id: string;
  step: number;
  href: string;
  titleKey: TranslationKey;
  descKey: TranslationKey;
  defaultMerge: MergeStrategy;
  toolIds: string[];
}

export interface RecipeStepConfig {
  stepId: string;
  enabled: boolean;
  toolIds: string[];
  params?: Record<string, unknown>;
}

export interface PipelineRecipe {
  id?: string;
  name: string;
  description?: string;
  steps: RecipeStepConfig[];
}

export interface WorkflowModel {
  id: string;
  name: string;
  description: string;
  status: ModelStatus;
  apiHint?: string;
  tag?: string;
}

export interface WorkflowStepConfig {
  step: number;
  href: string;
  titleKey: TranslationKey;
  descKey: TranslationKey;
  models: WorkflowModel[];
}

export const TOOL_REGISTRY: Record<string, ToolSpec> = {
  alphafold: {
    id: "alphafold",
    stepId: STEP_ID_TARGET_PREP,
    name: "AlphaFold",
    description: "Protein structure prediction.",
    apiRoute: "POST /api/v1/targets/predict",
    outputKey: "alphafold",
    status: "placeholder",
    resourceTag: "gpu",
    tag: "AI",
  },
  "pdb-fetch": {
    id: "pdb-fetch",
    stepId: STEP_ID_TARGET_PREP,
    name: "PDB Fetch",
    description: "Download PDB structures.",
    apiRoute: "POST /api/v1/targets/download",
    outputKey: "pdb-fetch",
    requires: ["target"],
    status: "implemented",
    tag: "Local",
  },
  "scaffold-extract": {
    id: "scaffold-extract",
    stepId: STEP_ID_LIBRARY_BUILD,
    name: "Scaffold Extraction",
    description: "Extract Bemis-Murcko scaffolds from uploaded molecules.",
    apiRoute: "POST /api/v1/libraries/scaffolds/extract",
    outputKey: "scaffold-extract",
    mergeStrategy: "union",
    status: "implemented",
    tag: "Local",
  },
  diffgui: {
    id: "diffgui",
    stepId: STEP_ID_LIBRARY_BUILD,
    name: "DiffGUI",
    description: "AI de novo molecule generation for library construction.",
    apiRoute: "POST /api/v1/diffgui/generate",
    outputKey: "diffgui",
    execution: "async_job",
    mergeStrategy: "union",
    inputKeys: ["target", "roundId"],
    requires: ["target"],
    status: "implemented",
    resourceTag: "gpu",
    tag: "GPU",
  },
  diffdynamic: {
    id: "diffdynamic",
    stepId: STEP_ID_LIBRARY_BUILD,
    name: "DiffDynamic",
    description: "Diffusion-based structure-based de novo generation (dynamic/prudent).",
    apiRoute: "POST /api/v1/diffdynamic/generate",
    outputKey: "diffdynamic",
    execution: "async_job",
    mergeStrategy: "union",
    inputKeys: ["target", "roundId"],
    requires: [],
    status: "implemented",
    resourceTag: "gpu",
    tag: "GPU",
  },
  "sdf-upload": {
    id: "sdf-upload",
    stepId: STEP_ID_LIBRARY_BUILD,
    name: "SDF Upload",
    description: "Upload SDF compound libraries.",
    apiRoute: "POST /api/v1/molecule-db/sync",
    outputKey: "sdf-upload",
    mergeStrategy: "union",
    status: "implemented",
    tag: "Local",
  },
  "tame-vs": {
    id: "tame-vs",
    stepId: STEP_ID_VIRTUAL_SCREEN,
    name: "TAME-VS",
    description: "Target-driven ML virtual screening.",
    apiRoute: "POST /api/v1/tame-vs/smoke-test",
    outputKey: "tame-vs",
    mergeStrategy: "intersect_pass",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "docker",
    tag: "Docker",
  },
  drugclip: {
    id: "drugclip",
    stepId: STEP_ID_VIRTUAL_SCREEN,
    name: "DrugCLIP",
    description: "Contrastive learning virtual screening.",
    apiRoute: "POST /api/v1/drugclip/pipeline-screen",
    outputKey: "drugclip",
    mergeStrategy: "intersect_pass",
    requires: ["target"],
    status: "implemented",
    resourceTag: "docker",
    tag: "Docker",
  },
  "glare-screen": {
    id: "glare-screen",
    stepId: STEP_ID_VIRTUAL_SCREEN,
    name: "GLARE (GNN+GRPO)",
    description: "GIN+ECFP encoder with GRPO policy active-learning screening.",
    apiRoute: "POST /api/v1/glare/screen",
    outputKey: "glare-screen",
    execution: "async_job",
    mergeStrategy: "intersect_pass",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "rl",
    tag: "RL",
  },
  "rdkit-descriptors": {
    id: "rdkit-descriptors",
    stepId: STEP_ID_ADMET,
    name: "RDKit Descriptors",
    description: "Lipinski, Veber, and drug-likeness rules.",
    apiRoute: "POST /api/v1/admet/filter",
    outputKey: "rdkit-filter",
    mergeStrategy: "all_must_pass",
    requires: ["molecules"],
    status: "implemented",
    tag: "Local",
  },
  "admet-ai": {
    id: "admet-ai",
    stepId: STEP_ID_ADMET,
    name: "ADMET-AI",
    description: "Deep learning ADMET prediction (22+ properties).",
    apiRoute: "POST /api/v1/admet/predict",
    outputKey: "admet-ai",
    mergeStrategy: "all_must_pass",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "gpu",
    tag: "AI",
  },
  "vina-dock": {
    id: "vina-dock",
    stepId: STEP_ID_AFFINITY,
    name: "Vina Docking",
    description: "AutoDock Vina molecular docking.",
    apiRoute: "POST /api/v1/affinity/dock/batch",
    outputKey: "vina-dock",
    mergeStrategy: "best_score",
    requires: ["molecules"],
    status: "implemented",
    tag: "Local",
  },
  "glide-dock": {
    id: "glide-dock",
    stepId: STEP_ID_AFFINITY,
    name: "Glide Dock",
    description: "Schrödinger Glide docking (HTVS/SP/XP).",
    apiRoute: "POST /api/v1/affinity/schrodinger/dock",
    outputKey: "glide-dock",
    mergeStrategy: "best_score",
    requires: ["molecules", "target"],
    status: "implemented",
    tag: "Local",
  },
  "mm-gbsa": {
    id: "mm-gbsa",
    stepId: STEP_ID_AFFINITY,
    name: "MM-GBSA",
    description: "Schrödinger Prime MM-GBSA binding free energy.",
    apiRoute: "POST /api/v1/affinity/mmgbsa",
    outputKey: "mm-gbsa",
    mergeStrategy: "best_score",
    requires: ["molecules"],
    status: "implemented",
    tag: "Schrödinger",
  },
  "md-simulation": {
    id: "md-simulation",
    stepId: STEP_ID_AFFINITY,
    name: "Desmond MD",
    description: "Schrödinger Desmond MD (dry_prep default; confirm for smoke/short).",
    apiRoute: "POST /api/v1/affinity/md ; GET /api/v1/affinity/md/{task_id}",
    outputKey: "md-simulation",
    status: "implemented",
    resourceTag: "hpc",
    tag: "Schrödinger",
  },
  "orthogonal-rank": {
    id: "orthogonal-rank",
    stepId: STEP_ID_RANKING,
    name: "Orthogonal Rank",
    description: "Multi-metric rescoring.",
    apiRoute: "POST /api/v1/ranking/orthogonal-rescore",
    outputKey: "orthogonal-rank",
    requires: ["molecules"],
    status: "implemented",
    tag: "Local",
  },
  "seed-reinforce": {
    id: "seed-reinforce",
    stepId: STEP_ID_RL_TRAIN,
    name: "Seed Reinforce",
    description: "Reinforce GLARE with seed wet-lab activity data.",
    apiRoute: "POST /api/v1/glare/train",
    outputKey: "glare-train",
    execution: "async_job",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "rl",
    tag: "RL",
  },
  "glare-train": {
    id: "glare-train",
    stepId: STEP_ID_RL_TRAIN,
    name: "GLARE Train",
    description: "Train GLARE policy on evaluated candidates.",
    apiRoute: "POST /api/v1/glare/train",
    outputKey: "glare-train",
    execution: "async_job",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "rl",
    tag: "RL",
  },
  "wetlab-reinforce": {
    id: "wetlab-reinforce",
    stepId: STEP_ID_RL_TRAIN,
    name: "Wet-lab Reinforce",
    description: "Reinforce GLARE with new pDC50 feedback.",
    apiRoute: "POST /api/v1/glare/import-wetlab",
    outputKey: "wetlab-reinforce",
    execution: "async_job",
    requires: ["molecules"],
    status: "implemented",
    resourceTag: "rl",
    tag: "RL",
  },
  "vav1-pipeline": {
    id: "vav1-pipeline",
    stepId: STEP_ID_VAV1_RL,
    name: "强化学习循环",
    description: "生成-筛选-强化学习闭环管线（排序集 RL + 第二轮验证）.",
    apiRoute: "POST /api/v1/vav1-rl/run",
    outputKey: "vav1-pipeline",
    execution: "vav1_orchestrator",
    requires: ["target"],
    status: "implemented",
    resourceTag: "workflow",
    tag: "Workflow",
  },
};

export const STEP_REGISTRY: StepSpec[] = [
  {
    id: STEP_ID_TARGET_PREP,
    step: 1,
    href: "/workflow/target-prep",
    titleKey: "workflowStep1",
    descKey: "workflowStep1Desc",
    defaultMerge: "replace",
    toolIds: ["alphafold", "pdb-fetch"],
  },
  {
    id: STEP_ID_LIBRARY_BUILD,
    step: 2,
    href: "/workflow/library-build",
    titleKey: "workflowStep2",
    descKey: "workflowStep2Desc",
    defaultMerge: "union",
    toolIds: ["scaffold-extract", "diffgui", "diffdynamic", "sdf-upload"],
  },
  {
    id: STEP_ID_VIRTUAL_SCREEN,
    step: 3,
    href: "/workflow/virtual-screening",
    titleKey: "workflowStep3",
    descKey: "workflowStep3Desc",
    defaultMerge: "intersect_pass",
    toolIds: ["tame-vs", "drugclip", "glare-screen"],
  },
  {
    id: STEP_ID_ADMET,
    step: 4,
    href: "/workflow/admet-filter",
    titleKey: "workflowStep4",
    descKey: "workflowStep4Desc",
    defaultMerge: "all_must_pass",
    toolIds: ["rdkit-descriptors", "admet-ai"],
  },
  {
    id: STEP_ID_AFFINITY,
    step: 5,
    href: "/workflow/affinity-eval",
    titleKey: "workflowStep5",
    descKey: "workflowStep5Desc",
    defaultMerge: "best_score",
    toolIds: ["vina-dock", "glide-dock", "mm-gbsa", "md-simulation"],
  },
  {
    id: STEP_ID_RANKING,
    step: 6,
    href: "/workflow/candidate-rank",
    titleKey: "workflowStep6",
    descKey: "workflowStep6Desc",
    defaultMerge: "replace",
    toolIds: ["orthogonal-rank"],
  },
  {
    id: STEP_ID_RL_TRAIN,
    step: 7,
    href: "/workflow/rl-training",
    titleKey: "workflowStep7",
    descKey: "workflowStep7Desc",
    defaultMerge: "replace",
    toolIds: ["seed-reinforce", "glare-train", "wetlab-reinforce"],
  },
  {
    id: STEP_ID_VAV1_RL,
    step: 8,
    href: "/workflow/vav1-rl",
    titleKey: "workflowStep8",
    descKey: "workflowStep8Desc",
    defaultMerge: "replace",
    toolIds: ["vav1-pipeline"],
  },
];

/** Backward-compatible workflowSteps for existing pages */
export const workflowSteps: WorkflowStepConfig[] = STEP_REGISTRY.map((step) => ({
  step: step.step,
  href: step.href,
  titleKey: step.titleKey,
  descKey: step.descKey,
  models: step.toolIds
    .map((id) => TOOL_REGISTRY[id])
    .filter(Boolean)
    .map((tool) => ({
      id: tool.id,
      name: tool.name,
      description: tool.description,
      status: tool.status,
      apiHint: tool.apiRoute,
      tag: tool.tag,
    })),
}));

export const PRESET_RECIPES: PipelineRecipe[] = [
  {
    id: "full-7-step",
    name: "Full 7-Step Pipeline",
    description: "Default end-to-end virtual screening workflow.",
    steps: [
      { stepId: STEP_ID_TARGET_PREP, enabled: true, toolIds: ["pdb-fetch"] },
      { stepId: STEP_ID_LIBRARY_BUILD, enabled: true, toolIds: ["diffgui"] },
      { stepId: STEP_ID_VIRTUAL_SCREEN, enabled: true, toolIds: ["drugclip"] },
      { stepId: STEP_ID_ADMET, enabled: true, toolIds: ["rdkit-descriptors", "admet-ai"] },
      { stepId: STEP_ID_AFFINITY, enabled: true, toolIds: ["vina-dock"] },
      { stepId: STEP_ID_RANKING, enabled: true, toolIds: ["orthogonal-rank"] },
      { stepId: STEP_ID_RL_TRAIN, enabled: true, toolIds: ["glare-train"] },
      { stepId: STEP_ID_VAV1_RL, enabled: false, toolIds: [] },
    ],
  },
  {
    id: "diffdynamic-full",
    name: "DiffDynamic Full Pipeline",
    description: "Target prep → DiffDynamic generation → ADMET → Vina dock → rank (no VS/RL).",
    steps: [
      { stepId: STEP_ID_TARGET_PREP, enabled: true, toolIds: ["pdb-fetch"] },
      { stepId: STEP_ID_LIBRARY_BUILD, enabled: true, toolIds: ["diffdynamic"] },
      { stepId: STEP_ID_VIRTUAL_SCREEN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_ADMET, enabled: true, toolIds: ["rdkit-descriptors"] },
      { stepId: STEP_ID_AFFINITY, enabled: true, toolIds: ["vina-dock"] },
      { stepId: STEP_ID_RANKING, enabled: true, toolIds: ["orthogonal-rank"] },
      { stepId: STEP_ID_RL_TRAIN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VAV1_RL, enabled: false, toolIds: [] },
    ],
  },
  {
    id: "quick-screen",
    name: "Quick Screen",
    description: "Target prep → virtual screen → ranking only.",
    steps: [
      { stepId: STEP_ID_TARGET_PREP, enabled: true, toolIds: ["pdb-fetch"] },
      { stepId: STEP_ID_LIBRARY_BUILD, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VIRTUAL_SCREEN, enabled: true, toolIds: ["drugclip"] },
      { stepId: STEP_ID_ADMET, enabled: false, toolIds: [] },
      { stepId: STEP_ID_AFFINITY, enabled: false, toolIds: [] },
      { stepId: STEP_ID_RANKING, enabled: true, toolIds: ["orthogonal-rank"] },
      { stepId: STEP_ID_RL_TRAIN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VAV1_RL, enabled: false, toolIds: [] },
    ],
  },
  {
    id: "admet-dock-rank",
    name: "ADMET + Dock + Rank",
    description: "Filter existing library molecules, dock, and rank.",
    steps: [
      { stepId: STEP_ID_TARGET_PREP, enabled: true, toolIds: ["pdb-fetch"] },
      { stepId: STEP_ID_LIBRARY_BUILD, enabled: true, toolIds: ["sdf-upload"] },
      { stepId: STEP_ID_VIRTUAL_SCREEN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_ADMET, enabled: true, toolIds: ["rdkit-descriptors", "admet-ai"] },
      { stepId: STEP_ID_AFFINITY, enabled: true, toolIds: ["vina-dock"] },
      { stepId: STEP_ID_RANKING, enabled: true, toolIds: ["orthogonal-rank"] },
      { stepId: STEP_ID_RL_TRAIN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VAV1_RL, enabled: false, toolIds: [] },
    ],
  },
  {
    id: "vav1-11-step",
    name: "RL Closed Loop",
    description: "Generation–screening–RL closed loop (rank-set RL).",
    steps: [
      { stepId: STEP_ID_TARGET_PREP, enabled: true, toolIds: ["pdb-fetch"] },
      { stepId: STEP_ID_LIBRARY_BUILD, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VIRTUAL_SCREEN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_ADMET, enabled: false, toolIds: [] },
      { stepId: STEP_ID_AFFINITY, enabled: false, toolIds: [] },
      { stepId: STEP_ID_RANKING, enabled: false, toolIds: [] },
      { stepId: STEP_ID_RL_TRAIN, enabled: false, toolIds: [] },
      { stepId: STEP_ID_VAV1_RL, enabled: true, toolIds: ["vav1-pipeline"] },
    ],
  },
];

export function getTool(toolId: string): ToolSpec {
  const tool = TOOL_REGISTRY[toolId];
  if (!tool) throw new Error(`Unknown tool: ${toolId}`);
  return tool;
}

export function getStep(stepId: string): StepSpec | undefined {
  return STEP_REGISTRY.find((s) => s.id === stepId);
}

export function getStepByHref(href: string): WorkflowStepConfig | undefined {
  return workflowSteps.find((s) => s.href === href);
}

export function implementedCount(step: WorkflowStepConfig): number {
  return step.models.filter((m) => m.status === "implemented").length;
}

export function defaultRecipe(): PipelineRecipe {
  return structuredClone(PRESET_RECIPES.find((r) => r.id === "full-7-step")!);
}

export function validateRecipe(recipe: PipelineRecipe): string[] {
  const errors: string[] = [];
  const enabledSteps = recipe.steps.filter((s) => s.enabled);

  if (enabledSteps.length === 0) {
    errors.push("At least one step must be enabled");
  }

  for (const step of recipe.steps) {
    if (!step.enabled) continue;
    if (step.toolIds.length === 0) {
      errors.push(`Step ${step.stepId} is enabled but has no tools selected`);
    }
    for (const toolId of step.toolIds) {
      if (!TOOL_REGISTRY[toolId]) {
        errors.push(`Unknown tool: ${toolId}`);
      } else if (TOOL_REGISTRY[toolId].status === "placeholder") {
        errors.push(`Tool ${toolId} is not implemented`);
      }
    }
  }

  const needsMolecules = enabledSteps.some((s) =>
    s.toolIds.some((id) => TOOL_REGISTRY[id]?.requires?.includes("molecules"))
  );
  const hasLibraryStep = enabledSteps.some((s) => s.stepId === STEP_ID_LIBRARY_BUILD);
  const hasScreenStep = enabledSteps.some((s) => s.stepId === STEP_ID_VIRTUAL_SCREEN);

  if (needsMolecules && !hasLibraryStep && !hasScreenStep) {
    const onlyTarget = enabledSteps.every((s) => s.stepId === STEP_ID_TARGET_PREP);
    if (!onlyTarget) {
      errors.push("Pipeline needs library_build or virtual_screen to supply molecules for downstream steps");
    }
  }

  return errors;
}

const RECIPE_STORAGE_KEY = "edrug-pipeline-recipe-v1";

export function saveRecipeToStorage(recipe: PipelineRecipe): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(RECIPE_STORAGE_KEY, JSON.stringify(recipe));
}

export function loadRecipeFromStorage(): PipelineRecipe | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(RECIPE_STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PipelineRecipe;
  } catch {
    return null;
  }
}
