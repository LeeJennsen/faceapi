$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

docker build -t faceapi2/flask-face-api:latest "$repoRoot\flask_face_api"
docker build -t faceapi2/face-md:latest "$repoRoot\face_data_push\face_md"
docker build -t faceapi2/face-pp:latest "$repoRoot\face_data_push\face_pp"

Write-Host "Images built successfully."
