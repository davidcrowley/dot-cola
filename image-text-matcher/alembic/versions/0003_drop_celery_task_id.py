from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_drop_celery_task_id"
down_revision = "0002_submission_images_string"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("queue_items") as batch_op:
        batch_op.drop_column("celery_task_id")


def downgrade() -> None:
    with op.batch_alter_table("queue_items") as batch_op:
        batch_op.add_column(sa.Column("celery_task_id", sa.String(length=255), nullable=True))
