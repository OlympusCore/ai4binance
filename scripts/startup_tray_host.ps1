param(
    [string]$StatusScript = "startup_status.ps1",
    [string]$TrayIconPath = "H:\GoogleDrive\_archive\icon_set\icon\sync.ico",
    [string]$LlamaServerScript = "start_llama_server.ps1"
)

$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "initialize_runtime_environment.ps1")
$root = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$statusScriptPath = Join-Path $PSScriptRoot $StatusScript
$llamaServerScriptPath = Join-Path $PSScriptRoot $LlamaServerScript
$stateDirectory = Join-Path $root "runtime\state"
$logDirectory = Join-Path $root "runtime\logs\services"
$llamaHost = "127.0.0.1"
$llamaPort = 8080
$llamaEndpoint = "http://$llamaHost`:$llamaPort"
$maxHistoryTurns = if ($env:AI4BINANCE_PROMPTER_HISTORY_TURNS) { [int]$env:AI4BINANCE_PROMPTER_HISTORY_TURNS } else { 4 }
$timeoutSeconds = if ($env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS) { [int]$env:AI4BINANCE_PROMPTER_TIMEOUT_SECONDS } else { 90 }
$maxPredictTokens = if ($env:AI4BINANCE_PROMPTER_MAX_PREDICT) { [int]$env:AI4BINANCE_PROMPTER_MAX_PREDICT } else { 256 }
$privateAccountStatePath = Join-Path $stateDirectory "private\account-management.json"
$assistantWalletContextScriptPath = Join-Path $PSScriptRoot "assistant_wallet_context.ps1"

if (-not (Test-Path -LiteralPath $statusScriptPath -PathType Leaf)) {
    throw "Status script not found: $statusScriptPath"
}
if (-not (Test-Path -LiteralPath $assistantWalletContextScriptPath -PathType Leaf)) {
    throw "Assistant wallet context script not found: $assistantWalletContextScriptPath"
}
. $assistantWalletContextScriptPath

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

function Get-NotifyIcon {
    param([string]$Path)

    if ($Path -and (Test-Path -LiteralPath $Path -PathType Leaf)) {
        try {
            return New-Object System.Drawing.Icon($Path)
        }
        catch {
            return [System.Drawing.SystemIcons]::Application
        }
    }

    return [System.Drawing.SystemIcons]::Application
}

function Get-PromptText {
    return @"
You are the local AI4BINANCE Assistant.

Rules:
- Respond only in Turkish.
- Answer directly, briefly, and naturally.
- Use one short paragraph for simple yes/no or status questions.
- Do not add headings, decorative symbols, emoji, role labels, or timestamps.
- Base every factual claim about the system, account, wallet, current value, or opportunity on verified local context supplied by the host.
- Chat history and previous assistant answers are not evidence. Correct an earlier unsupported claim instead of repeating it.
- Never infer that a user-provided label such as binance_wallet or binan_wallet is a defined or active system object.
- If verified local context is missing, say that the fact cannot be verified; do not provide a generic or invented answer.
- Translate raw field names and blocker codes into natural Turkish when context provides them.
- You have no authority to place live orders, increase risk, modify files, or access external services.
"@
}

function Test-LlamaServerReady {
    param([int]$Port = $llamaPort)

    try {
        $client = [System.Net.Sockets.TcpClient]::new()
        $async = $client.BeginConnect($llamaHost, $Port, $null, $null)
        $ready = $async.AsyncWaitHandle.WaitOne(250, $false)
        if ($ready) {
            $client.EndConnect($async)
            $client.Close()
            return $true
        }
        $client.Close()
    }
    catch {
        return $false
    }

    return $false
}

function Start-LlamaServerHidden {
    if (Test-LlamaServerReady) {
        return
    }

    if (-not (Test-Path -LiteralPath $llamaServerScriptPath -PathType Leaf)) {
        return
    }

    $powerShell = if (Get-Command pwsh.exe -ErrorAction SilentlyContinue) {
        (Get-Command pwsh.exe -ErrorAction Stop).Source
    }
    else {
        (Get-Command powershell.exe -ErrorAction Stop).Source
    }

    Start-Process `
        -FilePath $powerShell `
        -ArgumentList @(
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            $llamaServerScriptPath
        ) `
        -WorkingDirectory $root `
        -WindowStyle Hidden | Out-Null
}

function Wait-LlamaServerReady {
    param([int]$TimeoutSeconds = 120)

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (Test-LlamaServerReady) {
            return $true
        }
        Start-Sleep -Seconds 2
    }

    return $false
}

function Get-IstanbulTimeZone {
    foreach ($timeZoneId in @("Turkey Standard Time", "Europe/Istanbul")) {
        try {
            return [TimeZoneInfo]::FindSystemTimeZoneById($timeZoneId)
        }
        catch {
            continue
        }
    }
    return [TimeZoneInfo]::Utc
}

function Format-IstanbulTimestamp {
    param([Parameter(Mandatory = $true)][DateTimeOffset]$Instant)

    $timeZone = Get-IstanbulTimeZone
    $converted = [TimeZoneInfo]::ConvertTime($Instant, $timeZone)
    return $converted.ToString("yyyy-MM-dd HH:mm:ss zzz")
}

function Get-CurrentIstanbulTimestamp {
    return Format-IstanbulTimestamp -Instant ([DateTimeOffset]::UtcNow)
}

function Get-HumanReadableRuntimeState {
    param([Parameter(Mandatory = $true)][string]$State)

    switch ($State) {
        "READY" { return "hazir" }
        "COLLECTED" { return "calisiyor" }
        "DEGRADED" { return "kisitli" }
        "unavailable" { return "veri yok" }
        default { return $State.ToLowerInvariant() }
    }
}

function Get-JsonState {
    param([Parameter(Mandatory = $true)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Test-SystemStatusQuery {
    param([Parameter(Mandatory = $true)][string]$InputText)

    $normalized = $InputText.Trim().ToLowerInvariant()
    return $normalized -match "(?:^|[\s/])(?:status|durum|özet|summary|system|sistem|son durum)(?:$|[\s/])"
}

function Test-FastLocalStatusQuery {
    param([Parameter(Mandatory = $true)][string]$InputText)

    $normalized = $InputText.Trim().ToLowerInvariant()
    if ($normalized -match "(auto[- ]?learn|controlled learning|öğrenme|learning)") {
        return $normalized -match "(aktif mi|çalışıyor mu|calisiyor mu|açık mı|acik mi|durum|hazır mı|hazir mi)"
    }

    return $normalized -match "(?:^|[\s/])(?:status|durum|özet|summary|system|sistem|son durum)(?:$|[\s/])"
}

function Get-SystemStatusSnapshot {
    $observedAt = [DateTimeOffset]::UtcNow
    $timestamp = Format-IstanbulTimestamp -Instant $observedAt
    $health = Get-JsonState -Path (Join-Path $stateDirectory "qwen-prompter-health.json")
    $runtime = Get-JsonState -Path (Join-Path $stateDirectory "runtime.json")
    $runtimeState = if ($null -ne $runtime) {
        [string]$runtime.state
    }
    else {
        "unavailable"
    }
    $runtimeStateLabel = Get-HumanReadableRuntimeState -State $runtimeState
    $blockerCount = if ($null -ne $runtime -and $null -ne $runtime.blockers) {
        @($runtime.blockers).Count
    }
    else {
        0
    }
    $healthStatus = if ($null -ne $health) {
        "Prompter durumu: $($health.status); provider: $($health.provider); model: $($health.model); endpoint: $($health.endpoint)"
    }
    else {
        "Prompter durumu: unavailable"
    }
    $runtimeStatus = if ($null -ne $runtime) {
        "Calisma durumu: $runtimeStateLabel; aktif engel sayisi: $blockerCount"
    }
    else {
        "Calisma durumu: unavailable"
    }
    return @"
Sistem durum ozeti
Gozlem saati (Europe/Istanbul): $timestamp
$healthStatus
$runtimeStatus
Yonlendirme: kisa cevap ver, blokaj varsa soyle ve gerekiyorsa bir sonraki adimi ekle.
"@
}

function Get-FastLocalAnswer {
    param(
        [Parameter(Mandatory = $true)][string]$InputText,
        [string]$ContextText = ""
    )

    $walletAnswer = Get-AI4BinanceWalletAnswer `
        -InputText $InputText `
        -ContextText $ContextText `
        -StatePath $privateAccountStatePath
    if ($walletAnswer.handled) {
        $timestamp = Get-CurrentIstanbulTimestamp
        return "$($walletAnswer.message)`n[Europe/Istanbul time: $timestamp]"
    }

    if (-not (Test-FastLocalStatusQuery -InputText $InputText)) {
        return $null
    }

    $normalized = $InputText.Trim().ToLowerInvariant()
    $timestamp = Get-CurrentIstanbulTimestamp

    if ($normalized -match "(auto[- ]?learn|controlled learning|öğrenme|learning)") {
        $learningSummary = Get-JsonState -Path (Join-Path $stateDirectory "learning_summary.json")
        $runtime = Get-JsonState -Path (Join-Path $stateDirectory "runtime.json")
        $learningStatus = if ($null -ne $runtime -and $null -ne $runtime.controlled_learning) {
            [string]$runtime.controlled_learning.status
        }
        elseif ($null -ne $learningSummary) {
            if ($true -eq $learningSummary.execution_allowed) { "ACTIVE" } else { "RESEARCH_ONLY" }
        }
        else {
            "UNKNOWN"
        }
        $promotionStatus = if ($null -ne $runtime -and $null -ne $runtime.controlled_learning) {
            [string]$runtime.controlled_learning.promotion_status
        }
        elseif ($null -ne $learningSummary) {
            [string]$learningSummary.promotion_status
        }
        else {
            "UNKNOWN"
        }
        $executionAllowed = if ($null -ne $runtime -and $null -ne $runtime.controlled_learning) {
            [bool]$runtime.controlled_learning.execution_allowed
        }
        elseif ($null -ne $learningSummary) {
            [bool]$learningSummary.execution_allowed
        }
        else {
            $false
        }
        $riskChangeAllowed = if ($null -ne $runtime -and $null -ne $runtime.controlled_learning) {
            [bool]$runtime.controlled_learning.risk_change_allowed
        }
        elseif ($null -ne $learningSummary) {
            [bool]$learningSummary.risk_change_allowed
        }
        else {
            $false
        }

        $shortAnswer = if ($executionAllowed) { "Evet" } elseif ($learningStatus -eq "UNKNOWN") { "Bilinmiyor" } else { "Hayir" }
        return @"
Kisa cevap: $shortAnswer. Auto-learn durumu: $learningStatus. Promotion: $promotionStatus. Execution: $executionAllowed. Risk: $riskChangeAllowed.
Not: kontrollu ogrenme sadece research-only calisir; kendi kendine canli yetki veya risk degisikligi vermez.
[Europe/Istanbul time: $timestamp]
"@
    }

    $runtime = Get-JsonState -Path (Join-Path $stateDirectory "runtime.json")
    $runtimeState = if ($null -ne $runtime) {
        [string]$runtime.state
    }
    else {
        "unavailable"
    }
    $runtimeStateLabel = Get-HumanReadableRuntimeState -State $runtimeState
    $blockerCount = if ($null -ne $runtime -and $null -ne $runtime.blockers) {
        @($runtime.blockers).Count
    }
    else {
        0
    }
    $statusSummary = if ($runtimeState -eq "DEGRADED" -or $blockerCount -gt 0) {
        "Kisa cevap: Hayir, tam otonom degil. Calisma durumu $runtimeStateLabel ve $blockerCount aktif engel var."
    }
    elseif ($runtimeState -eq "READY" -or $runtimeState -eq "COLLECTED") {
        "Kisa cevap: Evet, sistem calisiyor."
    }
    elseif ($runtimeState -eq "unavailable") {
        "Kisa cevap: Durum verisi alinmadi."
    }
    else {
        "Kisa cevap: Calisma durumu $runtimeStateLabel."
    }
    return @"
$statusSummary
Not: canli emir yetkisi kapali; bu akis research-only / simulation odakli calisir.
[Europe/Istanbul time: $timestamp]
"@
}

function Convert-MessagesToPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$SystemPrompt,
        [Parameter(Mandatory = $true)][object[]]$Messages
    )

    $builder = [System.Text.StringBuilder]::new()
    [void]$builder.AppendLine("### System:")
    [void]$builder.AppendLine($SystemPrompt.Trim())
    [void]$builder.AppendLine("")
    foreach ($message in $Messages) {
        $role = [string]$message.role
        $content = [string]$message.content
        if ([string]::IsNullOrWhiteSpace($content)) {
            continue
        }
        switch ($role) {
            "user" {
                [void]$builder.AppendLine("### User:")
                [void]$builder.AppendLine($content.Trim())
                [void]$builder.AppendLine("")
            }
            "assistant" {
                [void]$builder.AppendLine("### Assistant:")
                [void]$builder.AppendLine($content.Trim())
                [void]$builder.AppendLine("")
            }
        }
    }
    [void]$builder.Append("### Assistant:")
    return $builder.ToString()
}

function Invoke-LlamaCompletion {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    $content = $null
    try {
        $client.Timeout = [TimeSpan]::FromSeconds($TimeoutSeconds)
        $body = [ordered]@{
            prompt = $Prompt
            temperature = 0
            n_predict = $maxPredictTokens
            stop = @("### User:", "### System:", "</s>")
        } | ConvertTo-Json -Depth 20
        $content = [System.Net.Http.StringContent]::new(
            $body,
            [System.Text.Encoding]::UTF8,
            "application/json"
        )
        $response = $client.PostAsync("$llamaEndpoint/completion", $content).GetAwaiter().GetResult()
        $responseText = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $statusCode = [int]$response.StatusCode
            throw "llama.cpp completion HTTP $statusCode $($response.ReasonPhrase): $responseText"
        }
        $payload = $responseText | ConvertFrom-Json
        $answer = [string]$payload.content
        if ([string]::IsNullOrWhiteSpace($answer)) {
            throw "LOCAL_LLM_EMPTY_RESPONSE"
        }
        return $answer.Trim()
    }
    catch [System.Threading.Tasks.TaskCanceledException] {
        throw "LLAMA_CPP_CHAT_TIMEOUT"
    }
    finally {
        if ($null -ne $content) {
            $content.Dispose()
        }
        $client.Dispose()
    }
}

function Add-ChatTranscriptLine {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Forms.TextBox]$Box,
        [Parameter(Mandatory = $true)][string]$Text
    )

    if ($Box.TextLength -gt 0) {
        $Box.AppendText([Environment]::NewLine)
        $Box.AppendText([Environment]::NewLine)
    }
    $Box.AppendText($Text)
    $Box.SelectionStart = $Box.TextLength
    $Box.ScrollToCaret()
}

function Invoke-ChatSend {
    param(
        [Parameter(Mandatory = $true)][System.Windows.Forms.Control]$SenderControl
    )

    try {
        $SenderForm = $SenderControl.FindForm()
        if ($null -eq $SenderForm) {
            $SenderForm = $script:assistantChatForm
        }
        if ($null -eq $SenderForm) {
            throw "CHAT_FORM_NOT_AVAILABLE"
        }

        $chatState = [pscustomobject]$SenderForm.Tag
        $inputText = [string]$chatState.InputBox.Text
        $trimmed = $inputText.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            return
        }

        $questionTimestamp = Get-CurrentIstanbulTimestamp

        $chatState.InputBox.Clear()
        Add-ChatTranscriptLine -Box $chatState.TranscriptBox -Text ("You [" + $questionTimestamp + "]: " + $trimmed)
        $chatState.Messages.Add([ordered]@{ role = "user"; content = "$trimmed`n`n[Europe/Istanbul time: $questionTimestamp]" })
        while ($chatState.Messages.Count -gt (1 + ($maxHistoryTurns * 2))) {
            $chatState.Messages.RemoveAt(1)
        }

        $recentUserContext = @(
            $chatState.Messages |
                Where-Object { [string]$_.role -eq "user" } |
                Select-Object -Last 3 |
                ForEach-Object { [string]$_.content }
        ) -join "`n"
        $quickAnswer = Get-FastLocalAnswer `
            -InputText $trimmed `
            -ContextText $recentUserContext
        if ($null -ne $quickAnswer) {
            $chatState.Messages.Add([ordered]@{ role = "assistant"; content = $quickAnswer })
            Add-ChatTranscriptLine -Box $chatState.TranscriptBox -Text ("Assistant: " + $quickAnswer)
            return
        }

        $effectiveSystemPrompt = $chatState.SystemPrompt
        if (Test-SystemStatusQuery -InputText $trimmed) {
            $effectiveSystemPrompt = $effectiveSystemPrompt + "`n`n" + (Get-SystemStatusSnapshot)
        }

        $prompt = Convert-MessagesToPrompt -SystemPrompt $effectiveSystemPrompt -Messages @($chatState.Messages)
        $SenderForm.Cursor = [System.Windows.Forms.Cursors]::WaitCursor
        $chatState.SendButton.Enabled = $false
        $SenderForm.Refresh()
        Add-ChatTranscriptLine -Box $chatState.TranscriptBox -Text "Asistan dusunuyor..."

        Start-LlamaServerHidden
        if (-not (Wait-LlamaServerReady -TimeoutSeconds $timeoutSeconds)) {
            throw "LLAMA_CPP_SERVER_NOT_READY"
        }

        $answer = Format-AI4BinanceAssistantAnswer -Answer (
            Invoke-LlamaCompletion -Prompt $prompt -TimeoutSeconds $timeoutSeconds
        )
        $answerTimestamp = Get-CurrentIstanbulTimestamp
        $chatState.Messages.Add([ordered]@{ role = "assistant"; content = $answer })
        Add-ChatTranscriptLine -Box $chatState.TranscriptBox -Text ("Assistant: " + $answer + "`n[Europe/Istanbul time: $answerTimestamp]")
    }
    catch {
        $errorMessage = $_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($errorMessage)) {
            $errorMessage = "UNHANDLED_CHAT_ERROR"
        }
        Add-ChatTranscriptLine -Box $chatState.TranscriptBox -Text ("Assistant error: " + $errorMessage)
    }
    finally {
        $chatState.SendButton.Enabled = $true
        $SenderForm.Cursor = [System.Windows.Forms.Cursors]::Default
    }
}

function New-ChatWindow {
    $form = New-Object System.Windows.Forms.Form
    $form.Text = "AI4BINANCE Chat"
    $form.StartPosition = [System.Windows.Forms.FormStartPosition]::Manual
    $form.Size = New-Object System.Drawing.Size(860, 640)
    $form.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::SizableToolWindow
    $form.MinimizeBox = $true
    $form.MaximizeBox = $true
    $form.ShowInTaskbar = $false
    $form.TopMost = $false
    $form.Icon = Get-NotifyIcon -Path $TrayIconPath

    $workingArea = [System.Windows.Forms.Screen]::PrimaryScreen.WorkingArea
    $form.Location = New-Object System.Drawing.Point(
        [Math]::Max($workingArea.Right - $form.Width - 8, $workingArea.Left + 8),
        [Math]::Max($workingArea.Bottom - $form.Height - 8, $workingArea.Top + 8)
    )

    $titleLabel = New-Object System.Windows.Forms.Label
    $titleLabel.AutoSize = $true
    $titleLabel.Text = "AI4BINANCE Assistant"
    $titleLabel.Location = New-Object System.Drawing.Point(12, 10)

    $transcriptBox = New-Object System.Windows.Forms.TextBox
    $transcriptBox.Multiline = $true
    $transcriptBox.ReadOnly = $true
    $transcriptBox.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
    $transcriptBox.WordWrap = $true
    $transcriptBox.Font = New-Object System.Drawing.Font("Consolas", 9)
    $transcriptBox.Location = New-Object System.Drawing.Point(12, 34)
    $transcriptBox.Size = New-Object System.Drawing.Size(820, 468)

    $inputBox = New-Object System.Windows.Forms.TextBox
    $inputBox.Multiline = $true
    $inputBox.ScrollBars = [System.Windows.Forms.ScrollBars]::Vertical
    $inputBox.WordWrap = $true
    $inputBox.Font = New-Object System.Drawing.Font("Consolas", 9)
    $inputBox.Location = New-Object System.Drawing.Point(12, 516)
    $inputBox.Size = New-Object System.Drawing.Size(820, 72)

    $sendButton = New-Object System.Windows.Forms.Button
    $sendButton.Text = "Send"
    $sendButton.Location = New-Object System.Drawing.Point(12, 596)
    $sendButton.Size = New-Object System.Drawing.Size(72, 26)

    $clearButton = New-Object System.Windows.Forms.Button
    $clearButton.Text = "Clear"
    $clearButton.Location = New-Object System.Drawing.Point(92, 596)
    $clearButton.Size = New-Object System.Drawing.Size(72, 26)

    $closeButton = New-Object System.Windows.Forms.Button
    $closeButton.Text = "Close"
    $closeButton.Location = New-Object System.Drawing.Point(170, 596)
    $closeButton.Size = New-Object System.Drawing.Size(72, 26)

    $hintLabel = New-Object System.Windows.Forms.Label
    $hintLabel.AutoSize = $true
    $hintLabel.Text = "Enter sends. Shift+Enter inserts a new line. Closing hides the window."
    $hintLabel.Location = New-Object System.Drawing.Point(260, 600)

    $systemPrompt = Get-PromptText
    $messages = [System.Collections.Generic.List[object]]::new()
    $messages.Add([ordered]@{ role = "system"; content = $systemPrompt })

    $state = [pscustomobject]@{
        TranscriptBox = $transcriptBox
        InputBox = $inputBox
        Messages = $messages
        SystemPrompt = $systemPrompt
        SendButton = $sendButton
    }
    $form.Tag = $state
    Add-ChatTranscriptLine -Box $transcriptBox -Text "AI4BINANCE asistani hazir."
    Add-ChatTranscriptLine -Box $transcriptBox -Text "Soru yaz ve Send tusuna bas."

    $sendButton.Add_Click({
        Invoke-ChatSend -SenderControl $sendButton
    })

    $inputBox.Add_KeyDown({
        param($sender, $e)

        if ($e.KeyCode -eq [System.Windows.Forms.Keys]::Enter -and -not $e.Shift) {
            $e.SuppressKeyPress = $true
            Invoke-ChatSend -SenderControl $sender
        }
    })

    $clearButton.Add_Click({
        $transcriptBox.Clear()
        $messages.Clear()
        $messages.Add([ordered]@{ role = "system"; content = $systemPrompt })
        Add-ChatTranscriptLine -Box $transcriptBox -Text "Chat cleared."
    })

    $closeButton.Add_Click({
        $form.Hide()
    })

    $form.Controls.Add($titleLabel)
    $form.Controls.Add($transcriptBox)
    $form.Controls.Add($inputBox)
    $form.Controls.Add($sendButton)
    $form.Controls.Add($clearButton)
    $form.Controls.Add($closeButton)
    $form.Controls.Add($hintLabel)

    $form.Add_FormClosing({
        param($sender, $e)

        if ($script:allowExit) {
            return
        }

        $e.Cancel = $true
        $sender.Hide()
    })

    $form.Add_FormClosed({
        $form.Dispose()
    })

    $script:assistantChatForm = $form
    $form.Show()
    $form.Activate()
    $inputBox.Focus()
}

function Show-AssistantChatWindow {
    if ($null -ne $script:assistantChatForm -and -not $script:assistantChatForm.IsDisposed) {
        $script:assistantChatForm.Show()
        $script:assistantChatForm.WindowState = [System.Windows.Forms.FormWindowState]::Normal
        $script:assistantChatForm.Activate()
        return
    }

    New-ChatWindow
}

$notifyIcon = New-Object System.Windows.Forms.NotifyIcon
$notifyIcon.Icon = Get-NotifyIcon -Path $TrayIconPath
$notifyIcon.Text = "AI4BINANCE Assistant"
$notifyIcon.Visible = $true

$bootstrapForm = $null
$contextMenu = New-Object System.Windows.Forms.ContextMenuStrip
$chatItem = New-Object System.Windows.Forms.ToolStripMenuItem("Chat")
$logsItem = New-Object System.Windows.Forms.ToolStripMenuItem("Open Logs")
$exitItem = New-Object System.Windows.Forms.ToolStripMenuItem("Exit")

$chatItem.add_Click({
    Show-AssistantChatWindow
})

$logsItem.add_Click({
    Start-Process -FilePath explorer.exe -ArgumentList $logDirectory
})

$exitItem.add_Click({
    $script:allowExit = $true
    if ($null -ne $script:assistantChatForm -and -not $script:assistantChatForm.IsDisposed) {
        $script:assistantChatForm.Close()
    }
    else {
        $bootstrapForm.Close()
    }
})

[void]$contextMenu.Items.Add($chatItem)
[void]$contextMenu.Items.Add($logsItem)
[void]$contextMenu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator))
[void]$contextMenu.Items.Add($exitItem)

$notifyIcon.ContextMenuStrip = $contextMenu

Start-LlamaServerHidden

$bootstrapForm = New-Object System.Windows.Forms.Form
$bootstrapForm.ShowInTaskbar = $false
$bootstrapForm.FormBorderStyle = [System.Windows.Forms.FormBorderStyle]::None
$bootstrapForm.Opacity = 0
$bootstrapForm.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
$bootstrapForm.Size = New-Object System.Drawing.Size(1, 1)
$bootstrapForm.Add_Shown({
    $bootstrapForm.Hide()
})
$bootstrapForm.Add_FormClosed({
    $notifyIcon.Visible = $false
    $notifyIcon.Dispose()
})

$script:allowExit = $false
$script:assistantChatForm = $null

[System.Windows.Forms.Application]::Run($bootstrapForm)
