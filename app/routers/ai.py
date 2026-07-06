from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import PhysiqueEvaluationRecord, User
from app.schemas import EvaluationHistoryItem, PhysiqueEvaluation
from app.security import get_current_user
from app.services.physique_ai import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    PhysiqueAIError,
    evaluate_physique,
)
from app.services.storage import save_pose_images

router = APIRouter(prefix="/ai", tags=["ai"])


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Financial guardrail -------------------------------------------------
# Counts persisted evaluations, so the limit survives server restarts and
# holds across multiple workers — an in-memory dict would do neither.
def enforce_daily_limit(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> User:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    used = (
        db.query(PhysiqueEvaluationRecord)
        .filter(
            PhysiqueEvaluationRecord.user_id == user.id,
            PhysiqueEvaluationRecord.created_at >= cutoff,  # ISO sorts lexically
        )
        .count()
    )
    if used >= settings.ai_daily_evaluation_limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Daily limit reached — you get {settings.ai_daily_evaluation_limit} "
                "AI evaluations per 24 hours. Try again tomorrow."
            ),
        )
    return user


async def _read_validated(upload: UploadFile, pose: str) -> tuple[str, bytes, str]:
    media_type = (upload.content_type or "").lower()
    if media_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{pose} image must be JPEG, PNG, or WebP (got {media_type or 'unknown'}).",
        )
    raw = await upload.read()
    if len(raw) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{pose} image is empty.",
        )
    if len(raw) > MAX_IMAGE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"{pose} image exceeds the 5 MB limit.",
        )
    return pose, raw, media_type


@router.post("/physique-evaluation", response_model=PhysiqueEvaluation)
async def physique_evaluation(
    front: UploadFile = File(..., description="Mandatory front pose"),
    side: UploadFile = File(..., description="Mandatory side pose"),
    back: UploadFile = File(..., description="Mandatory back pose"),
    user: User = Depends(enforce_daily_limit),
    db: Session = Depends(get_db),
) -> PhysiqueEvaluation:
    images = [
        await _read_validated(front, "front"),
        await _read_validated(side, "side"),
        await _read_validated(back, "back"),
    ]
    try:
        evaluation = evaluate_physique(images)
    except PhysiqueAIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))

    # Persist the verdict + source images. Failed AI calls never reach
    # this point, so they don't consume the daily limit.
    created_at = _utc_now_iso()
    paths = save_pose_images(user.id, created_at, images)
    db.add(
        PhysiqueEvaluationRecord(
            user_id=user.id,
            created_at=created_at,
            front_image_path=paths["front"],
            side_image_path=paths["side"],
            back_image_path=paths["back"],
            is_valid_submission=int(evaluation.is_valid_submission),
            validity_notes=evaluation.validity_notes,
            overall_score=float(evaluation.overall_score),
            strengths=evaluation.strengths,
            weaknesses=evaluation.weaknesses,
            training_adjustments=evaluation.training_adjustments,
        )
    )
    db.commit()

    return evaluation


@router.get("/evaluations", response_model=List[EvaluationHistoryItem])
def list_evaluations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[EvaluationHistoryItem]:
    rows = (
        db.query(PhysiqueEvaluationRecord)
        .filter(PhysiqueEvaluationRecord.user_id == user.id)
        .order_by(PhysiqueEvaluationRecord.created_at.desc())
        .all()
    )
    return [
        EvaluationHistoryItem(
            id=row.id,
            created_at=row.created_at,
            is_valid_submission=bool(row.is_valid_submission),
            validity_notes=row.validity_notes,
            overall_score=row.overall_score,
            strengths=row.strengths,
            weaknesses=row.weaknesses,
            training_adjustments=row.training_adjustments,
        )
        for row in rows
    ]
