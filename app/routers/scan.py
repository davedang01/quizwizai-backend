from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List
import uuid
from datetime import datetime
from ..database import get_scans_collection
from ..dependencies import get_current_user
from ..services import ai_stub

router = APIRouter(prefix="/api/scan", tags=["scan"])


class AnalyzeImagesRequest(BaseModel):
    images_base64: List[str]


class AnalyzePdfRequest(BaseModel):
    pdf_base64: str
    filename: str


class ScanResponse(BaseModel):
    id: str
    user_id: str
    content_text: str
    subject: str
    topics: List[str]
    difficulty: str
    num_pages: int
    created_at: str


@router.get("/{scan_id}", response_model=ScanResponse)
async def get_scan(scan_id: str, current_user: dict = Depends(get_current_user)):
    """Fetch a previously saved scan analysis by ID."""
    scans_collection = get_scans_collection()
    scan = await scans_collection.find_one({"_id": scan_id, "user_id": current_user["_id"]})

    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    return ScanResponse(
        id=scan["_id"],
        user_id=scan["user_id"],
        content_text=scan["content_text"],
        subject=scan["subject"],
        topics=scan["topics"],
        difficulty=scan["difficulty"],
        num_pages=scan["num_pages"],
        created_at=scan["created_at"]
    )


@router.post("/analyze", response_model=ScanResponse)
async def analyze_images_endpoint(request: AnalyzeImagesRequest, current_user: dict = Depends(get_current_user)):
    if not request.images_base64:
        raise HTTPException(status_code=400, detail="No images provided")

    # Use Vision API to properly analyze the images
    analysis = await ai_stub.analyze_images(request.images_base64)

    # If analysis failed, return an error instead of saving garbage content
    if analysis.get("analysis_failed"):
        raise HTTPException(
            status_code=422,
            detail="We couldn't read the uploaded image(s). Please try again with a clearer photo or ensure the image contains readable text/content."
        )

    scans_collection = get_scans_collection()
    scan = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "content_text": analysis["content_text"],
        "subject": analysis["subject"],
        "topics": analysis["topics"],
        "difficulty": analysis["difficulty"],
        "num_pages": analysis["num_pages"],
        "source_type": "images",
        "num_source_files": len(request.images_base64),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    await scans_collection.insert_one(scan)

    return ScanResponse(
        id=scan["_id"],
        user_id=scan["user_id"],
        content_text=scan["content_text"],
        subject=scan["subject"],
        topics=scan["topics"],
        difficulty=scan["difficulty"],
        num_pages=scan["num_pages"],
        created_at=scan["created_at"]
    )


@router.post("/analyze-pdf", response_model=ScanResponse)
async def analyze_pdf(request: AnalyzePdfRequest, current_user: dict = Depends(get_current_user)):
    if not request.pdf_base64:
        raise HTTPException(status_code=400, detail="No PDF provided")

    analysis = await ai_stub.analyze_content(request.pdf_base64)

    # If analysis failed, return an error instead of saving garbage content
    if analysis.get("analysis_failed"):
        raise HTTPException(
            status_code=422,
            detail="We couldn't read the uploaded PDF. Please try again with a different file or ensure it contains readable text."
        )

    scans_collection = get_scans_collection()
    scan = {
        "_id": str(uuid.uuid4()),
        "user_id": current_user["_id"],
        "content_text": analysis["content_text"],
        "subject": analysis["subject"],
        "topics": analysis["topics"],
        "difficulty": analysis["difficulty"],
        "num_pages": analysis["num_pages"],
        "source_type": "pdf",
        "filename": request.filename,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    await scans_collection.insert_one(scan)

    return ScanResponse(
        id=scan["_id"],
        user_id=scan["user_id"],
        content_text=scan["content_text"],
        subject=scan["subject"],
        topics=scan["topics"],
        difficulty=scan["difficulty"],
        num_pages=scan["num_pages"],
        created_at=scan["created_at"]
    )
