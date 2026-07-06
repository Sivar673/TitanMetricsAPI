from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.analytics import avg_fatigue, avg_weight, epley_1rm, week_monday
from app.database import get_db
from app.models import CheckIn, User, WorkoutSession
from app.schemas import (
    ClientReportOut,
    ClientSummaryOut,
    ProgressionOut,
    StrengthPoint,
    StrengthTrend,
    WeeklyDelta,
    WeightPoint,
)

router = APIRouter(tags=["coach"])

# Movements surfaced on the progression screen. Everything logged is
# stored; these are just the headline lifts.
KEY_LIFTS = ("Bench Press", "Back Squat")


def _get_client(db: Session, client_id: str) -> User:
    client = db.get(User, client_id)
    if client is None or client.role != "client":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No client with id {client_id!r}.",
        )
    return client


def _recent_check_ins(db: Session, client_id: str, limit: int = 3) -> List[CheckIn]:
    """Latest first. week_start is ISO, so lexicographic order is date order."""
    return (
        db.query(CheckIn)
        .filter(CheckIn.client_id == client_id)
        .order_by(CheckIn.week_start.desc())
        .limit(limit)
        .all()
    )


def _delta(
    metric: str, unit: str, current: Optional[float], previous: Optional[float]
) -> Optional[WeeklyDelta]:
    if current is None:
        return None
    delta = round(current - previous, 2) if previous is not None else None
    return WeeklyDelta(
        metric=metric, unit=unit, current=current, previous=previous, delta=delta
    )


@router.get("/coach/clients", response_model=List[ClientSummaryOut])
def list_clients(db: Session = Depends(get_db)) -> List[ClientSummaryOut]:
    clients = db.query(User).filter(User.role == "client").order_by(User.display_name).all()

    out: List[ClientSummaryOut] = []
    for client in clients:
        recent = _recent_check_ins(db, client.id, limit=2)
        latest = recent[0] if recent else None
        previous = recent[1] if len(recent) > 1 else None

        weight_delta = None
        if latest and previous:
            cur, prev = avg_weight(latest), avg_weight(previous)
            if cur is not None and prev is not None:
                weight_delta = round(cur - prev, 2)

        out.append(
            ClientSummaryOut(
                id=client.id,
                display_name=client.display_name,
                phase=client.phase or "off_season",
                weeks_out=client.weeks_out,
                last_check_in_at=latest.week_start if latest else None,
                weekly_weight_delta_lbs=weight_delta,
                compliance_rate=(latest.macro_adherent_days / 7) if latest else 0.0,
            )
        )
    return out


@router.get("/clients/{client_id}/report", response_model=ClientReportOut)
def client_report(client_id: str, db: Session = Depends(get_db)) -> ClientReportOut:
    client = _get_client(db, client_id)

    recent = _recent_check_ins(db, client_id, limit=3)
    if not recent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No check-ins recorded for this client yet.",
        )
    current = recent[0]
    previous = recent[1] if len(recent) > 1 else None

    def sessions_in_week(week_start: str) -> int:
        sessions = (
            db.query(WorkoutSession)
            .filter(WorkoutSession.client_id == client_id)
            .all()
        )
        return sum(1 for s in sessions if week_monday(s.performed_at) == week_start)

    cur_fatigue = avg_fatigue(current)
    prev_fatigue = avg_fatigue(previous) if previous else None
    cur_sleep = float(current.fatigue.get("sleep_quality", 0)) or None
    prev_sleep = (
        float(previous.fatigue.get("sleep_quality", 0)) or None if previous else None
    )

    deltas = [
        d
        for d in (
            _delta(
                "Avg Morning Weight",
                "lbs",
                avg_weight(current),
                avg_weight(previous) if previous else None,
            ),
            _delta(
                "Macro Adherence",
                "days",
                float(current.macro_adherent_days),
                float(previous.macro_adherent_days) if previous else None,
            ),
            _delta(
                "Training Sessions",
                "sessions",
                float(sessions_in_week(current.week_start)),
                float(sessions_in_week(previous.week_start)) if previous else None,
            ),
            _delta("Avg Fatigue Score", "/5", cur_fatigue, prev_fatigue),
            _delta("Avg Sleep Quality", "/5", cur_sleep, prev_sleep),
        )
        if d is not None
    ]

    # -- Automated coach flags ----------------------------------------------
    flags: List[str] = []
    fatigue_series = [avg_fatigue(ci) for ci in recent]  # latest first
    if (
        len(fatigue_series) >= 3
        and all(f is not None for f in fatigue_series[:3])
        and fatigue_series[0] > fatigue_series[1] > fatigue_series[2]
    ):
        flags.append("Fatigue trending up 2 consecutive weeks")
    if cur_sleep is not None and prev_sleep is not None and prev_sleep - cur_sleep >= 0.5:
        flags.append("Sleep quality declining — consider a refeed day")
    if current.macro_adherent_days <= 4:
        flags.append("Macro adherence under 70% this week")

    return ClientReportOut(
        client_id=client.id,
        display_name=client.display_name,
        week_start=current.week_start,
        phase=client.phase or "off_season",
        weeks_out=client.weeks_out,
        deltas=deltas,
        coach_flags=flags,
    )


@router.get("/clients/{client_id}/progression", response_model=ProgressionOut)
def client_progression(client_id: str, db: Session = Depends(get_db)) -> ProgressionOut:
    _get_client(db, client_id)

    check_ins = (
        db.query(CheckIn)
        .filter(CheckIn.client_id == client_id)
        .order_by(CheckIn.week_start.asc())
        .all()
    )
    weight_trend = [
        WeightPoint(week_start=ci.week_start, avg_weight_lbs=w)
        for ci in check_ins
        if (w := avg_weight(ci)) is not None
    ]

    sessions = (
        db.query(WorkoutSession)
        .filter(WorkoutSession.client_id == client_id)
        .order_by(WorkoutSession.performed_at.asc())
        .all()
    )

    # exercise -> week -> heaviest working set (weight, reps)
    top_sets: dict = {lift: {} for lift in KEY_LIFTS}
    for session in sessions:
        week = week_monday(session.performed_at)
        for exercise in session.exercises:
            name = exercise["name"]
            if name not in top_sets:
                continue
            for s in exercise["sets"]:
                if not s["is_working_set"]:
                    continue
                best: Optional[Tuple[float, int]] = top_sets[name].get(week)
                if best is None or s["weight_lbs"] > best[0]:
                    top_sets[name][week] = (s["weight_lbs"], s["reps"])

    strength_trends = [
        StrengthTrend(
            exercise=lift,
            points=[
                StrengthPoint(
                    week_start=week,
                    top_set_weight_lbs=weight,
                    est_one_rm_lbs=epley_1rm(weight, reps),
                )
                for week, (weight, reps) in sorted(weeks.items())
            ],
        )
        for lift, weeks in top_sets.items()
        if weeks
    ]

    return ProgressionOut(
        client_id=client_id,
        weight_trend=weight_trend,
        strength_trends=strength_trends,
    )
