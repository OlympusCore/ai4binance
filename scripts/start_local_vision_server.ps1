param(
    [ValidateSet("Start", "Status")]
    [string]$Mode = "Start",
    [string]$ModelPath = $(Join-Path $PSScriptRoot "..\\models\\local-vl\\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"),
    [string]$MmprojPath = $(Join-Path $PSScriptRoot "..\\models\\local-vl\\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"),
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8081,
    [int]$CtxSize = 4096,
    [int]$GpuLayers = 99,
    [int]$Parallel = 1,
    [int]$Threads = 8,
    [switch]$AllowConcurrentGpu
)

$ErrorActionPreference = "Stop"
$expectedModelSha256 = "d02fe9b69ad8cadbbd228e387667af66612c44bed29ffc8eb1e7caf9ac486c12"
$expectedModelBytes = 1929901056L
$expectedMmprojSha256 = "980c9b2f78c04e6cff93d277ada09e768394f112d75db3b4e9dea8a69f9fb904"
$expectedMmprojBytes = 844757728L

if ($HostName -notin @("127.0.0.1", "localhost", "::1")) {
    throw "Vision server host must be loopback: $HostName"
}

function Test-LoopbackPortOpen {
    param([Parameter(Mandatory = $true)][int]$TargetPort)

    try {
        $client = [Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect("127.0.0.1", $TargetPort, $null, $null)
        $open = $async.AsyncWaitHandle.WaitOne(500, $false)
        if ($open) {
            $client.EndConnect($async)
        }
        $client.Close()
        return $open
    } catch {
        return $false
    }
}

function Test-ExpectedArtifact {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][Int64]$ExpectedBytes,
        [Parameter(Mandatory = $true)][string]$ExpectedSha256
    )

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $false
    }
    $item = Get-Item -LiteralPath $Path
    if ($item.Length -ne $ExpectedBytes) {
        return $false
    }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() -eq $ExpectedSha256
}

$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$model = [IO.Path]::GetFullPath($ModelPath)
$mmproj = [IO.Path]::GetFullPath($MmprojPath)

if ($Mode -eq "Status") {
    [pscustomobject]@{
        model_id = "local-llamacpp-qwen25vl-3b"
        server_url = "http://$HostName`:$Port"
        loopback_only = $true
        model_verified = Test-ExpectedArtifact -Path $model -ExpectedBytes $expectedModelBytes -ExpectedSha256 $expectedModelSha256
        mmproj_verified = Test-ExpectedArtifact -Path $mmproj -ExpectedBytes $expectedMmprojBytes -ExpectedSha256 $expectedMmprojSha256
        listening = Test-LoopbackPortOpen -TargetPort $Port
        execution_allowed = $false
        promotion_status = "RESEARCH_ONLY"
        live_eligibility_status = "LIVE_ORDER_BLOCKED"
    } | ConvertTo-Json -Depth 3
    exit 0
}

if (-not (Test-ExpectedArtifact -Path $model -ExpectedBytes $expectedModelBytes -ExpectedSha256 $expectedModelSha256)) {
    throw "Vision model GGUF is missing, incomplete, or hash-mismatched: $model"
}
if (-not (Test-ExpectedArtifact -Path $mmproj -ExpectedBytes $expectedMmprojBytes -ExpectedSha256 $expectedMmprojSha256)) {
    throw "Vision projector GGUF is missing, incomplete, or hash-mismatched: $mmproj"
}
if (Test-LoopbackPortOpen -TargetPort $Port) {
    Write-Host "Vision server is already listening: http://$HostName`:$Port"
    exit 0
}
if (-not $AllowConcurrentGpu -and (Test-LoopbackPortOpen -TargetPort 8080)) {
    throw "A local llama.cpp server is already listening on 127.0.0.1:8080. Stop it before starting the vision server, or explicitly pass -AllowConcurrentGpu after capacity review."
}

& (Join-Path $root "scripts\\start_llama_server.ps1") `
    -ModelPath $model `
    -MmprojPath $mmproj `
    -HostName $HostName `
    -Port $Port `
    -CtxSize $CtxSize `
    -GpuLayers $GpuLayers `
    -Parallel $Parallel `
    -Threads $Threads
