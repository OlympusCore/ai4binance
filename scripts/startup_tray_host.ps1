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
    return Invoke-AI4BinanceAssistantRequest @{ operation = "system_prompt" }
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
    return Invoke-AI4BinanceAssistantRequest @{ operation = "is_status_query"; input_text = $InputText }
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
    $result = Invoke-AI4BinanceAssistantRequest @{
        operation = "runtime_status"; state_directory = $stateDirectory
        now = [DateTimeOffset]::UtcNow.ToString("o")
    }
    return ($result | ConvertTo-Json -Compress)
}

function Get-FastLocalAnswer {
    param([Parameter(Mandatory = $true)][string]$InputText, [string]$ContextText = "")
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "fast_answer"; input_text = $InputText; context_text = $ContextText
        state_path = $privateAccountStatePath; state_directory = $stateDirectory
        now = [DateTimeOffset]::UtcNow.ToString("o")
    }
}

function Convert-MessagesToPrompt {
    param(
        [Parameter(Mandatory = $true)][string]$SystemPrompt,
        [Parameter(Mandatory = $true)][object[]]$Messages
    )
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "build_prompt"; system_prompt = $SystemPrompt; messages = @($Messages)
    }
}

function Invoke-LlamaCompletion {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )
    return Invoke-AI4BinanceAssistantRequest @{
        operation = "complete"; prompt = $Prompt
        endpoint = $llamaEndpoint; timeout_seconds = $TimeoutSeconds
        max_tokens = $maxPredictTokens
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
        Add-AI4BinanceAssistantHistory $chatState.Messages "user" $trimmed $maxHistoryTurns

        $recentUserContext = Invoke-AI4BinanceAssistantRequest @{
            operation = "recent_context"; messages = @($chatState.Messages)
        }
        $quickAnswer = Get-FastLocalAnswer `
            -InputText $trimmed `
            -ContextText $recentUserContext
        if ($null -ne $quickAnswer) {
            Add-AI4BinanceAssistantHistory $chatState.Messages "assistant" $quickAnswer $maxHistoryTurns
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
        Add-AI4BinanceAssistantHistory $chatState.Messages "assistant" $answer $maxHistoryTurns
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
