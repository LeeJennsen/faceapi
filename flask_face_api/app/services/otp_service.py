import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from app.db.mysql import get_mysql_connection
from app.services.bcrypt_service import hash_password, verify_password
from loguru import logger


# --- Configuration ---
OTP_EXPIRY_MINUTES = 10

SMTP_SERVER = os.getenv("SMTP_SERVER")
SMTP_PORT = int(os.getenv("SMTP_PORT", 465))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL")
FROM_NAME = os.getenv("FROM_NAME")

def send_email(recipient_email, otp):
    try:
        subject = "Your Glueck OTP Code"
        body = f"""
        <p>Hello,</p>
        <p>Your verification code is:</p>
        <h2 style="color:#333;">{otp}</h2>
        <p>This code will expire in 10 minutes.</p>
        <br/>
        <p>— Glueck Tech Team</p>
        """

        msg = MIMEMultipart()
        msg['From'] = f"{FROM_NAME} <{FROM_EMAIL}>"
        msg['To'] = recipient_email
        msg['Subject'] = subject

        msg.attach(MIMEText(body, 'html'))

        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.sendmail(FROM_EMAIL, recipient_email, msg.as_string())

        logger.info(f"OTP sent successfully to {recipient_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send OTP to {recipient_email}: {e}")
        return False

def generate_and_store_otp(email):
    """
    Generates a 6-digit OTP, hashes it, and stores it in the database.
    """
    try:
        otp = str(random.randint(100000, 999999))
        otp_hash = hash_password(otp)
        expires_at = datetime.utcnow() + timedelta(minutes=OTP_EXPIRY_MINUTES)

        conn = get_mysql_connection()
        cursor = conn.cursor()

        # Remove any previous OTPs for this email to avoid conflicts
        cursor.execute("DELETE FROM otps WHERE email = %s", (email,))

        # Insert the new OTP
        cursor.execute(
            "INSERT INTO otps (email, otp_code, expires_at) VALUES (%s, %s, %s)",
            (email, otp_hash, expires_at)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Send the email with the plain OTP
        if send_email(email, otp):
            logger.info(f"Successfully generated and sent OTP to {email}")
            return True
        else:
            logger.error(f"Failed to send OTP email to {email}")
            return False

    except Exception as e:
        logger.error(f"Error in generate_and_store_otp: {e}")
        return False

def verify_otp(email, otp_provided):
    """
    Verifies if the provided OTP is valid and not expired.
    """
    try:
        conn = get_mysql_connection()
        # Use dictionary=True to easily access columns by name
        cursor = conn.cursor(dictionary=True)

        # Fetch the latest OTP for the given email
        cursor.execute(
            "SELECT otp_code, expires_at FROM otps WHERE email = %s ORDER BY created_at DESC LIMIT 1",
            (email,)
        )
        otp_record = cursor.fetchone()

        if not otp_record:
            logger.warning(f"Verification failed: No OTP found for email {email}.")
            return False

        # Check if the OTP has expired
        if datetime.utcnow() > otp_record['expires_at']:
            logger.warning(f"Verification failed: OTP for {email} has expired.")
            return False

        # Verify the provided OTP against the stored hash
        if not verify_password(otp_provided, otp_record['otp_code']):
            logger.warning(f"Verification failed: Invalid OTP for email {email}.")
            return False
        
        # If verification is successful, delete the OTP to prevent reuse
        cursor.execute("DELETE FROM otps WHERE email = %s", (email,))
        conn.commit()
        
        cursor.close()
        conn.close()
        
        logger.info(f"Successfully verified OTP for {email}")
        return True

    except Exception as e:
        logger.error(f"Error in verify_otp: {e}")
        return False
