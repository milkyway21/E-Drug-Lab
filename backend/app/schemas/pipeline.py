"""Pydantic schemas for modular pipeline orchestration."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class RecipeStepConfig(BaseModel):
    step_id: str
    enabled: bool = True
    tool_ids: list[str] = Field(default_factory=list)
    params: dict[str, Any] = Field(default_factory=dict)


class PipelineRecipe(BaseModel):
    id: Optional[str] = None
    name: str = "custom"
    description: str = ""
    steps: list[RecipeStepConfig] = Field(default_factory=list)


class PipelineContextDTO(BaseModel):
    run_id: Optional[str] = None
    target: Optional[dict[str, Any]] = None
    molecules: list[dict[str, Any]] = Field(default_factory=list)
    round_id: int = 1
    glare_checkpoint: str = ""
    library_source: Optional[str] = None
    step_results: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CreatePipelineRunRequest(BaseModel):
    recipe: PipelineRecipe
    context: PipelineContextDTO = Field(default_factory=PipelineContextDTO)
    execute: bool = False


class PipelineStepRunDTO(BaseModel):
    id: str
    step_id: str
    tool_ids: list[str]
    status: str
    progress: float = 0.0
    params_json: dict[str, Any] = Field(default_factory=dict)
    result_json: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class PipelineRunDTO(BaseModel):
    id: str
    status: str
    recipe_json: dict[str, Any]
    context_json: dict[str, Any]
    current_step_id: Optional[str] = None
    error_message: Optional[str] = None
    step_runs: list[PipelineStepRunDTO] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class RunStepRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ScreeningStartRequest(BaseModel):
    recipe: PipelineRecipe
    context: PipelineContextDTO = Field(default_factory=PipelineContextDTO)


ExecutionMode = Literal["local", "server"]
