$projectRoot = $PSScriptRoot
$parentRoot = Split-Path $projectRoot -Parent

$pythonCandidates = @(
    (Join-Path $projectRoot 'venv\Scripts\python.exe'),
    (Join-Path $parentRoot 'venv\Scripts\python.exe'),
    'python'
)

$pythonCmd = $null
foreach ($candidate in $pythonCandidates) {
    if ($candidate -eq 'python' -or (Test-Path $candidate)) {
        $pythonCmd = $candidate
        break
    }
}

if (-not $pythonCmd) {
    Write-Error 'Python executable not found. Create a venv or install Python first.'
    exit 1
}

$backendDir = Join-Path $projectRoot 'backend'
$frontendDir = $projectRoot

if (-not (Test-Path $backendDir)) {
    Write-Error "Backend directory not found: $backendDir"
    exit 1
}

Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$backendDir'; & '$pythonCmd' -m uvicorn main:app --reload"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "cd '$frontendDir'; & '$pythonCmd' frontend_server.py"

Write-Host 'SecureFin project started.'
Write-Host 'Backend:  http://127.0.0.1:8000'
Write-Host 'Frontend: http://127.0.0.1:5500'
Write-Host "Python:   $pythonCmd"
