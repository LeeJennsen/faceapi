from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from flask import Flask, Response, jsonify
from flask_cors import CORS
from flask_restx import Api
from loguru import logger

from app.config import Config
from app.db.mongo import check_mongo_connection, init_mongo
from app.db.mysql import check_mysql_connection, init_mysql
from app.routes.audit_routes import api as audit_ns
from app.routes.auth_routes import api as users_ns
from app.routes.data_routes import api as data_ns
from app.routes.mongo_routes import mongo_ns
from app.routes.mysql_routes import mysql_ns
from app.routes.reports_routes import api as reports_ns
from app.routes.v1_ui_routes import v1_ui_bp
from app.utils.logger import setup_logger

BASE_DIR = Path(__file__).resolve().parents[1]

try:
    from app.db.redis import check_redis_connection, init_redis
except ModuleNotFoundError:  # Optional local dependency.
    def init_redis(app=None):
        return None

    def check_redis_connection() -> tuple[bool, str | None]:
        return True, "redis package not installed"


try:
    from app.monitoring import collect_metrics_snapshot, init_metrics, set_dependency_health
    MONITORING_AVAILABLE = True
except ModuleNotFoundError:  # Optional local dependency.
    MONITORING_AVAILABLE = False

    def set_dependency_health(name: str, healthy: bool) -> None:
        return None

    def collect_metrics_snapshot() -> dict:
        summary = {
            "total_requests": 0,
            "error_requests": 0,
            "error_rate_percent": 0.0,
            "average_latency_ms": 0.0,
            "requests_in_progress": 0,
            "uptime_seconds": 0.0,
        }
        return {
            "service": Config.APP_NAME,
            "version": Config.API_VERSION,
            "total_requests": summary["total_requests"],
            "error_requests": summary["error_requests"],
            "error_rate_percent": summary["error_rate_percent"],
            "average_latency_ms": summary["average_latency_ms"],
            "summary": summary,
            "requests_by_status": [],
            "top_endpoints": [],
            "dependencies": {},
        }

    def init_metrics(app):
        if app.extensions.get("prometheus_metrics_initialized"):
            return

        @app.get("/metrics")
        def metrics():
            return Response(
                "# prometheus_client is not installed in this environment.\n",
                mimetype="text/plain; version=0.0.4; charset=utf-8",
            )

        app.extensions["prometheus_metrics_initialized"] = True


DOCKER_ONLY_HOSTS = {
    "alertmanager",
    "api",
    "flask",
    "grafana",
    "loki",
    "mongo",
    "mysql",
    "nginx",
    "prometheus",
    "redis",
}


def _browser_accessible_url(raw_url: str, default: str) -> str:
    candidate = (raw_url or default or "").strip() or default
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return default.rstrip("/")

    if not parsed.scheme or not parsed.netloc:
        return default.rstrip("/")

    hostname = (parsed.hostname or "").lower()
    if hostname not in DOCKER_ONLY_HOSTS:
        return candidate.rstrip("/")

    port = parsed.port
    rebuilt_netloc = "localhost"
    if parsed.username:
        credentials = parsed.username
        if parsed.password:
            credentials = f"{credentials}:{parsed.password}"
        rebuilt_netloc = f"{credentials}@{rebuilt_netloc}"
    if port:
        rebuilt_netloc = f"{rebuilt_netloc}:{port}"

    return urlunsplit(parsed._replace(netloc=rebuilt_netloc)).rstrip("/")


def _tool_links() -> dict:
    grafana = _browser_accessible_url(
        Config.GRAFANA_PUBLIC_URL,
        "http://localhost:3000",
    )
    prometheus = _browser_accessible_url(
        Config.PROMETHEUS_PUBLIC_URL,
        "http://localhost:9090",
    )
    alertmanager = _browser_accessible_url(
        Config.ALERTMANAGER_PUBLIC_URL,
        "http://localhost:9093",
    )
    loki = _browser_accessible_url(
        Config.LOKI_PUBLIC_URL,
        "http://localhost:3100",
    )
    return {
        "grafana": grafana,
        "prometheus": prometheus,
        "prometheus_query": f"{prometheus}/graph?g0.expr=sum(faceapi_http_requests_total)&g0.tab=0",
        "alertmanager": f"{alertmanager}/#/alerts",
        "loki": loki,
    }


def _dependency_payload(name: str, healthy: bool, detail: str | None = None) -> dict:
    payload = {"status": "up" if healthy else "down"}
    if detail:
        payload["detail"] = detail
    set_dependency_health(name, healthy)
    return payload


def _collect_dependency_health(check_dependencies: bool) -> dict:
    if not check_dependencies:
        dependencies = {
            "mysql": {"status": "skipped"},
            "mongo": {"status": "skipped"},
            "redis": {"status": "skipped"},
        }
        for dependency in dependencies:
            set_dependency_health(dependency, True)
        return dependencies

    mysql_ok, mysql_detail = check_mysql_connection()
    mongo_ok, mongo_detail = check_mongo_connection()
    redis_ok, redis_detail = check_redis_connection()

    return {
        "mysql": _dependency_payload("mysql", mysql_ok, mysql_detail),
        "mongo": _dependency_payload("mongo", mongo_ok, mongo_detail),
        "redis": _dependency_payload("redis", redis_ok, redis_detail),
    }


def create_app(template_folder=None, *, enable_integrations: bool = True, enable_metrics: bool = True):
    setup_logger()
    missing_settings = Config.validate_required_settings()
    if missing_settings:
        logger.warning("Application started with missing environment settings: {}", ", ".join(missing_settings))

    app = Flask(__name__, template_folder=template_folder or str(BASE_DIR / "templates"))
    app.config.from_object(Config)
    app.config["ENABLE_DEPENDENCY_CHECKS"] = enable_integrations
    CORS(app)

    if enable_metrics:
        init_metrics(app)

    if enable_integrations:
        init_mysql(app)
        init_mongo(app)
        init_redis(app)

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
        dependencies = _collect_dependency_health(app.config.get("ENABLE_DEPENDENCY_CHECKS", True))
        ready = all(item["status"] != "down" for item in dependencies.values())
        status_code = 200 if ready else 503
        return (
            jsonify(
                {
                    "status": "ok" if ready else "degraded",
                    "service": Config.APP_NAME,
                    "dependencies": dependencies,
                }
            ),
            status_code,
        )

    @app.get("/health/live")
    def live_check():
        return jsonify({"status": "ok", "service": Config.APP_NAME}), 200

    @app.get("/health/ready")
    def readiness_check():
        dependencies = _collect_dependency_health(app.config.get("ENABLE_DEPENDENCY_CHECKS", True))
        ready = all(item["status"] != "down" for item in dependencies.values())
        status_code = 200 if ready else 503
        return jsonify({"ready": ready, "dependencies": dependencies}), status_code

    @app.get("/api/v1/ops/overview")
    def operations_overview():
        dependencies = _collect_dependency_health(app.config.get("ENABLE_DEPENDENCY_CHECKS", True))
        ready = all(item["status"] != "down" for item in dependencies.values())
        return jsonify(
            {
                "health": {
                    "status": "ok" if ready else "degraded",
                    "dependencies": dependencies,
                },
                "metrics": collect_metrics_snapshot(),
                "links": _tool_links(),
            }
        )

    return app
