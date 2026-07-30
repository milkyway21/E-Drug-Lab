"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export interface PipelineMoleculeProperties {
  molecular_weight?: number | null;
  logp?: number | null;
  tpsa?: number | null;
  qed?: number | null;
  sa_score?: number | null;
}

export interface PipelineMolecule {
  id: string;
  smiles: string;
  name?: string;
  originalName?: string;
  standardName?: string;
  source: string;
  sourceMoleculeId?: string;
  status: "pending" | "pass" | "fail";
  stepResults: Record<string, unknown>;
  properties?: PipelineMoleculeProperties;
  addedAt: number;
}

export interface PipelineMoleculeInput {
  smiles: string;
  name?: string;
  originalName?: string;
  standardName?: string;
  sourceMoleculeId?: string;
  properties?: PipelineMoleculeProperties;
}

export interface WorkflowTarget {
  id?: string;
  pdbId?: string;
  name?: string;
  source?: string;
}

export type LibrarySource = "diffgui" | "diffdynamic" | "sdf" | "screen";

interface WorkflowContextValue {
  molecules: PipelineMolecule[];
  target: WorkflowTarget | null;
  roundId: number;
  glareCheckpoint: string;
  librarySource: LibrarySource | null;
  runId: string | null;
  recipe: import("@/lib/tool-registry").PipelineRecipe | null;
  addMolecules: (mols: PipelineMoleculeInput[], source: string, options?: { replace?: boolean }) => PipelineMolecule[];
  removeMolecule: (id: string) => void;
  clearPipeline: () => void;
  updateStepResult: (id: string, stepKey: string, result: unknown) => void;
  updateMoleculeNames: (names: Array<{ id: string; standardName?: string | null; originalName?: string | null }>) => void;
  setStatus: (id: string, status: PipelineMolecule["status"]) => void;
  filterByStep: (stepKey: string, passedIds: string[], failedIds: string[]) => void;
  setTarget: (target: WorkflowTarget | null) => void;
  setRoundId: (roundId: number) => void;
  setGlareCheckpoint: (checkpoint: string) => void;
  setLibrarySource: (source: LibrarySource | null) => void;
  setRunId: (runId: string | null) => void;
  setRecipe: (recipe: import("@/lib/tool-registry").PipelineRecipe | null) => void;
  getSmilesList: () => string[];
  getCounts: () => { total: number; pass: number; fail: number; pending: number };
}

const STORAGE_KEY = "edrug-workflow-pipeline-v1";
const TARGET_STORAGE_KEY = "edrug-workflow-target-v1";
const RL_STORAGE_KEY = "edrug-workflow-rl-v1";
const RUN_STORAGE_KEY = "edrug-workflow-run-v1";
const WorkflowContext = createContext<WorkflowContextValue | null>(null);

let counter = 0;
function genId(): string {
  return `mol-${Date.now()}-${++counter}`;
}

function isPipelineMolecule(value: unknown): value is PipelineMolecule {
  if (!value || typeof value !== "object") return false;
  const row = value as Record<string, unknown>;
  return typeof row.id === "string" && typeof row.smiles === "string" && typeof row.source === "string";
}

export function getPipelineMoleculeDisplayName(
  molecule: Pick<PipelineMolecule, "standardName" | "originalName" | "name" | "smiles">
): string {
  return molecule.standardName || molecule.originalName || molecule.name || molecule.smiles.slice(0, 30);
}

export function WorkflowProvider({ children }: { children: React.ReactNode }) {
  const [molecules, setMolecules] = useState<PipelineMolecule[]>([]);
  const [target, setTargetState] = useState<WorkflowTarget | null>(null);
  const [roundId, setRoundIdState] = useState(1);
  const [glareCheckpoint, setGlareCheckpointState] = useState("");
  const [librarySource, setLibrarySourceState] = useState<LibrarySource | null>(null);
  const [runId, setRunIdState] = useState<string | null>(null);
  const [recipe, setRecipeState] = useState<import("@/lib/tool-registry").PipelineRecipe | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        setHydrated(true);
        return;
      }
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        setMolecules(parsed.filter(isPipelineMolecule));
      }
      const rawTarget = window.localStorage.getItem(TARGET_STORAGE_KEY);
      if (rawTarget) {
        const parsedTarget = JSON.parse(rawTarget) as WorkflowTarget;
        if (parsedTarget && typeof parsedTarget === "object") {
          setTargetState(parsedTarget);
        }
      }
      const rawRl = window.localStorage.getItem(RL_STORAGE_KEY);
      if (rawRl) {
        const parsedRl = JSON.parse(rawRl) as {
          roundId?: number;
          glareCheckpoint?: string;
          librarySource?: LibrarySource | null;
        };
        if (typeof parsedRl.roundId === "number") setRoundIdState(parsedRl.roundId);
        if (typeof parsedRl.glareCheckpoint === "string") setGlareCheckpointState(parsedRl.glareCheckpoint);
        if (
          parsedRl.librarySource === "diffgui" ||
          parsedRl.librarySource === "diffdynamic" ||
          parsedRl.librarySource === "sdf" ||
          parsedRl.librarySource === "screen"
        ) {
          setLibrarySourceState(parsedRl.librarySource);
        }
      }
      const rawRun = window.localStorage.getItem(RUN_STORAGE_KEY);
      if (rawRun) {
        const parsedRun = JSON.parse(rawRun) as { runId?: string; recipe?: import("@/lib/tool-registry").PipelineRecipe };
        if (typeof parsedRun.runId === "string") setRunIdState(parsedRun.runId);
        if (parsedRun.recipe) setRecipeState(parsedRun.recipe);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
      window.localStorage.removeItem(TARGET_STORAGE_KEY);
      window.localStorage.removeItem(RL_STORAGE_KEY);
    } finally {
      setHydrated(true);
    }
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(molecules));
    if (target) {
      window.localStorage.setItem(TARGET_STORAGE_KEY, JSON.stringify(target));
    } else {
      window.localStorage.removeItem(TARGET_STORAGE_KEY);
    }
    window.localStorage.setItem(
      RL_STORAGE_KEY,
      JSON.stringify({ roundId, glareCheckpoint, librarySource })
    );
    window.localStorage.setItem(
      RUN_STORAGE_KEY,
      JSON.stringify({ runId, recipe })
    );
  }, [hydrated, molecules, target, roundId, glareCheckpoint, librarySource, runId, recipe]);

  const addMolecules = useCallback((mols: PipelineMoleculeInput[], source: string, options?: { replace?: boolean }) => {
    const newMolecules: PipelineMolecule[] = mols.map((molecule) => ({
      id: genId(),
      smiles: molecule.smiles,
      name: molecule.name,
      originalName: molecule.originalName ?? molecule.name,
      standardName: molecule.standardName,
      source,
      sourceMoleculeId: molecule.sourceMoleculeId,
      status: "pending",
      stepResults: {},
      properties: molecule.properties,
      addedAt: Date.now(),
    }));
    setMolecules((prev) => (options?.replace ? newMolecules : [...prev, ...newMolecules]));
    return newMolecules;
  }, []);

  const removeMolecule = useCallback((id: string) => {
    setMolecules((prev) => prev.filter((molecule) => molecule.id !== id));
  }, []);

  const clearPipeline = useCallback(() => {
    setMolecules([]);
  }, []);

  const setTarget = useCallback((nextTarget: WorkflowTarget | null) => {
    setTargetState(nextTarget);
  }, []);

  const setRoundId = useCallback((id: number) => {
    setRoundIdState(id);
  }, []);

  const setGlareCheckpoint = useCallback((checkpoint: string) => {
    setGlareCheckpointState(checkpoint);
  }, []);

  const setLibrarySource = useCallback((source: LibrarySource | null) => {
    setLibrarySourceState(source);
  }, []);

  const setRunId = useCallback((id: string | null) => {
    setRunIdState(id);
  }, []);

  const setRecipe = useCallback((nextRecipe: import("@/lib/tool-registry").PipelineRecipe | null) => {
    setRecipeState(nextRecipe);
  }, []);

  const updateStepResult = useCallback((id: string, stepKey: string, result: unknown) => {
    setMolecules((prev) =>
      prev.map((molecule) =>
        molecule.id === id
          ? { ...molecule, stepResults: { ...molecule.stepResults, [stepKey]: result } }
          : molecule
      )
    );
  }, []);

  const updateMoleculeNames = useCallback((names: Array<{ id: string; standardName?: string | null; originalName?: string | null }>) => {
    const nameMap = new Map(names.map((entry) => [entry.id, entry]));
    setMolecules((prev) =>
      prev.map((molecule) => {
        const next = nameMap.get(molecule.id);
        if (!next) return molecule;
        return {
          ...molecule,
          originalName: next.originalName ?? molecule.originalName ?? molecule.name,
          standardName: next.standardName ?? molecule.standardName,
        };
      })
    );
  }, []);

  const setStatus = useCallback((id: string, status: PipelineMolecule["status"]) => {
    setMolecules((prev) => prev.map((molecule) => (molecule.id === id ? { ...molecule, status } : molecule)));
  }, []);

  const filterByStep = useCallback((_stepKey: string, passedIds: string[], failedIds: string[]) => {
    setMolecules((prev) =>
      prev.map((molecule) => {
        if (passedIds.includes(molecule.id)) return { ...molecule, status: "pass" };
        if (failedIds.includes(molecule.id)) return { ...molecule, status: "fail" };
        return molecule;
      })
    );
  }, []);

  const getSmilesList = useCallback(() => molecules.map((molecule) => molecule.smiles), [molecules]);

  const getCounts = useCallback(() => {
    return {
      total: molecules.length,
      pass: molecules.filter((molecule) => molecule.status === "pass").length,
      fail: molecules.filter((molecule) => molecule.status === "fail").length,
      pending: molecules.filter((molecule) => molecule.status === "pending").length,
    };
  }, [molecules]);

  const value = useMemo<WorkflowContextValue>(
    () => ({
      molecules,
      target,
      roundId,
      glareCheckpoint,
      librarySource,
      runId,
      recipe,
      addMolecules,
      removeMolecule,
      clearPipeline,
      updateStepResult,
      updateMoleculeNames,
      setStatus,
      filterByStep,
      setTarget,
      setRoundId,
      setGlareCheckpoint,
      setLibrarySource,
      setRunId,
      setRecipe,
      getSmilesList,
      getCounts,
    }),
    [molecules, target, roundId, glareCheckpoint, librarySource, runId, recipe, addMolecules, removeMolecule, clearPipeline, updateStepResult, updateMoleculeNames, setStatus, filterByStep, setTarget, setRoundId, setGlareCheckpoint, setLibrarySource, setRunId, setRecipe, getSmilesList, getCounts]
  );

  return <WorkflowContext.Provider value={value}>{children}</WorkflowContext.Provider>;
}

export function useWorkflow() {
  const value = useContext(WorkflowContext);
  if (!value) throw new Error("useWorkflow must be used inside WorkflowProvider");
  return value;
}
