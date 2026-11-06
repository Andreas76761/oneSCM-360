# oneSCM360 Knowledge Studio - Start script (Windows PowerShell 5.1 / PowerShell 7)
# Usage:  powershell.exe -ExecutionPolicy Bypass -File '.\start_onescm360.ps1'
# Optional parameters: -OneDriveRoot 'C:\...\-oneSCM360' -Port 8080 -NoBrowser
param(
    [string]$OneDriveRoot = $env:ONESCM_LOCAL_ONEDRIVE_ROOT,
    [int]$Port = $(if ($env:ONESCM_PORT) { [int]$env:ONESCM_PORT } else { 8080 }),
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

# OneDrive target: parameter > ONESCM_LOCAL_ONEDRIVE_ROOT > business OneDrive > personal OneDrive
if (-not $OneDriveRoot) {
    $base = if ($env:OneDriveCommercial) { $env:OneDriveCommercial } elseif ($env:OneDrive) { $env:OneDrive } else { $null }
    if ($base) { $OneDriveRoot = Join-Path -Path $base -ChildPath '-oneSCM360' }
}
if ($OneDriveRoot) { $env:ONESCM_LOCAL_ONEDRIVE_ROOT = $OneDriveRoot }
$env:ONESCM_HOST = '127.0.0.1'
$env:ONESCM_PORT = [string]$Port

# Python 3.10+
$python = $null
foreach ($candidate in @('py', 'python')) {
    if (Get-Command $candidate -ErrorAction SilentlyContinue) { $python = $candidate; break }
}
if (-not $python) { Write-Host 'Python wurde nicht gefunden. Bitte Python 3.10 oder neuer installieren.' -ForegroundColor Red; exit 1 }
$pyArgs = @()
if ($python -eq 'py') { $pyArgs = @('-3') }
& $python @pyArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"
if ($LASTEXITCODE -ne 0) { Write-Host 'Python 3.10 oder neuer ist erforderlich.' -ForegroundColor Red; exit 1 }

# Required packages: flask, jsonschema
& $python @pyArgs -c "import flask, jsonschema" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installiere Pflichtpakete (flask, jsonschema) ...'
    & $python @pyArgs -m pip install -r (Join-Path -Path $PSScriptRoot -ChildPath 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { Write-Host 'Installation fehlgeschlagen. Bitte Meldung oben pruefen.' -ForegroundColor Red; exit 1 }
}

if ($OneDriveRoot -and -not (Test-Path -LiteralPath $OneDriveRoot -PathType Container)) {
    Write-Host "Hinweis: OneDrive-Ziel existiert nicht: $OneDriveRoot" -ForegroundColor Yellow
    Write-Host 'Der Pfad kann im Register Synchronisation angepasst werden (Status PATH_MISSING).' -ForegroundColor Yellow
}

$url = "http://127.0.0.1:$Port"
if (-not $NoBrowser) {
    Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList $url | Out-Null
}
Write-Host "oneSCM360 Knowledge Studio startet auf $url (Beenden mit Strg+C)"
& $python @pyArgs (Join-Path -Path $PSScriptRoot -ChildPath 'app.py')
exit $LASTEXITCODE
