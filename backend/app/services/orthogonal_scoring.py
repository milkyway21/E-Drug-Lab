"""Orthogonal rescoring utilities.

The final rank is driven by an independent orthogonal metric. Repeated values
for the same metric are reduced by selecting one observed value, never by
averaging model outputs.

Gap threshold 35.0: empirical threshold — a primary desirability 35+ points
higher than the orthogonal desirability indicates the primary metric is likely
a scoring-function artifact rather than a true binding signal.

Penalty weight 0.65: controls how aggressively artifact gaps reduce the final
score via a quadratic formula: penalty = max(0, gap - threshold)^2 * weight / 100.
A gap of 10 points above threshold yields a 0.65-point penalty; a gap of 45
yields 6.5 points.  Molecules flagged as artifacts (gap > threshold AND
primary_desirability >= 70) receive an additional 70% reduction (final_score * 0.3).
"""
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Literal


Direction = Literal["higher_is_better", "lower_is_better"]


@dataclass(frozen=True)
class MetricObservation:
    metric_name: str
    value: float
    model_name: str
    method_family: str
    direction: Direction = "lower_is_better"
    priority: int = 100


@dataclass(frozen=True)
class CandidateScoreInput:
    molecule_id: str
    name: str | None
    metrics: list[MetricObservation]


@dataclass(frozen=True)
class SelectedMetric:
    observation: MetricObservation
    selection_rule: str


@dataclass(frozen=True)
class OrthogonalRankResult:
    molecule_id: str
    name: str | None
    primary_value: float
    orthogonal_value: float
    primary_desirability: float
    orthogonal_desirability: float
    consistency_gap: float
    final_score: float
    artifact_flag: bool
    artifact_reason: str | None
    selected_primary_model: str
    selected_orthogonal_model: str


def select_representative_metric(
    observations: Iterable[MetricObservation],
    metric_name: str,
    preferred_models: list[str] | None = None,
) -> SelectedMetric:
    values = [item for item in observations if item.metric_name == metric_name]
    if not values:
        raise ValueError(f"Missing metric: {metric_name}")

    # direction 一致性校验
    directions = {item.direction for item in values}
    if len(directions) > 1:
        raise ValueError(
            f"Inconsistent directions for metric '{metric_name}': {directions}. "
            "All observations of the same metric must share the same direction."
        )

    preferred_models = preferred_models or []
    for model_name in preferred_models:
        preferred = [item for item in values if item.model_name == model_name]
        if preferred:
            selected = sorted(preferred, key=lambda item: item.priority)[0]
            return SelectedMetric(selected, f"preferred_model:{model_name}")

    best_priority = min(item.priority for item in values)
    priority_group = [item for item in values if item.priority == best_priority]
    if len(priority_group) == 1:
        return SelectedMetric(priority_group[0], "lowest_priority")

    center = median(item.value for item in priority_group)
    selected = min(priority_group, key=lambda item: (abs(item.value - center), item.model_name))
    return SelectedMetric(selected, "median_observed_value")


def robust_desirability(value: float, population: list[float], direction: Direction) -> float:
    if len(population) <= 1:
        return 50.0

    ordered = sorted(population)
    below = sum(1 for item in ordered if item < value)
    equal = sum(1 for item in ordered if item == value)
    percentile = (below + 0.5 * equal) / len(ordered)
    if direction == "lower_is_better":
        desirability = 1.0 - percentile
    else:
        desirability = percentile
    return round(max(0.0, min(1.0, desirability)) * 100.0, 4)


def rank_by_orthogonal_rescore(
    candidates: list[CandidateScoreInput],
    primary_metric: str,
    orthogonal_metric: str,
    preferred_primary_models: list[str] | None = None,
    preferred_orthogonal_models: list[str] | None = None,
    gap_threshold: float = 35.0,
    penalty_weight: float = 0.65,
) -> list[OrthogonalRankResult]:
    selected_rows = []
    for candidate in candidates:
        primary = select_representative_metric(candidate.metrics, primary_metric, preferred_primary_models)
        orthogonal = select_representative_metric(candidate.metrics, orthogonal_metric, preferred_orthogonal_models)
        selected_rows.append((candidate, primary, orthogonal))

    primary_values = [row[1].observation.value for row in selected_rows]
    orthogonal_values = [row[2].observation.value for row in selected_rows]

    results: list[OrthogonalRankResult] = []
    for candidate, primary, orthogonal in selected_rows:
        primary_obs = primary.observation
        orthogonal_obs = orthogonal.observation
        primary_desirability = robust_desirability(primary_obs.value, primary_values, primary_obs.direction)
        orthogonal_desirability = robust_desirability(orthogonal_obs.value, orthogonal_values, orthogonal_obs.direction)
        gap = round(primary_desirability - orthogonal_desirability, 4)

        # 非线性惩罚：gap 越大惩罚增长越快
        penalty = max(0.0, gap - gap_threshold) ** 2 * penalty_weight / 100.0
        final_score = round(max(0.0, orthogonal_desirability - penalty), 4)

        artifact_flag = gap > gap_threshold and primary_desirability >= 70.0
        artifact_reason = None
        if artifact_flag:
            # artifact 分子施加额外惩罚
            final_score = round(final_score * 0.3, 4)
            artifact_reason = (
                "Primary score is strong, but orthogonal rescoring is weak; "
                "treat as a possible scoring-function artifact."
            )
        results.append(
            OrthogonalRankResult(
                molecule_id=candidate.molecule_id,
                name=candidate.name,
                primary_value=primary_obs.value,
                orthogonal_value=orthogonal_obs.value,
                primary_desirability=primary_desirability,
                orthogonal_desirability=orthogonal_desirability,
                consistency_gap=gap,
                final_score=final_score,
                artifact_flag=artifact_flag,
                artifact_reason=artifact_reason,
                selected_primary_model=primary_obs.model_name,
                selected_orthogonal_model=orthogonal_obs.model_name,
            )
        )

    return sorted(results, key=lambda item: item.final_score, reverse=True)
