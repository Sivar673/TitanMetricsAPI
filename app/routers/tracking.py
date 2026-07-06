from datetime import date, datetime
from statistics import fmean

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CheckIn, User, WorkoutSession
from app.schemas import CheckInCreate, CheckInResponse, WorkoutCreate, WorkoutResponse
from app.security import get_current_user

router = APIRouter(prefix="/check-ins", tags=["tracking"])
workouts_router = APIRouter(prefix="/workouts", tags=["tracking"])


def _require_own_client_record(payload_client_id: str, user: User) -> None:
    """Clients submit their own data; nobody logs on someone else's behalf."""
    if user.role != "client" or user.id != payload_client_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only submit records for your own account.",
        )


# Path is "" (not "/") so POST /check-ins works without a 307 redirect.
@router.post("", response_model=CheckInResponse, status_code=status.HTTP_201_CREATED)
def create_check_in(
    payload: CheckInCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> CheckInResponse:
    _require_own_client_record(payload.client_id, user)

    # -- Validation the schema can't express on its own --------------------
    logged = [w for w in payload.morning_weights_lbs if w is not None]
    if not logged:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one morning weight is required to compute a weekly average.",
        )

    try:
        date.fromisoformat(payload.week_start)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='week_start must be an ISO date, e.g. "2026-06-29".',
        )

    if not 0 <= payload.macro_adherent_days <= 7:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="macro_adherent_days must be between 0 and 7.",
        )

    # One check-in per client per week; resubmitting is a conflict, not a dupe row
    exists = (
        db.query(CheckIn)
        .filter(
            CheckIn.client_id == payload.client_id,
            CheckIn.week_start == payload.week_start,
        )
        .first()
    )
    if exists is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A check-in for week {payload.week_start} already exists for this client.",
        )

    # -- Analytics ----------------------------------------------------------
    weekly_avg = round(fmean(logged), 2)

    # -- Persist -------------------------------------------------------------
    check_in = CheckIn(
        client_id=payload.client_id,
        week_start=payload.week_start,
        morning_weights_lbs=payload.morning_weights_lbs,
        macro_adherent_days=payload.macro_adherent_days,
        fatigue=payload.fatigue,
        notes=payload.notes,
    )
    db.add(check_in)
    db.commit()
    db.refresh(check_in)

    return CheckInResponse(
        id=check_in.id,
        client_id=check_in.client_id,
        week_start=check_in.week_start,
        morning_weights_lbs=check_in.morning_weights_lbs,
        macro_adherent_days=check_in.macro_adherent_days,
        fatigue=check_in.fatigue,
        notes=check_in.notes,
        weekly_avg_weight_lbs=weekly_avg,
        logged_days=len(logged),
    )


@workouts_router.post("", response_model=WorkoutResponse, status_code=status.HTTP_201_CREATED)
def log_workout(
    payload: WorkoutCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> WorkoutResponse:
    _require_own_client_record(payload.client_id, user)

    try:
        datetime.fromisoformat(payload.performed_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="performed_at must be an ISO 8601 datetime.",
        )

    if not payload.exercises or all(not ex.sets for ex in payload.exercises):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A workout needs at least one logged set.",
        )

    session = WorkoutSession(
        client_id=payload.client_id,
        performed_at=payload.performed_at,
        split_day=payload.split_day,
        exercises=[ex.model_dump() for ex in payload.exercises],
        session_notes=payload.session_notes,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    working_sets = [
        s for ex in payload.exercises for s in ex.sets if s.is_working_set
    ]
    return WorkoutResponse(
        id=session.id,
        client_id=session.client_id,
        performed_at=session.performed_at,
        split_day=session.split_day,
        total_working_sets=len(working_sets),
        total_volume_lbs=round(sum(s.weight_lbs * s.reps for s in working_sets), 1),
    )
