from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
from ..database import get_study_guides_collection, get_results_collection
from ..dependencies import get_current_user
from ..services.ai_stub import generate_study_guide_entry

router = APIRouter(prefix="/api/study-guides", tags=["study_guides"])


class GenerateStudyGuideRequest(BaseModel):
    result_id: str


class StudyGuideEntry(BaseModel):
    question_id: str
    question: str
    user_answer: str
    correct_answer: str
    explanation: str
    tips: str
    practice_question: str


class StudyGuideResponse(BaseModel):
    id: str
    user_id: str
    result_id: str
    test_name: str
    guides: List[dict]
    timestamp: str


@router.post("/generate", response_model=StudyGuideResponse)
async def generate_study_guide(
    request: GenerateStudyGuideRequest,
    current_user: dict = Depends(get_current_user)
):
    results_collection = get_results_collection()
    result = await results_collection.find_one({
        "_id": request.result_id,
        "user_id": current_user["_id"]
    })

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    wrong_answers = [
        answer for answer in result.get("answers", [])
        if not answer.get("is_correct", False)
    ]

    guides_list = []
    for answer in wrong_answers:
        guide_entry = await generate_study_guide_entry(
            answer.get("question_text", ""),
            answer.get("user_answer", ""),
            answer.get("correct_answer", "")
        )

        guides_list.append({
            "question_id": answer.get("question_id"),
            "question": answer.get("question_text", ""),
            "user_answer": answer.get("user_answer", ""),
            "correct_answer": answer.get("correct_answer", ""),
            "explanation": guide_entry["explanation"],
            "tips": guide_entry["tips"],
            "practice_question": guide_entry["practice_question"]
        })

    study_guide = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "result_id": request.result_id,
        "test_name": result.get("test_name", "Unnamed Test"),
        "guides": guides_list,
        "timestamp": datetime.utcnow().isoformat()
    }

    study_guides_collection = get_study_guides_collection()
    await study_guides_collection.insert_one(study_guide)

    return StudyGuideResponse(
        id=study_guide["_id"],
        user_id=study_guide["user_id"],
        result_id=study_guide["result_id"],
        test_name=study_guide["test_name"],
        guides=study_guide["guides"],
        timestamp=study_guide["timestamp"]
    )


@router.get("/{guide_id}", response_model=StudyGuideResponse)
async def get_study_guide(
    guide_id: str,
    current_user: dict = Depends(get_current_user)
):
    study_guides_collection = get_study_guides_collection()
    guide = await study_guides_collection.find_one({
        "_id": guide_id,
        "user_id": current_user["_id"]
    })

    if not guide:
        raise HTTPException(status_code=404, detail="Study guide not found")

    return StudyGuideResponse(
        id=guide["_id"],
        user_id=guide["user_id"],
        result_id=guide["result_id"],
        test_name=guide["test_name"],
        guides=guide["guides"],
        timestamp=guide["timestamp"]
    )


@router.get("/result/{result_id}")
async def get_study_guide_by_result(
    result_id: str,
    current_user: dict = Depends(get_current_user)
):
    study_guides_collection = get_study_guides_collection()
    guide = await study_guides_collection.find_one({
        "result_id": result_id,
        "user_id": current_user["_id"]
    })

    if not guide:
        return {"exists": False}

    return {
        "exists": True,
        "id": guide["_id"],
        "result_id": guide["result_id"],
        "test_name": guide["test_name"],
        "timestamp": guide["timestamp"]
    }
