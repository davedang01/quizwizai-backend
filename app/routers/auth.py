import os
from fastapi import APIRouter, HTTPException, Response, Cookie, Request
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import bcrypt
import secrets
import uuid
from ..database import get_users_collection, get_user_sessions_collection
from ..config import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Detect if running in production (cross-origin) or local dev (same-origin)
IS_PRODUCTION = os.environ.get("RENDER", "") == "true" or os.environ.get("PRODUCTION", "") == "true"


class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    user: dict
    token: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str


def _set_session_cookie(response: Response, session_token: str, max_age: int):
    """Set session cookie with appropriate settings for the environment."""
    if IS_PRODUCTION:
        # Cross-origin: Netlify frontend -> Render backend
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=max_age,
        )
    else:
        # Local dev: same origin via Vite proxy
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            secure=False,
            samesite="lax",
            max_age=max_age,
        )


@router.post("/signup")
async def signup(request: SignupRequest, response: Response):
    users_collection = get_users_collection()
    settings = get_settings()

    existing_user = await users_collection.find_one({"email": request.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    hashed_password = bcrypt.hashpw(request.password.encode(), bcrypt.gensalt())

    user = {
        "_id": str(uuid.uuid4()),
        "name": request.name,
        "email": request.email,
        "password_hash": hashed_password,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    await users_collection.insert_one(user)

    session_token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(days=settings.session_expiry_days)

    sessions_collection = get_user_sessions_collection()
    session = {
        "token": session_token,
        "user_id": user["_id"],
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat()
    }

    await sessions_collection.insert_one(session)

    max_age = settings.session_expiry_days * 86400
    _set_session_cookie(response, session_token, max_age)

    return {
        "user": {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "created_at": user["created_at"],
        },
        "token": session_token,
    }


@router.post("/login")
async def login(request: LoginRequest, response: Response):
    users_collection = get_users_collection()
    settings = get_settings()

    user = await users_collection.find_one({"email": request.email})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not bcrypt.checkpw(request.password.encode(), user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    session_token = secrets.token_hex(32)
    expires_at = datetime.utcnow() + timedelta(days=settings.session_expiry_days)

    sessions_collection = get_user_sessions_collection()
    session = {
        "token": session_token,
        "user_id": user["_id"],
        "created_at": datetime.utcnow().isoformat(),
        "expires_at": expires_at.isoformat()
    }

    await sessions_collection.insert_one(session)

    max_age = settings.session_expiry_days * 86400
    _set_session_cookie(response, session_token, max_age)

    return {
        "user": {
            "id": user["_id"],
            "name": user["name"],
            "email": user["email"],
            "created_at": user["created_at"],
        },
        "token": session_token,
    }


@router.get("/me")
async def get_me(request: Request, session_token: str = Cookie(None)):
    # Try cookie first, then Authorization header (for cross-origin)
    token = session_token
    if not token:
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    sessions_collection = get_user_sessions_collection()
    session = await sessions_collection.find_one({"token": token})

    if not session:
        raise HTTPException(status_code=401, detail="Session not found")

    if datetime.fromisoformat(session["expires_at"]) < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Session expired")

    users_collection = get_users_collection()
    user = await users_collection.find_one({"_id": session["user_id"]})

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": user["_id"],
        "name": user["name"],
        "email": user["email"],
        "created_at": user["created_at"],
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {"message": "Logged out successfully"}
