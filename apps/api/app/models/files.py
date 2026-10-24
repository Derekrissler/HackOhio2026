from sqlalchemy import Boolean, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._mixins import SourceMixin

MATERIAL_KINDS = ("lecture", "slides", "reading", "exam")


class File(SourceMixin, Base):
    __tablename__ = "files"

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    display_name: Mapped[str] = mapped_column(String(300))
    filename: Mapped[str] = mapped_column(String(300))
    mime: Mapped[str] = mapped_column(String(100))
    storage_path: Mapped[str] = mapped_column(String(500))  # relative to <repo>/data/
    size: Mapped[int]
    sha256: Mapped[str] = mapped_column(String(64))
    page_count: Mapped[int | None]
    has_text_layer: Mapped[bool] = mapped_column(Boolean, default=True)


class CourseMaterial(SourceMixin, Base):
    __tablename__ = "course_materials"
    __table_args__ = (CheckConstraint(f"kind IN {MATERIAL_KINDS}", name="ck_material_kind"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"))
    file_id: Mapped[int] = mapped_column(ForeignKey("files.id"))
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(20))
    module_label: Mapped[str | None] = mapped_column(String(200))
    module_position: Mapped[int] = mapped_column(default=0)
    position: Mapped[int] = mapped_column(default=0)
