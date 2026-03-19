from fastapi import APIRouter, Depends
from pydantic import BaseModel
from typing import List
from datetime import datetime, timedelta
from ..database import get_tests_collection, get_scans_collection, get_results_collection
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/progress", tags=["progress"])


class RecentResult(BaseModel):
    test_id: str
    test_name: str
    score: float
    created_at: str


class Badge(BaseModel):
    id: str
    name: str
    description: str
    earned_at: str


class ProgressStats(BaseModel):
    total_tests: int
    tests_created: int
    avg_score: float
    total_scans: int
    streak_days: int
    badges: List[Badge]
    recent_results: List[RecentResult]


@router.get("/stats", response_model=ProgressStats)
async def get_progress_stats(current_user: dict = Depends(get_current_user)):
    user_id = current_user["_id"]

    tests_collection = get_tests_collection()
    scans_collection = get_scans_collection()
    results_collection = get_results_collection()

    completed_tests = await tests_collection.find(
        {"user_id": user_id, "is_completed": True}
    ).to_list(None)

    total_tests = len(completed_tests)

    # Total tests created (completed + pending)
    tests_created = await tests_collection.count_documents({"user_id": user_id})

    results = await results_collection.find(
        {"user_id": user_id}
    ).sort("created_at", -1).to_list(None)

    scores = [r["score"] for r in results]
    avg_score = sum(scores) / len(scores) if scores else 0

    recent_results = []
    tests_by_id = {t["_id"]: t for t in completed_tests}

    for result in results[:10]:
        test = tests_by_id.get(result["test_id"])
        if test:
            recent_results.append(RecentResult(
                test_id=result["test_id"],
                test_name=test["test_name"],
                score=result["score"],
                created_at=result["created_at"]
            ))

    total_scans = await scans_collection.count_documents({"user_id": user_id})

    activity_dates = set()
    for result in results:
        created_at = datetime.fromisoformat(result["created_at"])
        activity_dates.add(created_at.date())

    for test in completed_tests:
        created_at = datetime.fromisoformat(test["created_at"])
        activity_dates.add(created_at.date())

    streak_days = 0
    if activity_dates:
        sorted_dates = sorted(activity_dates, reverse=True)
        today = datetime.utcnow().date()

        for i, date in enumerate(sorted_dates):
            expected_date = today - timedelta(days=i)
            if date == expected_date:
                streak_days += 1
            else:
                break

    badges = []
    if total_tests >= 1:
        badges.append(Badge(
            id="first_test",
            name="First Test",
            description="Completed your first test",
            earned_at=results[0]["created_at"] if results else datetime.utcnow().isoformat()
        ))

    if total_tests >= 5:
        badges.append(Badge(
            id="test_master",
            name="Test Master",
            description="Completed 5 tests",
            earned_at=results[4]["created_at"] if len(results) > 4 else datetime.utcnow().isoformat()
        ))

    if avg_score >= 80:
        badges.append(Badge(
            id="high_scorer",
            name="High Scorer",
            description="Achieved average score of 80% or higher",
            earned_at=datetime.utcnow().isoformat()
        ))

    if streak_days >= 3:
        badges.append(Badge(
            id="streak_warrior",
            name="Streak Warrior",
            description="Maintained a 3-day activity streak",
            earned_at=datetime.utcnow().isoformat()
        ))

    return ProgressStats(
        total_tests=total_tests,
        tests_created=tests_created,
        avg_score=round(avg_score, 2),
        total_scans=total_scans,
        streak_days=streak_days,
        badges=badges,
        recent_results=recent_results
    )
