import base64

import cv2
import face_recognition
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from runtime import get_logger

LOGGER = get_logger(__name__, "logs/face-utils.log")


def base64_to_image(base64_str):
    img_data = base64.b64decode(base64_str)
    img_array = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(img_array, cv2.IMREAD_COLOR)


def image_to_base64(image):
    _, buffer = cv2.imencode(".jpg", image)
    return base64.b64encode(buffer).decode("utf-8")


def validate_image(img):
    if img is None:
        return False, "Invalid image or base64 input."
    if img.shape[0] < 160 or img.shape[1] < 160:
        return False, "Image too small. Minimum size is 160x160 pixels."
    if img.shape[0] > 1024 or img.shape[1] > 1024:
        return False, "Image too large. Maximum size is 1024x1024 pixels."
    return True, None


def extract_aligned_face(image_bgr):
    if image_bgr is None:
        return "Invalid image input."

    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb)
    if not boxes:
        return "No face detected."

    top, right, bottom, left = boxes[0]
    face = image_bgr[top:bottom, left:right]
    if face.size == 0:
        return "Detected face crop was empty."

    return cv2.resize(face, (160, 160))


def get_face_embedding(face_image):
    if face_image is None:
        return None

    rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)
    if not encodings:
        return None
    return encodings[0]


def compare_faces(new_face, registered_face, threshold=0.6):
    try:
        similarity = cosine_similarity([new_face], [registered_face])[0][0]
        is_match = similarity > threshold
        LOGGER.debug("Compared embeddings with similarity %.4f", similarity)
        return similarity, is_match
    except Exception as exc:
        LOGGER.error("Failed to compare faces: %s", exc)
        return None, False
