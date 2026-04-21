# faceapi2

`faceapi2` is a face-recognition platform composed of a Flask API/dashboard, MQTT-based ingestion workers, MySQL and MongoDB storage, and Kubernetes/Helm deployment assets.

## What This Repository Contains

- `flask_face_api/`: Flask REST API, dashboard templates, auth flows, reporting, and persistence adapters.
- `face_data_push/face_md/`: MQTT publisher/subscriber services for metadata simulation and forwarding.
- `face_data_push/face_pp/`: Face-processing workers for registration, live matching, and image ingestion.
- `k8s/`: Kustomize-based Kubernetes manifests.
- `charts/faceapi2/`: Helm chart for cluster deployments.

## Architecture

The platform is organized around three concerns:

1. Ingestion and processing: MQTT workers publish and consume face events and images.
2. Application services: the Flask app provides REST APIs, authentication, reporting, and dashboard pages.
3. Deployment: Docker, Kubernetes, and Helm assets support both local and cluster-based environments.

## Repository Highlights

- Centralized Flask configuration and application factory
- Shared auth decorators for token and admin enforcement
- Connection-managed MySQL and lazy MongoDB access
- Secret-safe Kubernetes and Helm workflows using local, ignored secret files
- Cleaner worker logging and more maintainable face-processing scripts
- Basic CI smoke check for syntax validation

## Quick Start

Clone the repository:

```bash
git clone https://github.com/LeeJennsen/faceapi.git
cd faceapi
```

### Flask API

1. Copy `flask_face_api/.env.example` to `flask_face_api/.env`.
2. Fill in the real credentials and service endpoints.
3. Build and run the API:

```bash
cp flask_face_api/.env.example flask_face_api/.env
docker build -t faceapi2/flask-face-api:latest ./flask_face_api
docker run --env-file flask_face_api/.env -p 5000:5000 faceapi2/flask-face-api:latest
```

### Kubernetes

Use the sanitized Kustomize workflow documented in [k8s/README.md](./k8s/README.md). Secrets are generated from a local `k8s/secret.env` file and are no longer stored in tracked manifests.

### Helm

Use the local secrets override flow documented in [charts/faceapi2/README.md](./charts/faceapi2/README.md). Keep `values.secrets.local.yaml` out of Git.

## Project Structure

```text
faceapi2/
|-- charts/
|-- face_data_push/
|   |-- face_md/
|   `-- face_pp/
|-- flask_face_api/
|   |-- app/
|   `-- templates/
`-- k8s/
```

## Portfolio Notes

This repository is intentionally organized to show:

- multi-service backend design
- API and UI integration in one product
- cluster deployment readiness
- environment and secret hygiene
- maintainability-focused refactoring, not just feature code

## Verification

The repository includes a lightweight CI workflow that compiles the Python codebase to catch syntax regressions before merge.
