"""Unified tool registry — single source of truth for pipeline building blocks."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from app.core.workflow_steps import (
    STEP_ID_ADMET,
    STEP_ID_AFFINITY,
    STEP_ID_LIBRARY_BUILD,
    STEP_ID_RANKING,
    STEP_ID_RL_TRAIN,
    STEP_ID_TARGET_PREP,
    STEP_ID_VAV1_RL,
    STEP_ID_VIRTUAL_SCREEN,
)

ToolStatus = Literal["implemented", "partial", "placeholder"]
ExecutionMode = Literal["sync", "async_job", "vav1_orchestrator"]
MergeStrategy = Literal["replace", "union", "intersect_pass", "all_must_pass", "best_score", "skip"]
ResourceTag = Literal["cpu", "gpu", "docker", "api", "hpc", "rl", "workflow"]


@dataclass(frozen=True)
class ToolSpec:
    id: str
    step_id: str
    name: str
    description: str
    api_route: str
    output_key: str
    execution: ExecutionMode = "sync"
    merge_strategy: MergeStrategy = "replace"
    input_keys: tuple[str, ...] = ()
    requires: tuple[str, ...] = ()
    status: ToolStatus = "implemented"
    resource_tag: ResourceTag = "cpu"
    tag: str = "Local"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class StepSpec:
    id: str
    step_number: int
    title: str
    description: str
    href: str
    default_merge: MergeStrategy
    tools: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "tool_specs": [get_tool(t).to_dict() for t in self.tools if t in TOOL_REGISTRY],
        }


TOOL_REGISTRY: dict[str, ToolSpec] = {
    "alphafold": ToolSpec(
        id="alphafold",
        step_id=STEP_ID_TARGET_PREP,
        name="AlphaFold",
        description="Protein structure prediction.",
        api_route="POST /api/v1/targets/predict",
        output_key="alphafold",
        status="placeholder",
        resource_tag="gpu",
        tag="AI",
    ),
    "pdb-fetch": ToolSpec(
        id="pdb-fetch",
        step_id=STEP_ID_TARGET_PREP,
        name="PDB Fetch",
        description="Download PDB structures.",
        api_route="POST /api/v1/targets/download",
        output_key="pdb-fetch",
        input_keys=("target",),
        requires=("target",),
        status="implemented",
        tag="Local",
    ),
    "scaffold-extract": ToolSpec(
        id="scaffold-extract",
        step_id=STEP_ID_LIBRARY_BUILD,
        name="Scaffold Extraction",
        description="Extract Bemis-Murcko scaffolds.",
        api_route="POST /api/v1/libraries/scaffolds/extract",
        output_key="scaffold-extract",
        merge_strategy="union",
        status="implemented",
        tag="Local",
    ),
    "diffgui": ToolSpec(
        id="diffgui",
        step_id=STEP_ID_LIBRARY_BUILD,
        name="DiffGUI",
        description="AI de novo molecule generation.",
        api_route="POST /api/v1/diffgui/generate",
        output_key="diffgui",
        execution="async_job",
        merge_strategy="union",
        input_keys=("target", "round_id"),
        requires=("target",),
        status="implemented",
        resource_tag="gpu",
        tag="GPU",
    ),
    "diffdynamic": ToolSpec(
        id="diffdynamic",
        step_id=STEP_ID_LIBRARY_BUILD,
        name="DiffDynamic",
        description="Diffusion-based SBDD molecule generation (dynamic/prudent).",
        api_route="POST /api/v1/diffdynamic/generate",
        output_key="diffdynamic",
        execution="async_job",
        merge_strategy="union",
        input_keys=("target", "round_id"),
        requires=(),
        status="implemented",
        resource_tag="gpu",
        tag="GPU",
    ),
    "sdf-upload": ToolSpec(
        id="sdf-upload",
        step_id=STEP_ID_LIBRARY_BUILD,
        name="SDF Upload",
        description="Upload SDF compound libraries.",
        api_route="POST /api/v1/molecule-db/sync",
        output_key="sdf-upload",
        merge_strategy="union",
        status="implemented",
        tag="Local",
    ),
    "tame-vs": ToolSpec(
        id="tame-vs",
        step_id=STEP_ID_VIRTUAL_SCREEN,
        name="TAME-VS",
        description="Target-driven ML virtual screening.",
        api_route="POST /api/v1/tame-vs/smoke-test",
        output_key="tame-vs",
        merge_strategy="intersect_pass",
        input_keys=("target", "molecules"),
        requires=("molecules",),
        status="implemented",
        resource_tag="docker",
        tag="Docker",
    ),
    "drugclip": ToolSpec(
        id="drugclip",
        step_id=STEP_ID_VIRTUAL_SCREEN,
        name="DrugCLIP",
        description="Contrastive learning virtual screening.",
        api_route="POST /api/v1/drugclip/pipeline-screen",
        output_key="drugclip",
        merge_strategy="intersect_pass",
        input_keys=("target", "molecules"),
        requires=("target",),
        status="implemented",
        resource_tag="docker",
        tag="Docker",
    ),
    "glare-screen": ToolSpec(
        id="glare-screen",
        step_id=STEP_ID_VIRTUAL_SCREEN,
        name="GLARE Screen",
        description="GNN+GRPO active-learning screening.",
        api_route="POST /api/v1/glare/screen",
        output_key="glare-screen",
        execution="async_job",
        merge_strategy="intersect_pass",
        input_keys=("molecules", "round_id", "glare_checkpoint"),
        requires=("molecules",),
        status="implemented",
        resource_tag="rl",
        tag="RL",
    ),
    "rdkit-descriptors": ToolSpec(
        id="rdkit-descriptors",
        step_id=STEP_ID_ADMET,
        name="RDKit Descriptors",
        description="Lipinski, Veber, drug-likeness rules.",
        api_route="POST /api/v1/admet/filter",
        output_key="rdkit-filter",
        merge_strategy="all_must_pass",
        input_keys=("molecules",),
        requires=("molecules",),
        status="implemented",
        tag="Local",
    ),
    "admet-ai": ToolSpec(
        id="admet-ai",
        step_id=STEP_ID_ADMET,
        name="ADMET-AI",
        description="Deep learning ADMET prediction.",
        api_route="POST /api/v1/admet/predict",
        output_key="admet-ai",
        merge_strategy="all_must_pass",
        input_keys=("molecules",),
        requires=("molecules",),
        status="implemented",
        resource_tag="gpu",
        tag="AI",
    ),
    "vina-dock": ToolSpec(
        id="vina-dock",
        step_id=STEP_ID_AFFINITY,
        name="Vina Docking",
        description="AutoDock Vina molecular docking.",
        api_route="POST /api/v1/affinity/dock/batch",
        output_key="vina-dock",
        merge_strategy="best_score",
        input_keys=("molecules", "target"),
        requires=("molecules",),
        status="implemented",
        tag="Local",
    ),
    "glide-dock": ToolSpec(
        id="glide-dock",
        step_id=STEP_ID_AFFINITY,
        name="Glide Dock",
        description="Schrödinger Glide docking (HTVS/SP/XP).",
        api_route="POST /api/v1/affinity/schrodinger/dock",
        output_key="glide-dock",
        merge_strategy="best_score",
        input_keys=("molecules", "target"),
        requires=("molecules", "target"),
        status="implemented",
        resource_tag="local",
        tag="Local",
    ),
    "mm-gbsa": ToolSpec(
        id="mm-gbsa",
        step_id=STEP_ID_AFFINITY,
        name="MM-GBSA",
        description="Schrödinger Prime MM-GBSA binding free energy.",
        api_route="POST /api/v1/affinity/mmgbsa",
        output_key="mm-gbsa",
        merge_strategy="best_score",
        input_keys=("molecules", "target"),
        requires=("molecules",),
        status="implemented",
        resource_tag="local",
        tag="Schrödinger",
    ),
    "md-simulation": ToolSpec(
        id="md-simulation",
        step_id=STEP_ID_AFFINITY,
        name="Desmond MD",
        description="Schrödinger Desmond MD (dry_prep default; confirm for smoke/short).",
        api_route="POST /api/v1/affinity/md ; GET /api/v1/affinity/md/{task_id}",
        output_key="md-simulation",
        status="implemented",
        resource_tag="hpc",
        tag="Schrödinger",
    ),
    "orthogonal-rank": ToolSpec(
        id="orthogonal-rank",
        step_id=STEP_ID_RANKING,
        name="Orthogonal Rank",
        description="Multi-metric rescoring.",
        api_route="POST /api/v1/ranking/orthogonal-rescore",
        output_key="orthogonal-rank",
        input_keys=("molecules",),
        requires=("molecules",),
        status="implemented",
        tag="Local",
    ),
    "seed-reinforce": ToolSpec(
        id="seed-reinforce",
        step_id=STEP_ID_RL_TRAIN,
        name="Seed Reinforce",
        description="Reinforce GLARE with seed wet-lab data.",
        api_route="POST /api/v1/glare/train",
        output_key="glare-train",
        execution="async_job",
        input_keys=("molecules", "round_id"),
        requires=("molecules",),
        status="implemented",
        resource_tag="rl",
        tag="RL",
    ),
    "glare-train": ToolSpec(
        id="glare-train",
        step_id=STEP_ID_RL_TRAIN,
        name="GLARE Train",
        description="Train GLARE policy on evaluated candidates.",
        api_route="POST /api/v1/glare/train",
        output_key="glare-train",
        execution="async_job",
        input_keys=("molecules", "round_id"),
        requires=("molecules",),
        status="implemented",
        resource_tag="rl",
        tag="RL",
    ),
    "wetlab-reinforce": ToolSpec(
        id="wetlab-reinforce",
        step_id=STEP_ID_RL_TRAIN,
        name="Wet-lab Reinforce",
        description="Reinforce GLARE with pDC50 feedback.",
        api_route="POST /api/v1/glare/import-wetlab",
        output_key="wetlab-reinforce",
        execution="async_job",
        input_keys=("molecules", "round_id"),
        requires=("molecules",),
        status="implemented",
        resource_tag="rl",
        tag="RL",
    ),
    "vav1-pipeline": ToolSpec(
        id="vav1-pipeline",
        step_id=STEP_ID_VAV1_RL,
        name="RL Closed Loop",
        description="Generation–screening–RL closed loop (rank-set RL).",
        api_route="POST /api/v1/vav1-rl/run",
        output_key="vav1-pipeline",
        execution="vav1_orchestrator",
        input_keys=("target",),
        requires=("target",),
        status="implemented",
        resource_tag="workflow",
        tag="Workflow",
    ),
}

STEP_REGISTRY: dict[str, StepSpec] = {
    STEP_ID_TARGET_PREP: StepSpec(
        id=STEP_ID_TARGET_PREP,
        step_number=1,
        title="Target Prep",
        description="Prepare protein target structure.",
        href="/workflow/target-prep",
        default_merge="replace",
        tools=("alphafold", "pdb-fetch"),
    ),
    STEP_ID_LIBRARY_BUILD: StepSpec(
        id=STEP_ID_LIBRARY_BUILD,
        step_number=2,
        title="Library Build",
        description="Build compound library.",
        href="/workflow/library-build",
        default_merge="union",
        tools=("scaffold-extract", "diffgui", "diffdynamic", "sdf-upload"),
    ),
    STEP_ID_VIRTUAL_SCREEN: StepSpec(
        id=STEP_ID_VIRTUAL_SCREEN,
        step_number=3,
        title="Virtual Screen",
        description="Virtual screening.",
        href="/workflow/virtual-screening",
        default_merge="intersect_pass",
        tools=("tame-vs", "drugclip", "glare-screen"),
    ),
    STEP_ID_ADMET: StepSpec(
        id=STEP_ID_ADMET,
        step_number=4,
        title="ADMET Filter",
        description="ADMET filtering and prediction.",
        href="/workflow/admet-filter",
        default_merge="all_must_pass",
        tools=("rdkit-descriptors", "admet-ai"),
    ),
    STEP_ID_AFFINITY: StepSpec(
        id=STEP_ID_AFFINITY,
        step_number=5,
        title="Affinity Eval",
        description="Binding affinity evaluation.",
        href="/workflow/affinity-eval",
        default_merge="best_score",
        tools=("vina-dock", "glide-dock", "mm-gbsa", "md-simulation"),
    ),
    STEP_ID_RANKING: StepSpec(
        id=STEP_ID_RANKING,
        step_number=6,
        title="Candidate Ranking",
        description="Multi-metric candidate ranking.",
        href="/workflow/candidate-rank",
        default_merge="replace",
        tools=("orthogonal-rank",),
    ),
    STEP_ID_RL_TRAIN: StepSpec(
        id=STEP_ID_RL_TRAIN,
        step_number=7,
        title="RL Training",
        description="Reinforcement learning training.",
        href="/workflow/rl-training",
        default_merge="replace",
        tools=("seed-reinforce", "glare-train", "wetlab-reinforce"),
    ),
    STEP_ID_VAV1_RL: StepSpec(
        id=STEP_ID_VAV1_RL,
        step_number=8,
        title="RL Cycle",
        description="Generation–screening–RL closed loop.",
        href="/workflow/vav1-rl",
        default_merge="replace",
        tools=("vav1-pipeline",),
    ),
}


def get_tool(tool_id: str) -> ToolSpec:
    if tool_id not in TOOL_REGISTRY:
        raise KeyError(f"Unknown tool: {tool_id}")
    return TOOL_REGISTRY[tool_id]


def get_step(step_id: str) -> StepSpec:
    if step_id not in STEP_REGISTRY:
        raise KeyError(f"Unknown step: {step_id}")
    return STEP_REGISTRY[step_id]


def list_tools() -> list[dict]:
    return [t.to_dict() for t in TOOL_REGISTRY.values()]


def list_steps() -> list[dict]:
    return [s.to_dict() for s in STEP_REGISTRY.values()]


# Backward compatibility with screening_tools.py
DIFFGUI = "diffgui"
GLARE_SCREEN = "glare_screen"
GLARE_TRAIN = "glare_train"
TAME_VS = "tame-vs"
DRUGCLIP = "drugclip"
VINA = "vina"

SCREENING_TOOL_NAMES = frozenset({
    DIFFGUI,
    GLARE_SCREEN,
    GLARE_TRAIN,
    TAME_VS,
    DRUGCLIP,
    VINA,
    *TOOL_REGISTRY.keys(),
})
