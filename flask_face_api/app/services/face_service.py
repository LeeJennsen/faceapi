from app.db.mongo import get_face_collection
from datetime import datetime
from loguru import logger

def process_face_metadata(payload):
    data = payload.dict()
    data["server_received_time"] = datetime.utcnow().isoformat()
    face_collection = get_face_collection()

    try:
        result = face_collection.insert_one(data)
        logger.info(f"Inserted document with ID: {result.inserted_id}")
    except Exception as e:
        logger.error(f"MongoDB insertion failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "face_unique_id": payload.face_unique_id
        }

    return {
        "status": "processed",
        "inserted_id": str(result.inserted_id),
        "device_id": payload.device_id,
        "face_unique_id": payload.face_unique_id,
        "detections": [
            {
                "track_id": d.track_id,
                "emotion": d.emotion,
                "confidence": d.confidence,
                "location": d.location
            } for d in payload.detections
        ]
    }
