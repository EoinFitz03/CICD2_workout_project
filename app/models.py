# app/models.py

from datetime import date

from sqlalchemy import String, Integer, Date, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


class WorkoutDB(Base):
    __tablename__ = "workouts"

    workout_id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    workout_type: Mapped[str] = mapped_column(String(100), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    calories: Mapped[int | None] = mapped_column(Integer, nullable=True)
    workout_date: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


