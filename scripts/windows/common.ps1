Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-ProjectName([string]$Path) {
    $identityFile = Join-Path $Path '.petshop-project-name'
    if (Test-Path -LiteralPath $identityFile -PathType Leaf) {
        $identity = [IO.File]::ReadAllText($identityFile).Trim()
        if ($identity -cnotmatch '^petshop-[a-f0-9]{12}$') {
            throw 'Invalid .petshop-project-name. Restore the original project identity before starting Docker.'
        }
        return $identity
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes([IO.Path]::GetFullPath($Path).ToLowerInvariant())
        $hash = [BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '').ToLowerInvariant()
        return "petshop-$($hash.Substring(0, 12))"
    } finally { $sha.Dispose() }
}

function New-RandomSecret {
    $bytes = New-Object byte[] 48
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Write-PrivateNewFile([string]$Path, [string]$Text) {
    $acl = New-Object Security.AccessControl.FileSecurity
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl.SetOwner($identity)
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($identity, 'FullControl', 'Allow')))
    $systemSid = New-Object Security.Principal.SecurityIdentifier('S-1-5-18')
    $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($systemSid, 'FullControl', 'Allow')))
    # Apply the private ACL before writing credentials; never replace an existing file.
    $stream = [IO.FileStream]::new($Path, [IO.FileMode]::CreateNew,
        [Security.AccessControl.FileSystemRights]::Write, [IO.FileShare]::None,
        4096, [IO.FileOptions]::None, $acl)
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes($Text)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally { $stream.Dispose() }
}

function Find-DockerDesktop {
    $locations = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\DockerDesktop'),
        (Join-Path $env:ProgramFiles 'Docker\Docker')
    )
    foreach ($location in $locations) {
        $desktop = Join-Path $location 'Docker Desktop.exe'
        $cli = Join-Path $location 'resources\bin\docker.exe'
        if ((Test-Path -LiteralPath $desktop) -and (Test-Path -LiteralPath $cli)) {
            return @{ Desktop = $desktop; Cli = $cli }
        }
    }
    return $null
}

function Get-WslVersion {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) { return $null }
    $output = (& wsl.exe --version 2>&1 | Out-String).Replace([string][char]0, '')
    if ($LASTEXITCODE -ne 0 -or $output -notmatch '(\d+\.\d+\.\d+(?:\.\d+)?)') { return $null }
    return [version]$Matches[1]
}

function Install-WslIfNeeded([version]$Minimum) {
    $version = Get-WslVersion
    if ($version -and $version -ge $Minimum) { return }
    $arguments = if ($version) { @('--update') } else { @('--install', '--no-distribution') }
    Write-Host 'Installing or updating WSL. Windows may request administrator approval.'
    $process = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments -Verb RunAs -WindowStyle Hidden -PassThru -Wait
    $version = Get-WslVersion
    if ($process.ExitCode -ne 0 -or -not $version -or $version -lt $Minimum) {
        throw 'WSL setup is incomplete. Restart Windows if requested, then run START.bat again.'
    }
}

function Get-VerifiedInstaller($Dependency, [string]$Directory) {
    $null = New-Item -ItemType Directory -Path $Directory -Force
    $target = Join-Path $Directory "DockerDesktop-$($Dependency.version).exe"
    if (Test-Path -LiteralPath $target) {
        $validHash = (Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -eq $Dependency.sha256
        $cachedSignature = Get-AuthenticodeSignature -LiteralPath $target
        if (-not $validHash -or $cachedSignature.Status -ne 'Valid' -or $cachedSignature.SignerCertificate.Subject -notmatch $Dependency.signerPattern) {
            Move-Item -LiteralPath $target -Destination ($target + '.invalid-' + [Guid]::NewGuid().ToString('N'))
            Write-Host 'Invalid cached installer preserved separately; downloading a verified copy.'
        }
    }
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Host "Downloading Docker Desktop $($Dependency.version) from desktop.docker.com..."
        Add-Type -AssemblyName System.Net.Http
        $client = New-Object Net.Http.HttpClient
        $cancel = New-Object Threading.CancellationTokenSource
        $cancel.CancelAfter([TimeSpan]::FromMinutes(20))
        $partial = "$target.$([Guid]::NewGuid().ToString('N')).partial"
        try {
            $response = $client.GetAsync([uri]$Dependency.url, [Net.Http.HttpCompletionOption]::ResponseHeadersRead, $cancel.Token).GetAwaiter().GetResult()
            $null = $response.EnsureSuccessStatusCode()
            $inputStream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
            $outputStream = [IO.File]::Open($partial, [IO.FileMode]::CreateNew)
            try { $inputStream.CopyToAsync($outputStream, 81920, $cancel.Token).GetAwaiter().GetResult() }
            finally { $outputStream.Dispose(); $inputStream.Dispose(); $response.Dispose() }
            if ((Get-FileHash -LiteralPath $partial -Algorithm SHA256).Hash -ne $Dependency.sha256) {
                throw 'Downloaded installer checksum does not match. Installation was cancelled.'
            }
            Move-Item -LiteralPath $partial -Destination $target
        } finally { $cancel.Dispose(); $client.Dispose() }
    }
    if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $Dependency.sha256) {
        throw 'Cached Docker installer checksum does not match. Installation was cancelled.'
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $target
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch $Dependency.signerPattern) {
        throw 'Docker installer signature is invalid. Installation was cancelled.'
    }
    return $target
}

function Invoke-Docker([string[]]$DockerArguments, [switch]$Capture) {
    # Force the local Desktop context; do not inherit a remote DOCKER_HOST.
    $previous = $ErrorActionPreference
    $previousMemoryLimit = [Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process')
    $ErrorActionPreference = 'Continue'
    try {
        # Reduce CLI/Compose/Buildx memory pressure on small Windows hosts.
        # Respect an explicit override and restore the parent environment.
        if ([string]::IsNullOrWhiteSpace($previousMemoryLimit)) {
            [Environment]::SetEnvironmentVariable('GOMEMLIMIT', '128MiB', 'Process')
        }
        $result = @(& $script:Docker.Cli --context desktop-linux @DockerArguments 2>&1)
        $exitCode = $LASTEXITCODE
    } finally {
        [Environment]::SetEnvironmentVariable('GOMEMLIMIT', $previousMemoryLimit, 'Process')
        $ErrorActionPreference = $previous
    }
    if ($exitCode -ne 0) {
        $detail = ConvertTo-SafeDiagnostic (($result | Select-Object -Last 20 | Out-String).Trim())
        if ($detail) {
            Write-Host $detail
            if (Get-Variable -Name LauncherLogPath -Scope Script -ErrorAction SilentlyContinue) {
                Add-Content -LiteralPath $script:LauncherLogPath -Value $detail -Encoding UTF8
            }
        }
        throw "Docker command failed (exit $exitCode). Run DIAGNOSTICS.bat."
    }
    if ($Capture) { return ($result | Out-String).Trim() }
    $result | ForEach-Object { Write-Host $_ }
}

function Get-ComposeContainer([string]$ProjectName, [string]$Root, [string]$Service) {
    $ids = Invoke-Docker @('ps', '--all', '--quiet', '--filter', "label=com.docker.compose.project=$ProjectName",
        '--filter', "label=com.docker.compose.service=$Service") -Capture
    $matches = @($ids -split '\s+' | Where-Object { $_ })
    if ($matches.Count -ne 1) { return $null }
    $containers = @(ConvertFrom-Json -InputObject (Invoke-Docker @('inspect', $matches[0]) -Capture))
    if ($containers.Count -ne 1) { return $null }
    $container = $containers[0]
    $labels = $container.Config.Labels
    if (-not $labels -or -not $labels.'com.docker.compose.project.working_dir' -or
        $labels.'com.docker.compose.project' -ne $ProjectName -or
        $labels.'com.docker.compose.service' -ne $Service -or
        -not [string]::Equals([IO.Path]::GetFullPath($labels.'com.docker.compose.project.working_dir').TrimEnd('\'),
            [IO.Path]::GetFullPath($Root).TrimEnd('\'), [StringComparison]::OrdinalIgnoreCase)) {
        return $null
    }
    return $container
}

function Get-ContainerEnvironment($Container) {
    $values = @{}
    foreach ($line in $Container.Config.Env) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) { $values[$line.Substring(0, $separator)] = $line.Substring($separator + 1) }
    }
    return $values
}

function Get-LoopbackPort($Container, [string]$ContainerPort) {
    if (-not $Container -or -not $Container.HostConfig.PortBindings) { return $null }
    $property = $Container.HostConfig.PortBindings.PSObject.Properties[$ContainerPort]
    if (-not $property) { return $null }
    $bindings = @($property.Value)
    if ($bindings.Count -ne 1 -or $bindings[0].HostIp -ne '127.0.0.1') { return $null }
    $port = 0
    if (-not [int]::TryParse($bindings[0].HostPort, [ref]$port) -or $port -lt 1 -or $port -gt 65535) {
        return $null
    }
    return [string]$port
}

function Restore-EnvFromComposeContainers([string]$ProjectName, [string]$Root, [string]$EnvFile) {
    $api = Get-ComposeContainer $ProjectName $Root 'api'
    $postgres = Get-ComposeContainer $ProjectName $Root 'postgres'
    if (-not $api -or -not $postgres) { return $false }
    $dataVolume = "${ProjectName}_petshop_postgres_data"
    if (-not @($postgres.Mounts | Where-Object {
        $_.Type -eq 'volume' -and $_.Name -eq $dataVolume -and $_.Destination -eq '/var/lib/postgresql/data'
    }).Count) { return $false }

    $appEnv = Get-ContainerEnvironment $api
    $dbEnv = Get-ContainerEnvironment $postgres
    foreach ($key in @('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD')) {
        if ([string]::IsNullOrWhiteSpace($dbEnv[$key])) { return $false }
    }
    foreach ($key in @('PETSHOP_DATABASE_URL', 'PETSHOP_JWT_SECRET', 'PETSHOP_ENV')) {
        if ([string]::IsNullOrWhiteSpace($appEnv[$key])) { return $false }
    }
    # Compose expands dollar signs in .env. Recover only values generated by this launcher.
    if ($dbEnv.POSTGRES_PASSWORD -notmatch '^[A-Za-z0-9_-]{32,}$' -or
        $appEnv.PETSHOP_JWT_SECRET -notmatch '^[A-Za-z0-9_-]{32,}$') { return $false }
    $uri = $null
    if (-not [Uri]::TryCreate($appEnv.PETSHOP_DATABASE_URL, [UriKind]::Absolute, [ref]$uri) -or
        $uri.Scheme -notin @('postgresql', 'postgresql+psycopg') -or $uri.Host -ne 'postgres' -or
        $uri.Port -ne 5432) { return $false }
    $credentials = [Uri]::UnescapeDataString($uri.UserInfo)
    $separator = $credentials.IndexOf(':')
    if ($separator -lt 1 -or $credentials.Substring(0, $separator) -cne $dbEnv.POSTGRES_USER -or
        $credentials.Substring($separator + 1) -cne $dbEnv.POSTGRES_PASSWORD -or
        [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/')) -cne $dbEnv.POSTGRES_DB) {
        return $false
    }

    $apiPort = Get-LoopbackPort $api '8000/tcp'
    $web = Get-ComposeContainer $ProjectName $Root 'web'
    $webPort = if ($web) { Get-LoopbackPort $web '8080/tcp' } else { '8080' }
    if (-not $apiPort -or -not $webPort -or $apiPort -eq $webPort) { return $false }
    $values = [ordered]@{
        POSTGRES_DB = $dbEnv.POSTGRES_DB
        POSTGRES_USER = $dbEnv.POSTGRES_USER
        POSTGRES_PASSWORD = $dbEnv.POSTGRES_PASSWORD
        PETSHOP_DATABASE_URL = $appEnv.PETSHOP_DATABASE_URL
        PETSHOP_JWT_SECRET = $appEnv.PETSHOP_JWT_SECRET
        PETSHOP_ENV = $appEnv.PETSHOP_ENV
        PETSHOP_IMAGE = "${ProjectName}:local"
        PETSHOP_HTTP_PORT = $apiPort
        PETSHOP_WEB_PORT = $webPort
    }
    foreach ($key in @('PETSHOP_ACCESS_TOKEN_MINUTES', 'PETSHOP_SQL_ECHO', 'PETSHOP_CORS_ORIGINS',
        'PETSHOP_DOCS_ENABLED', 'PETSHOP_LOGIN_MAX_ATTEMPTS', 'PETSHOP_LOGIN_WINDOW_SECONDS',
        'PETSHOP_PUBLIC_ORIGIN', 'PETSHOP_SECURE_COOKIES',
        'PETSHOP_GEOAPIFY_API_KEY', 'PETSHOP_GEOAPIFY_DAILY_LIMIT')) {
        if ($appEnv.ContainsKey($key)) { $values[$key] = $appEnv[$key] }
    }
    if ($web) {
        $webEnv = Get-ContainerEnvironment $web
        if ($webEnv.ContainsKey('PETSHOP_PUBLIC_HOST')) { $values['PETSHOP_PUBLIC_HOST'] = $webEnv.PETSHOP_PUBLIC_HOST }
    }
    foreach ($value in $values.Values) {
        if ($null -eq $value -or $value -match '[\r\n\$]' ) { return $false }
    }
    $content = (($values.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "`n") + "`n"
    Write-PrivateNewFile $EnvFile $content
    return $true
}

function ConvertTo-SafeDiagnostic([string]$Text) {
    if ((Get-Variable -Name LauncherEnvPath -Scope Script -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $script:LauncherEnvPath)) {
        foreach ($line in [IO.File]::ReadAllLines($script:LauncherEnvPath)) {
            if ($line -match '^\s*[A-Z0-9_]*(?:PASSWORD|SECRET|TOKEN|DATABASE_URL)[A-Z0-9_]*\s*=\s*(.+)$') {
                $value = $Matches[1].Trim().Trim('"').Trim("'")
                if ($value.Length -ge 4) { $Text = $Text.Replace($value, '[redacted]') }
            }
        }
    }
    $Text = $Text -replace '(?i)([a-z][a-z0-9+.-]*://)[^\s/@]+:[^\s/@]+@', '$1[redacted]@'
    $Text = $Text -replace '\x1b\[[0-9;]*[a-zA-Z]', ''
    if ($Text.Length -gt 4000) { return $Text.Substring($Text.Length - 4000) }
    return $Text
}

function Test-DockerReady {
    $process = New-Object Diagnostics.Process
    try {
        $process.StartInfo.FileName = $script:Docker.Cli
        $process.StartInfo.Arguments = '--context desktop-linux info --format {{.OSType}}'
        $process.StartInfo.UseShellExecute = $false
        $process.StartInfo.CreateNoWindow = $true
        $process.StartInfo.RedirectStandardOutput = $true
        $process.StartInfo.RedirectStandardError = $true
        $null = $process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit(10000)) { $process.Kill(); $process.WaitForExit(); return $false }
        return $process.ExitCode -eq 0 -and $stdout.GetAwaiter().GetResult().Trim() -eq 'linux'
    } catch { return $false } finally { $process.Dispose() }
}

function Wait-DockerReady([int]$Seconds = 180) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-DockerReady) { return }
        Start-Sleep -Seconds 3
    }
    throw 'Docker did not become ready. Open Docker Desktop to check first-run prompts or errors; run DIAGNOSTICS.bat.'
}

function Get-EnvValue([string]$Path, [string]$Name, [string]$Default = '') {
    foreach ($line in [IO.File]::ReadAllLines($Path)) {
        if ($line -match ('^\s*' + [regex]::Escape($Name) + '\s*=\s*(.*)\s*$')) {
            return $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    return $Default
}

function Wait-Api([string]$Url, [int]$Seconds = 120) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri "$Url/ready" -TimeoutSec 5
            if ($response.StatusCode -eq 200) { return }
        } catch { }
        Start-Sleep -Seconds 2
    }
    throw 'API readiness check failed. Run DIAGNOSTICS.bat.'
}
