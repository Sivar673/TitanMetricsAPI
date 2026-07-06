import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, LoginResponse, UserCreate, UserOut
from app.security import create_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: UserCreate, db: Session = Depends(get_db)) -> LoginResponse:
    """Create a client account and log it straight in — the response is
    the same shape as /auth/login, so the app lands on the dashboard
    without a second round trip."""
    email = payload.email.strip().lower()

    if db.query(User).filter(User.email == email).first() is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use.",
        )

    user = User(
        id=f"c_{uuid.uuid4().hex[:12]}",
        email=email,
        password_hash=hash_password(payload.password),
        display_name=payload.display_name.strip(),
        role="client",  # coaches are provisioned, not self-registered
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # Race: two signups with the same email between check and commit
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already in use.",
        )
    db.refresh(user)

    return LoginResponse(
        token=create_token(user),
        user=UserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        ),
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    """Validate a stored token and return its owner — used by the app to
    restore a persisted session on launch."""
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
    )


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> LoginResponse:
    user = db.query(User).filter(User.email == payload.email.strip().lower()).first()
    # Same error for unknown email and wrong password — don't leak which
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )

    return LoginResponse(
        token=create_token(user),
        user=UserOut(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            role=user.role,
        ),
    )
