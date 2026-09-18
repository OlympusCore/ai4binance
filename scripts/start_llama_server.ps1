param(
    [string]$ModelPath = $env:AI4BINANCE_LLAMA_MODEL_PATH,
    [string]$LlamaCppRoot = $(if ($env:LLAMA_CPP_ROOT) { $env:LLAMA_CPP_ROOT } else { "" }),
    [string]$HostName = $(if ($env:LLAMA_HOST) { $env:LLAMA_HOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:LLAMA_PORT) { [int]$env:LLAMA_PORT } else { 8080 }),
    [string]$MmprojPath = $env:AI4BINANCE_LLAMA_MMPROJ_PATH,
    [int]$CtxSize = $(if ($env:LLAMA_CTX_LIMIT) { [int]$env:LLAMA_CTX_LIMIT } else { 4096 }),
    [int]$GpuLayers = $(if ($env:AI4BINANCE_LLAMA_GPU_LAYERS) { [int]$env:AI4BINANCE_LLAMA_GPU_LAYERS } elseif ($env:LLAMA_GPU_LAYERS) { [int]$env:LLAMA_GPU_LAYERS } else { 0 }),
    [int]$Parallel = $(if ($env:AI4BINANCE_LLAMA_PARALLEL) { [int]$env:AI4BINANCE_LLAMA_PARALLEL } elseif ($env:LLAMA_PARALLEL) { [int]$env:LLAMA_PARALLEL } else { 2 }),
    [int]$Threads = $(if ($env:AI4BINANCE_LLAMA_THREADS) { [int]$env:AI4BINANCE_LLAMA_THREADS } elseif ($env:LLAMA_THREADS) { [int]$env:LLAMA_THREADS } else { 8 })
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

function Get-AI4BinanceQwen3BlobPath {
    param([Parameter(Mandatory = $true)][string]$HomePath)

    $manifestPath = Join-Path $HomePath ".ollama\models\manifests\registry.ollama.ai\library\qwen3\8b"
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        return $null
    }
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } catch {
        return $null
    }
    $modelLayer = @($manifest.layers | Where-Object {
        [string]$_.mediaType -eq "application/vnd.ollama.image.model"
    } | Select-Object -First 1)
    if ($modelLayer.Count -eq 0 -or -not $modelLayer[0].digest) {
        return $null
    }
    $digest = ([string]$modelLayer[0].digest).Replace("sha256:", "")
    $blobPath = Join-Path (Join-Path $HomePath ".ollama\models\blobs") ("sha256-$digest")
    if (Test-Path -LiteralPath $blobPath -PathType Leaf) {
        return $blobPath
    }
    return $null
}

if (-not $LlamaCppRoot -or -not (Test-Path -LiteralPath $LlamaCppRoot -PathType Container)) {
    $rootCandidates = @(
        (Join-Path $root "tools\llama.cpp"),
        $LlamaCppRoot
    ) | Where-Object { $_ }
    $LlamaCppRoot = $rootCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $LlamaCppRoot) {
        $LlamaCppRoot = Join-Path $root "tools\llama.cpp"
    }
}

if ($HostName -notin @("127.0.0.1", "localhost", "::1")) {
    throw "llama.cpp host must be loopback: $HostName"
}

$serverPrefixArgs = @()
$serverExe = $null
$serverCandidates = @(
    @{ Path = (Join-Path $LlamaCppRoot "llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "ai4binance-llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "llama-server-local.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "build\bin\Release\llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "build\bin\llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "llama.exe"); Prefix = @("serve") }
)
$serverCandidate = $serverCandidates |
    Where-Object { Test-Path -LiteralPath $_.Path -PathType Leaf } |
    Select-Object -First 1
if ($null -ne $serverCandidate) {
    $serverExe = [string]$serverCandidate.Path
    $serverPrefixArgs = @($serverCandidate.Prefix)
}
if (-not $serverExe -and (Test-Path -LiteralPath $LlamaCppRoot -PathType Container)) {
    $serverExe = Get-ChildItem -LiteralPath $LlamaCppRoot -Recurse -File -Include "llama.exe", "ai4binance-llama-server.exe", "llama-server-local.exe", "llama-server.exe" |
        Sort-Object @{ Expression = {
            switch ($_.Name) {
                "llama-server.exe" { 0 }
                "ai4binance-llama-server.exe" { 1 }
                "llama-server-local.exe" { 2 }
                "llama.exe" { 3 }
                default { 4 }
            }
        } }, FullName |
        Select-Object -ExpandProperty FullName -First 1
    if ($serverExe -and (Split-Path $serverExe -Leaf) -eq "llama.exe") {
        $serverPrefixArgs = @("serve")
    }
}
if (-not $serverExe) {
    $commandCandidates = @("llama-server.exe", "llama.exe")
    foreach ($commandName in $commandCandidates) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $command -and $command.Source) {
            $serverExe = [string]$command.Source
            if ((Split-Path $serverExe -Leaf) -eq "llama.exe") {
                $serverPrefixArgs = @("serve")
            }
            break
        }
    }
}
if (-not $serverExe) {
    throw "llama.cpp server launcher was not found. Set LLAMA_CPP_ROOT to the llama.cpp directory or extract the official Windows package under tools\llama.cpp."
}

 $portOpen = $false
try {
    $client = [Net.Sockets.TcpClient]::new()
    $async = $client.BeginConnect($HostName, $Port, $null, $null)
    $portOpen = $async.AsyncWaitHandle.WaitOne(500, $false)
    if ($portOpen) {
        $client.EndConnect($async)
    }
    $client.Close()
} catch {
    $portOpen = $false
}

if ($portOpen) {
    Write-Host "llama-server is already listening: http://$HostName`:$Port"
    exit 0
}

if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath)) {
    $homePath = [Environment]::GetFolderPath([Environment+SpecialFolder]::UserProfile)
    $modelCandidates = @(
        $ModelPath,
        (Join-Path $root "models\local-llm\Qwen3-8B-Q4_K_M.gguf"),
        (Join-Path $root "models\local-llm\Llama-3.1-8B-Instruct-Q4_K_M.gguf"),
        (Join-Path $LlamaCppRoot "models\Qwen3-8B-Q4_K_M.gguf"),
        (Get-AI4BinanceQwen3BlobPath -HomePath $homePath)
    ) | Where-Object { $_ }
    $ModelPath = $modelCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath)) {
    throw "GGUF model was not found. Set AI4BINANCE_LLAMA_MODEL_PATH or place the Qwen3 8B GGUF under .ollama\\models\\blobs or tools\\llama.cpp\\models."
}
if ($MmprojPath -and -not (Test-Path -LiteralPath $MmprojPath -PathType Leaf)) {
    throw "Multimodal projector GGUF was not found: $MmprojPath"
}

$arguments = @($serverPrefixArgs) + @(
    "--model", $ModelPath,
    "--host", $HostName,
    "--port", "$Port",
    "--cors-origins", "localhost",
    "--no-cors-credentials",
    "--ctx-size", "$CtxSize",
    "--threads", "$Threads",
    "--n-gpu-layers", "$GpuLayers",
    "--parallel", "$Parallel"
)
if ($MmprojPath) {
    $arguments += @("--mmproj", $MmprojPath)
}

New-Item -ItemType Directory -Path (Join-Path $root "runtime\logs") -Force | Out-Null
$stdoutPath = Join-Path $root "runtime\logs\llama-server.stdout.log"
$stderrPath = Join-Path $root "runtime\logs\llama-server.stderr.log"
$process = Start-Process `
    -FilePath $serverExe `
    -ArgumentList $arguments `
    -WorkingDirectory (Split-Path $serverExe -Parent) `
    -WindowStyle Hidden `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -PassThru

$deadline = [DateTimeOffset]::UtcNow.AddSeconds(180)
while ([DateTimeOffset]::UtcNow -lt $deadline) {
    Start-Sleep -Seconds 2
    if ($process.HasExited) {
        Write-Error "llama-server exited early. Recent stderr lines:"
        if (Test-Path -LiteralPath $stderrPath -PathType Leaf) {
            Get-Content -LiteralPath $stderrPath -Tail 40 | ForEach-Object { Write-Error $_ }
        }
        exit 1
    }
    try {
        $client = [Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($HostName, $Port, $null, $null)
        $ready = $async.AsyncWaitHandle.WaitOne(500, $false)
        if ($ready) {
            $client.EndConnect($async)
            $client.Close()
            break
        }
        $client.Close()
    } catch {
        continue
    }
}

if ([DateTimeOffset]::UtcNow -ge $deadline) {
    Write-Error "llama-server did not open the port before timeout: http://$HostName`:$Port"
    exit 1
}

Write-Host "llama-server started: http://$HostName`:$Port/completion"
Write-Host "Model: $ModelPath"
Write-Host "Log: $stdoutPath"

