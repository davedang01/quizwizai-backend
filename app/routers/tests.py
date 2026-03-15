from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional, Any
import uuid
from datetime import datetime
from ..database import get_tests_collection, get_scans_collection, get_results_collection
from ..dependencies import get_current_user
from ..services import ai_stub

router = APIRouter(prefix="/api/tests", tags=["tests"])


class GenerateTestRequest(BaseModel):
    scan_id: Optional[str] = None
    test_name: str
    test_type: str
    difficulty: str
    num_questions: int
    additional_prompts: Optional[str] = None
    content_text: Optional[str] = None
    topics: Optional[List[str]] = None


class SubmitAnswerItem(BaseModel):
    question_id: str
    answer: str


class SubmitTestRequest(BaseModel):
    test_id: str
    answers: List[SubmitAnswerItem]


class QuestionResponse(BaseModel):
    id: str
    type: str
    text: str
    options: Optional[List[str]] = None
    difficulty: str


class TestResponse(BaseModel):
    id: str
    user_id: str
    scan_id: str
    test_name: str
    test_type: str
    difficulty: str
    questions: List[dict]
    is_completed: bool
    score: Optional[float] = None
    created_at: str


class ResultResponse(BaseModel):
    id: str
    user_id: str
    test_id: str
    score: float
    num_correct: int
    num_total: int
    answers: List[dict]
    created_at: str


@router.post("/generate", response_model=TestResponse)
async def generate_test(request: GenerateTestRequest, current_user: dict = Depends(get_current_user)):
    # Support both scan_id lookup and direct content_text
    content_text = request.content_text
    scan_id = request.scan_id or "direct"
    topics = request.topics or []

    if not content_text and request.scan_id:
        scans_collection = get_scans_collection()
        scan = await scans_collection.find_one({"_id": request.scan_id, "user_id": current_user["_id"]})
        if not scan:
            raise HTTPException(status_code=404, detail="Scan not found")
        content_text = scan["content_text"]
        scan_id = request.scan_id

    if not content_text:
        raise HTTPException(status_code=400, detail="No content provided. Upload a photo or PDF first.")

    questions = await ai_stub.generate_questions(
        content_text=content_text,
        test_type=request.test_type,
        difficulty=request.difficulty,
        num_questions=request.num_questions,
        topics=topics,
        additional_prompts=request.additional_prompts,
    )

    tests_collection = get_tests_collection()
    test = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_id": scan_id,
        "test_name": request.test_name,
        "test_type": request.test_type,
        "difficulty": request.difficulty,
        "questions": questions,
        "is_completed": False,
        "score": None,
        "additional_prompts": request.additional_prompts,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    await tests_collection.insert_one(test)

    return TestResponse(
        id=test["_id"],
        user_id=test["user_id"],
        scan_id=test["scan_id"],
        test_name=test["test_name"],
        test_type=test["test_type"],
        difficulty=test["difficulty"],
        questions=test["questions"],
        is_completed=test["is_completed"],
        score=test["score"],
        created_at=test["created_at"]
    )


@router.get("", response_model=List[TestResponse])
async def get_all_tests(current_user: dict = Depends(get_current_user)):
    tests_collection = get_tests_collection()
    tests = await tests_collection.find(
        {"user_id": current_user["_id"]}
    ).sort("created_at", -1).to_list(None)

    return [
        TestResponse(
            id=test["_id"],
            user_id=test["user_id"],
            scan_id=test["scan_id"],
            test_name=test["test_name"],
            test_type=test["test_type"],
            difficulty=test["difficulty"],
            questions=test["questions"],
            is_completed=test["is_completed"],
            score=test.get("score"),
            created_at=test["created_at"]
        )
        for test in tests
    ]


@router.get("/{test_id}", response_model=TestResponse)
async def get_test(test_id: str, current_user: dict = Depends(get_current_user)):
    tests_collection = get_tests_collection()
    test = await tests_collection.find_one({"_id": test_id, "user_id": current_user["_id"]})

    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    return TestResponse(
        id=test["_id"],
        user_id=test["user_id"],
        scan_id=test["scan_id"],
        test_name=test["test_name"],
        test_type=test["test_type"],
        difficulty=test["difficulty"],
        questions=test["questions"],
        is_completed=test["is_completed"],
        score=test.get("score"),
        created_at=test["created_at"]
    )


@router.delete("/{test_id}")
async def delete_test(test_id: str, current_user: dict = Depends(get_current_user)):
    tests_collection = get_tests_collection()
    result = await tests_collection.delete_one({"_id": test_id, "user_id": current_user["_id"]})

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Test not found")

    results_collection = get_results_collection()
    await results_collection.delete_many({"test_id": test_id})

    return {"message": "Test deleted successfully"}


@router.post("/{test_id}/reset")
async def reset_test(test_id: str, current_user: dict = Depends(get_current_user)):
    tests_collection = get_tests_collection()
    result = await tests_collection.update_one(
        {"_id": test_id, "user_id": current_user["_id"]},
        {
            "$set": {
                "is_completed": False,
                "score": None,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Test not found")

    return {"message": "Test reset successfully"}


@router.post("/submit", response_model=ResultResponse)
async def submit_test(request: SubmitTestRequest, current_user: dict = Depends(get_current_user)):
    tests_collection = get_tests_collection()
    test = await tests_collection.find_one({"_id": request.test_id, "user_id": current_user["_id"]})

    if not test:
        raise HTTPException(status_code=404, detail="Test not found")

    num_correct = 0
    num_total = len(test["questions"])
    answers_detail = []

    for answer_item in request.answers:
        question = next((q for q in test["questions"] if q["id"] == answer_item.question_id), None)

        if not question:
            continue

        is_correct = ai_stub.grade_answer(question, answer_item.answer)
        if is_correct:
            num_correct += 1

        answers_detail.append({
            "question_id": answer_item.question_id,
            "user_answer": answer_item.answer,
            "correct_answer": question.get("correct_answer"),
            "is_correct": is_correct
        })

    score = (num_correct / num_total * 100) if num_total > 0 else 0

    results_collection = get_results_collection()
    result = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "test_id": request.test_id,
        "score": score,
        "num_correct": num_correct,
        "num_total": num_total,
        "answers": answers_detail,
        "created_at": datetime.utcnow().isoformat()
    }

    await results_collection.insert_one(result)

    await tests_collection.update_one(
        {"_id": request.test_id},
        {
            "$set": {
                "is_completed": True,
                "score": score,
                "updated_at": datetime.utcnow().isoformat()
            }
        }
    )

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
