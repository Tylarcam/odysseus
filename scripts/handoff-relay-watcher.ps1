# Poll Odysseus for pending Cursor/Claude handoffs and optionally run Cursor Agent CLI.
#
# Requires: ODYSSEUS_URL, ODYSSEUS_API_TOKEN (Settings > Integrations)
#
# Usage:
#   .\scripts\handoff-relay-watcher.ps1 -Target cursor -Once
#   .\scripts\handoff-relay-watcher.ps1 -Target cursor -RunAgent
#   .\scripts\handoff-relay-watcher.ps1 -Target cursor -RunAgent -IntervalSeconds 60
#
# Prerequisites:
#   agent login          # Cursor Agent CLI authenticated
#   agent status         # confirms whoami

param(
    [ValidateSet("cursor", "claude")]
    [string]$Target = "cursor",
    [int]$IntervalSeconds = 90,
    [switch]$Once,
    [switch]$RunAgent,
    [string]$AgentCommand = "",
    [string]$OdysseusRoot = "",
    [string]$DefaultWorkspace = "",
    [string]$Model = "",
    [int]$TimeoutMinutes = 120
)

$ErrorActionPreference = "Stop"

function Write-RelayLog {
    param([string]$Message)
    Write-Host ('[handoff-relay] ' + $Message)
}

function Write-RelayWarn {
    param([string]$Message)
    Write-Warning ('[handoff-relay] ' + $Message)
}

function Resolve-OdysseusRoot {
    if ($OdysseusRoot -and (Test-Path $OdysseusRoot)) {
        return (Resolve-Path $OdysseusRoot).Path
    }
    $here = Split-Path -Parent $PSScriptRoot
    if (Test-Path (Join-Path $here "app.py")) {
        return (Resolve-Path $here).Path
    }
    $fallback = "C:\Users\tylar\code\odysseus"
    if (Test-Path $fallback) { return $fallback }
    return $here
}

function Resolve-AgentCommand {
    param([string]$TargetName = "cursor")
    if ($AgentCommand) {
        $cmd = Get-Command $AgentCommand -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        if (Test-Path -LiteralPath $AgentCommand) { return (Resolve-Path -LiteralPath $AgentCommand).Path }
        return $AgentCommand
    }
    if ($TargetName -eq "claude") {
        $cmd = Get-Command claude -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
        return $null
    }
    foreach ($name in @("agent", "cursor")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function New-AgentProcessStartInfo {
    param(
        [string]$AgentPath,
        [string[]]$AgentArgs,
        [string]$WorkingDirectory
    )
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.WorkingDirectory = $WorkingDirectory

    $argString = ($AgentArgs | ForEach-Object {
        '"' + ($_.ToString() -replace '"', '""') + '"'
    }) -join ' '

    $ext = [System.IO.Path]::GetExtension($AgentPath).ToLowerInvariant()
    if ($ext -in @('.ps1', '.cmd', '.bat')) {
        $shell = (Get-Command powershell.exe -ErrorAction Stop).Source
        $psi.FileName = $shell
        $psi.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$AgentPath`" $argString"
    } else {
        $psi.FileName = $AgentPath
        $psi.Arguments = $argString
    }
    return $psi
}

function Get-ApiBase {
    $base = $env:ODYSSEUS_URL
    if (-not $base) { $base = "http://127.0.0.1:7000" }
    return $base.TrimEnd("/")
}

function Get-AuthHeaders {
    $token = $env:ODYSSEUS_API_TOKEN
    if (-not $token) {
        throw "Set ODYSSEUS_API_TOKEN (Settings > Integrations > Claude Agent)"
    }
    return @{
        Authorization = "Bearer $token"
        Accept        = "application/json"
    }
}

function Get-PendingHandoffs {
    param($Headers, [string]$Base, [string]$TargetName)
    $url = "$Base/api/handoff-relay/pending?target=$TargetName"
    $resp = Invoke-RestMethod -Uri $url -Headers $Headers -Method Get
    return @($resp.handoffs)
}

function Claim-Handoff {
    param($Headers, [string]$Base, [string]$DocId)
    $url = "$Base/api/handoff-relay/$DocId/claim"
    try {
        Invoke-RestMethod -Uri $url -Headers $Headers -Method Post | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Complete-Handoff {
    param($Headers, [string]$Base, [string]$DocId, [string]$Outcome, [string]$Status)
    $url = "$Base/api/handoff-relay/$DocId/complete"
    $text = [string]$Outcome
    if ($text.Length -gt 3900) { $text = $text.Substring(0, 3900) }
    $payload = @{
        outcome = $text
        status  = $Status
    }
    $json = $payload | ConvertTo-Json -Compress -Depth 4
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($json)
    try {
        Invoke-RestMethod -Uri $url -Headers $Headers -Method Post -Body $bytes -ContentType 'application/json; charset=utf-8' | Out-Null
    } catch {
        $detail = ''
        if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $detail = " - $($_.ErrorDetails.Message)" }
        throw "$($_.Exception.Message)$detail"
    }
}

function Get-HostInboxPath {
    param([string]$Root, [string]$TargetName, [string]$DocId, [string]$HostInboxRel)
    if ($HostInboxRel) {
        $p = Join-Path $Root ($HostInboxRel -replace '/', '\')
        if (Test-Path $p) { return $p }
    }
    return Join-Path $Root "data\handoff-inbox\$TargetName\$DocId.md"
}

function Get-WorkspaceFromHandoff {
    param($Handoff, [string]$Fallback)
    $content = [string]$Handoff.content
    if ($content -match '(?m)^project:\s*(.+)$') {
        $project = $Matches[1].Trim()
        if ($project -and (Test-Path -LiteralPath $project)) {
            return (Resolve-Path -LiteralPath $project).Path
        }
    }
    if ($Fallback -and (Test-Path -LiteralPath $Fallback)) {
        return (Resolve-Path -LiteralPath $Fallback).Path
    }
    return (Get-Location).Path
}

function Build-RelayPrompt {
    param([string]$InboxPath, $Handoff)
    if ($InboxPath -and (Test-Path -LiteralPath $InboxPath)) {
        return @(
            "Execute this Odysseus handoff relay. Read the file below (full instructions + packet), then execute Next steps with tools."
            "When finished, end your reply with a ## Outcome section as specified in the file."
            ""
            "Handoff file (read entirely):"
            $InboxPath
        ) -join "`n"
    }
    $title = [string]$Handoff.title
    $content = [string]$Handoff.content
    return @(
        "# $title"
        ""
        "You are executing an Odysseus handoff relay. Read the packet and execute Next steps."
        ""
        "--- HANDOFF PACKET ---"
        ""
        $content
    ) -join "`n"
}

function Test-AgentOutcomeFailed {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $true }
    $low = $Text.ToLowerInvariant()
    if ($low -match 'unique constraint|integrityerror|traceback \(most recent call last\)') { return $true }
    if ($Text -match '\.ps1:\d+\s+char:\d+') { return $true }
    if ($Text -match 'node\.exe\s*:') { return $true }
    return $false
}

function Invoke-ExternalAgent {
    param(
        [string]$AgentExe,
        [string]$Prompt,
        [string]$Workspace,
        [string]$ModelName,
        [int]$TimeoutMin,
        [string]$TargetName = "cursor"
    )
    if ($TargetName -eq "claude") {
        $agentArgs = @(
            "-p",
            "--dangerously-skip-permissions",
            "--output-format", "text"
        )
        if ($ModelName) { $agentArgs += @("--model", $ModelName) }
        $agentArgs += $Prompt
    } else {
        $agentArgs = @(
            "-p", "--trust", "--yolo", "--approve-mcps",
            "--output-format", "text",
            "--workspace", $Workspace,
            $Prompt
        )
        if ($ModelName) {
            $agentArgs = @("-p", "--trust", "--yolo", "--approve-mcps", "--output-format", "text", "--workspace", $Workspace, "--model", $ModelName, $Prompt)
        }
    }

    Write-RelayLog "$TargetName workspace: $Workspace"
    Write-RelayLog "$TargetName timeout: ${TimeoutMin}m"
    Write-RelayLog "launching $TargetName (same shell as watcher)"

    $previousLocation = Get-Location
    Set-Location -LiteralPath $Workspace
    try {
        $psi = New-AgentProcessStartInfo -AgentPath $AgentExe -AgentArgs $agentArgs -WorkingDirectory $Workspace
        $proc = New-Object System.Diagnostics.Process
        $proc.StartInfo = $psi
        [void]$proc.Start()
        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        $timeoutMs = [Math]::Max(60000, $TimeoutMin * 60 * 1000)
        if (-not $proc.WaitForExit($timeoutMs)) {
            try { $proc.Kill($true) } catch {}
            throw "Agent timed out after ${TimeoutMin} minutes"
        }
        if ($proc.ExitCode -and $proc.ExitCode -ne 0) {
            $err = ($stderr + "`n" + $stdout).Trim()
            throw "Agent exited with code $($proc.ExitCode): $err"
        }
        $combined = ($stdout + $(if ($stderr) { "`n$stderr" } else { "" })).Trim()
        if (-not $combined) {
            throw "Agent produced no output"
        }
        if (Test-AgentOutcomeFailed -Text $combined) {
            throw $combined
        }
        return $combined
    } finally {
        Set-Location -Path $previousLocation
    }
}

$script:InFlight = @{}

function Process-PendingHandoff {
    param($Handoff, $Headers, [string]$Base, [string]$Root, [string]$AgentExe, [string]$WorkspaceDefault, [string]$ModelName, [int]$TimeoutMin)

    $docId = [string]$Handoff.doc_id
    if ($script:InFlight.ContainsKey($docId)) { return }

    if ([string]$Handoff.status -notin @('queued', 'running')) { return }

    $script:InFlight[$docId] = $true
    try {
        if ([string]$Handoff.status -eq 'queued') {
            if (-not (Claim-Handoff -Headers $Headers -Base $Base -DocId $docId)) {
                Write-RelayLog "skip $docId (not claimable)"
                return
            }
        } else {
            Write-RelayLog "resuming running $docId"
        }

        $inbox = Get-HostInboxPath -Root $Root -TargetName $Target -DocId $docId -HostInboxRel ([string]$Handoff.host_inbox_rel)
        $prompt = Build-RelayPrompt -InboxPath $inbox -Handoff $Handoff
        $workspace = Get-WorkspaceFromHandoff -Handoff $Handoff -Fallback $WorkspaceDefault

        Write-RelayLog "running $docId - $($Handoff.title)"
        $outcome = Invoke-ExternalAgent -AgentExe $AgentExe -Prompt $prompt -Workspace $workspace -ModelName $ModelName -TimeoutMin $TimeoutMin -TargetName $Target
        Complete-Handoff -Headers $Headers -Base $Base -DocId $docId -Outcome $outcome -Status "complete"
        Write-RelayLog "complete $docId"
    } catch {
        $msg = $_.Exception.Message
        Write-RelayWarn "failed $docId - $msg"
        try {
            Complete-Handoff -Headers $Headers -Base $Base -DocId $docId -Outcome $msg -Status "failed"
        } catch {
            Write-RelayWarn "could not report failure for $docId"
        }
    } finally {
        $script:InFlight.Remove($docId) | Out-Null
    }
}

$root = Resolve-OdysseusRoot
$workspaceDefault = if ($DefaultWorkspace) { $DefaultWorkspace } else { $root }
$base = Get-ApiBase
$headers = Get-AuthHeaders
$agentExe = $null
if ($RunAgent) {
    $agentExe = Resolve-AgentCommand -TargetName $Target
    if (-not $agentExe) {
        if ($Target -eq "claude") {
            Write-Error "Claude Code CLI not found. Install claude and ensure it is on PATH, or pass -AgentCommand."
        } else {
            Write-Error "Cursor Agent CLI not found. Install Cursor CLI and run 'agent login', or pass -AgentCommand."
        }
        exit 1
    }
    Write-RelayLog "using $Target CLI: $agentExe"
}
Write-RelayLog "odysseus: $base"
Write-RelayLog "data root: $root"
Write-RelayLog "target: $Target runAgent=$($RunAgent.IsPresent)"

do {
    try {
        $pending = Get-PendingHandoffs -Headers $headers -Base $base -TargetName $Target
        foreach ($h in $pending) {
            Write-RelayLog "$($h.status) $($h.doc_id) - $($h.title)"
            $inbox = Get-HostInboxPath -Root $root -TargetName $Target -DocId ([string]$h.doc_id) -HostInboxRel ([string]$h.host_inbox_rel)
            if (Test-Path -LiteralPath $inbox) {
                Write-Host "  inbox: $inbox"
            }
            if ($RunAgent) {
                Process-PendingHandoff -Handoff $h -Headers $headers -Base $base -Root $root -AgentExe $agentExe -WorkspaceDefault $workspaceDefault -ModelName $Model -TimeoutMin $TimeoutMinutes
            }
        }
        if ($pending.Count -eq 0) {
            Write-RelayLog "no pending $Target handoffs"
        }
    } catch {
        Write-RelayWarn "poll failed: $_"
    }
    if ($Once) { break }
    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
