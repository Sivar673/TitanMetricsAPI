from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


# DEV STUB: no passwords, token is not a real JWT. Replace with proper
# credential verification + signed tokens before anything public-facing.
@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if user is None:
        # Dev convenience: fall back to the first user with the requested role
        user = db.query(User).filter(User.role == payload.role).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No matching user. Run seed.py to create dev users.",
        )

    return LoginResponse(
        token=f"dev-token-{user.id}",
        user=UserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        ),
    )
