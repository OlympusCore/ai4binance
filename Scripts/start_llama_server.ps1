param(
    [string]$ModelPath = $env:AI4BINANCE_LLAMA_MODEL_PATH,
    [string]$LlamaCppRoot = $(if ($env:LLAMA_CPP_ROOT) { $env:LLAMA_CPP_ROOT } else { "" }),
    [string]$HostName = $(if ($env:LLAMA_HOST) { $env:LLAMA_HOST } else { "127.0.0.1" }),
    [int]$Port = $(if ($env:LLAMA_PORT) { [int]$env:LLAMA_PORT } else { 8080 }),
    [int]$CtxSize = $(if ($env:LLAMA_CTX_LIMIT) { [int]$env:LLAMA_CTX_LIMIT } else { 4096 }),
    [int]$GpuLayers = $(if ($env:LLAMA_GPU_LAYERS) { [int]$env:LLAMA_GPU_LAYERS } else { 0 }),
    [int]$Parallel = $(if ($env:LLAMA_PARALLEL) { [int]$env:LLAMA_PARALLEL } else { 2 }),
    [int]$Threads = $(if ($env:LLAMA_THREADS) { [int]$env:LLAMA_THREADS } else { 8 })
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

if (-not $LlamaCppRoot -or -not (Test-Path -LiteralPath $LlamaCppRoot -PathType Container)) {
    $rootCandidates = @(
        (Join-Path $root "Tools\llama.cpp"),
        "C:\vscode-projects\llama.cpp",
        $LlamaCppRoot
    ) | Where-Object { $_ }
    $LlamaCppRoot = $rootCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $LlamaCppRoot) {
        $LlamaCppRoot = Join-Path $root "Tools\llama.cpp"
    }
}

if ($HostName -notin @("127.0.0.1", "localhost", "::1")) {
    throw "llama.cpp host loopback olmalı: $HostName"
}

$serverPrefixArgs = @()
$serverCandidates = @(
    @{ Path = (Join-Path $LlamaCppRoot "llama.exe"); Prefix = @("serve") },
    @{ Path = (Join-Path $LlamaCppRoot "ai4binance-llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "llama-server-local.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "build\bin\Release\llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "build\bin\llama-server.exe"); Prefix = @() },
    @{ Path = (Join-Path $LlamaCppRoot "llama-server.exe"); Prefix = @() }
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
        Sort-Object @{ Expression = { if ($_.Name -eq "llama.exe") { 0 } else { 1 } } }, FullName |
        Select-Object -ExpandProperty FullName -First 1
    if ($serverExe -and (Split-Path $serverExe -Leaf) -eq "llama.exe") {
        $serverPrefixArgs = @("serve")
    }
}
if (-not $serverExe) {
    throw "llama.cpp server launcher bulunamadı. LLAMA_CPP_ROOT değerini doğru llama.cpp klasörüne ayarla veya Tools\llama.cpp altına resmi Windows paketini çıkar."
}

if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath)) {
    $modelCandidates = @(
        $ModelPath,
        (Join-Path $root "Models\local-llm\Qwen3-8B-Q4_K_M.gguf"),
        (Join-Path $root "Models\local-llm\Llama-3.1-8B-Instruct-Q4_K_M.gguf"),
        (Join-Path $LlamaCppRoot "models\Qwen3-8B-Q4_K_M.gguf"),
        "C:\vscode-projects\ai4ohs-hybrid\models\base\Llama-3.1-8B-Instruct-Q4_K_M.gguf"
    ) | Where-Object { $_ }
    $ModelPath = $modelCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}

if (-not $ModelPath -or -not (Test-Path -LiteralPath $ModelPath)) {
    throw "GGUF model bulunamadı. AI4BINANCE_LLAMA_MODEL_PATH ile Qwen3 8B Q4_K_M GGUF yolunu belirt."
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
    Write-Host "llama-server zaten dinliyor: http://$HostName`:$Port"
    exit 0
}

$arguments = @($serverPrefixArgs) + @(
    "--model", $ModelPath,
    "--host", $HostName,
    "--port", "$Port",
    "--ctx-size", "$CtxSize",
    "--threads", "$Threads",
    "--n-gpu-layers", "$GpuLayers",
    "--parallel", "$Parallel"
)

New-Item -ItemType Directory -Path (Join-Path $root "Logs") -Force | Out-Null
$stdoutPath = Join-Path $root "Logs\llama-server.stdout.log"
$stderrPath = Join-Path $root "Logs\llama-server.stderr.log"
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
        Write-Error "llama-server erken kapandı. Stderr son satırlar:"
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
    Write-Error "llama-server portu zamanında açılmadı: http://$HostName`:$Port"
    exit 1
}

Write-Host "llama-server başlatıldı: http://$HostName`:$Port/completion"
Write-Host "Model: $ModelPath"
Write-Host "Log: $stdoutPath"
