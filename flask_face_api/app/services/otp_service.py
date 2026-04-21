import random
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from loguru import logger

from app.config import Config
from app.db.mysql import mysql_cursor
from app.services.bcrypt_service import hash_password, verify_password

OTP_EXPIRY_MINUTES = 10


def send_email(recipient_email, otp):
    try:
        subject = "Your Glueck OTP Code"
        body = f"""
        <p>Hello,</p>
        <p>Your verification code is:</p>
        <h2 style="color:#333;">{otp}</h2>
        <p>This code will expire in 10 minutes.</p>
        <br/>
        <p>- Glueck Tech Team</p>
        """

        msg = MIMEMultipart()
        msg["From"] = f"{Config.FROM_NAME} <{Config.FROM_EMAIL}>"
        msg["To"] = recipient_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "html"))

        with smtplib.SMTP_SSL(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.sendmail(Config.FROM_EMAIL, recipient_email, msg.as_string())

        logger.info("OTP sent successfully to {}", recipient_email)
        return True
    except Exception as exc:
        logger.error("Failed to send OTP to {}: {}", recipient_email, exc)
        return False


def generate_and_store_otp(email):
    try:
        otp = str(random.randint(100000, 999999))
        otp_hash = hash_password(otp)
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

        with mysql_cursor() as (conn, cursor):
            cursor.execute("DELETE FROM otps WHERE email = %s", (email,))
            cursor.execute(
                "INSERT INTO otps (email, otp_code, expires_at) VALUES (%s, %s, %s)",
                (email, otp_hash, expires_at),
            )
            conn.commit()

        if send_email(email, otp):
            logger.info("Successfully generated and sent OTP to {}", email)
            return True

        logger.error("Failed to send OTP email to {}", email)
        return False
    except Exception as exc:
        logger.error("Error in generate_and_store_otp for {}: {}", email, exc)
        return False


def verify_otp(email, otp_provided):
    try:
        with mysql_cursor(dictionary=True) as (conn, cursor):
            cursor.execute(
                "SELECT otp_code, expires_at FROM otps WHERE email = %s ORDER BY created_at DESC LIMIT 1",
                (email,),
            )
            otp_record = cursor.fetchone()

            if not otp_record:
                logger.warning("Verification failed: no OTP found for {}", email)
                return False

            if datetime.utcnow() > otp_record["expires_at"]:
                logger.warning("Verification failed: OTP for {} has expired", email)
                return False

            if not verify_password(otp_provided, otp_record["otp_code"]):
                logger.warning("Verification failed: invalid OTP for {}", email)
                return False

            cursor.execute("DELETE FROM otps WHERE email = %s", (email,))
            conn.commit()

        logger.info("Successfully verified OTP for {}", email)
        return True
    except Exception as exc:
        logger.error("Error in verify_otp for {}: {}", email, exc)
        return False
