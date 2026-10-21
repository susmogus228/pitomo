$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
. (Join-Path $root 'scripts\windows\common.ps1')

$project = 'petshop-recovery-test'
$password = 'A' * 48
$jwt = 'B' * 48
$script:mockContainers = @{
    api = [pscustomobject]@{
        Config = [pscustomobject]@{ Env = @(
            "PETSHOP_DATABASE_URL=postgresql+psycopg://petshop:$password@postgres:5432/petshop",
            "PETSHOP_JWT_SECRET=$jwt", 'PETSHOP_ENV=development', 'PETSHOP_DOCS_ENABLED=true'
        ) }
        HostConfig = [pscustomobject]@{ PortBindings = [pscustomobject]@{
            '8000/tcp' = @([pscustomobject]@{ HostIp = '127.0.0.1'; HostPort = '8000' })
        } }
    }
    postgres = [pscustomobject]@{
        Config = [pscustomobject]@{ Env = @(
            'POSTGRES_DB=petshop', 'POSTGRES_USER=petshop', "POSTGRES_PASSWORD=$password"
        ) }
        Mounts = @([pscustomobject]@{
            Type = 'volume'; Name = "${project}_petshop_postgres_data";
            Destination = '/var/lib/postgresql/data'
        })
    }
    web = [pscustomobject]@{
        Config = [pscustomobject]@{ Env = @('PETSHOP_PUBLIC_HOST=') }
        HostConfig = [pscustomobject]@{ PortBindings = [pscustomobject]@{
            '8080/tcp' = @([pscustomobject]@{ HostIp = '127.0.0.1'; HostPort = '8080' })
        } }
    }
}

# Replace only the container lookup; the recovery validation and private writer are real.
function Get-ComposeContainer([string]$ProjectName, [string]$Root, [string]$Service) {
    return $script:mockContainers[$Service]
}

$directory = Join-Path $root ('work\launcher-recovery-test-' + [Guid]::NewGuid().ToString('N'))
$null = New-Item -ItemType Directory -Path $directory
$envFile = Join-Path $directory '.env'
$checks = 0
function Check([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "Failed: $Message" }
    $script:checks++
}

Check (Restore-EnvFromComposeContainers $project $root $envFile) 'matching containers restore configuration'
Check ((Get-EnvValue $envFile 'POSTGRES_PASSWORD') -ceq $password) 'database password is preserved'
Check ((Get-EnvValue $envFile 'PETSHOP_JWT_SECRET') -ceq $jwt) 'JWT secret is preserved'
Check ((Get-Acl -LiteralPath $envFile).AreAccessRulesProtected) 'restored file has private ACL'
$originalHash = (Get-FileHash -LiteralPath $envFile -Algorithm SHA256).Hash
$refused = $false
try { Restore-EnvFromComposeContainers $project $root $envFile | Out-Null } catch { $refused = $true }
Check $refused 'existing configuration cannot be overwritten'
Check ((Get-FileHash -LiteralPath $envFile -Algorithm SHA256).Hash -eq $originalHash) 'existing bytes remain unchanged'

$script:mockContainers.postgres.Mounts[0].Name = 'other_project_petshop_postgres_data'
$invalidFile = Join-Path $directory 'invalid-volume.env'
Check (-not (Restore-EnvFromComposeContainers $project $root $invalidFile)) 'foreign database volume is rejected'
Check (-not (Test-Path -LiteralPath $invalidFile)) 'foreign volume creates no configuration'
$script:mockContainers.postgres.Mounts[0].Name = "${project}_petshop_postgres_data"

$script:mockContainers.web.HostConfig.PortBindings.'8080/tcp'[0].HostIp = '0.0.0.0'
$unsafeFile = Join-Path $directory 'public-port.env'
Check (-not (Restore-EnvFromComposeContainers $project $root $unsafeFile)) 'non-loopback port is rejected'
Check (-not (Test-Path -LiteralPath $unsafeFile)) 'unsafe port creates no configuration'

# A moved installation must retain its original Compose volumes.
$movedDirectory = Join-Path $directory 'moved-installation'
$null = New-Item -ItemType Directory -Path $movedDirectory
$originalProjectName = Get-ProjectName $root
Check ((Get-ProjectName $movedDirectory) -cne $originalProjectName) 'fresh folder derives its own project identity'
$identityFile = Join-Path $movedDirectory '.petshop-project-name'
[IO.File]::WriteAllText($identityFile, $originalProjectName + "`n")
Check ((Get-ProjectName $movedDirectory) -ceq $originalProjectName) 'moved installation reuses original Compose identity'
[IO.File]::WriteAllText($identityFile, 'other_project')
$invalidIdentityRejected = $false
try { Get-ProjectName $movedDirectory | Out-Null } catch { $invalidIdentityRejected = $true }
Check $invalidIdentityRejected 'invalid identity fails before selecting another database'

# Use a real child process to verify environment inheritance and cleanup.
$probe = Join-Path $directory 'docker-environment-probe.cmd'
[IO.File]::WriteAllText($probe, "@echo off`r`necho %GOMEMLIMIT%`r`nif `"%~3`"==`"fail`" exit /b 7`r`nexit /b 0`r`n", [Text.Encoding]::ASCII)
$script:Docker = @{ Cli = $probe }
$originalMemoryLimit = [Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process')
try {
    [Environment]::SetEnvironmentVariable('GOMEMLIMIT', $null, 'Process')
    Check ((Invoke-Docker @('version') -Capture) -ceq '128MiB') 'Docker child receives the default memory budget'
    Check ($null -eq [Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process')) 'successful invocation leaves no parent override'
    [Environment]::SetEnvironmentVariable('GOMEMLIMIT', '384MiB', 'Process')
    Check ((Invoke-Docker @('version') -Capture) -ceq '384MiB') 'Docker child respects an explicit memory budget'
    Check ([Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process') -ceq '384MiB') 'explicit parent budget is preserved'
    [Environment]::SetEnvironmentVariable('GOMEMLIMIT', $null, 'Process')
    $dockerFailureReported = $false
    try { Invoke-Docker @('fail') -Capture | Out-Null } catch { $dockerFailureReported = $_.Exception.Message -like 'Docker command failed (exit 7).*' }
    Check $dockerFailureReported 'failed Docker child retains the actionable error'
    Check ($null -eq [Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process')) 'failed invocation leaves no parent override'
    [Environment]::SetEnvironmentVariable('GOMEMLIMIT', '384MiB', 'Process')
    try { Invoke-Docker @('fail') -Capture | Out-Null } catch { }
    Check ([Environment]::GetEnvironmentVariable('GOMEMLIMIT', 'Process') -ceq '384MiB') 'failed invocation preserves an explicit parent budget'
} finally {
    [Environment]::SetEnvironmentVariable('GOMEMLIMIT', $originalMemoryLimit, 'Process')
}

Write-Output "Launcher recovery, relocation and child memory checks passed: $checks"
