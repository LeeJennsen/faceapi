from pydantic import BaseModel, Field
from typing import List


class BoundingBox(BaseModel):
    x: float
    y: float
    width: float
    height: float


class DetectionMetadata(BaseModel):
    track_id: str
    object_type: str
    bounding_box: BoundingBox
    confidence: float
    gender: str
    age: str
    emotion: str
    attention_time: float
    length_of_stay: float
    location: str
    frame_reference: int
    face_quality_score: float


class FacePayload(BaseModel):
    device_id: str
    face_unique_id: str
    start_timestamp: str
    end_timestamp: str
    camera_id: str
    detections: List[DetectionMetadata]

