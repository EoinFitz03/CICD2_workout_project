# app/main.py

from typing import List

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Base, WorkoutDB
from app.schemas import WorkoutInput, WorkoutOutput, WorkoutUpdate

# Create tables using the Base from app.models
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Workout Service",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["health"])
def health_check():
    return {"status": "ok", "service": "workout"}


@app.post(
    "/workouts",
    response_model=WorkoutOutput,
    status_code=status.HTTP_201_CREATED,
    tags=["workouts"],
)
def create_workout(
    payload: WorkoutInput,
    db: Session = Depends(get_db),
):
    workout = WorkoutDB(
        user_id=payload.user_id,
        workout_type=payload.workout_type,
        duration_minutes=payload.duration_minutes,
        calories=payload.calories,
        workout_date=payload.workout_date,
        notes=payload.notes,
    )
    db.add(workout)
    db.commit()
    db.refresh(workout)
    return workout


@app.get(
    "/workouts",
    response_model=List[WorkoutOutput],
    tags=["workouts"],
)
def list_workouts(
    user_id: int | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(WorkoutDB)
    if user_id is not None:
        query = query.filter(WorkoutDB.user_id == user_id)
    return query.all()


@app.get(
    "/workouts/{workout_id}",
    response_model=WorkoutOutput,
    tags=["workouts"],
)
def get_workout(
    workout_id: int,
    db: Session = Depends(get_db),
):
    workout = (
        db.query(WorkoutDB)
        .filter(WorkoutDB.workout_id == workout_id)
        .first()
    )
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


@app.put(
    "/workouts/{workout_id}",
    response_model=WorkoutOutput,
    tags=["workouts"],
)
def update_workout(
    workout_id: int,
    payload: WorkoutUpdate,
    db: Session = Depends(get_db),
):
    workout = (
        db.query(WorkoutDB)
        .filter(WorkoutDB.workout_id == workout_id)
        .first()
    )
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(workout, key, value)

    db.commit()
    db.refresh(workout)
    return workout


@app.delete(
    "/workouts/{workout_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["workouts"],
)
def delete_workout(
    workout_id: int,
    db: Session = Depends(get_db),
):
    workout = (
        db.query(WorkoutDB)
        .filter(WorkoutDB.workout_id == workout_id)
        .first()
    )
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    db.delete(workout)
    db.commit()
    return
