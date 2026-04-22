param(
    [string]$Namespace = "faceapi2",
    [switch]$ApiOnly
)

$ErrorActionPreference = "Stop"

function Test-LocalPortAvailable {
    param(
        [int]$Port
    )

    $getNetTcpConnection = Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue
    if ($getNetTcpConnection) {
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        return @($listeners).Count -eq 0
    }

    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    try {
        $listener.Start()
        return $true
    } catch {
        return $false
    } finally {
        try {
            $listener.Stop()
        } catch {
        }
    }
}

function Get-ReadyPodNameForService {
    param(
        [string]$KubectlPath,
        [string]$Namespace,
        [string]$ServiceName
    )

    $podNames = & $KubectlPath -n $Namespace get "endpoints/$ServiceName" -o jsonpath="{range .subsets[*].addresses[*]}{.targetRef.name}{'\n'}{end}" 2>$null
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    $firstPod = @($podNames -split "\r?\n" | Where-Object { $_.Trim() } | Select-Object -First 1)
    if (-not $firstPod) {
        return $null
    }

    return $firstPod.Trim()
}

function Wait-ServiceReadyPod {
    param(
        [string]$KubectlPath,
        [string]$Namespace,
        [string]$ServiceName,
        [int]$TimeoutSeconds = 120
    )

    & $KubectlPath -n $Namespace get "svc/$ServiceName" *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Kubernetes service '$ServiceName' was not found in namespace '$Namespace'."
    }

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $podName = Get-ReadyPodNameForService -KubectlPath $KubectlPath -Namespace $Namespace -ServiceName $ServiceName
        if ($podName) {
            return $podName
        }

        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)

    throw "Service '$ServiceName' has no ready pod endpoints in namespace '$Namespace'."
}

$kubectl = Get-Command kubectl -ErrorAction Stop

$targets = @(
    @{
        Name = "api"
        LocalPort = 5000
        RemotePort = 5000
        Url = "http://localhost:5000"
        Required = $true
    }
)

if (-not $ApiOnly) {
    $targets += @(
        @{
            Name = "grafana"
            LocalPort = 3000
            RemotePort = 3000
            Url = "http://localhost:3000"
            Required = $false
        },
        @{
            Name = "prometheus"
            LocalPort = 9090
            RemotePort = 9090
            Url = "http://localhost:9090"
            Required = $false
        },
        @{
            Name = "alertmanager"
            LocalPort = 9093
            RemotePort = 9093
            Url = "http://localhost:9093/#/alerts"
            Required = $false
        },
        @{
            Name = "loki"
            LocalPort = 3100
            RemotePort = 3100
            Url = "http://localhost:3100"
            Required = $false
        }
    )
}

$activeTargets = @()
foreach ($target in $targets) {
    & $kubectl.Source -n $Namespace get "svc/$($target.Name)" *> $null
    if ($LASTEXITCODE -ne 0) {
        if ($target.Required) {
            throw "Kubernetes service '$($target.Name)' was not found in namespace '$Namespace'. Check 'kubectl -n $Namespace get svc' first."
        }

        Write-Host "Skipping '$($target.Name)' because the service does not exist in namespace '$Namespace'."
        continue
    }

    try {
        $target.PodName = Wait-ServiceReadyPod -KubectlPath $kubectl.Source -Namespace $Namespace -ServiceName $target.Name
        $activeTargets += $target
    } catch {
        if ($target.Required) {
            throw
        }

        Write-Host "Skipping '$($target.Name)' because it has no ready pods right now."
    }
}

if ($activeTargets.Count -eq 0) {
    throw "No ready services are available to port-forward in namespace '$Namespace'."
}

$busyTargets = @($activeTargets | Where-Object { -not (Test-LocalPortAvailable -Port $_.LocalPort) })
if ($busyTargets.Count -gt 0) {
    $descriptions = $busyTargets | ForEach-Object { "localhost:$($_.LocalPort) ($($_.Name))" }
    throw ("These local ports are already in use: {0}. Stop the conflicting local services first, especially any Docker Compose observability stack." -f ($descriptions -join ", "))
}

$jobScript = {
    param(
        [string]$KubectlPath,
        [string]$Namespace,
        [string]$PodName,
        [int]$LocalPort,
        [int]$RemotePort
    )

    & $KubectlPath -n $Namespace port-forward --address localhost "pod/$PodName" "${LocalPort}:${RemotePort}"
}

function Start-PortForwardJob {
    param(
        [object]$Target,
        [string]$KubectlPath,
        [string]$Namespace
    )

    return Start-Job -Name "faceapi2-port-forward-$($Target.Name)" -ScriptBlock $jobScript -ArgumentList @(
        $KubectlPath,
        $Namespace,
        $Target.PodName,
        $Target.LocalPort,
        $Target.RemotePort
    )
}

$jobs = @()
foreach ($target in $activeTargets) {
    $jobs += [pscustomobject]@{
        Target = $target
        Job = Start-PortForwardJob -Target $target -KubectlPath $kubectl.Source -Namespace $Namespace
    }
}

Write-Host "Port-forwards are running for namespace '$Namespace'. Press Ctrl+C to stop them."
foreach ($target in $activeTargets) {
    Write-Host ("  {0,-12} {1}" -f $target.Name, $target.Url)
}

try {
    while ($true) {
        $stoppedJobs = @($jobs | Where-Object { $_.Job.State -ne "Running" })
        if ($stoppedJobs.Count -gt 0) {
            $jobsToRemove = @()
            foreach ($entry in $stoppedJobs) {
                $output = (Receive-Job -Job $entry.Job -Keep -ErrorAction SilentlyContinue | Out-String).Trim()
                if ($output) {
                    Write-Host $output
                }

                Remove-Job -Job $entry.Job -Force -ErrorAction SilentlyContinue
                Write-Host "Port-forward for '$($entry.Target.Name)' stopped. Waiting for a ready pod, then reconnecting..."

                try {
                    $entry.Target.PodName = Wait-ServiceReadyPod -KubectlPath $kubectl.Source -Namespace $Namespace -ServiceName $entry.Target.Name
                    $entry.Job = Start-PortForwardJob -Target $entry.Target -KubectlPath $kubectl.Source -Namespace $Namespace
                } catch {
                    if ($entry.Target.Required) {
                        throw
                    }

                    Write-Host "Port-forward for '$($entry.Target.Name)' is paused because the service has no ready pods right now."
                    $jobsToRemove += $entry.Target.Name
                }
            }

            if ($jobsToRemove.Count -gt 0) {
                $jobs = @($jobs | Where-Object { $jobsToRemove -notcontains $_.Target.Name })
            }
        }

        Start-Sleep -Seconds 2
    }
} finally {
    foreach ($entry in $jobs) {
        if ($entry.Job.State -eq "Running") {
            Stop-Job -Job $entry.Job | Out-Null
        }

        Receive-Job -Job $entry.Job -ErrorAction SilentlyContinue | Out-Null
        Remove-Job -Job $entry.Job -Force -ErrorAction SilentlyContinue
    }
}
