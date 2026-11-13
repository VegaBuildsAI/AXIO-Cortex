$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeScript = Join-Path $ProjectRoot "scripts\axio_memory_runtime.py"
$StartupScript = Join-Path $ProjectRoot "start_axio_memory.cmd"
$BackupScript = Join-Path $ProjectRoot "scripts\backup_cortex.ps1"
$RuntimeLauncher = Join-Path $ProjectRoot "run_memory_runtime.cmd"
# Every task runs through a headless console host, so no window opens (and
# none can be closed by accident, which used to kill runs mid-way). Memory
# runtime output goes to logs\memory_runtime_task.log via run_memory_runtime.cmd.
$Conhost = Join-Path $env:SystemRoot "System32\conhost.exe"

foreach ($Path in @($PythonExe, $RuntimeScript, $StartupScript, $BackupScript, $RuntimeLauncher, $Conhost)) {
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Required AXIO path not found: $Path"
    }
}

$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

$StartupAction = New-ScheduledTaskAction `
    -Execute $Conhost `
    -Argument "--headless cmd.exe /c `"$StartupScript`"" `
    -WorkingDirectory $ProjectRoot
$StartupTrigger = New-ScheduledTaskTrigger -AtLogOn -User $UserId
Register-ScheduledTask `
    -TaskName "AXIO Cortex Startup" `
    -Description "Start Cortex, reconcile local memory, and sync canonical knowledge." `
    -Action $StartupAction -Trigger $StartupTrigger `
    -Principal $Principal -Settings $Settings -Force | Out-Null

$SyncAction = New-ScheduledTaskAction `
    -Execute $Conhost `
    -Argument "--headless cmd.exe /c `"$RuntimeLauncher`" --once --sync-only" `
    -WorkingDirectory $ProjectRoot
$SyncTrigger = New-ScheduledTaskTrigger `
    -Once `
    -At ((Get-Date).AddMinutes(2)) `
    -RepetitionInterval (New-TimeSpan -Minutes 30) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
Register-ScheduledTask `
    -TaskName "AXIO Memory Sync" `
    -Description "Reconcile outbox and sync AXIO seeds plus Second Brain every 30 minutes." `
    -Action $SyncAction -Trigger $SyncTrigger `
    -Principal $Principal -Settings $Settings -Force | Out-Null

$ConsolidateAction = New-ScheduledTaskAction `
    -Execute $Conhost `
    -Argument "--headless cmd.exe /c `"$RuntimeLauncher`" --once --consolidate-only" `
    -WorkingDirectory $ProjectRoot
$ConsolidateTrigger = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask `
    -TaskName "AXIO Memory Consolidate" `
    -Description "Consolidate new sessions into durable Cortex lessons nightly." `
    -Action $ConsolidateAction -Trigger $ConsolidateTrigger `
    -Principal $Principal -Settings $Settings -Force | Out-Null

$BackupAction = New-ScheduledTaskAction `
    -Execute $Conhost `
    -Argument "--headless powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$BackupScript`"" `
    -WorkingDirectory $ProjectRoot
$BackupTrigger = New-ScheduledTaskTrigger -Daily -At "02:30"
Register-ScheduledTask `
    -TaskName "AXIO Cortex Backup" `
    -Description "Create a rotating local pg_dump backup of the Cortex database." `
    -Action $BackupAction -Trigger $BackupTrigger `
    -Principal $Principal -Settings $Settings -Force | Out-Null

Get-ScheduledTask -TaskName "AXIO Cortex Startup", "AXIO Memory Sync", "AXIO Memory Consolidate", "AXIO Cortex Backup" |
    Select-Object TaskName, State
