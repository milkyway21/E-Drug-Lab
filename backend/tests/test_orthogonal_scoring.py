"""正交重打分算法测试"""
import pytest
from app.services.orthogonal_scoring import (
    MetricObservation,
    CandidateScoreInput,
    select_representative_metric,
    robust_desirability,
    rank_by_orthogonal_rescore,
)


# ===== robust_desirability =====

class TestDesirability:
    def test_lower_is_better(self):
        """验证越小越好方向：最好值 desirability 接近 100。"""
        population = [1.0, 2.0, 3.0, 4.0, 5.0]
        d_best = robust_desirability(1.0, population, "lower_is_better")
        d_worst = robust_desirability(5.0, population, "lower_is_better")
        assert d_best > d_worst
        assert d_best == 90.0  # percentile 0.1 → desirability 0.9 → 90

    def test_higher_is_better(self):
        """验证越大越好方向：最好值 desirability 接近 100。"""
        population = [1.0, 2.0, 3.0, 4.0, 5.0]
        d_best = robust_desirability(5.0, population, "higher_is_better")
        d_worst = robust_desirability(1.0, population, "higher_is_better")
        assert d_best > d_worst

    def test_single_candidate(self):
        """单个候选返回 50.0。"""
        assert robust_desirability(1.0, [1.0], "lower_is_better") == 50.0

    def test_all_equal_values(self):
        """所有值相同时，desirability 均为 50。"""
        population = [3.0, 3.0, 3.0]
        d = robust_desirability(3.0, population, "lower_is_better")
        assert d == 50.0

    def test_two_values(self):
        """两个值时，lower_is_better 的最好值为 75。"""
        population = [1.0, 5.0]
        d_best = robust_desirability(1.0, population, "lower_is_better")
        d_worst = robust_desirability(5.0, population, "lower_is_better")
        assert d_best == 75.0
        assert d_worst == 25.0


# ===== select_representative_metric =====

class TestSelectMetric:
    def test_preferred_model(self):
        obs = [
            MetricObservation("score", -7.0, "vina", "docking"),
            MetricObservation("score", -6.5, "gnina", "docking"),
        ]
        sel = select_representative_metric(obs, "score", preferred_models=["gnina"])
        assert sel.observation.model_name == "gnina"
        assert sel.selection_rule == "preferred_model:gnina"

    def test_select_median_observed_value(self):
        obs = [
            MetricObservation("score", -7.0, "vina", "docking", priority=100),
            MetricObservation("score", -6.5, "gnina", "docking", priority=100),
            MetricObservation("score", -6.8, "gold", "docking", priority=100),
        ]
        sel = select_representative_metric(obs, "score")
        assert sel.selection_rule == "median_observed_value"

    def test_lowest_priority(self):
        obs = [
            MetricObservation("score", -7.0, "vina", "docking", priority=50),
            MetricObservation("score", -6.5, "gnina", "docking", priority=100),
        ]
        sel = select_representative_metric(obs, "score")
        assert sel.observation.model_name == "vina"
        assert sel.selection_rule == "lowest_priority"

    def test_missing_metric_raises(self):
        obs = [MetricObservation("score", -7.0, "vina", "docking")]
        with pytest.raises(ValueError, match="Missing metric"):
            select_representative_metric(obs, "nonexistent")

    def test_direction_consistency(self):
        obs = [
            MetricObservation("score", -7.0, "vina", "docking", direction="lower_is_better"),
            MetricObservation("score", -6.5, "gnina", "docking", direction="higher_is_better"),
        ]
        with pytest.raises(ValueError, match="Inconsistent directions"):
            select_representative_metric(obs, "score")


# ===== rank_by_orthogonal_rescore =====

class TestRankByOrthogonalRescore:
    def _make_candidates(self) -> list[CandidateScoreInput]:
        return [
            CandidateScoreInput(
                molecule_id="mol-a",
                name="Good candidate",
                metrics=[
                    MetricObservation("docking", -8.0, "vina", "docking"),
                    MetricObservation("mmgbsa", -35.0, "mmgbsa", "physics"),
                ],
            ),
            CandidateScoreInput(
                molecule_id="mol-b",
                name="Average candidate",
                metrics=[
                    MetricObservation("docking", -6.0, "vina", "docking"),
                    MetricObservation("mmgbsa", -20.0, "mmgbsa", "physics"),
                ],
            ),
            CandidateScoreInput(
                molecule_id="mol-artifact",
                name="Artifact candidate",
                metrics=[
                    MetricObservation("docking", -12.0, "vina", "docking"),
                    MetricObservation("mmgbsa", -5.0, "mmgbsa", "physics"),
                ],
            ),
        ]

    def test_basic_ranking(self):
        candidates = self._make_candidates()
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        assert len(results) == 3
        # 结果按 final_score 降序排列
        scores = [r.final_score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_artifact_detection(self):
        candidates = self._make_candidates()
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        artifact = next(r for r in results if r.molecule_id == "mol-artifact")
        assert artifact.artifact_flag is True
        assert artifact.artifact_reason is not None

    def test_artifact_extra_penalty(self):
        """artifact 分子的 final_score 应被乘以 0.3。"""
        candidates = self._make_candidates()
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        artifact = next(r for r in results if r.molecule_id == "mol-artifact")
        # artifact 的 final_score 应该很低
        assert artifact.final_score < 20.0

    def test_non_artifact_no_flag(self):
        candidates = self._make_candidates()
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        good = next(r for r in results if r.molecule_id == "mol-a")
        assert good.artifact_flag is False

    def test_single_candidate_edge_case(self):
        candidates = [
            CandidateScoreInput(
                molecule_id="only-one",
                name="Lonely molecule",
                metrics=[
                    MetricObservation("docking", -7.0, "vina", "docking"),
                    MetricObservation("mmgbsa", -25.0, "mmgbsa", "physics"),
                ],
            )
        ]
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        assert len(results) == 1
        assert results[0].final_score == 50.0  # single candidate → desirability 50

    def test_all_artifacts(self):
        candidates = [
            CandidateScoreInput(
                molecule_id=f"artifact-{i}",
                name=f"Artifact {i}",
                metrics=[
                    MetricObservation("docking", float(-10 - i), "vina", "docking"),
                    MetricObservation("mmgbsa", float(-2 - i), "mmgbsa", "physics"),
                ],
            )
            for i in range(3)
        ]
        results = rank_by_orthogonal_rescore(candidates, "docking", "mmgbsa")
        # 所有 artifact 的 final_score 都被惩罚
        for r in results:
            if r.artifact_flag:
                assert r.final_score < 30.0
