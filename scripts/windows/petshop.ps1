param(
    [ValidateSet('Start', 'Stop', 'Diagnose', 'Admin')]
    [string]$Action = 'Start',
    [switch]$NoBrowser
)

. (Join-Path $PSScriptRoot 'common.ps1')
$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$ProjectName = Get-ProjectName $Root
$EnvFile = Join-Path $Root '.env'
$StateDirectory = Join-Path $Root 'work\windows'
$null = New-Item -ItemType Directory -Path $StateDirectory -Force
$LogFile = Join-Path $StateDirectory ('launcher-' + (Get-Date -Format 'yyyyMMdd-HHmmss-fff') + '.log')
$script:LauncherLogPath = $LogFile
$script:LauncherEnvPath = $EnvFile
$mutex = New-Object Threading.Mutex($false, "Local\$ProjectName-launcher")
$locked = $false
$exitCode = 0

function Write-Status([string]$Message) {
    Write-Host $Message
    Add-Content -LiteralPath $LogFile -Value ("{0:o} {1}" -f (Get-Date), $Message) -Encoding UTF8
}

function Invoke-Compose([string[]]$ComposeArguments, [switch]$Capture) {
    $arguments = @('compose', '--project-name', $ProjectName, '--project-directory', $Root,
        '--env-file', $EnvFile, '-f', (Join-Path $Root 'docker-compose.yml'))
    $frontendCompose = Join-Path $Root 'docker-compose.frontend.yml'
    if (Test-Path -LiteralPath $frontendCompose) { $arguments += @('-f', $frontendCompose) }
    Invoke-Docker ($arguments + $ComposeArguments) -Capture:$Capture
}

try {
    try { $locked = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $locked = $true }
    if (-not $locked) { throw 'Another Petshop launcher is already running for this folder.' }
    Set-Location -LiteralPath $Root
    # This launcher uses the checked-in configuration, not inherited Compose files.
    foreach ($name in @('COMPOSE_FILE', 'COMPOSE_PROJECT_NAME', 'COMPOSE_PROFILES', 'COMPOSE_ENV_FILES', 'DOCKER_HOST', 'DOCKER_CONTEXT')) {
        [Environment]::SetEnvironmentVariable($name, $null, 'Process')
    }
    $script:Docker = Find-DockerDesktop
    if ($Action -eq 'Diagnose') {
        Write-Status "Project: $Root"
        Write-Status "Compose project: $ProjectName"
        Write-Status "WSL: $(Get-WslVersion)"
        Write-Status "Docker Desktop installed: $($null -ne $script:Docker)"
        Write-Status "Configuration exists: $(Test-Path -LiteralPath $EnvFile)"
        if ($script:Docker) {
            Write-Status "Docker ready: $(Test-DockerReady)"
            if (Test-DockerReady) {
                Write-Status (Invoke-Docker @('ps', '--all', '--filter', "label=com.docker.compose.project=$ProjectName", '--format', '{{.Names}} | {{.State}} | {{.Status}} | {{.Ports}}') -Capture)
            }
        }
        Write-Status "Diagnostic log: $LogFile"
    } else {
        if ($Action -eq 'Start') {
            if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
                throw 'This launcher currently supports Windows x64. ARM64 requires a matching Docker installer.'
            }
            $dependencies = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'dependencies.json') -Raw | ConvertFrom-Json
            Install-WslIfNeeded ([version]$dependencies.minimumWslVersion)
            if (-not $script:Docker) {
                $installer = Get-VerifiedInstaller $dependencies.dockerDesktop (Join-Path $Root 'work\downloads')
                Write-Status 'Installing Docker Desktop for the current Windows user...'
                $process = Start-Process -FilePath $installer -ArgumentList 'install', '--user', '--quiet' -WindowStyle Hidden -PassThru -Wait
                if ($process.ExitCode -notin @(0, 3010)) { throw "Docker installer failed (exit $($process.ExitCode))." }
                if ($process.ExitCode -eq 3010) { throw 'Docker setup requires a Windows restart. Run START.bat again after restarting.' }
                $script:Docker = Find-DockerDesktop
                if (-not $script:Docker) { throw 'Docker installation could not be verified.' }
            } else { Write-Status 'Docker Desktop is installed; skipping download and installation.' }
            if (-not (Test-DockerReady)) {
                Write-Status 'Starting Docker Desktop...'
                $null = Start-Process -FilePath $script:Docker.Desktop -WindowStyle Hidden -PassThru
                Wait-DockerReady
            }
        } elseif (-not $script:Docker -or -not (Test-DockerReady)) {
            throw 'Docker engine is unavailable. Container state could not be verified; no stop or admin command was sent.'
        }

        if ($Action -eq 'Stop') {
            $ids = Invoke-Docker @('ps', '--quiet', '--filter', "label=com.docker.compose.project=$ProjectName") -Capture
            if ($ids) { Invoke-Docker (@('stop', '--time', '30') + @($ids -split '\s+')) }
            Write-Status 'Petshop stopped. Database, configuration and downloaded images are preserved.'
        } elseif ($script:Docker -and (Test-DockerReady)) {
            if ($Action -eq 'Start' -and -not (Test-Path -LiteralPath $EnvFile)) {
                $volumes = Invoke-Docker @('volume', 'ls', '--quiet', '--filter', "label=com.docker.compose.project=$ProjectName") -Capture
                if ($volumes) {
                    if (-not (Restore-EnvFromComposeContainers $ProjectName $Root $EnvFile)) {
                        throw 'Existing project data found but .env is missing. Matching container credentials could not be verified; restore the original .env. Database data was not changed.'
                    }
                    Write-Status 'Restored private .env from matching project containers; existing database credentials were preserved.'
                } else {
                    $password = New-RandomSecret
                    $secret = New-RandomSecret
                    $configuration = @(
                        'POSTGRES_DB=petshop', 'POSTGRES_USER=petshop', "POSTGRES_PASSWORD=$password",
                        "PETSHOP_DATABASE_URL=postgresql+psycopg://petshop:$password@postgres:5432/petshop",
                        "PETSHOP_JWT_SECRET=$secret", 'PETSHOP_ENV=development', 'PETSHOP_DOCS_ENABLED=true',
                        "PETSHOP_IMAGE=${ProjectName}:local", 'PETSHOP_HTTP_PORT=8000', 'PETSHOP_WEB_PORT=8080'
                    ) -join "`n"
                    Write-PrivateNewFile $EnvFile ($configuration + "`n")
                    Write-Status 'Created private .env with separate random credentials.'
                    $password = $null; $secret = $null; $configuration = $null
                }
            }
            if (Test-Path -LiteralPath $EnvFile) {
                foreach ($required in @('POSTGRES_PASSWORD', 'PETSHOP_DATABASE_URL', 'PETSHOP_JWT_SECRET')) {
                    if ([string]::IsNullOrWhiteSpace((Get-EnvValue $EnvFile $required))) { throw "Fill $required in the existing .env. Existing configuration was preserved." }
                }
                # Avoid inherited values silently overriding credentials in the explicit .env.
                foreach ($variable in @(Get-ChildItem Env: | Where-Object Name -match '^(PETSHOP|POSTGRES)_')) {
                    [Environment]::SetEnvironmentVariable($variable.Name, $null, 'Process')
                }
                Invoke-Compose @('config', '--quiet')
                switch ($Action) {
                    'Start' {
                        $portText = Get-EnvValue $EnvFile 'PETSHOP_HTTP_PORT' '8000'
                        $port = 0
                        if (-not [int]::TryParse($portText, [ref]$port) -or $port -lt 1 -or $port -gt 65535) { throw 'PETSHOP_HTTP_PORT must be 1-65535.' }
                        $hasFrontend = Test-Path -LiteralPath (Join-Path $Root 'docker-compose.frontend.yml')
                        $webPort = 0
                        if ($hasFrontend) {
                            if ((Get-EnvValue $EnvFile 'PETSHOP_ENV' 'production') -notin @('development', 'test')) {
                                throw 'The local HTTP storefront requires PETSHOP_ENV=development in .env. Production uses Secure cookies and requires a separately configured HTTPS deployment; see docs/WINDOWS.md. Existing .env was preserved.'
                            }
                            $webPortText = Get-EnvValue $EnvFile 'PETSHOP_WEB_PORT' '8080'
                            if (-not [int]::TryParse($webPortText, [ref]$webPort) -or $webPort -lt 1 -or $webPort -gt 65535) { throw 'PETSHOP_WEB_PORT must be 1-65535.' }
                            if ($webPort -eq $port) { throw 'PETSHOP_WEB_PORT and PETSHOP_HTTP_PORT must be different.' }
                        }
                        Write-Status 'Checking image build. Unchanged layers and downloaded packages are reused.'
                        $services = @('api')
                        if ($hasFrontend) { $services += 'web' }
                        Invoke-Compose (@('build') + $services)
                        Write-Status 'Starting database, migrations and application...'
                        Invoke-Compose @('up', '--detach', '--no-build', '--pull', 'missing', '--wait', '--wait-timeout', '300')
                        $apiUrl = "http://127.0.0.1:$port"
                        Wait-Api $apiUrl
                        if ($hasFrontend -and (Get-EnvValue $EnvFile 'PETSHOP_ENV' 'production') -in @('development', 'test')) {
                            Write-Status 'Checking the marked Pitomo demonstration catalog; existing products and stock are preserved.'
                            Invoke-Compose @('exec', '-T', 'api', 'python', '-m', 'app.db.cli', 'seed-pitomo')
                        }
                        $url = if ($services -contains 'web') {
                            $webUrl = "http://127.0.0.1:$webPort"
                            $response = Invoke-WebRequest -UseBasicParsing -Uri "$webUrl/api/v1/storefront/config" -TimeoutSec 10
                            if ($response.StatusCode -ne 200) { throw 'Storefront API proxy is not ready.' }
                            $webUrl
                        } elseif ((Get-EnvValue $EnvFile 'PETSHOP_DOCS_ENABLED' 'false') -eq 'true') { "$apiUrl/docs" }
                        else { "$apiUrl/health" }
                        Write-Status "Petshop is ready: $url"
                        if (-not $NoBrowser) { Start-Process -FilePath $url }
                    }
                    'Admin' {
                        $email = Read-Host 'Administrator email'
                        $firstName = Read-Host 'First name'
                        # Interactive password stays inside the container prompt; no logs or command-line secret.
                        $arguments = @('compose', '--project-name', $ProjectName, '--project-directory', $Root,
                            '--env-file', $EnvFile, '-f', (Join-Path $Root 'docker-compose.yml'),
                            'exec', 'api', 'python', '-m', 'app.admin.bootstrap', '--email', $email, '--first-name', $firstName)
                        & $script:Docker.Cli --context desktop-linux @arguments
                        if ($LASTEXITCODE -ne 0) { throw 'Administrator setup failed.' }
                    }
                }
            } elseif ($Action -eq 'Stop') { Write-Status 'No project configuration exists; nothing to stop.' }
            else { throw 'Start Petshop with START.bat first.' }
        }
    }
} catch {
    Write-Status ("ERROR: " + $_.Exception.Message)
    Write-Host "Log: $LogFile"
    $exitCode = 1
} finally {
    if ($locked) { $mutex.ReleaseMutex() }
    $mutex.Dispose()
}
exit $exitCode
