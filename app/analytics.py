"""Shared metric math used by the tracking and coach routers."""

from datetime import date, datetime, timedelta
from statistics import fmean
from typing import List, Optional

from app.models import CheckIn


def logged_weights(check_in: CheckIn) -> List[float]:
    """Morning weights with missed days (nulls) stripped out."""
    return [w for w in check_in.morning_weights_lbs if w is not None]


def avg_weight(check_in: CheckIn) -> Optional[float]:
    weights = logged_weights(check_in)
    return round(fmean(weights), 2) if weights else None


def avg_fatigue(check_in: CheckIn) -> Optional[float]:
    values = list(check_in.fatigue.values())
    return round(fmean(values), 1) if values else None


def week_monday(iso_datetime: str) -> str:
    """Collapse any timestamp onto its week's Monday (ISO date)."""
    d = datetime.fromisoformat(iso_datetime.replace("Z", "+00:00")).date()
    return (d - timedelta(days=d.weekday())).isoformat()


def epley_1rm(weight_lbs: float, reps: int) -> float:
    """Estimated one-rep max. At 1 rep this is just the weight itself."""
    if reps <= 1:
        return round(weight_lbs, 1)
    return round(weight_lbs * (1 + reps / 30), 1)


def most_recent_monday(today: Optional[date] = None) -> str:
    d = today or date.today()
    return (d - timedelta(days=d.weekday())).isoformat()
