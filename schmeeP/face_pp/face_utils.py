import numpy as np
import cv2
from mtcnn import MTCNN
import base64
from dotenv import load_dotenv
import os
from sklearn.metrics.pairwise import cosine_similarity
detector = MTCNN()


# Load Haar cascade classifier for face detection
face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

#load environment variables
load_dotenv()


def base64_to_image(base64_str):
    """
    Convert a base64 string to an OpenCV image.
    
    Args:
        base64_str (str): Base64 encoded image string
        
    Returns:
        numpy.ndarray: OpenCV image object
    """
    img_data = base64.b64decode(base64_str)
    img_array = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    return img


def image_to_base64(image):
    """
    Convert an OpenCV image to base64 string.
    
    Args:
        image (numpy.ndarray): OpenCV image object
        
    Returns:
        str: Base64 encoded image string
    """
    _, buffer = cv2.imencode('.jpg', image)
    b64_str = base64.b64encode(buffer).decode('utf-8')
    return b64_str


def validate_image(img):
    """
    Validate image for face recognition:
    - Check if image is valid
    - Check if image dimensions are within acceptable range
    - Check if a face is present in the image
    
    Args:
        img (numpy.ndarray): OpenCV image object
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if img is None:
        return False, 'Invalid image or base64 input.'
    if img.shape[0] < 160 or img.shape[1] < 160:
        return False, 'Image too small. Minimum size is 160x160 pixels.'
    if img.shape[0] > 1024 or img.shape[1] > 1024:
        return False, 'Image too large. Maximum size is 1024x1024 pixels.'
    # if not is_face_present(img):
    #     return False, 'No face detected in the image.'
    return True, None


# def is_face_present(image):
#     """
#     Check if at least one face is present in the image.
    
#     Args:
#         image (numpy.ndarray): OpenCV image object
        
#     Returns:
#         bool: True if at least one face is detected, False otherwise
#     """
#     gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#     faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
#     return len(faces) > 0


def align_face(image, keypoints, desired_left_eye=(0.35, 0.35), desired_face_width=160, desired_face_height=160):
    """
    Aligns face image based on eyes position.
    Args:
        image: RGB image
        keypoints: dict with 'left_eye' and 'right_eye' (x, y)
        desired_left_eye: tuple, relative position of left eye in output aligned image
        desired_face_width: int, width of output face
        desired_face_height: int, height of output face
    Returns:
        aligned face image (RGB)
    """

    left_eye = keypoints['left_eye']
    right_eye = keypoints['right_eye']

    # Compute the angle between the eye centroids
    dY = right_eye[1] - left_eye[1]
    dX = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dY, dX))

    # Compute the desired right eye x-coordinate based on desired left eye x
    desired_right_eye_x = 1.0 - desired_left_eye[0]

    # Compute the scale of the new face
    dist = np.sqrt((dX ** 2) + (dY ** 2))
    desired_dist = (desired_right_eye_x - desired_left_eye[0]) * desired_face_width
    scale = desired_dist / dist

    # Compute center between eyes
    eyes_center = ((left_eye[0] + right_eye[0]) / 2,
                   (left_eye[1] + right_eye[1]) / 2)

    # Get rotation matrix for the desired angle & scale
    M = cv2.getRotationMatrix2D(eyes_center, angle, scale)

    # Update translation component of the matrix
    tX = desired_face_width * 0.5
    tY = desired_face_height * desired_left_eye[1]
    M[0, 2] += (tX - eyes_center[0])
    M[1, 2] += (tY - eyes_center[1])

    # Apply affine transformation
    aligned_face = cv2.warpAffine(image, M, (desired_face_width, desired_face_height), flags=cv2.INTER_CUBIC)

    return aligned_face


import face_recognition

def extract_aligned_face(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb)

    if not boxes:
        return False, 'No face detected.'

    top, right, bottom, left = boxes[0]  # first face only
    face = rgb[top:bottom, left:right]
    face_resized = cv2.resize(face, (160, 160))
    return face_resized

def get_face_embedding(face_image):
    rgb = cv2.cvtColor(face_image, cv2.COLOR_BGR2RGB)
    encodings = face_recognition.face_encodings(rgb)

    if not encodings:
        return None
    return encodings[0]


def compare_faces(new_face, registered_face, threshold=0.6):
    try:
        emb1, emb2 = new_face, registered_face
        similarity = cosine_similarity([emb1], [emb2])[0][0]
        is_match = similarity > threshold

        print(f"Similarity: {similarity:.4f}")
        print("Match!" if is_match else "No match.")
        return similarity, is_match
    except Exception as e:
        print(f"Error: {e}")
        return None, False
