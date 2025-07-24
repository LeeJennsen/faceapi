from pymongo import MongoClient
from app.config import Config

client = MongoClient(Config.MONGO_URI)
db = client.face_metadata

def init_mongo(app=None):
    try:
        client = MongoClient(Config.MONGO_URI)
        db = client.face_metadata
        print("MongoDB connected")
        return db
    except Exception as e:
        print("MongoDB connection failed:", e)
        raise

def get_face_collection():
    return db.face_data
