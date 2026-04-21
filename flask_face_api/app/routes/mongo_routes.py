from flask_restx import Namespace, Resource
from app.services.face_service import process_face_metadata
from app.db.mongo import get_face_collection
from app.utils.validators import FacePayload
from loguru import logger
from flask_pydantic import validate

mongo_ns = Namespace('faces-mongo', description='Face data operations (MongoDB)')

@mongo_ns.route('/')
class FaceMetadataResource(Resource):
    @validate()
    def post(self, body: FacePayload):
        try:
            payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
            logger.info(f"Received data: {payload}")
            result = process_face_metadata(body)
            return {"message": "Data processed successfully", "result": result}, 200
        except Exception as e:
            logger.error(f"Validation/Processing error: {e}")
            return {"error": str(e)}, 400

    def get(self):
        try:
            collection = get_face_collection()
            records = list(collection.find({}, {"_id": 0}))
            return {"message": "Fetched face data", "data": records}, 200
        except Exception as e:
            logger.error(f"MongoDB fetch error: {e}")
            return {"error": str(e)}, 500
