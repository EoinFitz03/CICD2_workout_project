# app/main.py

from typing import List
import os          # NEW: for reading env vars
import httpx       # NEW: for HTTP calls to other services

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

# ---------- NEW: Base URLs for other microservices ----------
# Same pattern as the lab: use env vars so this service knows where others live.
# In dev: usually localhost with different ports.
# In Docker: these will be service names, e.g. http://user_service:8000
USER_SERVICE_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8000")
GOALS_SERVICE_BASE_URL = os.getenv("GOALS_SERVICE_BASE_URL", "http://localhost:8002")


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


# ---------- NEW: Integration endpoint (workout service calling others) ----------

@app.get("/api/workout-summary/{user_id}", tags=["proxy"])
def workout_summary(user_id: int, db: Session = Depends(get_db)):
    """
    This endpoint lives in the WORKOUT service but:
      - Calls the USER service:   GET /api/users/{user_id}
      - Calls the GOALS service:  GET /goals?user_id={user_id}
      - Uses its own DB to load workouts for that user.

    It follows the same pattern as the user service:
    env-based base URLs + httpx.Client().
    """

    # 1) Call USER service to get the user (and fail if it doesn't exist)
    user_url = f"{USER_SERVICE_BASE_URL}/api/users/{user_id}"

    try:
        with httpx.Client() as client:
            user_res = client.get(user_url)
        user_res.raise_for_status()
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Error contacting user service: {exc}",
        )
    except httpx.HTTPStatusError as exc:
        # If user service says 404, propagate that
        if exc.response.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"User service error: {exc.response.text}",
        )

    user_data = user_res.json()

    # 2) Get workouts locally from this service's own DB
    workouts = (
        db.query(WorkoutDB)
        .filter(WorkoutDB.user_id == user_id)
        .all()
    )
    # convert ORM objects to plain dicts using the Pydantic schema
    workout_list = [WorkoutOutput.model_validate(w).model_dump() for w in workouts]

    # 3) Call GOALS service for this user (optional but mirrors the pattern)
    goals_url = f"{GOALS_SERVICE_BASE_URL}/goals"
    goals_data = []

    try:
        with httpx.Client() as client:
            goals_res = client.get(goals_url, params={"user_id": user_id})
        # it's fine if goals returns empty list; just error on real HTTP failure
        goals_res.raise_for_status()
        goals_data = goals_res.json()
    except httpx.RequestError:
        # If goals service is down, we still return user + workouts
        goals_data = []
    except httpx.HTTPStatusError:
        goals_data = []

    return {
        "user": user_data,
        "workouts": workout_list,
        "goals": goals_data,
    }
