$ErrorActionPreference = 'Stop'
$labRoot = $PSScriptRoot
try {
    $existingLab = Invoke-RestMethod -Uri 'http://127.0.0.1:8788/api/report' -TimeoutSec 2
    if ($existingLab.id) { Write-Output 'PolyLab is already running: http://127.0.0.1:8788'; exit 0 }
} catch {}
Start-Process -FilePath "$labRoot/.venv/Scripts/python.exe" -ArgumentList '-m','polylab.server' -WorkingDirectory $labRoot -RedirectStandardOutput "$labRoot/data/server.stdout.log" -RedirectStandardError "$labRoot/data/server.stderr.log" -WindowStyle Hidden
Write-Output 'PolyLab is starting at http://127.0.0.1:8788'
