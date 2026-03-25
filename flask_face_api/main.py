import os
from flask import Flask, render_template, request, redirect, url_for
from flask_restx import Api
from flask_cors import CORS
from app import create_app
from app.utils.logger import setup_logger
from app.routes.auth_routes import api as users_ns
from app.routes.mongo_routes import mongo_ns
from app.routes.mysql_routes import mysql_ns
from app.routes.v1_ui_routes import v1_ui_bp
from app.routes.reports_routes import api as reports_ns
from app.routes.data_routes import api as data_ns
from app.routes.audit_routes import api as audit_ns
from app.services.jwt_service import verify_token
from dotenv import load_dotenv

setup_logger()

load_dotenv()

template_dir = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')
app = create_app(template_folder=template_dir)
CORS(app)

app.register_blueprint(v1_ui_bp)

api = Api(
    app,
    version='1.0',
    title='Jennsen API',
    doc='/docs',
    description='Full shown API for the AI Dashboard',
    authorizations={
        'apikey': {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
            'description': "Type in the *'Value'* field below: **'Bearer &lt;JWT&gt;'**, where JWT is the token"
        }
    },
    security='apikey'
)

api.add_namespace(users_ns, path='/api/v1/users')
api.add_namespace(mongo_ns, path='/api/v1/faces-mongo')
api.add_namespace(mysql_ns, path='/api/v1/faces-mysql')
api.add_namespace(reports_ns, path='/api/v1/reports')
api.add_namespace(data_ns, path='/api/v1/data')
api.add_namespace(audit_ns, path='/api/v1/audit')

if __name__=="__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

