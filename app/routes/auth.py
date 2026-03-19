from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, EmailStr

from app.auth import create_access_token, hash_password, verify_password
from app.config import get_settings
from app.rate_limiter import auth_rate_limiter
from app.services.chat_memory import (
    create_user,
    get_user_by_email,
    create_reset_token,
    validate_reset_token,
    mark_reset_token_used,
    update_user_password,
)
from app.services.vector_store import ensure_user_collections
from app.services.integrations_service import send_password_reset_email
from app.logger import get_logger

logger = get_logger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Auth"])





class SignupRequest(BaseModel):
    """Signup request body."""

    email: EmailStr
    password: str
    display_name: str = ""


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """Successful auth response."""

    access_token: str
    token_type: str = "bearer"
    user_id: str
    display_name: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str





@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(request: SignupRequest, http_request: Request) -> AuthResponse:
    """
    Register a new user.

    Args:
        request: Signup payload with email, password, and optional display name.

    Returns:
        JWT access token and user metadata.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    rate_key = f"signup:{client_ip}:{request.email.lower()}"
    if not auth_rate_limiter.allow(
        key=rate_key,
        limit=settings.rate_limit_requests,
        period_seconds=settings.rate_limit_period,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many signup attempts. Please retry later.",
        )

    existing = await get_user_by_email(request.email)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    try:
        hashed = hash_password(request.password)
        user = await create_user(
            email=request.email,
            password_hash=hashed,
            display_name=request.display_name,
        )
        try:
            await ensure_user_collections(user.email)
        except Exception as exc:
            logger.warning(
                "Failed to create Chroma collections for %s: %s", user.email, exc
            )
        token = create_access_token(user.email)
        logger.info("New user registered: %s", user.email)
        return AuthResponse(
            access_token=token,
            user_id=user.email,
            display_name=user.display_name or "",
        )
    except Exception as exc:
        logger.error("Signup error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating account",
        )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, http_request: Request) -> AuthResponse:
    """
    Authenticate an existing user.

    Args:
        request: Login payload with email and password.

    Returns:
        JWT access token and user metadata.
    """
    client_ip = http_request.client.host if http_request.client else "unknown"
    rate_key = f"login:{client_ip}:{request.email.lower()}"
    if not auth_rate_limiter.allow(
        key=rate_key,
        limit=settings.rate_limit_requests,
        period_seconds=settings.rate_limit_period,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Please retry later.",
        )

    user = await get_user_by_email(request.email)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(user.email)
    logger.info("User logged in: %s", user.email)
    return AuthResponse(
        access_token=token,
        user_id=user.email,
        display_name=user.display_name or "",
    )


@router.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    """
    Initiate password reset. Returns 200 regardless of user existence to prevent enumeration.
    """
    try:
        user = await get_user_by_email(payload.email)
        if user:
            token = await create_reset_token(user.email)
            sent = send_password_reset_email(user.email, token)
            if not sent:
                logger.warning("SMTP not configured; returning token for dev use.")
                return {"status": "ok", "reset_token": token}
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Forgot password error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to process password reset",
        )


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    """Reset password using a one-time token."""
    if len(payload.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )

    user = await validate_reset_token(payload.token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token",
        )

    try:
        new_hash = hash_password(payload.new_password)
        await update_user_password(user.email, new_hash)
        await mark_reset_token_used(payload.token)
        logger.info("Password reset for user %s", user.email)
        return {"status": "ok"}
    except Exception as exc:
        logger.error("Reset password error: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset password",
        )
