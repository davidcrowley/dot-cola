from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_optional_submission_alcohol"
down_revision = "0003_drop_celery_task_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column(
            "alcohol",
            existing_type=sa.String(length=255),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("submissions") as batch_op:
        batch_op.alter_column(
            "alcohol",
            existing_type=sa.String(length=255),
            nullable=False,
        )
