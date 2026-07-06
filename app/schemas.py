from typing import Dict, List, Optional

from pydantic import BaseModel, EmailStr, Field

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


# ---- AI Physique Coach ----


class PhysiqueEvaluation(BaseModel):
    """Structured verdict from the vision model. This schema is enforced
    server-side by the Claude structured-outputs API, so every response
    is guaranteed to parse."""

    is_valid_submission: bool = Field(
        description=(
            "True only if all three images clearly show one person in the "
            "requested poses with enough visibility to judge a physique."
        )
    )
    validity_notes: Optional[str] = Field(
        default=None,
        description="If not valid: which pose/image is the problem and why.",
    )
    overall_score: int = Field(
        ge=1,
        le=10,
        description="Overall Men's Physique package score, 1-10. Use 1 when invalid.",
    )
    strengths: List[str] = Field(
        description="Specific standout attributes, referencing judging criteria."
    )
    weaknesses: List[str] = Field(
        description="Specific detractors from the package, referencing criteria."
    )
    training_adjustments: List[str] = Field(
        description=(
            "Actionable programming changes, each tied to a named weakness, "
            "with concrete exercises/volumes where possible."
        )
    )


class EvaluationHistoryItem(BaseModel):
    """A persisted evaluation, as returned by GET /ai/evaluations.
    Image paths are intentionally not exposed until an authenticated
    image-serving endpoint exists."""

    id: int
    created_at: str  # ISO 8601 UTC
    is_valid_submission: bool
    validity_notes: Optional[str]
    overall_score: float
    strengths: List[str]
    weaknesses: List[str]
    training_adjustments: List[str]


# ---- Auth ----


class LoginRequest(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    # users.display_name is NOT NULL — the coach roster and reports
    # render it, so signup must collect it.
    display_name: str = Field(min_length=1, max_length=80)


class UserOut(BaseModel):
    id: str
    email: str
    display_name: str
    role: str


class LoginResponse(BaseModel):
    token: str
    user: UserOut
