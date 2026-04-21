from threading import Lock

from loguru import logger
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import Config

_client = None
_db = None
_mongo_lock = Lock()


def get_mongo_client() -> MongoClient:
    global _client
    if _client is None:
        with _mongo_lock:
            if _client is None:
                _client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
                logger.info("MongoDB client initialized")
    return _client


def get_mongo_db():
    global _db
    if _db is None:
        client = get_mongo_client()
        _db = client[Config.MONGO_DB_NAME]
    return _db


def init_mongo(app=None):
    try:
        db = get_mongo_db()
        if app is not None:
            app.extensions["mongo_db"] = db
        logger.info("MongoDB integration ready")
        return db
    except PyMongoError as exc:
        logger.error("MongoDB initialization failed: {}", exc)
        raise


def get_face_collection():
    return get_mongo_db().face_data
