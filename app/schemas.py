from typing import Dict, List, Optional

from pydantic import BaseModel, Field

# ---- Check-ins ----


class CheckInCreate(BaseModel):
    client_id: str
    week_start: str
    morning_weights_lbs: List[Optional[float]]
    macro_adherent_days: int
    fatigue: Dict[str, int]
    notes: Optional[str] = None


class CheckInResponse(BaseModel):
    """The saved check-in echoed back with computed weekly metrics."""

    id: int
    client_id: str
    week_start: str
    morning_weights_lbs: List[Optional[float]]
    macro_adherent_days: int
    fatigue: Dict[str, int]
    notes: Optional[str]
    weekly_avg_weight_lbs: float
    logged_days: int


# ---- Workouts ----


class SetIn(BaseModel):
    set_number: int
    weight_lbs: float
    reps: int = Field(gt=0)
    rpe: Optional[float] = None  # 6-10 scale
    is_working_set: bool


class ExerciseIn(BaseModel):
    name: str
    order: int
    sets: List[SetIn]


class WorkoutCreate(BaseModel):
    client_id: str
    performed_at: str  # ISO 8601 datetime
    split_day: str
    exercises: List[ExerciseIn]
    session_notes: Optional[str] = None


class WorkoutResponse(BaseModel):
    id: int
    client_id: str
    performed_at: str
    split_day: str
    total_working_sets: int
    total_volume_lbs: float  # sum of weight * reps over working sets


# ---- Coach / analytics (shapes mirror the mobile app's types/api.ts) ----


class ClientSummaryOut(BaseModel):
    id: str
    display_name: str
    phase: str
    weeks_out: Optional[int]
    last_check_in_at: Optional[str]
    weekly_weight_delta_lbs: Optional[float]
    compliance_rate: float


class WeeklyDelta(BaseModel):
    metric: str
    unit: str
    current: float
    previous: Optional[float]
    delta: Optional[float]


class ClientReportOut(BaseModel):
    client_id: str
    display_name: str
    week_start: str
    phase: str
    weeks_out: Optional[int]
    deltas: List[WeeklyDelta]
    coach_flags: List[str]


class WeightPoint(BaseModel):
    week_start: str
    avg_weight_lbs: float


class StrengthPoint(BaseModel):
    week_start: str
    top_set_weight_lbs: float
    est_one_rm_lbs: float


class StrengthTrend(BaseModel):
    exercise: str
    points: List[StrengthPoint]


class ProgressionOut(BaseModel):
    client_id: str
    weight_trend: List[WeightPoint]
    strength_trends: List[StrengthTrend]


# ---- Auth (dev stub) ----


class LoginRequest(BaseModel):
    email: str
    role: str  # "coach" | "client"


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut
