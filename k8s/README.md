# faceapi2 Kubernetes

This directory deploys the full `faceapi2` stack on Kubernetes:

- `api` for the Flask dashboard/API
- `mysql`
- `mongo`
- `mqtt`
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

Check rollout:

```powershell
kubectl -n faceapi2 get pods
kubectl -n faceapi2 get svc
kubectl -n faceapi2 get jobs
```

## 4. Open the API/dashboard

Port-forward the API service:

```powershell
kubectl -n faceapi2 port-forward svc/api 5000:5000
```

Then open:

```text
http://localhost:5000
```

## Notes

- The manifests use Kustomize via [kustomization.yaml](./kustomization.yaml).
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
