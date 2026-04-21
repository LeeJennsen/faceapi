$ErrorActionPreference = "Stop"

$k8sDir = $PSScriptRoot
$secretEnv = Join-Path $k8sDir "secret.env"

if (-not (Test-Path $secretEnv)) {
    throw "Missing $secretEnv. Copy secret.env.example to secret.env and fill in your real values before deploying."
}

kubectl apply -k $k8sDir
kubectl -n faceapi2 get pods
kubectl -n faceapi2 get svc
kubectl -n faceapi2 get jobs
