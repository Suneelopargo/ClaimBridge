from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth_schemas import LoginRequest, LoginResponse
from app.services.auth_service import verify_password
from app.services.token_service import create_access_token

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .one_or_none()
    )

    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token, expires_in = create_access_token(
        user_id=user.id,
        username=user.username,
        role=user.role,
    )

    user.last_login_at = datetime.utcnow()
    db.commit()

    return {
        "success": True,
        "message": "Authentication successful",
        "accessToken": access_token,
        "tokenType": "bearer",
        "expiresIn": expires_in,
        "user": {
            "id": user.id,
            "username": user.username,
            "fullName": user.full_name,
            "role": user.role,
        },
    }
