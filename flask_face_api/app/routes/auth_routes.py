from datetime import datetime

from flask import g, request
from flask_restx import Namespace, Resource, fields
from loguru import logger

from app.auth import admin_required, token_required
from app.config import Config
from app.db.mysql import mysql_cursor
from app.services.audit_service import log_activity
from app.services.bcrypt_service import hash_password, verify_password
from app.services.jwt_service import generate_tokens
from app.services.otp_service import generate_and_store_otp, verify_otp
from app.utils.serialization import serialize_datetime

api = Namespace("users", description="User operations")

register_model = api.model(
    "Register",
    {
        "name": fields.String(required=True, description="User full name"),
        "email": fields.String(required=True, description="User email address"),
        "password": fields.String(required=True, description="User password"),
        "otp": fields.String(required=True, description="6-digit OTP from email"),
    },
)

change_password_model = api.model(
    "ChangePassword",
    {
        "current_password": fields.String(required=True),
        "new_password": fields.String(required=True),
    },
)

login_model = api.model(
    "Login",
    {
        "email": fields.String(required=True),
        "password": fields.String(required=True),
    },
)

send_otp_model = api.model(
    "SendOTP",
    {"email": fields.String(required=True, description="Email to send OTP to")},
)

forgot_password_model = api.model(
    "ForgotPassword",
    {
        "email": fields.String(
            required=True,
            description="Email of the user who forgot their password",
        )
    },
)

reset_password_model = api.model(
    "ResetPassword",
    {
        "email": fields.String(required=True, description="User email address"),
        "otp": fields.String(required=True, description="6-digit OTP from email"),
        "new_password": fields.String(
            required=True,
            description="The new password for the user",
        ),
    },
)


def _request_json():
    return request.get_json(silent=True) or {}


def _normalize_email(value):
    return (value or "").strip().lower()


def _serialize_user_row(user):
    if not user:
        return None
    serialized = dict(user)
    if "created_at" in serialized:
        serialized["created_at"] = serialize_datetime(serialized["created_at"])
    if "last_login" in serialized:
        serialized["last_login"] = serialize_datetime(serialized["last_login"])
    return serialized


@api.route("/send-otp")
class SendOTP(Resource):
    @api.expect(send_otp_model)
    @api.doc(description="Generate and send an OTP to the user's email.")
    def post(self):
        data = _request_json()
        email = _normalize_email(data.get("email"))

        if not email:
            return {"message": "Email is required."}, 400

        try:
            with mysql_cursor() as (_, cursor):
                cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cursor.fetchone():
                    return {"message": "An account with this email already exists."}, 409
        except Exception:
            logger.exception("Failed while checking whether {} already exists.", email)
            return {"message": "Unable to process OTP request."}, 500

        if generate_and_store_otp(email):
            return {"message": f"OTP has been sent to {email}."}, 200
        return {"message": "Failed to send OTP. Please try again later."}, 500


@api.route("/register")
class Register(Resource):
    @api.expect(register_model)
    @api.doc(description="Register a new user after verifying the OTP.")
    def post(self):
        data = _request_json()
        name = (data.get("name") or "").strip()
        email = _normalize_email(data.get("email"))
        password = data.get("password")
        otp = data.get("otp")

        if not all([name, email, password, otp]):
            return {"message": "Missing required fields."}, 400

        if not verify_otp(email, otp):
            return {"message": "Invalid or expired OTP. Please try again."}, 401

        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
                if cursor.fetchone():
                    return {"message": "User already exists."}, 409

                cursor.execute(
                    "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                    (name, email, hash_password(password)),
                )
                conn.commit()

            logger.info("New user registered: {}", email)
            log_activity(email, "User Registered")
            return {"message": "Registration successful."}, 201
        except Exception:
            logger.exception("Error during registration for {}", email)
            return {"message": "An internal error occurred during registration."}, 500


@api.route("/login")
class Login(Resource):
    @api.expect(login_model)
    @api.doc(description="Login a user and return access/refresh tokens along with user data.")
    def post(self):
        data = _request_json()
        email = _normalize_email(data.get("email"))
        password = data.get("password")

        if not email or not password:
            return {"message": "Email and password are required."}, 400

        try:
            with mysql_cursor(dictionary=True) as (conn, cursor):
                cursor.execute(
                    "SELECT id, name, email, role, password FROM users WHERE email=%s",
                    (email,),
                )
                user = cursor.fetchone()

                if not user or not verify_password(password, user["password"]):
                    return {"message": "Invalid email or password."}, 401

                cursor.execute(
                    "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s",
                    (user["id"],),
                )
                conn.commit()

            access_token, refresh_token = generate_tokens(user["id"])
            log_activity(email, "User Login", f"Successful login for user {email}")

            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "user": {
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"],
                },
            }, 200
        except Exception:
            logger.exception("Error during login for {}", email)
            return {"message": "An internal error occurred during login."}, 500


@api.route("/forgot_password")
class ForgotPassword(Resource):
    @api.expect(forgot_password_model)
    @api.doc(description="Sends an OTP to a user's email if the account exists.")
    def post(self):
        data = _request_json()
        email = _normalize_email(data.get("email"))

        if not email:
            return {"message": "Email is required."}, 400

        try:
            with mysql_cursor() as (_, cursor):
                cursor.execute("SELECT id FROM users WHERE email=%s", (email,))
                user_exists = cursor.fetchone() is not None
        except Exception:
            logger.exception("Failed to process forgot password for {}", email)
            return {"message": "An internal error occurred."}, 500

        if not user_exists:
            logger.warning("Forgot password attempt for non-existent user: {}", email)
            return {"message": "If an account exists, an OTP has been sent."}, 200

        if generate_and_store_otp(email):
            log_activity(email, "Forgot Password", "OTP requested for password reset.")
            return {"message": "If an account exists, an OTP has been sent."}, 200
        return {"message": "Failed to send OTP. Please try again later."}, 500


@api.route("/reset-password")
class ResetPassword(Resource):
    @api.expect(reset_password_model)
    @api.doc(description="Resets the user's password after OTP verification.")
    def post(self):
        data = _request_json()
        email = _normalize_email(data.get("email"))
        otp = data.get("otp")
        new_password = data.get("new_password")

        if not all([email, otp, new_password]):
            return {"message": "Email, OTP, and new password are required."}, 400

        if not verify_otp(email, otp):
            return {"message": "Invalid or expired OTP."}, 401

        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute(
                    "UPDATE users SET password = %s WHERE email = %s",
                    (hash_password(new_password), email),
                )
                conn.commit()

            log_activity(email, "Password Reset", "User successfully reset their password.")
            return {"message": "Password has been reset successfully."}, 200
        except Exception:
            logger.exception("Error resetting password for {}", email)
            return {"message": "An internal error occurred while resetting the password."}, 500


@api.route("/change-password")
class ChangePassword(Resource):
    @api.expect(change_password_model)
    @api.doc(description="Allows a logged-in user to change their own password.")
    @token_required
    def put(self):
        data = _request_json()
        current_password = data.get("current_password")
        new_password = data.get("new_password")

        if not current_password or not new_password:
            return {"message": "Current and new passwords are required."}, 400

        try:
            with mysql_cursor(dictionary=True) as (conn, cursor):
                cursor.execute(
                    "SELECT email, password FROM users WHERE id=%s",
                    (g.current_user_id,),
                )
                user = cursor.fetchone()

                if not user or not verify_password(current_password, user["password"]):
                    log_activity(
                        user["email"] if user else "unknown",
                        "Change Password Failed",
                        "Incorrect current password provided.",
                    )
                    return {"message": "Incorrect current password."}, 403

                cursor.execute(
                    "UPDATE users SET password=%s WHERE id=%s",
                    (hash_password(new_password), g.current_user_id),
                )
                conn.commit()

            log_activity(user["email"], "Change Password Success", "User changed their password.")
            return {"message": "Password updated successfully."}, 200
        except Exception:
            logger.exception("Error changing password for user ID {}", g.current_user_id)
            return {"message": "An internal error occurred."}, 500


@api.route("/all")
class AllUsers(Resource):
    @api.doc(description="Get all registered users with optional filters. Admin only.")
    @admin_required
    def get(self):
        email_filter = request.args.get("email")
        name_filter = request.args.get("name")

        try:
            query = "SELECT id, name, email, role, last_login, created_at FROM users WHERE 1=1"
            params = []

            if email_filter:
                query += " AND email LIKE %s"
                params.append(f"%{email_filter}%")
            if name_filter:
                query += " AND name LIKE %s"
                params.append(f"%{name_filter}%")

            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(query, tuple(params))
                users = [_serialize_user_row(row) for row in cursor.fetchall()]

            return {"users": users}, 200
        except Exception:
            logger.exception("Error fetching users.")
            return {"message": "Failed to fetch users."}, 500


@api.route("/<string:email>")
class UserOperations(Resource):
    @api.doc(description="Delete a user by email. Admin only.")
    @admin_required
    def delete(self, email):
        target_email = _normalize_email(email)

        try:
            with mysql_cursor() as (conn, cursor):
                cursor.execute("DELETE FROM users WHERE email = %s", (target_email,))
                conn.commit()
                affected = cursor.rowcount

            if not affected:
                return {"message": f"User {target_email} not found."}, 404

            log_activity(g.current_user_email, "User Deleted", f"Admin deleted user: {target_email}")
            return {"message": f"User {target_email} deleted."}, 200
        except Exception:
            logger.exception("Error deleting user {}", target_email)
            return {"message": "Internal server error."}, 500

    @api.doc(description="Update a user's details (name, role, password).")
    @token_required
    def put(self, email):
        target_email = _normalize_email(email)
        data = _request_json()
        name = (data.get("name") or "").strip()
        new_role = data.get("role")
        password = data.get("password")
        promo_code = data.get("promotion_code")

        if not any([name, new_role, password]):
            return {"message": "At least one field must be provided for update."}, 400

        try:
            with mysql_cursor(dictionary=True) as (conn, cursor):
                cursor.execute(
                    "SELECT id, email, role FROM users WHERE id=%s",
                    (g.current_user_id,),
                )
                actor = cursor.fetchone()
                if not actor:
                    return {"message": "Acting user not found."}, 404

                cursor.execute(
                    "SELECT id, role FROM users WHERE email=%s",
                    (target_email,),
                )
                user_to_edit = cursor.fetchone()
                if not user_to_edit:
                    return {"message": f"User {target_email} not found."}, 404

                actor_is_admin = actor["role"] == "Admin"
                editing_self = str(user_to_edit["id"]) == str(g.current_user_id)
                if not actor_is_admin and not editing_self:
                    return {"message": "You are not authorized to perform this action."}, 403

                requested_role = None
                if new_role and new_role != user_to_edit["role"]:
                    if actor_is_admin:
                        requested_role = new_role
                    elif (
                        editing_self
                        and new_role == "Admin"
                        and promo_code
                        and promo_code == Config.ADMIN_PROMOTION_CODE
                    ):
                        requested_role = new_role
                    else:
                        return {"message": "You are not authorized to change this role."}, 403

                update_parts = []
                params = []

                if name:
                    update_parts.append("name=%s")
                    params.append(name)
                if requested_role:
                    update_parts.append("role=%s")
                    params.append(requested_role)
                if password:
                    update_parts.append("password=%s")
                    params.append(hash_password(password))

                if not update_parts:
                    return {"message": "No valid changes were provided."}, 400

                params.append(target_email)
                cursor.execute(
                    f"UPDATE users SET {', '.join(update_parts)} WHERE email=%s",
                    tuple(params),
                )
                conn.commit()

            log_activity(actor["email"], "User Updated", f"Details updated for user: {target_email}")
            return {"message": "User updated successfully."}, 200
        except Exception:
            logger.exception("Error updating user {}", target_email)
            return {"message": "An internal server error occurred."}, 500


@api.route("/me")
class UserProfile(Resource):
    @api.doc(description="Get the profile of the currently logged-in user.")
    @token_required
    def get(self):
        try:
            with mysql_cursor(dictionary=True) as (_, cursor):
                cursor.execute(
                    "SELECT id, name, email, role FROM users WHERE id=%s",
                    (g.current_user_id,),
                )
                user = cursor.fetchone()

            if not user:
                return {"message": "User not found for this token."}, 404
            return {"user": user}, 200
        except Exception:
            logger.exception("Could not fetch profile for user ID {}", g.current_user_id)
            return {"message": "An internal error occurred."}, 500


@api.route("/test-token")
class TestToken(Resource):
    @token_required
    def get(self):
        return {"message": f"Token OK. User ID: {g.current_user_id}"}, 200
