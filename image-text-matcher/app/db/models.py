from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


json_type = JSON().with_variant(JSONB, "postgresql")


class Submission(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    brand: Mapped[str] = mapped_column(String(255), nullable=False)
    class_type: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    net_contents: Mapped[str] = mapped_column(String(255), nullable=False)
    alcohol: Mapped[str | None] = mapped_column(String(255), nullable=True)
    origin: Mapped[str | None] = mapped_column(String(255), nullable=True)
    appellation: Mapped[str | None] = mapped_column(String(255), nullable=True)
    warning: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    images: Mapped[str] = mapped_column(String(1024), nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    process_results: Mapped[list["ProcessResult"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    queue_items: Mapped[list["QueueItem"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_submissions_created", "created"),
        Index("ix_submissions_processed", "processed"),
        Index("ix_submissions_approved", "approved"),
    )


class ProcessResult(Base):
    __tablename__ = "process_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    combined_image: Mapped[str] = mapped_column(String(1024), nullable=False)
    match_results: Mapped[list[dict[str, object]]] = mapped_column(json_type, nullable=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    process_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    process_completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="process_results")

    __table_args__ = (
        Index("ix_process_results_submission_id", "submission_id"),
        Index("ix_process_results_status", "status"),
    )


class QueueItem(Base):
    __tablename__ = "queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    started: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    submission: Mapped[Submission] = relationship(back_populates="queue_items")

    __table_args__ = (
        Index("ix_queue_items_submission_id", "submission_id"),
        Index("ix_queue_items_status", "status"),
        Index("ix_queue_items_created", "created"),
    )


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
