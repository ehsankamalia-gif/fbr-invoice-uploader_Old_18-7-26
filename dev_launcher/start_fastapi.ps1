param(
    [string]$ConfigPath = ""
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:LauncherRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$script:RepoRoot = Split-Path -Parent $script:LauncherRoot
$script:ManagedFastApiProcess = $null
$script:StartedLaragon = $false
$script:CleanupComplete = $false
$script:PidFilePath = $null
$script:Mutex = $null
$script:LogFile = $null
$script:DebugConfig = $null

function Get-DebugConfig {
    if ($script:DebugConfig) {
        return $script:DebugConfig
    }

    $envPath = Join-Path $script:RepoRoot ".dbg\api-autostart-failure.env"
    $config = @{
        Url = "http://127.0.0.1:7777/event"
        SessionId = "api-autostart-failure"
    }

    if (Test-Path -LiteralPath $envPath) {
        foreach ($line in Get-Content -LiteralPath $envPath) {
            if ($line -like "DEBUG_SERVER_URL=*") {
                $config.Url = $line.Substring("DEBUG_SERVER_URL=".Length)
            } elseif ($line -like "DEBUG_SESSION_ID=*") {
                $config.SessionId = $line.Substring("DEBUG_SESSION_ID=".Length)
            }
        }
    }

    $script:DebugConfig = $config
    return $script:DebugConfig
}

function Send-DebugEvent {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HypothesisId,
        [Parameter(Mandatory = $true)]
        [string]$Location,
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [hashtable]$Data = @{}
    )

    try {
        $debugConfig = Get-DebugConfig
        $payload = @{
            sessionId = $debugConfig.SessionId
            runId = "pre-fix"
            hypothesisId = $HypothesisId
            location = $Location
            msg = "[DEBUG] $Message"
            data = $Data
            ts = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
        } | ConvertTo-Json -Depth 5 -Compress

        Invoke-WebRequest -Uri $debugConfig.Url -Method Post -ContentType "application/json" -Body $payload -UseBasicParsing | Out-Null
    } catch {
    }
}

function Resolve-AbsolutePath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue,
        [Parameter(Mandatory = $true)]
        [string]$BasePath
    )

    if ([System.IO.Path]::IsPathRooted($PathValue)) {
        return [System.IO.Path]::GetFullPath($PathValue)
    }

    return [System.IO.Path]::GetFullPath((Join-Path $BasePath $PathValue))
}

function Ensure-Directory {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Write-LauncherLog {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Message,
        [ValidateSet("INFO", "WARN", "ERROR")]
        [string]$Level = "INFO"
    )

    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "{0} [{1}] {2}" -f $timestamp, $Level, $Message
    Write-Host $line
    if ($script:LogFile) {
        Add-Content -LiteralPath $script:LogFile -Value $line
    }
}

function Test-TcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [int]$TimeoutMilliseconds = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $asyncResult = $client.BeginConnect($HostName, $Port, $null, $null)
        if (-not $asyncResult.AsyncWaitHandle.WaitOne($TimeoutMilliseconds, $false)) {
            return $false
        }

        $client.EndConnect($asyncResult)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Wait-ForTcpPort {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    Write-LauncherLog ("Waiting for {0} on {1}:{2}..." -f $Name, $HostName, $Port)
    # #region debug-point B:wait-for-port
    Send-DebugEvent -HypothesisId "B" -Location "start_fastapi.ps1:Wait-ForTcpPort" -Message "Waiting for TCP port readiness." -Data @{
        name = $Name
        host = $HostName
        port = $Port
        timeoutSeconds = $TimeoutSeconds
    }
    # #endregion

    while ((Get-Date) -lt $deadline) {
        if (Test-TcpPort -HostName $HostName -Port $Port) {
            Write-LauncherLog ("{0} is available on {1}:{2}." -f $Name, $HostName, $Port)
            # #region debug-point B:port-ready
            Send-DebugEvent -HypothesisId "B" -Location "start_fastapi.ps1:Wait-ForTcpPort" -Message "TCP port became available." -Data @{
                name = $Name
                host = $HostName
                port = $Port
            }
            # #endregion
            return $true
        }

        Start-Sleep -Seconds 2
    }

    # #region debug-point B:port-timeout
    Send-DebugEvent -HypothesisId "B" -Location "start_fastapi.ps1:Wait-ForTcpPort" -Message "TCP port did not become available before timeout." -Data @{
        name = $Name
        host = $HostName
        port = $Port
        timeoutSeconds = $TimeoutSeconds
    }
    # #endregion
    return $false
}

function Test-HttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [int]$TimeoutSeconds = 3
    )

    try {
        $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSeconds
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    } catch {
        return $false
    }
}

function Wait-ForHttpEndpoint {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Uri,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-HttpEndpoint -Uri $Uri) {
            return $true
        }

        Start-Sleep -Seconds 2
    }

    return $false
}

function Get-LaragonProcess {
    Get-Process -Name "laragon" -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Stop-LaragonProcesses {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LaragonRoot
    )

    $escapedRoot = [Regex]::Escape($LaragonRoot)
    $processes = Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -and $_.ExecutablePath -match "^$escapedRoot"
    }

    foreach ($processInfo in $processes) {
        try {
            Write-LauncherLog ("Stopping Laragon process {0} ({1})..." -f $processInfo.Name, $processInfo.ProcessId)
            Stop-Process -Id $processInfo.ProcessId -Force -ErrorAction Stop
        } catch {
            Write-LauncherLog ("Failed to stop Laragon process {0} ({1}): {2}" -f $processInfo.Name, $processInfo.ProcessId, $_.Exception.Message) "WARN"
        }
    }
}

function Save-FastApiState {
    param(
        [Parameter(Mandatory = $true)]
        [int]$ProcessId,
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    if (-not $script:PidFilePath) {
        return
    }

    $state = @{
        pid = $ProcessId
        host = $HostName
        port = $Port
        started_at = (Get-Date).ToString("o")
    } | ConvertTo-Json

    Set-Content -LiteralPath $script:PidFilePath -Value $state
}

function Clear-FastApiState {
    if ($script:PidFilePath -and (Test-Path -LiteralPath $script:PidFilePath)) {
        Remove-Item -LiteralPath $script:PidFilePath -Force -ErrorAction SilentlyContinue
    }
}

function Stop-ManagedFastApi {
    if (-not $script:ManagedFastApiProcess) {
        Clear-FastApiState
        return
    }

    try {
        if (-not $script:ManagedFastApiProcess.HasExited) {
            Write-LauncherLog ("Stopping FastAPI process {0}..." -f $script:ManagedFastApiProcess.Id)
            Stop-Process -Id $script:ManagedFastApiProcess.Id -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 2

            if (-not $script:ManagedFastApiProcess.HasExited) {
                Stop-Process -Id $script:ManagedFastApiProcess.Id -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-LauncherLog ("FastAPI shutdown encountered an error: {0}" -f $_.Exception.Message) "WARN"
    } finally {
        $script:ManagedFastApiProcess = $null
        Clear-FastApiState
    }
}

function Invoke-Cleanup {
    param(
        [Parameter(Mandatory = $true)]
        [bool]$StopLaragonOnExit,
        [Parameter(Mandatory = $true)]
        [string]$LaragonRoot
    )

    if ($script:CleanupComplete) {
        return
    }

    $script:CleanupComplete = $true

    try {
        Stop-ManagedFastApi

        if ($StopLaragonOnExit -and $script:StartedLaragon) {
            Write-LauncherLog "Configured to stop Laragon on exit."
            Stop-LaragonProcesses -LaragonRoot $LaragonRoot
        } else {
            Write-LauncherLog "Leaving Laragon running."
        }
    } finally {
        if ($script:Mutex) {
            try {
                $script:Mutex.ReleaseMutex() | Out-Null
            } catch {
            }

            $script:Mutex.Dispose()
            $script:Mutex = $null
        }
    }
}

function Start-LaragonIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LaragonExePath
    )

    $laragonProcess = Get-LaragonProcess
    if ($laragonProcess) {
        Write-LauncherLog ("Laragon is already running with PID {0}." -f $laragonProcess.Id)
        # #region debug-point B:laragon-already-running
        Send-DebugEvent -HypothesisId "B" -Location "start_fastapi.ps1:Start-LaragonIfNeeded" -Message "Laragon is already running before startup logic begins." -Data @{
            pid = $laragonProcess.Id
        }
        # #endregion
        return
    }

    Write-LauncherLog "Starting Laragon..."
    # #region debug-point B:starting-laragon
    Send-DebugEvent -HypothesisId "B" -Location "start_fastapi.ps1:Start-LaragonIfNeeded" -Message "Launcher is starting Laragon." -Data @{
        laragonExePath = $LaragonExePath
    }
    # #endregion
    Start-Process -FilePath $LaragonExePath -WorkingDirectory (Split-Path -Parent $LaragonExePath) | Out-Null
    $script:StartedLaragon = $true
}

function Start-ManagedFastApi {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PythonExe,
        [Parameter(Mandatory = $true)]
        [string]$ProjectPath,
        [Parameter(Mandatory = $true)]
        [string]$AppReference,
        [Parameter(Mandatory = $true)]
        [string]$HostName,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$LogLevel,
        [Parameter(Mandatory = $true)]
        [string]$HealthCheckPath,
        [Parameter(Mandatory = $true)]
        [int]$StartupTimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [bool]$EnableReload,
        [Parameter(Mandatory = $true)]
        [string]$LogRoot
    )

    if (Test-TcpPort -HostName $HostName -Port $Port) {
        Write-LauncherLog ("FastAPI is already running on {0}:{1}. Not starting another instance." -f $HostName, $Port)
        # #region debug-point D:port-already-occupied
        Send-DebugEvent -HypothesisId "D" -Location "start_fastapi.ps1:Start-ManagedFastApi" -Message "FastAPI port was already occupied, so a new managed instance was not started." -Data @{
            host = $HostName
            port = $Port
        }
        # #endregion
        $script:ManagedFastApiProcess = $null
        return
    }

    $stdoutLog = Join-Path $LogRoot "fastapi.stdout.log"
    $stderrLog = Join-Path $LogRoot "fastapi.stderr.log"

    $arguments = @(
        "-m", "uvicorn", $AppReference,
        "--host", $HostName,
        "--port", [string]$Port,
        "--log-level", $LogLevel
    )

    if ($EnableReload) {
        $arguments += "--reload"
    }

    Write-LauncherLog "Starting FastAPI..."
    # #region debug-point C:starting-fastapi
    Send-DebugEvent -HypothesisId "C" -Location "start_fastapi.ps1:Start-ManagedFastApi" -Message "Launcher is starting a managed FastAPI process." -Data @{
        pythonExe = $PythonExe
        projectPath = $ProjectPath
        appReference = $AppReference
        host = $HostName
        port = $Port
    }
    # #endregion
    $process = Start-Process -FilePath $PythonExe `
        -ArgumentList $arguments `
        -WorkingDirectory $ProjectPath `
        -PassThru `
        -RedirectStandardOutput $stdoutLog `
        -RedirectStandardError $stderrLog

    $script:ManagedFastApiProcess = $process
    Save-FastApiState -ProcessId $process.Id -HostName $HostName -Port $Port
    # #region debug-point C:fastapi-started
    Send-DebugEvent -HypothesisId "C" -Location "start_fastapi.ps1:Start-ManagedFastApi" -Message "Managed FastAPI process started and health check is beginning." -Data @{
        pid = $process.Id
        healthCheckPath = $HealthCheckPath
    }
    # #endregion

    $healthUri = "http://{0}:{1}{2}" -f $HostName, $Port, $HealthCheckPath
    if (-not (Wait-ForHttpEndpoint -Uri $healthUri -TimeoutSeconds $StartupTimeoutSeconds)) {
        # #region debug-point C:health-timeout
        Send-DebugEvent -HypothesisId "C" -Location "start_fastapi.ps1:Start-ManagedFastApi" -Message "Managed FastAPI process did not reach a healthy HTTP endpoint before timeout." -Data @{
            pid = $process.Id
            healthUri = $healthUri
            timeoutSeconds = $StartupTimeoutSeconds
        }
        # #endregion
        throw ("FastAPI did not become ready at {0} within {1} seconds." -f $healthUri, $StartupTimeoutSeconds)
    }

    Write-LauncherLog ("API Server is running. PID={0} URL=http://{1}:{2}" -f $process.Id, $HostName, $Port)
    # #region debug-point C:health-success
    Send-DebugEvent -HypothesisId "C" -Location "start_fastapi.ps1:Start-ManagedFastApi" -Message "Managed FastAPI process reached a healthy HTTP endpoint." -Data @{
        pid = $process.Id
        healthUri = $healthUri
    }
    # #endregion
}

if ([string]::IsNullOrWhiteSpace($ConfigPath)) {
    $ConfigPath = Join-Path $script:LauncherRoot "config\local-dev.json"
}

$configPathResolved = Resolve-AbsolutePath -PathValue $ConfigPath -BasePath $script:RepoRoot
if (-not (Test-Path -LiteralPath $configPathResolved)) {
    throw "Config file not found: $configPathResolved"
}

$config = Get-Content -LiteralPath $configPathResolved -Raw | ConvertFrom-Json

$laragonPath = Resolve-AbsolutePath -PathValue $config.laragon.install_path -BasePath $script:RepoRoot
$laragonExePath = Join-Path $laragonPath $config.laragon.exe_name
$projectPath = Resolve-AbsolutePath -PathValue $config.fastapi.project_path -BasePath $script:RepoRoot
$venvPath = Resolve-AbsolutePath -PathValue $config.fastapi.venv_path -BasePath $projectPath
$pythonExe = Join-Path $venvPath "Scripts\python.exe"
$logRoot = Resolve-AbsolutePath -PathValue $config.paths.log_dir -BasePath $script:RepoRoot
$stateRoot = Resolve-AbsolutePath -PathValue $config.paths.state_dir -BasePath $script:RepoRoot

Ensure-Directory -Path $logRoot
Ensure-Directory -Path $stateRoot

$script:LogFile = Join-Path $logRoot ("launcher-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$script:PidFilePath = Join-Path $stateRoot "fastapi-process.json"

if (-not (Test-Path -LiteralPath $laragonExePath)) {
    throw "Laragon executable not found: $laragonExePath"
}

if (-not (Test-Path -LiteralPath $projectPath)) {
    throw "FastAPI project path not found: $projectPath"
}

if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Virtual environment Python not found: $pythonExe"
}

$mutexName = "Global\FBRInvoiceUploaderLocalLauncher"
$createdNew = $false
$script:Mutex = New-Object System.Threading.Mutex($true, $mutexName, [ref]$createdNew)
if (-not $createdNew) {
    Write-LauncherLog "Another launcher instance is already running." "WARN"
    # #region debug-point D:mutex-collision
    Send-DebugEvent -HypothesisId "D" -Location "start_fastapi.ps1:mutex" -Message "Launcher mutex indicates another supervisor instance is already running." -Data @{
        mutexName = $mutexName
    }
    # #endregion
    exit 1
}

$stopLaragonOnExit = [bool]$config.laragon.stop_laragon_on_exit
$requireApache = [bool]$config.laragon.require_apache
$enableReload = [bool]$config.fastapi.enable_reload

try {
    Write-LauncherLog "Launcher initialized."
    Write-LauncherLog ("Using Laragon path: {0}" -f $laragonPath)
    Write-LauncherLog ("Using FastAPI project path: {0}" -f $projectPath)
    Write-LauncherLog ("Using Python interpreter: {0}" -f $pythonExe)

    Start-LaragonIfNeeded -LaragonExePath $laragonExePath

    $laragonTimeout = [int]$config.laragon.startup_timeout_seconds
    if (-not (Wait-ForTcpPort -Name "MySQL" -HostName $config.laragon.mysql_host -Port ([int]$config.laragon.mysql_port) -TimeoutSeconds $laragonTimeout)) {
        throw ("MySQL did not become available on {0}:{1} within {2} seconds." -f $config.laragon.mysql_host, $config.laragon.mysql_port, $laragonTimeout)
    }

    $apacheReady = Wait-ForTcpPort -Name "Apache" -HostName $config.laragon.apache_host -Port ([int]$config.laragon.apache_port) -TimeoutSeconds 20
    if (-not $apacheReady -and $requireApache) {
        throw ("Apache did not become available on {0}:{1}." -f $config.laragon.apache_host, $config.laragon.apache_port)
    } elseif (-not $apacheReady) {
        Write-LauncherLog "Apache is not available, but configuration allows startup to continue." "WARN"
    }

    Start-ManagedFastApi `
        -PythonExe $pythonExe `
        -ProjectPath $projectPath `
        -AppReference $config.fastapi.app `
        -HostName $config.fastapi.host `
        -Port ([int]$config.fastapi.port) `
        -LogLevel $config.fastapi.log_level `
        -HealthCheckPath $config.fastapi.health_check_path `
        -StartupTimeoutSeconds ([int]$config.fastapi.startup_timeout_seconds) `
        -EnableReload $enableReload `
        -LogRoot $logRoot

    Write-LauncherLog "Supervisor loop is active. Press Ctrl+C to stop the launcher."

    while ($true) {
        Start-Sleep -Seconds 2

        if ($script:ManagedFastApiProcess) {
            if ($script:ManagedFastApiProcess.HasExited) {
                $exitCode = $script:ManagedFastApiProcess.ExitCode
                Write-LauncherLog ("FastAPI process exited with code {0}. Restarting in {1} seconds..." -f $exitCode, $config.fastapi.restart_delay_seconds) "WARN"
                $script:ManagedFastApiProcess = $null
                Clear-FastApiState
                Start-Sleep -Seconds ([int]$config.fastapi.restart_delay_seconds)

                Start-ManagedFastApi `
                    -PythonExe $pythonExe `
                    -ProjectPath $projectPath `
                    -AppReference $config.fastapi.app `
                    -HostName $config.fastapi.host `
                    -Port ([int]$config.fastapi.port) `
                    -LogLevel $config.fastapi.log_level `
                    -HealthCheckPath $config.fastapi.health_check_path `
                    -StartupTimeoutSeconds ([int]$config.fastapi.startup_timeout_seconds) `
                    -EnableReload $enableReload `
                    -LogRoot $logRoot
            }
        } elseif (-not (Test-TcpPort -HostName $config.fastapi.host -Port ([int]$config.fastapi.port))) {
            Write-LauncherLog "FastAPI is not running. Starting a managed instance."

            Start-ManagedFastApi `
                -PythonExe $pythonExe `
                -ProjectPath $projectPath `
                -AppReference $config.fastapi.app `
                -HostName $config.fastapi.host `
                -Port ([int]$config.fastapi.port) `
                -LogLevel $config.fastapi.log_level `
                -HealthCheckPath $config.fastapi.health_check_path `
                -StartupTimeoutSeconds ([int]$config.fastapi.startup_timeout_seconds) `
                -EnableReload $enableReload `
                -LogRoot $logRoot
        }
    }
} catch {
    Write-LauncherLog $_.Exception.Message "ERROR"
    throw
} finally {
    Invoke-Cleanup -StopLaragonOnExit $stopLaragonOnExit -LaragonRoot $laragonPath
}
