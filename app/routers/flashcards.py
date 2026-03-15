from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import uuid
from datetime import datetime
from ..database import get_flashcards_collection, get_scans_collection
from ..dependencies import get_current_user
from ..services.ai_stub import generate_flashcards

router = APIRouter(prefix="/api/flashcards", tags=["flashcards"])


class FlashcardCard(BaseModel):
    front: str
    back: str


class GenerateFlashcardsRequest(BaseModel):
    scan_id: str
    deck_name: str
    num_cards: int
    additional_prompts: Optional[str] = None


class ManualFlashcardsRequest(BaseModel):
    deck_name: str
    cards: List[FlashcardCard]


class FlashcardResponse(BaseModel):
    id: str
    user_id: str
    scan_id: str
    deck_name: str
    cards: List[dict]
    total_cards: int
    timestamp: str


@router.post("/generate", response_model=FlashcardResponse)
async def generate_flashcard_deck(
    request: GenerateFlashcardsRequest,
    current_user: dict = Depends(get_current_user)
):
    scans_collection = get_scans_collection()
    scan = await scans_collection.find_one({
        "_id": request.scan_id,
        "user_id": current_user["_id"]
    })

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    if request.num_cards < 5 or request.num_cards > 30:
        raise HTTPException(status_code=400, detail="num_cards must be between 5 and 30")

    cards_data = await generate_flashcards(
        scan.get("content_text", ""),
        request.num_cards,
        request.additional_prompts
    )

    deck = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_id": request.scan_id,
        "deck_name": request.deck_name,
        "cards": [
            {
                "id": f"c{i}",
                "front": card["front"],
                "back": card["back"]
            }
            for i, card in enumerate(cards_data)
        ],
        "total_cards": len(cards_data),
        "timestamp": datetime.utcnow().isoformat()
    }

    flashcards_collection = get_flashcards_collection()
    await flashcards_collection.insert_one(deck)

    return FlashcardResponse(
        id=deck["_id"],
        user_id=deck["user_id"],
        scan_id=deck["scan_id"],
        deck_name=deck["deck_name"],
        cards=deck["cards"],
        total_cards=deck["total_cards"],
        timestamp=deck["timestamp"]
    )


@router.post("/manual")
async def create_manual_flashcards(
    request: ManualFlashcardsRequest,
    current_user: dict = Depends(get_current_user)
):
    deck = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "scan_id": "manual",
        "deck_name": request.deck_name,
        "cards": [
            {
                "id": f"c{i}",
                "front": card.front,
                "back": card.back
            }
            for i, card in enumerate(request.cards)
        ],
        "total_cards": len(request.cards),
        "timestamp": datetime.utcnow().isoformat()
    }

    flashcards_collection = get_flashcards_collection()
    await flashcards_collection.insert_one(deck)

    return {
        "id": deck["_id"],
        "message": "Flashcard deck created successfully"
    }


@router.get("/", response_model=List[FlashcardResponse])
async def get_all_flashcards(current_user: dict = Depends(get_current_user)):
    flashcards_collection = get_flashcards_collection()
    decks = await flashcards_collection.find({
        "user_id": current_user["_id"]
    }).sort("timestamp", -1).to_list(None)

    return [
        FlashcardResponse(
            id=deck["_id"],
            user_id=deck["user_id"],
            scan_id=deck["scan_id"],
            deck_name=deck["deck_name"],
            cards=deck["cards"],
            total_cards=deck["total_cards"],
            timestamp=deck["timestamp"]
        )
        for deck in decks
    ]


@router.get("/{deck_id}", response_model=FlashcardResponse)
async def get_flashcard_deck(
    deck_id: str,
    current_user: dict = Depends(get_current_user)
):
    flashcards_collection = get_flashcards_collection()
    deck = await flashcards_collection.find_one({
        "_id": deck_id,
        "user_id": current_user["_id"]
    })

    if not deck:
        raise HTTPException(status_code=404, detail="Flashcard deck not found")

    return FlashcardResponse(
        id=deck["_id"],
        user_id=deck["user_id"],
        scan_id=deck["scan_id"],
        deck_name=deck["deck_name"],
        cards=deck["cards"],
        total_cards=deck["total_cards"],
        timestamp=deck["timestamp"]
    )


@router.delete("/{deck_id}")
async def delete_flashcard_deck(
    deck_id: str,
    current_user: dict = Depends(get_current_user)
):
    flashcards_collection = get_flashcards_collection()
    result = await flashcards_collection.delete_one({
        "_id": deck_id,
        "user_id": current_user["_id"]
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Flashcard deck not found")

    return {"message": "Flashcard deck deleted successfully"}
