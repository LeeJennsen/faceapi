from flask_restx import Namespace, Resource, fields
from flask import request
from app.services.face_service import process_face_metadata
from app.db.mongo import init_mongo
from app.utils.validators import FacePayload
from loguru import logger
from flask_pydantic import validate

mongo_ns = Namespace('faces-mongo', description='Face data operations (MongoDB)')
db = init_mongo()
collection = db.face_data

@mongo_ns.route('/')
class FaceMetadataResource(Resource):
    @validate()
    def post(self, body: FacePayload):
        try:
            logger.info(f"Received data: {body.dict()}")
            result = process_face_metadata(body)
            return {"message": "Data processed successfully", "result": result}, 200
        except Exception as e:
            logger.error(f"Validation/Processing error: {e}")
            return {"error": str(e)}, 400

    def get(self):
        try:
            records = list(collection.find({}, {"_id": 0}))
            return {"message": "Fetched face data", "data": records}, 200
        except Exception as e:
            logger.error(f"MongoDB fetch error: {e}")
            return {"error": str(e)}, 500

