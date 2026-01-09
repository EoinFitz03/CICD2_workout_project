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

# RabbitMQ publisher 
from app.rabbit import publish_event

# Make sure the workouts table exists in the database
Base.metadata.create_all(bind=engine)

# Create the FastAPI app (this shows up in Swagger)
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

# ---------- Users service config ----------
# Where the Users service lives.
# In Docker this should match the docker-compose service name + port.
USER_SERVICE_BASE_URL = os.getenv("USER_SERVICE_BASE_URL", "http://localhost:8000")

# How long we wait before we give up calling Users service
USER_SERVICE_TIMEOUT = float(os.getenv("USER_SERVICE_TIMEOUT", "2.0"))

# fail_max = how many failures before we "open" the circuit
# reset_timeout = how long to wait before trying again
USER_CB_FAIL_MAX = int(os.getenv("USER_CB_FAIL_MAX", "3"))
USER_CB_RESET_TIMEOUT = int(os.getenv("USER_CB_RESET_TIMEOUT", "30"))

# Circuit breaker to stop spamming Users service if it's down
user_service_breaker = pybreaker.CircuitBreaker(
    fail_max=USER_CB_FAIL_MAX,
    reset_timeout=USER_CB_RESET_TIMEOUT,
)

def _check_user_exists_via_http(user_id: int) -> None:
    """
    This calls the Users service to make sure the user exists.
    We do this before creating a workout, so we don't store workouts for fake users.

    Raises:
      - 404 if the user doesn't exist
      - 503 if Users service is down / slow / giving server errors
    """

    url = f"{USER_SERVICE_BASE_URL}/users/{user_id}"

    # Try the HTTP request
    try:
        with httpx.Client(timeout=USER_SERVICE_TIMEOUT) as client:
            resp = client.get(url)
    except httpx.RequestError:
        # Can't connect / timeout / DNS problem
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service unavailable. Please try again later.",
        )

    # If Users says "not found", we return 404 here too
    if resp.status_code == 404:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {user_id} not found.",
        )

    # If Users is having server issues, treat it as unavailable
    if resp.status_code >= 500:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service error. Please try again later.",
        )

    # Any other weird status code, also fail safely
    if resp.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to verify user at this time.",
        )


def ensure_user_exists(user_id: int) -> None:
    """
    This wraps the user check with the circuit breaker.

    If Users service keeps failing:
      - the breaker "opens"
      - we stop calling Users for a while
      - we return a quick 503 instead
    """
    try:
        user_service_breaker.call(_check_user_exists_via_http, user_id)
    except pybreaker.CircuitBreakerError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="User service circuit is open. Please try again later.",
        )



@app.post("/workouts", response_model=WorkoutOutput, status_code=status.HTTP_201_CREATED)
async def create_workout(payload: WorkoutInput, db: Session = Depends(get_db)):
    # Before we save the workout, make sure the user exists in Users service
    ensure_user_exists(payload.user_id)

    # Create the workout row
    workout = WorkoutDB(
        user_id=payload.user_id,
        workout_type=payload.workout_type,
        duration_minutes=payload.duration_minutes,
        calories=payload.calories,
        workout_date=payload.workout_date,
        notes=payload.notes,
    )

    # Save it
    db.add(workout)
    db.commit()
    db.refresh(workout)

    # Send an event to RabbitMQ so other services like Notifications
    # We skip this during tests so tests don’t need RabbitMQ running
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
    # Return every workout in the DB
    return db.query(WorkoutDB).all()


@app.get("/workouts/{workout_id}", response_model=WorkoutOutput)
def get_workout_by_id(workout_id: int, db: Session = Depends(get_db)):
    # Find workout by ID
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


@app.put("/workouts/{workout_id}", response_model=WorkoutOutput)
def update_workout(workout_id: int, payload: WorkoutUpdate, db: Session = Depends(get_db)):
    # Find the workout first
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    # Only update fields that were actually sent
    # probaly should have just added a patch for this but this worked better with the pybreaker
    if payload.workout_type is not None:
        workout.workout_type = payload.workout_type
    if payload.duration_minutes is not None:
        workout.duration_minutes = payload.duration_minutes
    if payload.calories is not None:
        workout.calories = payload.calories
    if payload.workout_date is not None
        workout.workout_date = payload.workout_date
    if payload.notes is not None:
        workout.notes = payload.notes

    # Save updates
    db.commit()
    db.refresh(workout)
    return workout


@app.delete("/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workout(workout_id: int, db: Session = Depends(get_db)):
    # Find the workout
    workout = db.query(WorkoutDB).filter(WorkoutDB.id == workout_id).first()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    db.delete(workout)
    db.commit()
    return None
