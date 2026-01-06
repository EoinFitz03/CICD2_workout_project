# app/main.py

from typing import List
import os

import httpx
import pybreaker

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.models import Base, WorkoutDB
from app.schemas import WorkoutInput, WorkoutOutput, WorkoutUpdate

# NEW: RabbitMQ publisher helper
from app.rabbit import publish_event

# Create tables using the Base from app.models
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Workout Service API",
    description="CRUD microservice for workouts",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Cross-service config ----------
# This must match your deploy docker-compose service name + port for users service.
USER_SERVICE_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8000")

USER_SERVICE_TIMEOUT = float(os.getenv("USER_SERVICE_TIMEOUT", "2.0"))

# ---------- Circuit breaker config ----------
USER_CB_FAIL_MAX = int(os.getenv("USER_CB_FAIL_MAX", "3"))
USER_CB_RESET_TIMEOUT = int(os.getenv("USER_CB_RESET_TIMEOUT", "30"))

user_service_breaker = pybreaker.CircuitBreaker(
    fail_max=USER_CB_FAIL_MAX,
    reset_timeout=USER_CB_RESET_TIMEOUT,
)

# ---------- Helper: sync call to Users with error handling ----------
def _check_user_exists_via_http(user_id: int) -> None:
    """
    Synchronous call to users_service to confirm a user exists.
    Raises HTTPException:
      - 404 if user not found
      - 503 if users service is down/slow or returns server errors
    """

    # IMPORTANT:
    # If your users service route is not /users/{id}, change this path to match it.
    url = f"{USER_SERVICE_BASE_URL}/users/{user_id}"



    try:
        with httpx.Client(timeout=USER_SERVICE_TIMEOUT) as client:
            resp = client.get(url)
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable. Please try again later.",
        )

    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )

    if resp.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service error. Please try again later.",
        )

    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify user at this time.",
        )


def ensure_user_exists(user_id: int) -> None:
    """
    Wrap the user check in a circuit breaker.
    If the circuit is OPEN, return a fast fallback 503 without calling users_service.
    """
    try:
        user_service_breaker.call(_check_user_exists_via_http, user_id)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service circuit is open. Please try again later.",
        )


# ----------------- CRUD Endpoints -----------------

@app.post("/workouts", response_model=WorkoutOutput, status_code=status.HTTP_201_CREATED)
async def create_workout(payload: WorkoutInput, db: Session = Depends(get_db)):
    # Sync validation: confirm user exists before creating workout
    ensure_user_exists(payload.user_id)

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

    # NEW: publish workout.created event to RabbitMQ (skip during tests)
    if os.getenv("APP_ENV") != "test":
        await publish_event(
            "workout.created",
            {
                "workout_id": workout.id,
                "user_id": workout.user_id,
                "workout_type": workout.workout_type,
                "duration_minutes": workout.duration_minutes,
                "calories": workout.calories,
                "workout_date": str(workout.workout_date),
            },
        )

    return workout


@app.get("/workouts", response_model=List[WorkoutOutput])
def get_all_workouts(db: Session = Depends(get_db)):
    return db.query(WorkoutDB).all()


@app.get("/workouts/{workout_id}", response_model=WorkoutOutput)
def get_workout_by_id(workout_id: int, db: Session = Depends(get_db)):
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


@app.put("/workouts/{workout_id}", response_model=WorkoutOutput)
def update_workout(workout_id: int, payload: WorkoutUpdate, db: Session = Depends(get_db)):
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    if payload.workout_type is not None:
        workout.workout_type = payload.workout_type
    if payload.duration_minutes is not None:
        workout.duration_minutes = payload.duration_minutes
    if payload.calories is not None:
        workout.calories = payload.calories
    if payload.workout_date is not None:
        workout.workout_date = payload.workout_date
    if payload.notes is not None:
        workout.notes = payload.notes

    db.commit()
    db.refresh(workout)
    return workout


@app.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: int, db: Session = Depends(get_db)):
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    db.delete(workout)
    db.commit()
    return None
