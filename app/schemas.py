# app/schemas.py

from typing import Annotated, Optional
from datetime import date

from annotated_types import Ge, Le
from pydantic import BaseModel, ConfigDict, StringConstraints

WorkoutTypeStr = Annotated[str, StringConstraints(min_length=2, max_length=100)]
NotesStr = Annotated[str, StringConstraints(max_length=500)]
DurationMinutesInt = Annotated[int, Ge(1), Le(1000)]
CaloriesInt = Annotated[int, Ge(0), Le(100000)]

UserIdInt = int
WorkoutIdInt = int


class WorkoutInput(BaseModel):
    user_id: UserIdInt
    workout_type: WorkoutTypeStr
    duration_minutes: DurationMinutesInt
    calories: Optional[CaloriesInt] = None
    workout_date: date
    notes: Optional[NotesStr] = None


class WorkoutOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workout_id: WorkoutIdInt
    user_id: UserIdInt
    workout_type: WorkoutTypeStr
    duration_minutes: DurationMinutesInt
    calories: Optional[CaloriesInt] = None
    workout_date: date
    notes: Optional[NotesStr] = None


class WorkoutUpdate(BaseModel):
    workout_type: Optional[WorkoutTypeStr] = None
    duration_minutes: Optional[DurationMinutesInt] = None
    calories: Optional[CaloriesInt] = None
    workout_date: Optional[date] = None
    notes: Optional[NotesStr] = None


class WorkoutRemove(BaseModel):
    workout_id: WorkoutIdInt
