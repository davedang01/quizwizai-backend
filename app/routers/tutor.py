from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
from ..database import get_homework_sessions_collection
from ..dependencies import get_current_user
from ..services.ai_stub import generate_tutor_response

router = APIRouter(prefix="/api/homework", tags=["tutor"])


class Message(BaseModel):
    role: str
    content: str
    timestamp: str
    has_attachment: bool = False
    attachment_type: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    has_attachment: bool = False
    attachment_type: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    session_id: str


class SessionListItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class SessionDetailResponse(BaseModel):
    id: str
    user_id: str
    title: str
    messages: List[dict]
    created_at: str
    updated_at: str


@router.post("/chat", response_model=ChatResponse)
async def chat_with_tutor(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user)
):
    homework_sessions_collection = get_homework_sessions_collection()

    session_id = request.session_id
    session = None

    if session_id:
        session = await homework_sessions_collection.find_one({
            "_id": session_id,
            "user_id": current_user["_id"]
        })

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        session_id = str(uuid.uuid4())
        session = {
            "_id": session_id,
            "user_id": current_user["_id"],
            "title": request.message[:50] if len(request.message) <= 50 else request.message[:47] + "...",
            "messages": [],
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat()
        }
        await homework_sessions_collection.insert_one(session)

    user_message = {
        "role": "user",
        "content": request.message,
        "timestamp": datetime.utcnow().isoformat(),
        "has_attachment": request.has_attachment,
        "attachment_type": request.attachment_type
    }

    updated_messages = session.get("messages", []) + [user_message]

    ai_response = await generate_tutor_response(updated_messages, request.message)

    assistant_message = {
        "role": "assistant",
        "content": ai_response,
        "timestamp": datetime.utcnow().isoformat(),
        "has_attachment": False,
        "attachment_type": None
    }

    final_messages = updated_messages + [assistant_message]

    await homework_sessions_collection.update_one(
        {"_id": session_id},
        {
            "$set": {
                "messages": final_messages,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )

    return ChatResponse(
        response=ai_response,
        session_id=session_id
    )


@router.get("/sessions", response_model=List[SessionListItem])
async def get_all_sessions(current_user: dict = Depends(get_current_user)):
    homework_sessions_collection = get_homework_sessions_collection()
    sessions = await homework_sessions_collection.find({
        "user_id": current_user["_id"]
    }).sort("updated_at", -1).to_list(None)

    return [
        SessionListItem(
            id=session["_id"],
            title=session["title"],
            created_at=session["created_at"],
            updated_at=session["updated_at"],
            message_count=len(session.get("messages", []))
        )
        for session in sessions
    ]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    homework_sessions_collection = get_homework_sessions_collection()
    session = await homework_sessions_collection.find_one({
        "_id": session_id,
        "user_id": current_user["_id"]
    })

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return SessionDetailResponse(
        id=session["_id"],
        user_id=session["user_id"],
        title=session["title"],
        messages=session.get("messages", []),
        created_at=session["created_at"],
        updated_at=session["updated_at"]
    )


@router.post("/sessions/new")
async def create_new_session(current_user: dict = Depends(get_current_user)):
    session_id = str(uuid.uuid4())
    session = {
        "_id": session_id,
        "user_id": current_user["_id"],
        "title": "New Chat",
        "messages": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    homework_sessions_collection = get_homework_sessions_collection()
    await homework_sessions_collection.insert_one(session)

    return {
        "id": session_id,
        "title": "New Chat"
    }


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    homework_sessions_collection = get_homework_sessions_collection()
    result = await homework_sessions_collection.delete_one({
        "_id": session_id,
        "user_id": current_user["_id"]
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"message": "Session deleted successfully"}
