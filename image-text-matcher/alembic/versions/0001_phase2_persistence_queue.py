from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_phase2"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=255), primary_key=True),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("brand", sa.String(length=255), nullable=False),
        sa.Column("class_type", sa.String(length=255), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("net_contents", sa.String(length=255), nullable=False),
        sa.Column("alcohol", sa.String(length=255), nullable=False),
        sa.Column("origin", sa.String(length=255), nullable=True),
        sa.Column("appellation", sa.String(length=255), nullable=True),
        sa.Column("warning", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=255), nullable=False),
        sa.Column("images", sa.JSON(), nullable=False),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("processed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved", sa.Boolean(), nullable=True),
    )
    op.create_index("ix_submissions_created", "submissions", ["created"])
    op.create_index("ix_submissions_processed", "submissions", ["processed"])
    op.create_index("ix_submissions_approved", "submissions", ["approved"])

    op.create_table(
        "process_results",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("combined_image", sa.String(length=1024), nullable=False),
        sa.Column("match_results", sa.JSON(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("process_started", sa.DateTime(timezone=True), nullable=False),
        sa.Column("process_completed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_process_results_submission_id", "process_results", ["submission_id"])
    op.create_index("ix_process_results_status", "process_results", ["status"])

    op.create_table(
        "queue_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("submission_id", sa.Integer(), sa.ForeignKey("submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("celery_task_id", sa.String(length=255), nullable=True),
        sa.Column("created", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_index("ix_queue_items_submission_id", "queue_items", ["submission_id"])
    op.create_index("ix_queue_items_status", "queue_items", ["status"])
    op.create_index("ix_queue_items_created", "queue_items", ["created"])


def downgrade() -> None:
    op.drop_index("ix_queue_items_created", table_name="queue_items")
    op.drop_index("ix_queue_items_status", table_name="queue_items")
    op.drop_index("ix_queue_items_submission_id", table_name="queue_items")
    op.drop_table("queue_items")
    op.drop_index("ix_process_results_status", table_name="process_results")
    op.drop_index("ix_process_results_submission_id", table_name="process_results")
    op.drop_table("process_results")
    op.drop_index("ix_submissions_approved", table_name="submissions")
    op.drop_index("ix_submissions_processed", table_name="submissions")
    op.drop_index("ix_submissions_created", table_name="submissions")
    op.drop_table("submissions")
    op.drop_table("app_settings")
