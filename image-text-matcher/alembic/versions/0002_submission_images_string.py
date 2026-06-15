from __future__ import annotations

import json
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision = "0002_submission_images_string"
down_revision = "0001_phase2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("submissions", sa.Column("image_path", sa.String(length=1024), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, images FROM submissions")).mappings()
    for row in rows:
        image_path = _extract_single_path(row["images"])
        if image_path is None:
            raise ValueError(f"Submission {row['id']} does not contain a usable image path")
        connection.execute(
            sa.text("UPDATE submissions SET image_path = :image_path WHERE id = :submission_id"),
            {"image_path": image_path, "submission_id": row["id"]},
        )

    with op.batch_alter_table("submissions") as batch_op:
        batch_op.drop_column("images")
        batch_op.alter_column("image_path", existing_type=sa.String(length=1024), nullable=False)
        batch_op.alter_column("image_path", new_column_name="images", existing_type=sa.String(length=1024))


def downgrade() -> None:
    op.add_column("submissions", sa.Column("images_json", sa.JSON(), nullable=True))

    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, images FROM submissions")).mappings()
    for row in rows:
        image_paths = _wrap_single_path(row["images"])
        connection.execute(
            sa.text("UPDATE submissions SET images_json = :images_json WHERE id = :submission_id"),
            {"images_json": json.dumps(image_paths), "submission_id": row["id"]},
        )

    with op.batch_alter_table("submissions") as batch_op:
        batch_op.drop_column("images")
        batch_op.alter_column("images_json", existing_type=sa.JSON(), nullable=False)
        batch_op.alter_column("images_json", new_column_name="images", existing_type=sa.JSON())


def _extract_single_path(value: object) -> str | None:
    if isinstance(value, str):
        value = _try_parse_json(value)

    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        for item in value:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    return cleaned
        return None

    return None


def _wrap_single_path(value: object) -> list[str]:
    if not isinstance(value, str):
        raise ValueError(f"Expected image path string during downgrade, got {type(value)!r}")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Submission image path cannot be empty during downgrade")
    return [cleaned]


def _try_parse_json(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
