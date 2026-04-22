import json
import os
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.mongo import get_face_collection
from app.db.mysql import mysql_cursor
from app.services.bcrypt_service import hash_password

DEMO_USER_EMAIL = os.getenv("DEMO_ADMIN_EMAIL", "admin@faceapi2.local")
DEMO_USER_PASSWORD = os.getenv("DEMO_ADMIN_PASSWORD", "admin12345")
DEMO_USER_NAME = os.getenv("DEMO_ADMIN_NAME", "Local Demo Admin")
DEMO_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9WlH0n8AAAAASUVORK5CYII="
)


def seed_demo_user() -> None:
    with mysql_cursor() as (conn, cursor):
        cursor.execute("SELECT id FROM users WHERE email=%s", (DEMO_USER_EMAIL,))
        existing = cursor.fetchone()
        if existing:
            cursor.execute(
                """
                UPDATE users
                SET name=%s, role='Admin', password=%s
                WHERE email=%s
                """,
                (DEMO_USER_NAME, hash_password(DEMO_USER_PASSWORD), DEMO_USER_EMAIL),
            )
        else:
            cursor.execute(
                """
                INSERT INTO users (name, email, password, role)
                VALUES (%s, %s, %s, 'Admin')
                """,
                (DEMO_USER_NAME, DEMO_USER_EMAIL, hash_password(DEMO_USER_PASSWORD)),
            )
        conn.commit()


def reset_demo_rows() -> None:
    with mysql_cursor() as (conn, cursor):
        cursor.execute("DELETE FROM face_tracking WHERE unique_id LIKE 'demo-%'")
        cursor.execute("DELETE FROM face_persons WHERE unique_id LIKE 'demo-%'")
        conn.commit()

    get_face_collection().delete_many({"face_unique_id": {"$regex": r"^demo-"}})


def seed_mysql_records() -> None:
    people = [
        ("demo-alice", "Alice Tan"),
        ("demo-bala", "Bala Kumar"),
        ("demo-chloe", "Chloe Lim"),
        ("demo-daniel", "Daniel Ong"),
        ("demo-eva", "Eva Lee"),
    ]
    now = datetime.utcnow()
    cameras = ["cam-lobby-1", "cam-retail-2", "cam-atrium-3"]

    with mysql_cursor() as (conn, cursor):
        for index, (unique_id, label) in enumerate(people, start=1):
            cursor.execute(
                """
                INSERT INTO face_persons (unique_id, images_json, embedding, label, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    unique_id,
                    json.dumps([DEMO_IMAGE]),
                    json.dumps([round(index * 0.11, 4), round(index * 0.19, 4), round(index * 0.07, 4)]),
                    label,
                    now - timedelta(days=index),
                ),
            )

        for index in range(1, 31):
            unique_id, _ = random.choice(people)
            timestamp = now - timedelta(
                days=random.randint(0, 9),
                hours=random.randint(0, 20),
                minutes=random.randint(0, 55),
            )
            cursor.execute(
                """
                INSERT INTO face_tracking (
                    track_id, unique_id, image_base64, embedding,
                    timestamp, camera_id, custom_track_key
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    f"demo-track-{index:03d}",
                    unique_id,
                    DEMO_IMAGE,
                    json.dumps([round(index * 0.03, 4), round(index * 0.05, 4), round(index * 0.07, 4)]),
                    timestamp,
                    random.choice(cameras),
                    f"demo-custom-{index:03d}",
                ),
            )
        conn.commit()


def seed_mongo_records() -> None:
    collection = get_face_collection()
    now = datetime.utcnow()
    locations = ["Lobby", "Cafe", "Retail Zone", "Lift Hall"]
    emotions = ["Happy", "Neutral", "Surprised", "Focused"]
    ages = ["18-24", "25-34", "35-44", "45-54"]
    genders = ["Male", "Female"]
    cameras = ["cam-lobby-1", "cam-retail-2", "cam-atrium-3"]
    devices = ["edge-01", "edge-02"]
    identities = ["demo-alice", "demo-bala", "demo-chloe", "demo-daniel", "demo-eva"]

    documents = []
    for index in range(1, 19):
        start_time = now - timedelta(
            days=random.randint(0, 9),
            hours=random.randint(0, 18),
            minutes=random.randint(0, 50),
        )
        if index <= 6:
            start_time = now - timedelta(minutes=index * 7)

        detection_count = random.randint(1, 3)
        detections = []
        for inner in range(detection_count):
            detections.append(
                {
                    "track_id": f"demo-live-{index:03d}-{inner}",
                    "object_type": "face",
                    "bounding_box": {"x": 0.2, "y": 0.15, "width": 0.25, "height": 0.25},
                    "confidence": round(random.uniform(0.86, 0.99), 2),
                    "gender": random.choice(genders),
                    "age": random.choice(ages),
                    "emotion": random.choice(emotions),
                    "attention_time": round(random.uniform(3.5, 18.0), 1),
                    "length_of_stay": round(random.uniform(12.0, 160.0), 1),
                    "location": random.choice(locations),
                    "frame_reference": index * 10 + inner,
                    "face_quality_score": round(random.uniform(0.78, 0.98), 2),
                }
            )

        documents.append(
            {
                "device_id": random.choice(devices),
                "face_unique_id": random.choice(identities),
                "start_timestamp": start_time.isoformat(),
                "end_timestamp": (start_time + timedelta(seconds=30)).isoformat(),
                "camera_id": random.choice(cameras),
                "detections": detections,
                "server_received_time": datetime.utcnow().isoformat(),
            }
        )

    if documents:
        collection.insert_many(documents)


if __name__ == "__main__":
    random.seed(42)
    reset_demo_rows()
    seed_demo_user()
    seed_mysql_records()
    seed_mongo_records()
    print("Demo data seeded successfully.")
    print(f"Demo admin email: {DEMO_USER_EMAIL}")
    print(f"Demo admin password: {DEMO_USER_PASSWORD}")
