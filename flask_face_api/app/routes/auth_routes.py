import email
import os
from flask_restx import Namespace, Resource, fields
from flask import request, g
from app.db.mysql import get_mysql_connection
from app.services.bcrypt_service import hash_password, verify_password
from app.services.jwt_service import generate_tokens, verify_token
from app.services.otp_service import generate_and_store_otp, verify_otp
from app.services.audit_service import log_activity
from loguru import logger
from datetime import datetime
from functools import wraps
from app.config import Config

api = Namespace('users', description='User operations')

# --- API Models for Swagger Documentation ---

# Model for the registration payload
register_model = api.model('Register', {
    'name': fields.String(required=True, description='User full name'),
    'email': fields.String(required=True, description='User email address'),
    'password': fields.String(required=True, description='User password'),
    'otp': fields.String(required=True, description='6-digit OTP from email')
})

# Model for changing password
change_password_model = api.model('ChangePassword', {
    'current_password': fields.String(required=True),
    'new_password': fields.String(required=True)
})

# Model for the login payload
login_model = api.model('Login', {
    'email': fields.String(required=True),
    'password': fields.String(required=True)
})

# Model for the send-otp payload
send_otp_model = api.model('SendOTP', {
    'email': fields.String(required=True, description='Email to send OTP to')
})

# Models for Forgot Password Flow
forgot_password_model = api.model('ForgotPassword', {
    'email': fields.String(required=True, description='Email of the user who forgot their password')
})

reset_password_model = api.model('ResetPassword', {
    'email': fields.String(required=True, description='User email address'),
    'otp': fields.String(required=True, description='6-digit OTP from email'),
    'new_password': fields.String(required=True, description='The new password for the user')
})

# Define promotion code
ADMIN_PROMOTION_CODE = os.getenv("ADMIN_PROMOTION_CODE")

# --- Authorization Decorator ---
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token or ' ' not in token:
            return {"message": "Token is missing!"}, 401
        
        token = token.split(" ")[1]
        user_id = verify_token(token)
        if not user_id:
             return {"message": "Invalid or expired token."}, 401
        
        # Add user_id to the global request context
        request.current_user_id = user_id
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    @token_required # Depends on token_required to get user_id
    def decorated(*args, **kwargs):
        conn = get_mysql_connection()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT email, role FROM users WHERE id=%s", (request.current_user_id,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and user['role'] == 'Admin':
            request.current_user_email = user['email'] # Store email for logging
            return f(*args, **kwargs)
        else:
            return {"message": "Admin privileges required."}, 403
    return decorated

# --- API Endpoints ---

@api.route('/send-otp')
class SendOTP(Resource):
    @api.expect(send_otp_model)
    @api.doc(description="Generate and send an OTP to the user's email.")
    def post(self):
        data = request.json
        email = data.get('email')

        if not email:
            return {"message": "Email is required"}, 400

        # Check if user already exists
        conn = get_mysql_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email=%s", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return {"message": "An account with this email already exists."}, 409 # 409 Conflict
        cur.close()
        conn.close()
        
        if generate_and_store_otp(email):
            return {"message": f"OTP has been sent to {email}"}, 200
        else:
            return {"message": "Failed to send OTP. Please try again later."}, 500


@api.route('/register')
class Register(Resource):
    @api.expect(register_model)
    @api.doc(description="Register a new user after verifying the OTP.")
    def post(self):
        data = request.json
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        otp = data.get('otp')

        if not all([name, email, password, otp]):
            return {"message": "Missing required fields"}, 400

        # 1. Verify the OTP first
        if not verify_otp(email, otp):
            return {"message": "Invalid or expired OTP. Please try again."}, 401 # 401 Unauthorized

        # 2. If OTP is valid, proceed with registration
        try:
            conn = get_mysql_connection()
            cur = conn.cursor()

            # Double-check if user exists (though checked in send-otp)
            cur.execute("SELECT id FROM users WHERE email=%s", (email,))
            if cur.fetchone():
                return {"message": "User already exists"}, 409

            # Insert new user
            cur.execute("INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
                        (name, email, hash_password(password)))
            conn.commit()
            
            cur.close()
            conn.close()
            
            logger.info(f"New user registered: {email}")
            log_activity(email, "User Registered")
            return {"message": "Registration successful!"}, 201

        except Exception as e:
            logger.error(f"Error during registration for {email}: {e}")
            return {"message": "An internal error occurred during registration."}, 500


@api.route('/login')
class Login(Resource):
    @api.expect(login_model)
    @api.doc(description="Login a user and return access/refresh tokens along with user data.")
    def post(self):
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return {"message": "Email and password are required"}, 400
            
        try:
            conn = get_mysql_connection()
            cur = conn.cursor(dictionary=True)
            
            cur.execute("SELECT id, name, email, role, password FROM users WHERE email=%s", (email,))
            user = cur.fetchone()

            if not user or not verify_password(password, user['password']):
                cur.close()
                conn.close()
                return {"message": "Invalid email or password"}, 401

            # Update the last_login timestamp
            user_id = user['id']
            cur.execute("UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = %s", (user_id,))
            conn.commit()
            
            cur.close()
            conn.close()
            
            user_data = { "name": user['name'], "email": user['email'], "role": user['role'] }
            access_token, refresh_token = generate_tokens(user['id'])

            if user and verify_password(password, user['password']):
             log_activity(email, "User Login", f"Successful login for user {email}")
            
            return {
                "access_token": access_token, 
                "refresh_token": refresh_token,
                "user": user_data 
            }, 200
        
        except Exception as e:
            logger.error(f"Error during login for {email}: {e}")
            return {"message": "An internal error occurred during login."}, 500

# FORGOT PASSWORD ENDPOINT ---
@api.route('/forgot_password')
class ForgotPassword(Resource):
    @api.expect(forgot_password_model)
    @api.doc(description="Sends an OTP to a user's email if the account exists.")
    def post(self):
        data = request.json
        email = data.get('email')

        if not email:
            return {"message": "Email is required"}, 400

        conn = get_mysql_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE email = %s", (email,))
        user_exists = cur.fetchone()
        cur.close()
        conn.close()

        if not user_exists:
            # To prevent user enumeration, we can send a generic success message.
            # However, for clearer debugging, we'll send a 404 for now.
            logger.warning(f"Forgot password attempt for non-existent user: {email}")
            return {"message": "User with this email does not exist."}, 404

        if generate_and_store_otp(email):
            log_activity(email, "Forgot Password", "OTP requested for password reset.")
            return {"message": f"An OTP has been sent to {email}."}, 200
        else:
            return {"message": "Failed to send OTP. Please try again later."}, 500

# RESET PASSWORD ENDPOINT ---
@api.route('/reset-password')
class ResetPassword(Resource):
    @api.expect(reset_password_model)
    @api.doc(description="Resets the user's password after OTP verification.")
    def post(self):
        data = request.json
        email = data.get('email')
        otp = data.get('otp')
        new_password = data.get('new_password')

        if not all([email, otp, new_password]):
            return {"message": "Email, OTP, and new password are required."}, 400

        if not verify_otp(email, otp):
            return {"message": "Invalid or expired OTP."}, 401

        try:
            hashed_new_password = hash_password(new_password)
            conn = get_mysql_connection()
            cur = conn.cursor()
            cur.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_new_password, email))
            conn.commit()
            cur.close()
            conn.close()
            
            log_activity(email, "Password Reset", "User successfully reset their password.")
            return {"message": "Password has been reset successfully."}, 200
        except Exception as e:
            logger.error(f"Error resetting password for {email}: {e}")
            return {"message": "An internal error occurred while resetting the password."}, 500

@api.route('/change-password')
class ChangePassword(Resource):
    @api.expect(change_password_model)
    @api.doc(description="Allows a logged-in user to change their own password.")
    @token_required
    def put(self):
        user_id = request.current_user_id
        data = request.json
        current_password = data.get('current_password')
        new_password = data.get('new_password')

        if not current_password or not new_password:
            return {"message": "Current and new passwords are required."}, 400

        try:
            conn = get_mysql_connection()
            cur = conn.cursor(dictionary=True)

            cur.execute("SELECT email, password FROM users WHERE id=%s", (user_id,))
            user = cur.fetchone()

            if not user or not verify_password(current_password, user['password']):
                cur.close()
                conn.close()
                log_activity(user['email'] if user else 'unknown', "Change Password Failed", "Incorrect current password provided.")
                return {"message": "Incorrect current password."}, 403

            # Hash the new password and update the database
            hashed_new_password = hash_password(new_password)
            cur.execute("UPDATE users SET password=%s WHERE id=%s", (hashed_new_password, user_id))
            conn.commit()

            cur.close()
            conn.close()
            
            log_activity(user['email'], "Change Password Success", "User changed their password.")
            return {"message": "Password updated successfully."}, 200

        except Exception as e:
            logger.error(f"Error changing password for user ID {user_id}: {e}")
            return {"message": "An internal error occurred."}, 500

@api.route('/all')
class AllUsers(Resource):
    @api.doc(description="Get all registered users with optional filters")
    def get(self):
        
        try:
            email_filter = request.args.get('email')
            name_filter = request.args.get('name')

            conn = get_mysql_connection()
            cursor = conn.cursor(dictionary=True)

            query = "SELECT id, name, email, role, last_login, created_at FROM users WHERE 1=1"
            params = []

            if email_filter:
                query += " AND email LIKE %s"
                params.append(f"%{email_filter}%")
            if name_filter:
                query += " AND name LIKE %s"
                params.append(f"%{name_filter}%")

            cursor.execute(query, tuple(params))
            users = cursor.fetchall()

            # Convert datetime to ISO string
            for user in users:
                if isinstance(user.get("created_at"), datetime):
                    user["created_at"] = user["created_at"].isoformat()
                if isinstance(user.get("last_login"), datetime):
                    user["last_login"] = user["last_login"].isoformat()

            cursor.close()
            conn.close()

            return {"users": users}, 200

        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return {"message": "Failed to fetch users."}, 500
        
        
@api.route('/<string:email>')
class UserOperations(Resource):
    
    @api.doc(description="Delete a user by email")
    @admin_required # Security: Only admins can delete users
    def delete(self, email):
        actor_email = request.current_user_email
        try:
            conn = get_mysql_connection()
            cur = conn.cursor()

            cur.execute("DELETE FROM users WHERE email = %s", (email,))
            conn.commit()

            affected = cur.rowcount
            cur.close()
            conn.close()

            if affected:
                log_activity(actor_email, "User Deleted", f"Admin deleted user: {email}")
                return {"message": f"User {email} deleted."}, 200
            else:
                return {"message": f"User {email} not found."}, 404
        except Exception as e:
            logger.error(f"Error deleting user {email}: {e}")
            return {"message": "Internal server error."}, 500
        
    @api.doc(description="Update a user's details (name, role, password).")
    def put(self, email):
        data = request.json
        name = data.get('name')
        new_role = data.get('role')
        password = data.get('password')
        promo_code = data.get('promotion_code')

        if not name:
            return {"message": "Name is required for an update."}, 400

        auth_header = request.headers.get('Authorization')
        if not auth_header or ' ' not in auth_header:
            logger.warning(f"Update attempt on {email} failed: Missing or malformed Authorization header.")
            return {"message": "Authorization header is missing or malformed."}, 401
        
        auth_token = auth_header.split(" ")[1]
        actor_id = verify_token(auth_token)
        
        if not actor_id:
            logger.warning(f"Update attempt on {email} failed: Invalid or expired session token.")
            return {"message": "Invalid or expired session token."}, 401

        try:
            conn = get_mysql_connection()
            cur = conn.cursor(dictionary=True)

            # Get the actor's info (role and email for logging)
            cur.execute("SELECT email, role FROM users WHERE id=%s", (actor_id,))
            actor = cur.fetchone()
            if not actor:
                # This should not happen if token is valid, but as a safeguard:
                cur.close()
                conn.close()
                return {"message": "Acting user not found."}, 404
            
            actor_role = actor['role']
            actor_email = actor['email']
            
            # 1. First, check if the user to be edited exists
            cur.execute("SELECT id, role FROM users WHERE email=%s", (email,))
            user_to_edit = cur.fetchone() # Store the result in a variable

            if not user_to_edit: # Check the variable
                cur.close()
                conn.close()
                return {"message": f"User {email} not found."}, 404
            
            # --- Authorization Logic ---
            can_update = False
            if actor_role == 'Admin':
                can_update = True
            elif str(user_to_edit['id']) == str(actor_id):
                can_update = True
                if new_role and new_role != user_to_edit['role']:
                    if new_role == 'Admin' and promo_code == ADMIN_PROMOTION_CODE:
                        pass # Allow promotion with correct code
                    else:
                        can_update = False # Disallow any other role change
            
            if not can_update:
                cur.close()
                conn.close()
                return {"message": "You are not authorized to perform this action."}, 403

            # --- Build and Execute the SQL Query ---
            update_parts = ["name=%s"]
            params = [name]

            if new_role:
                update_parts.append("role=%s")
                params.append(new_role)
            
            if password:
                update_parts.append("password=%s")
                params.append(hash_password(password))

            params.append(email)
            query = f"UPDATE users SET {', '.join(update_parts)} WHERE email=%s"

            cur.execute(query, tuple(params))
            conn.commit()
            
            cur.close()
            conn.close()

            log_activity(actor_email, "User Updated", f"Details updated for user: {email}")
            return {"message": "User updated successfully."}, 200

        except Exception as e:
            logger.error(f"Error updating user {email}: {e}")
            return {"message": "An internal server error occurred."}, 500
        
@api.route('/me')
class UserProfile(Resource):
    @api.doc(description="Get the profile of the currently logged-in user.")
    @token_required
    def get(self):
        """Fetches the current user's details based on their token"""
        user_id = request.current_user_id
        try:
            conn = get_mysql_connection()
            cur = conn.cursor(dictionary=True)
            cur.execute("SELECT id, name, email, role FROM users WHERE id=%s", (user_id,))
            user = cur.fetchone()
            cur.close()
            conn.close()
            if user:
                return {"user": user}, 200
            else:
                return {"message": "User not found for this token."}, 404
        except Exception as e:
            logger.error(f"Could not fetch profile for user ID {user_id}: {e}")
            return {"message": "An internal error occurred."}, 500

@api.route('/test-token')
class TestToken(Resource):
    def get(self):
        auth_header = request.headers.get("Authorization", "")
        if " " not in auth_header:
            return {"message": "Missing Bearer token"}, 401
        token = auth_header.split(" ")[1]
        user_id = verify_token(token)
        if user_id:
            return {"message": f"Token OK. User ID: {user_id}"}, 200
        return {"message": "Token invalid or expired"}, 401
