from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
from ..database import get_results_collection
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/results", tags=["results"])


class AnswerDetail(BaseModel):
    question_id: str
    user_answer: str
    correct_answer: str
    is_correct: bool


class ResultResponse(BaseModel):
    id: str
    user_id: str
    test_id: str
    score: float
    num_correct: int
    num_total: int
    answers: List[AnswerDetail]
    created_at: str


@router.get("/{result_id}", response_model=ResultResponse)
async def get_result(result_id: str, current_user: dict = Depends(get_current_user)):
    results_collection = get_results_collection()
    result = await results_collection.find_one({"_id": result_id, "user_id": current_user["_id"]})

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return ResultResponse(
        id=result["_id"],
        user_id=result["user_id"],
        test_id=result["test_id"],
        score=result["score"],
        num_correct=result["num_correct"],
        num_total=result["num_total"],
        answers=result["answers"],
        created_at=result["created_at"]
    )


@router.get("/test/{test_id}", response_model=ResultResponse)
async def get_result_by_test(test_id: str, current_user: dict = Depends(get_current_user)):
    results_collection = get_results_collection()
    result = await results_collection.find_one({"test_id": test_id, "user_id": current_user["_id"]})

    if not result:
        raise HTTPException(status_code=404, detail="Result not found for this test")

    return ResultResponse(
        id=result["_id"],
        user_id=result["user_id"],
        test_id=result["test_id"],
        score=result["score"],
        num_correct=result["num_correct"],
        num_total=result["num_total"],
        answers=result["answers"],
        created_at=result["created_at"]
    )
