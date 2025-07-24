from flask import Blueprint, render_template, redirect

v1_ui_bp = Blueprint('v1_ui', __name__, url_prefix='/v1')

@v1_ui_bp.route('/')
def root_redirect():
    return redirect('/v1/login')

@v1_ui_bp.route('/login')
def login():
    return render_template("v1/login.html")

@v1_ui_bp.route('/register')
def register():
    return render_template("v1/register.html")

@v1_ui_bp.route('/dashboard')
def dashboard():
    return render_template("v1/dashboard.html")

@v1_ui_bp.route('/forgot_password')
def forgot_password():
    return render_template("v1/forgot_password.html")