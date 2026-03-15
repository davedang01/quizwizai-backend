from motor.motor_asyncio import AsyncIOMotorClient
from .config import get_settings

settings = get_settings()

client = None
db = None


async def connect_to_mongo():
    global client, db
    client = AsyncIOMotorClient(settings.mongo_url)
    db = client[settings.db_name]

    await db.command("ping")
    print("Connected to MongoDB")


async def close_mongo_connection():
    global client
    if client:
        client.close()
        print("Closed MongoDB connection")


async def get_db():
    return db


def get_users_collection():
    return db["users"]


def get_user_sessions_collection():
    return db["user_sessions"]


def get_scans_collection():
    return db["scans"]


def get_tests_collection():
    return db["tests"]


def get_results_collection():
    return db["results"]


def get_flashcards_collection():
    return db["flashcards"]


def get_study_guides_collection():
    return db["study_guides"]


def get_homework_sessions_collection():
    return db["homework_sessions"]
