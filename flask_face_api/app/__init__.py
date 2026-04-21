from flask import Flask, jsonify
from flask_cors import CORS
from flask_restx import Api
from loguru import logger

from app.config import Config
from app.db import init_mongo, init_mysql
from app.routes.audit_routes import api as audit_ns
from app.routes.auth_routes import api as users_ns
from app.routes.data_routes import api as data_ns
from app.routes.mongo_routes import mongo_ns
from app.routes.mysql_routes import mysql_ns
from app.routes.reports_routes import api as reports_ns
from app.routes.v1_ui_routes import v1_ui_bp
from app.utils.logger import setup_logger


def create_app(template_folder=None):
    setup_logger()
    missing_settings = Config.validate_required_settings()
    if missing_settings:
        logger.warning("Application started with missing environment settings: {}", ", ".join(missing_settings))

    app = Flask(__name__, template_folder=template_folder or "templates")
    app.config.from_object(Config)
    CORS(app)

    init_mysql(app)
    init_mongo(app)

    app.register_blueprint(v1_ui_bp)

    api = Api(
        app,
        version=Config.API_VERSION,
        title=Config.API_TITLE,
        doc="/docs",
        description=Config.API_DESCRIPTION,
        authorizations={
            "apikey": {
                "type": "apiKey",
                "in": "header",
                "name": "Authorization",
                "description": "Use `Bearer <JWT>` in the Authorization header.",
            }
        },
        security="apikey",
    )

    api.add_namespace(users_ns, path="/api/v1/users")
    api.add_namespace(mongo_ns, path="/api/v1/faces-mongo")
    api.add_namespace(mysql_ns, path="/api/v1/faces-mysql")
    api.add_namespace(reports_ns, path="/api/v1/reports")
    api.add_namespace(data_ns, path="/api/v1/data")
    api.add_namespace(audit_ns, path="/api/v1/audit")

    app.extensions["restx_api"] = api

    @app.get("/health")
    def health_check():
        return jsonify({"status": "ok", "service": Config.APP_NAME})

    return app
