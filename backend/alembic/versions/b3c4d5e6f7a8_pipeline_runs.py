"""Add pipeline_runs and pipeline_step_runs tables."""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "2aae692a3003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("target_id", sa.String(length=36), nullable=True),
        sa.Column("recipe_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("current_step_id", sa.String(length=50), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("idx_pipeline_runs_target", "pipeline_runs", ["target_id"])

    op.create_table(
        "pipeline_step_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pipeline_run_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=50), nullable=False),
        sa.Column("tool_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("progress", sa.Float(), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("screening_task_id", sa.String(length=36), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["screening_task_id"], ["screening_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pipeline_step_runs_run", "pipeline_step_runs", ["pipeline_run_id"])
    op.create_index("idx_pipeline_step_runs_status", "pipeline_step_runs", ["status"])


def downgrade() -> None:
    op.drop_index("idx_pipeline_step_runs_status", table_name="pipeline_step_runs")
    op.drop_index("idx_pipeline_step_runs_run", table_name="pipeline_step_runs")
    op.drop_table("pipeline_step_runs")
    op.drop_index("idx_pipeline_runs_target", table_name="pipeline_runs")
    op.drop_index("idx_pipeline_runs_status", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
