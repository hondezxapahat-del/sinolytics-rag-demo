<#
  sinolyticsdemo.ps1 - one-click launcher for the Sinolytics RAG demo.

  USAGE
    Double-click sinolyticsdemo.bat (recommended - no PowerShell prompts),
    or run this script directly from PowerShell:
        powershell -ExecutionPolicy Bypass -File sinolyticsdemo.ps1

  WHAT IT DOES
    1. Navigates to the project folder itself - you can run this script
       from anywhere (e.g. a Desktop shortcut), it doesn't need you to
       already be in the right directory.
    2. Checks if port 8000 (the backend) is already in use and, if so,
       stops whatever is listening there (safe: on this machine, only this
       project's own backend ever binds to that port).
    3. Starts the FastAPI backend (python -m uvicorn api:app) in its own
       window on port 8000.
    4. Waits until the backend actually responds to /health - not just a
       fixed delay - before continuing.
    5. Opens the login page directly as a local file in Chrome (NOT via a
       web server - a static file server would expose the whole project
       folder, including .env, to anything that can reach that port, so
       the frontend is deliberately just opened as a file:// page instead).

  STOPPING
    Close the "sinolyticsdemo backend" window, or run:
        Get-Content .sinolyticsdemo.pid | ForEach-Object { Stop-Process -Id $_ -Force }
#>

$ErrorActionPreference = 'Stop'

$ProjectDir  = 'd:\firstclass-demo'
$BackendPort = 8000
$ChromePaths = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

# --- Step 1: always run from the project folder, regardless of where this
# script itself was launched from. ---
Set-Location $ProjectDir
Write-Host "Working directory: $ProjectDir"

# --- Step 2: free up the backend port if something's already on it. ---
Write-Host "`nChecking port $BackendPort..."
$existing = Get-NetTCPConnection -LocalPort $BackendPort -State Listen -ErrorAction SilentlyContinue
foreach ($conn in $existing) {
    Write-Host "  Port $BackendPort is in use (PID $($conn.OwningProcess)) - stopping it."
    Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
}
if ($existing) { Start-Sleep -Milliseconds 800 }

# --- Step 3: start the backend in its own window. ---
Write-Host "`nStarting backend on port $BackendPort..."
$backend = Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "api:app", "--port", "$BackendPort" `
    -WorkingDirectory $ProjectDir `
    -WindowStyle Normal `
    -PassThru
"$($backend.Id)" | Out-File -FilePath ".sinolyticsdemo.pid" -Encoding utf8

# --- Step 4: wait for readiness (poll, don't guess a fixed sleep). ---
Write-Host "Waiting for the backend to be ready..."
$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$BackendPort/health" -UseBasicParsing -TimeoutSec 2
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if (-not $ready) {
    Write-Host "`nBackend did not become ready within 30 seconds." -ForegroundColor Red
    Write-Host "Check the 'sinolyticsdemo backend' window for the actual error." -ForegroundColor Red
    exit 1
}
Write-Host "Backend is ready at http://127.0.0.1:$BackendPort"

# --- Step 5: open the frontend as a local file (never as a served directory). ---
$loginPage = Join-Path $ProjectDir "login.html"
$chrome = $ChromePaths | Where-Object { Test-Path $_ } | Select-Object -First 1

Write-Host "`nOpening $loginPage"
if ($chrome) {
    Start-Process -FilePath $chrome -ArgumentList $loginPage
} else {
    Write-Host "Chrome wasn't found in the usual install locations - opening with your default browser instead." -ForegroundColor Yellow
    Start-Process $loginPage
}

Write-Host "`nAll set. Leave the 'sinolyticsdemo backend' window open while you use the app."
