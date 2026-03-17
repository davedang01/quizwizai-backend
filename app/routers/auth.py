import os
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
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

# Load settings (reads from .env file via pydantic-settings)
_settings = get_settings()

# Frontend URL for password reset links
FRONTEND_URL = os.environ.get("FRONTEND_URL", "") or _settings.frontend_url or "https://quizwizai.netlify.app"

# Gmail SMTP settings
GMAIL_USER = os.environ.get("GMAIL_USER", "") or _settings.gmail_user
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "") or _settings.gmail_app_password


# ─── Approved Email Allowlist ───────────────────────────────
def _load_approved_emails() -> set:
    """Load approved emails from JSON file shipped with the backend."""
    json_path = Path(__file__).parent.parent.parent / "approved_emails.json"
    try:
        with open(json_path, "r") as f:
            emails = json.load(f)
        return {e.strip().lower() for e in emails}
    except FileNotFoundError:
        print(f"WARNING: approved_emails.json not found at {json_path}. All signups allowed.")
        return set()


APPROVED_EMAILS = _load_approved_emails()


def _is_email_approved(email: str) -> bool:
    """Check if email is on the approved list. If list is empty, allow all."""
    if not APPROVED_EMAILS:
        return True  # No allowlist = open signup
    return email.strip().lower() in APPROVED_EMAILS


# ─── Email Sending ──────────────────────────────────────────
def _send_reset_email(to_email: str, reset_token: str):
    """Send password reset email via Gmail SMTP."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="Email service not configured. Please contact the administrator."
        )

    reset_link = f"{FRONTEND_URL}/reset-password?token={reset_token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Quiz Wiz AI — Reset Your Password"
    msg["From"] = f"Quiz Wiz AI <{GMAIL_USER}>"
    msg["To"] = to_email

    text_body = f"""Hi there!

We received a request to reset your Quiz Wiz AI password.

Click the link below to set a new password:
{reset_link}

This link expires in 1 hour.

If you didn't request this, you can safely ignore this email.

— The Quiz Wiz AI Team
"""

    html_body = f"""
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px 24px;">
    <div style="text-align: center; margin-bottom: 32px;">
        <div style="display: inline-block; width: 48px; height: 48px; background: linear-gradient(135deg, #0ea5e9, #06b6d4); border-radius: 12px; line-height: 48px; font-size: 24px;">
            &#10024;
        </div>
        <h1 style="color: #111827; font-size: 24px; margin: 16px 0 4px;">Quiz Wiz AI</h1>
        <p style="color: #6b7280; font-size: 14px; margin: 0;">Password Reset</p>
    </div>

    <p style="color: #374151; font-size: 16px; line-height: 1.5;">Hi there!</p>
    <p style="color: #374151; font-size: 16px; line-height: 1.5;">We received a request to reset your password. Click the button below to choose a new one:</p>

    <div style="text-align: center; margin: 32px 0;">
        <a href="{reset_link}"
           style="display: inline-block; padding: 14px 32px; background: linear-gradient(135deg, #0ea5e9, #06b6d4); color: white; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px;">
            Reset Password
        </a>
    </div>

    <p style="color: #6b7280; font-size: 13px; line-height: 1.5;">This link expires in 1 hour. If you didn't request a password reset, you can safely ignore this email.</p>

    <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 24px 0;" />
    <p style="color: #9ca3af; font-size: 12px; text-align: center;">Quiz Wiz AI — Smart Study Made Easy</p>
</div>
"""

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
    except smtplib.SMTPAuthenticationError:
        raise HTTPException(
            status_code=500,
            detail="Email authentication failed. Please contact the administrator."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send reset email: {str(e)}"
        )


# ─── Request/Response Models ────────────────────────────────

class SignupRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class AuthResponse(BaseModel):
    user: dict
    token: str


class UserResponse(BaseModel):
    id: str
    name: str
    email: str
    created_at: str


# ─── Helpers ────────────────────────────────────────────────

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


# ─── Routes ─────────────────────────────────────────────────

@router.post("/signup")
async def signup(request: SignupRequest, response: Response):
    # Check email allowlist
    if not _is_email_approved(request.email):
        raise HTTPException(
            status_code=403,
            detail="This email is not authorized to sign up. Please contact the administrator for access."
        )

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


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Send a password reset email if the user exists."""
    print(f"DEBUG FORGOT-PW: Request received for email={request.email}")
    print(f"DEBUG FORGOT-PW: GMAIL_USER='{GMAIL_USER}', HAS_PASSWORD={'yes' if GMAIL_APP_PASSWORD else 'no'}")
    users_collection = get_users_collection()
    user = await users_collection.find_one({"email": request.email})

    # Always return success to avoid email enumeration attacks
    success_msg = "If an account with that email exists, a reset link has been sent."

    if not user:
        print(f"DEBUG FORGOT-PW: No user found for {request.email} — returning early")
        return {"message": success_msg}

    # Generate reset token and store in DB
    reset_token = secrets.token_urlsafe(48)
    expires_at = datetime.utcnow() + timedelta(hours=1)

    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "reset_token": reset_token,
            "reset_token_expires": expires_at.isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }}
    )

    # Send the email
    try:
        print(f"DEBUG: Sending reset email to {request.email}")
        print(f"DEBUG: GMAIL_USER='{GMAIL_USER}', GMAIL_APP_PASSWORD={'SET' if GMAIL_APP_PASSWORD else 'EMPTY'}")
        print(f"DEBUG: FRONTEND_URL='{FRONTEND_URL}'")
        _send_reset_email(request.email, reset_token)
        print(f"DEBUG: Reset email sent successfully to {request.email}")
    except HTTPException as e:
        # If email fails, still return generic success (don't leak info)
        # but log it server-side
        print(f"ERROR: Failed to send reset email to {request.email}: {e.detail}")

    return {"message": success_msg}


@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    """Reset password using a valid reset token."""
    users_collection = get_users_collection()

    user = await users_collection.find_one({"reset_token": request.token})

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    # Check token expiry
    expires_at = datetime.fromisoformat(user.get("reset_token_expires", "2000-01-01"))
    if datetime.utcnow() > expires_at:
        raise HTTPException(status_code=400, detail="Reset link has expired. Please request a new one.")

    # Validate new password
    if len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")

    # Update password and clear reset token
    hashed_password = bcrypt.hashpw(request.new_password.encode(), bcrypt.gensalt())

    await users_collection.update_one(
        {"_id": user["_id"]},
        {"$set": {
            "password_hash": hashed_password,
            "updated_at": datetime.utcnow().isoformat()
        },
        "$unset": {
            "reset_token": "",
            "reset_token_expires": ""
        }}
    )

    return {"message": "Password reset successfully. You can now sign in with your new password."}


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
