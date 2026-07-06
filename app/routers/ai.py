from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.models import User
from app.schemas import PhysiqueEvaluation
from app.security import get_current_user
from app.services.physique_ai import (
    ALLOWED_IMAGE_TYPES,
    MAX_IMAGE_BYTES,
    PhysiqueAIError,
    evaluate_physique,
)

router = APIRouter(prefix="/ai", tags=["ai"])


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
    _user: User = Depends(get_current_user),
) -> PhysiqueEvaluation:
    images = [
        await _read_validated(front, "front"),
        await _read_validated(side, "side"),
        await _read_validated(back, "back"),
    ]
    try:
        return evaluate_physique(images)
    except PhysiqueAIError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
