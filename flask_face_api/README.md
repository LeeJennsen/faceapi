# Flask Face API Local Stack

This folder contains the full local development stack for the FaceAPI2 application. It includes the Flask API, HTML dashboard pages, Redis, MySQL, MongoDB, NGINX, Prometheus, Grafana, Loki, Alertmanager, Promtail, pytest, k6, and Postman assets.

## 1. Prerequisites

Make sure these are available before starting:

- Docker Desktop with Compose enabled
- PowerShell or another terminal
- The host ports `5000`, `3000`, `3100`, `3307`, `6379`, `9090`, and `9093`

## 2. Configure The Environment

Copy the template and replace placeholder values with your real secrets and SMTP settings.

```powershell
cd C:\Users\leeje\Downloads\faceapi2\flask_face_api
Copy-Item .env.example .env
```

Important defaults in `.env.example`:

- `NGINX_HOST_PORT=5000`
- `MYSQL_HOST_PORT=3307`
- `GRAFANA_HOST_PORT=3000`
- `PROMETHEUS_HOST_PORT=9090`
- `ALERTMANAGER_HOST_PORT=9093`
- `LOKI_HOST_PORT=3100`

## 3. Start The Full Stack

```powershell
cd C:\Users\leeje\Downloads\faceapi2\flask_face_api
docker compose up -d --build
```

If you want the dashboard to show sample charts immediately, load the bundled demo dataset:

```powershell
docker compose --profile tooling run --rm seed-demo
```

Demo login created by the seeder:

- email: `admin@faceapi2.local`
- password: `admin12345`

To restart only the observability services:

```powershell
docker compose up -d --force-recreate nginx prometheus grafana loki alertmanager promtail
```

## 4. Open The UIs

```powershell
Start-Process http://localhost:5000
Start-Process http://localhost:5000/v1/login
Start-Process http://localhost:5000/v1/dashboard
Start-Process http://localhost:5000/v1/operations
Start-Process http://localhost:5000/docs
Start-Process http://localhost:5000/health
Start-Process http://localhost:5000/metrics
Start-Process http://localhost:3000
Start-Process http://localhost:9090
Start-Process http://localhost:9093
Start-Process http://localhost:3100
```

## 5. What Each URL Is For

- `http://localhost:5000`: NGINX entry point for the app
- `http://localhost:5000/v1/login`: login UI
- `http://localhost:5000/v1/register`: registration UI
- `http://localhost:5000/v1/forgot_password`: password reset UI
- `http://localhost:5000/v1/dashboard`: main application dashboard
- `http://localhost:5000/v1/operations`: professional runtime UI for health, metrics, tools, and dependency status
- `http://localhost:5000/docs`: Swagger UI
- `http://localhost:5000/health`: JSON health output for probes
- `http://localhost:5000/metrics`: raw Prometheus metrics output
- `http://localhost:3000`: Grafana dashboards and Explore
- `http://localhost:9090`: Prometheus query console
- `http://localhost:9093`: Alertmanager alerts page
- `http://localhost:3100`: Loki API endpoint

## 6. Observability Behavior Explained

## 6a. Why The App Dashboard Can Still Look Empty

- The Compose stack in this folder does not automatically start the MQTT and face-processing worker pipeline from `face_data_push/`.
- So the web app can be healthy while the dashboard has no business records yet.
- If you want a quick local demo, run `docker compose --profile tooling run --rm seed-demo`.

### Grafana

- Local Grafana is configured for anonymous viewing.
- The login form is disabled.
- Sign-up is disabled.
- The home page is a pre-provisioned FaceAPI2 dashboard.

If your browser still shows a login page, recreate the Grafana container and hard refresh:

```powershell
cd C:\Users\leeje\Downloads\faceapi2\flask_face_api
docker compose up -d --force-recreate grafana
```

### Prometheus

- Prometheus is a query tool, so the page is normal even if no charts are preloaded there.
- The main visual dashboard is in Grafana.
- If the data looks sparse, generate traffic by opening the dashboard or docs, or run the k6 smoke test.

Example Prometheus queries:

```text
sum(faceapi_http_requests_total)
sum by (status) (faceapi_http_requests_total)
sum(rate(faceapi_http_requests_total[5m]))
histogram_quantile(0.95, sum by (le) (rate(faceapi_http_request_duration_seconds_bucket[5m])))
```

### Alertmanager

- Alertmanager only shows alerts when Prometheus sends them.
- A `Watchdog` alert is bundled so the UI is not permanently empty.
- The API health, 5xx rate, and p95 latency rules are also included.

### Loki

- Loki on port `3100` is the logs backend, not a standalone website.
- Use Grafana Explore to browse logs with a proper UI.

## 7. Testing

Install dev dependencies and run the automated tests:

```powershell
cd C:\Users\leeje\Downloads\faceapi2\flask_face_api
python -m pip install -r requirements-dev.txt
pytest
```

Run the bundled k6 smoke test:

```powershell
cd C:\Users\leeje\Downloads\faceapi2\flask_face_api
docker compose --profile tooling run --rm k6
```

If you want authenticated load, set `K6_USER_EMAIL` and `K6_USER_PASSWORD` in `.env`.

## 8. Postman

Import these files into Postman:

- `postman/faceapi2.postman_collection.json`
- `postman/faceapi2.local.postman_environment.json`

The collection stores login tokens into environment variables for follow-up requests.

## 9. Troubleshooting

- If `docker compose up` fails on `5000`, another process is already using the port. Stop that process or change `NGINX_HOST_PORT`.
- If `docker compose up` fails on `3306`, your host machine is already using MySQL. This project already maps container MySQL to host port `3307` by default.
- If `/v1/dashboard` loads but the data calls fail, log in again so the browser has a fresh JWT in local storage.
- If `/metrics` looks ugly, that is expected. Prometheus requires the raw text format.
- If `http://localhost:3100` has no UI, open Grafana Explore instead.
