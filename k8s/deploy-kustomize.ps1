param(
    [switch]$SkipBuild,
    [switch]$SkipRestart,
    [switch]$UseDockerComposeData
)

$ErrorActionPreference = "Stop"

$k8sDir = $PSScriptRoot
$repoRoot = Split-Path $k8sDir -Parent
$secretEnv = Join-Path $k8sDir "secret.env"
$buildScript = Join-Path $k8sDir "build-images.ps1"
$sharedDataOverlay = Join-Path $k8sDir "overlays\shared-docker-data"
$sharedDataConfigEnv = Join-Path $sharedDataOverlay "shared-docker-data.env"
$sharedDataSecretEnv = Join-Path $sharedDataOverlay "shared-docker-data.secrets.env"
$composeDir = Join-Path $repoRoot "flask_face_api"
$composeEnv = Join-Path $composeDir ".env"
$customDeployments = @(
    "api",
    "alertmanager",
    "face-pub",
    "face-recognition-engine",
    "face-sub",
    "grafana",
    "live-match-engine",
    "loki",
    "prometheus"
)
$customDaemonSets = @(
    "promtail"
)

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne(2000, $false)) {
            return $false
        }
        $client.EndConnect($asyncResult)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Get-EnvFileValues {
    param(
        [string]$Path
    )

    $values = @{}
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith("#")) {
            continue
        }

        $separatorIndex = $line.IndexOf("=")
        if ($separatorIndex -lt 1) {
            continue
        }

        $key = $line.Substring(0, $separatorIndex).Trim()
        $value = $line.Substring($separatorIndex + 1).Trim()
        $commentIndex = $value.IndexOf(" #")
        if ($commentIndex -ge 0) {
            $value = $value.Substring(0, $commentIndex).Trim()
        }

        $values[$key] = $value
    }

    return $values
}

function Get-EnvValueOrDefault {
    param(
        [hashtable]$Values,
        [string]$Name,
        [string]$DefaultValue
    )

    if ($Values.ContainsKey($Name) -and $null -ne $Values[$Name] -and $Values[$Name] -ne "") {
        return $Values[$Name]
    }

    return $DefaultValue
}

function Get-RequiredEnvValue {
    param(
        [hashtable[]]$Sources,
        [string]$Name
    )

    foreach ($source in $Sources) {
        if ($null -ne $source -and $source.ContainsKey($Name) -and $null -ne $source[$Name] -and $source[$Name] -ne "") {
            return $source[$Name]
        }
    }

    throw "Missing required value '$Name' for shared Docker data mode."
}

function Get-MongoDatabaseName {
    param(
        [string]$MongoUri
    )

    if (-not $MongoUri) {
        return "face_metadata"
    }

    try {
        $uri = [System.Uri]$MongoUri
    } catch {
        return "face_metadata"
    }

    $path = $uri.AbsolutePath.Trim("/")
    if (-not $path) {
        return "face_metadata"
    }

    return $path.Split("/")[0]
}

function Write-EnvFile {
    param(
        [string]$Path,
        [string[]]$Lines
    )

    $content = ($Lines -join [Environment]::NewLine) + [Environment]::NewLine
    [System.IO.File]::WriteAllText($Path, $content, [System.Text.Encoding]::ASCII)
}

if (-not (Test-Path $secretEnv)) {
    throw "Missing $secretEnv. Copy secret.env.example to secret.env and fill in your real values before deploying."
}

if ($UseDockerComposeData) {
    if (-not (Test-Path $composeEnv)) {
        throw "Missing $composeEnv. Shared Docker data mode needs the Docker Compose .env file so Kubernetes can connect to the same databases."
    }

    $composeValues = Get-EnvFileValues -Path $composeEnv
    $secretValues = Get-EnvFileValues -Path $secretEnv

    $mysqlPort = Get-EnvValueOrDefault -Values $composeValues -Name "MYSQL_HOST_PORT" -DefaultValue "3307"
    $mongoPort = Get-EnvValueOrDefault -Values $composeValues -Name "MONGO_HOST_PORT" -DefaultValue "27017"
    $redisPort = Get-EnvValueOrDefault -Values $composeValues -Name "REDIS_HOST_PORT" -DefaultValue "6379"
    $mysqlDatabase = Get-EnvValueOrDefault -Values $composeValues -Name "MYSQL_DATABASE" -DefaultValue "face_auth"
    $composeMongoUri = Get-EnvValueOrDefault -Values $composeValues -Name "MONGO_URI" -DefaultValue "mongodb://mongo:27017/face_metadata"
    $mongoDatabase = Get-MongoDatabaseName -MongoUri $composeMongoUri

    Write-EnvFile -Path $sharedDataConfigEnv -Lines @(
        "FLASK_ENV=production",
        "MYSQL_HOST=host.docker.internal",
        "MYSQL_PORT=$mysqlPort",
        "MYSQL_DATABASE=$mysqlDatabase",
        "MONGO_URI=mongodb://host.docker.internal:$mongoPort/$mongoDatabase",
        "JWT_EXPIRY_SECONDS=3600",
        "JWT_REFRESH_EXPIRY_SECONDS=604800",
        "SMTP_SERVER=smtpdm-ap-southeast-1.aliyun.com",
        "SMTP_PORT=465",
        "FROM_EMAIL=no-reply@servicemail.gluecktech.com",
        "FROM_NAME=Glueck Tech Team",
        "MQTT_HOST=mqtt",
        "MQTT_PORT=1883",
        "FACE_DATA_TOPIC=face/data/raw",
        "FACE_IMAGE_TOPIC=face/images/incoming",
        "FACE_API_BASE_URL=http://api:5000",
        "REDIS_ENABLED=true",
        "REDIS_URL=redis://host.docker.internal:$redisPort/0"
    )

    Write-EnvFile -Path $sharedDataSecretEnv -Lines @(
        "MYSQL_ROOT_PASSWORD=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'MYSQL_ROOT_PASSWORD')",
        "MYSQL_USER=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'MYSQL_USER')",
        "MYSQL_PASSWORD=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'MYSQL_PASSWORD')",
        "JWT_SECRET_KEY=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'JWT_SECRET_KEY')",
        "SMTP_USERNAME=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'SMTP_USERNAME')",
        "SMTP_PASSWORD=$(Get-RequiredEnvValue -Sources @($composeValues, $secretValues) -Name 'SMTP_PASSWORD')"
    )

    Push-Location $composeDir
    try {
        docker compose up -d mysql mongo redis
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to start Docker Compose data services from $composeDir."
        }
    } finally {
        Pop-Location
    }

    $requiredPorts = @(
        @{ Name = "MySQL"; Port = [int]$mysqlPort },
        @{ Name = "MongoDB"; Port = [int]$mongoPort },
        @{ Name = "Redis"; Port = [int]$redisPort }
    )

    foreach ($endpoint in $requiredPorts) {
        if (-not (Test-TcpPort -HostName "127.0.0.1" -Port $endpoint.Port)) {
            throw "$($endpoint.Name) on localhost:$($endpoint.Port) is not reachable. Start the Docker Compose data services first, for example: docker compose up -d mysql mongo redis"
        }
    }

    kubectl get namespace faceapi2 *> $null
    if ($LASTEXITCODE -eq 0) {
        kubectl -n faceapi2 delete deployment/mysql deployment/mongo deployment/redis service/mysql service/mongo service/redis pvc/mysql-data pvc/mongo-data pvc/redis-data configmap/mysql-init --ignore-not-found | Out-Null
        kubectl -n faceapi2 delete job/register-faces job/image-pusher --ignore-not-found | Out-Null
    }
}

if (-not $SkipBuild) {
    & $buildScript
}

$kustomizeTarget = if ($UseDockerComposeData) { $sharedDataOverlay } else { $k8sDir }

if ($UseDockerComposeData) {
    $renderedManifest = kubectl kustomize --load-restrictor LoadRestrictionsNone $kustomizeTarget
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to render shared Docker data overlay."
    }

    $tempManifest = Join-Path ([System.IO.Path]::GetTempPath()) ("faceapi2-shared-data-{0}.yaml" -f [guid]::NewGuid().ToString("N"))
    try {
        [System.IO.File]::WriteAllText($tempManifest, ($renderedManifest -join [Environment]::NewLine), [System.Text.Encoding]::UTF8)
        kubectl apply -f $tempManifest
        if ($LASTEXITCODE -ne 0) {
            throw "Failed to apply shared Docker data manifest."
        }
    } finally {
        if (Test-Path $tempManifest) {
            Remove-Item -LiteralPath $tempManifest -Force
        }
    }
} else {
    kubectl apply -k $kustomizeTarget
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to apply Kubernetes manifests."
    }
}

if (-not $SkipRestart) {
    foreach ($deployment in $customDeployments) {
        kubectl -n faceapi2 rollout restart "deployment/$deployment" | Out-Null
    }

    foreach ($daemonSet in $customDaemonSets) {
        kubectl -n faceapi2 rollout restart "daemonset/$daemonSet" | Out-Null
    }
}

kubectl -n faceapi2 get pods
kubectl -n faceapi2 get svc
kubectl -n faceapi2 get jobs

Write-Host "Completed Kubernetes deploy. If you changed Job images, delete and recreate those Jobs explicitly before re-applying."
Write-Host "Run $(Join-Path $k8sDir 'port-forward-local.ps1') to expose the API, Grafana, Prometheus, Alertmanager, and Loki on localhost."
if ($UseDockerComposeData) {
    Write-Host "Shared Docker data mode is active. Kubernetes is using the Docker Compose MySQL, MongoDB, and Redis services via host ports."
}
