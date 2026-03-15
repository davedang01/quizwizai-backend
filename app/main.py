import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .database import connect_to_mongo, close_mongo_connection
from .routers import auth, scan, tests, results, progress, flashcards, study_guides, tutor


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongo()
    yield
    await close_mongo_connection()


app = FastAPI(
    title="Quiz Wiz AI",
    description="AI-powered study app backend",
    version="1.0.0",
    lifespan=lifespan
)

# Allow Netlify frontend + local dev origins
allowed_origins = os.environ.get(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in allowed_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(scan.router)
app.include_router(tests.router)
app.include_router(results.router)
app.include_router(progress.router)
app.include_router(flashcards.router)
app.include_router(study_guides.router)
app.include_router(tutor.router)


@app.get("/health")
async def health_check():
    return {"status": "healthy"}
