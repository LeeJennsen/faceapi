# faceapi2 Kubernetes

This directory deploys the full `faceapi2` stack on Kubernetes:

- `api` for the Flask dashboard/API
- `mysql`
- `mongo`
- `mqtt`
- `prometheus`
- `alertmanager`
- `loki`
- `grafana`
- `promtail`
- `face-sub`
- `face-pub`
- `live-match-engine`
- `face-recognition-engine`
- `register-faces` as a one-shot job
- `image-pusher` as a one-shot job

## 1. Build the images

From the repository root, build the three custom images:

```bash
docker build -t faceapi2/flask-face-api:latest ./flask_face_api
docker build -t faceapi2/face-md:latest ./face_data_push/face_md
docker build -t faceapi2/face-pp:latest ./face_data_push/face_pp
```

Or run the helper script from the repository root:

```powershell
./k8s/build-images.ps1
```

Why Docker and Kubernetes can look different during local development:

- `docker compose` mounts your local `flask_face_api` folder into the container, so UI template edits show up immediately.
- Kubernetes runs the already-built image `faceapi2/flask-face-api:latest`, so it will keep serving whatever UI was baked into that image until you rebuild it and restart the deployment.
- Plain `kubectl apply -k ./k8s` also creates a separate in-cluster MySQL and MongoDB, so its users, logins, images, and face records are isolated from the Docker Compose data unless you use the shared-data mode below.
- For `docker-desktop` Kubernetes, rebuilding locally is enough. You normally do not need `kind load docker-image`.

If you are using a local cluster, load the images into it:

```powershell
kind load docker-image faceapi2/flask-face-api:latest
kind load docker-image faceapi2/face-md:latest
kind load docker-image faceapi2/face-pp:latest
```

Or for Minikube:

```powershell
minikube image load faceapi2/flask-face-api:latest
minikube image load faceapi2/face-md:latest
minikube image load faceapi2/face-pp:latest
```

## 2. Secrets

Create a local `secret.env` file from the checked-in template, then fill in your real values:

```bash
cp k8s/secret.env.example k8s/secret.env
```

`secret.env` is ignored by Git and is used by Kustomize to generate the `faceapi2-secrets` object at deploy time. Do not commit it.

## 3. Deploy

Apply the full stack:

```bash
kubectl apply -k ./k8s
```

Or run the helper script:

```powershell
./k8s/deploy-kustomize.ps1
```

The PowerShell helper is recommended for local development because it:

- rebuilds the local custom images first
- applies the Kustomize manifests
- restarts the custom deployments so they pick up the newly rebuilt images

If you use `kubectl apply -k ./k8s` directly after changing UI code, also restart the API deployment:

```powershell
kubectl -n faceapi2 rollout restart deployment/api
```

### Shared Docker data mode

By default, the Kubernetes manifests create their own in-cluster `mysql` and `mongo`, so their data is separate from the Docker Compose stack.

If you want local Kubernetes to reuse the same Docker Compose-backed login users, face records, Mongo detections, images, and Redis-backed state, deploy Kubernetes using the shared-data mode:

```powershell
./k8s/deploy-kustomize.ps1 -UseDockerComposeData
```

That mode:

- starts the Docker Compose `mysql`, `mongo`, and `redis` services from `flask_face_api`
- generates Kubernetes connection settings from the same Docker Compose `.env` values
- removes the in-cluster MySQL and MongoDB resources
- points Kubernetes workloads at the Docker Compose host ports instead
- keeps Docker and Kubernetes reading and writing the same backing data stores

The overlay lives at [overlays/shared-docker-data](./overlays/shared-docker-data/kustomization.yaml).

If you want to apply it manually, render it with the relaxed Kustomize load restrictor:

```powershell
kubectl kustomize --load-restrictor LoadRestrictionsNone .\k8s\overlays\shared-docker-data | kubectl apply -f -
kubectl -n faceapi2 rollout restart deployment/api deployment/face-pub deployment/face-sub deployment/live-match-engine deployment/face-recognition-engine
```

That manual path expects the helper script to have already generated `shared-docker-data.env` and `shared-docker-data.secrets.env` inside the overlay directory.

Check rollout:

```powershell
kubectl -n faceapi2 get pods
kubectl -n faceapi2 get svc
kubectl -n faceapi2 get jobs
```

## 4. Open the API/dashboard and observability tools

Forward the full local access bundle:

```powershell
./k8s/port-forward-local.ps1
```

The helper waits for a ready pod behind each service before it opens the forwards, and it reconnects automatically if Kubernetes replaces a pod later.
The API forward is required; Grafana, Prometheus, Alertmanager, and Loki are forwarded when they have healthy pods and skipped when they do not.

That keeps these local URLs available while the script is running:

```text
http://localhost:5000
http://localhost:3000
http://localhost:9090
http://localhost:9093
http://localhost:3100
```

If you only need the API, the old single-service command still works, but it can still drop during a rollout because raw `kubectl port-forward` stays attached to one pod:

```powershell
kubectl -n faceapi2 port-forward svc/api 5000:5000
```

If the helper reports that one of those localhost ports is already in use, stop the conflicting local services first. The most common conflict is an already-running Docker Compose observability stack.

## Notes

- The manifests use Kustomize via [kustomization.yaml](./kustomization.yaml).
- The shared local-data overlay is available at [overlays/shared-docker-data](./overlays/shared-docker-data/kustomization.yaml) when you want Kubernetes and Docker Compose to use the same MySQL, MongoDB, and Redis data, and the deploy script generates its local env files automatically.
- Secrets are generated from the local `secret.env` file instead of being stored in the repo.
- [ingress.example.yaml](./ingress.example.yaml) and [hpa.example.yaml](./hpa.example.yaml) are optional production-oriented add-ons.
- `register-faces` and `image-pusher` are Kubernetes `Job`s, not always-on deployments.
- If you want to rerun a job, delete it and apply again:

```bash
kubectl -n faceapi2 delete job register-faces
kubectl -n faceapi2 delete job image-pusher
kubectl apply -k ./k8s
```

- The stack is wired through service names, so the face-processing services no longer depend on Docker-only addresses like `host.docker.internal`.
- A Helm chart is also available at [../charts/faceapi2](../charts/faceapi2/README.md).
- Because the old Kubernetes secret file contained real credentials, rotate those credentials if they were committed or shared before this change.
