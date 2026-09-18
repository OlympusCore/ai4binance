function Get-AI4BinanceOllamaEndpoint {
    param(
        [string]$HostValue = $(if ($env:OLLAMA_HOST) { $env:OLLAMA_HOST } else { "http://127.0.0.1:11434" })
    )

    $candidate = $HostValue.Trim().TrimEnd("/")
    if ($candidate -notmatch "^https?://") {
        $candidate = "http://$candidate"
    }
    $uri = [Uri]$candidate
    $loopbackHosts = @("127.0.0.1", "localhost", "::1", "[::1]")
    if ($uri.Scheme -ne "http" -or $uri.Host -notin $loopbackHosts) {
        throw "OLLAMA_ENDPOINT_NOT_LOOPBACK"
    }
    return $uri.GetLeftPart([System.UriPartial]::Authority).TrimEnd("/")
}

function Get-AI4BinanceOllamaListeners {
    param([Parameter(Mandatory = $true)][int]$Port)

    try {
        return @(
            Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
                Select-Object LocalAddress, LocalPort, OwningProcess
        )
    } catch {
        return @()
    }
}

function Test-AI4BinanceOllamaApi {
    param(
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [int]$TimeoutSeconds = 5
    )

    try {
        $tags = Invoke-RestMethod -Uri "$Endpoint/api/tags" -TimeoutSec $TimeoutSeconds
        return [pscustomobject]@{
            ready = $true
            tags = $tags
            error_code = $null
        }
    } catch {
        return [pscustomobject]@{
            ready = $false
            tags = $null
            error_code = "OLLAMA_PROVIDER_UNAVAILABLE"
        }
    }
}

function Wait-AI4BinanceOllamaApi {
    param(
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [int]$TimeoutSeconds = 60,
        [int]$PollSeconds = 2
    )

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds([Math]::Max(1, $TimeoutSeconds))
    do {
        $probe = Test-AI4BinanceOllamaApi -Endpoint $Endpoint -TimeoutSeconds 5
        if ($probe.ready) {
            return $probe
        }
        if ([DateTimeOffset]::UtcNow -lt $deadline) {
            Start-Sleep -Seconds ([Math]::Max(1, $PollSeconds))
        }
    } while ([DateTimeOffset]::UtcNow -lt $deadline)
    return $probe
}

function Ensure-AI4BinanceOllamaApi {
    param(
        [Parameter(Mandatory = $true)][string]$OllamaPath,
        [Parameter(Mandatory = $true)][string]$Endpoint,
        [int]$TimeoutSeconds = 60
    )

    $uri = [Uri]$Endpoint
    $port = if ($uri.IsDefaultPort) { 80 } else { $uri.Port }
    $initialProbe = Test-AI4BinanceOllamaApi -Endpoint $Endpoint -TimeoutSeconds 5
    $providerStarted = $false
    $providerPid = $null

    if (-not $initialProbe.ready) {
        $listeners = @(Get-AI4BinanceOllamaListeners -Port $port)
        $unsafeListeners = @(
            $listeners | Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") }
        )
        if ($unsafeListeners.Count -gt 0) {
            $unsafePids = @($unsafeListeners | ForEach-Object { [int]$_.OwningProcess } | Sort-Object -Unique)
            foreach ($unsafePid in $unsafePids) {
                Stop-Process -Id $unsafePid -Force -ErrorAction SilentlyContinue
            }
            Start-Sleep -Seconds 2
            $listeners = @(Get-AI4BinanceOllamaListeners -Port $port)
        }
        if ($listeners.Count -eq 0) {
            $cmd = [Environment]::GetEnvironmentVariable("ComSpec")
            if (-not $cmd) {
                $cmd = "cmd.exe"
            }
            $argumentList = @(
                "/d",
                "/c",
                "set OLLAMA_HOST=127.0.0.1:11434&& `"$OllamaPath`" serve"
            )
            $provider = Start-Process `
                -FilePath $cmd `
                -ArgumentList $argumentList `
                -WindowStyle Hidden `
                -PassThru
            $providerStarted = $true
            $providerPid = $provider.Id
        }
    }

    $probe = Wait-AI4BinanceOllamaApi `
        -Endpoint $Endpoint `
        -TimeoutSeconds $TimeoutSeconds
    $listeners = @(Get-AI4BinanceOllamaListeners -Port $port)
    $listenerPids = @($listeners | ForEach-Object { $_.OwningProcess } | Sort-Object -Unique)
    $errorCode = $probe.error_code
    $unsafeListeners = @(
        $listeners | Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") }
    )
    if ($unsafeListeners.Count -gt 0) {
        $errorCode = "OLLAMA_LISTENER_NOT_LOOPBACK"
    }
    if (-not $probe.ready -and -not $providerStarted -and $listenerPids.Count -gt 0) {
        $errorCode = "PROVIDER_LISTENER_PRESENT_BUT_UNHEALTHY"
    }

    return [pscustomobject]@{
        ready = [bool]$probe.ready
        tags = $probe.tags
        endpoint = $Endpoint
        provider_started = $providerStarted
        provider_pid = $providerPid
        listener_pids = $listenerPids
        loopback_only = $unsafeListeners.Count -eq 0
        error_code = $errorCode
    }
}

function Test-AI4BinanceOllamaModel {
    param(
        [Parameter(Mandatory = $true)]$Tags,
        [Parameter(Mandatory = $true)][string]$Model
    )

    $modelNames = @($Tags.models | ForEach-Object { [string]$_.name })
    return $modelNames -contains $Model
}
