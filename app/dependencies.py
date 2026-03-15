from fastapi import HTTPException, Cookie, Request
from datetime import datetime
from .database import get_user_sessions_collection, get_users_collection


async def get_current_user(request: Request, session_token: str = Cookie(None)):
    """Authenticate user via session cookie OR Authorization: Bearer <token> header."""
    token = session_token

    # Fall back to Authorization header (needed for cross-origin deployments)
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

    return user
