from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base


class VideoTask(Base):
    __tablename__ = "video_tasks"
    __table_args__ = (UniqueConstraint("task_id", "job_id", name="uq_task_job"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    project: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    assignee: Mapped[str] = mapped_column(String(256), nullable=True, index=True)
    # class_counts: Mapped[str] = mapped_column(Text, nullable=False, default="")
    localization: Mapped[str] = mapped_column(String(512), nullable=True, index=True)
    scope: Mapped[str] = mapped_column(String(512), nullable=True, index=True)
    visual: Mapped[str] = mapped_column(String(512), nullable=True, index=True)
    lab: Mapped[str] = mapped_column(String(512), nullable=True, index=True)


class AnnotationColumn(Base):
    __tablename__ = "annotation_columns"
    __table_args__ = (
        UniqueConstraint("project", "name", name="uq_annotation_project_column"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


class AnnotationValue(Base):
    __tablename__ = "annotation_values"
    __table_args__ = (
        UniqueConstraint("video_task_id", "column_id", name="uq_task_annotation_column"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    video_task_id: Mapped[int] = mapped_column(
        ForeignKey("video_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    column_id: Mapped[int] = mapped_column(
        ForeignKey("annotation_columns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    value: Mapped[str] = mapped_column(String(512), nullable=False)
