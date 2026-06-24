param(
  [int]$ApiPort = 8000,
  [int]$WebPort = 5173
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

function Start-If-Free {
  param(
    [int]$Port,
    [string]$Name,
    [string]$FilePath,
    [string[]]$ArgumentList,
    [string]$WorkingDirectory
  )

  $existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($existing) {
    Write-Host "$Name already listening on port $Port (PID $($existing.OwningProcess))"
    return
  }

  Start-Process -FilePath $FilePath -ArgumentList $ArgumentList -WorkingDirectory $WorkingDirectory -WindowStyle Hidden
  Write-Host "Started $Name on port $Port"
}

Start-If-Free `
  -Port $ApiPort `
  -Name "FastAPI" `
  -FilePath "uv" `
  -ArgumentList @("run", "--with-requirements", "backend\requirements.txt", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "$ApiPort") `
  -WorkingDirectory $Root

Start-If-Free `
  -Port $WebPort `
  -Name "Vite" `
  -FilePath "npm.cmd" `
  -ArgumentList @("--prefix", "frontend", "run", "dev", "--", "--host", "0.0.0.0", "--port", "$WebPort") `
  -WorkingDirectory $Root

Write-Host "Frontend: http://localhost:$WebPort"
Write-Host "Backend:  http://localhost:$ApiPort"
Write-Host "Health:   http://localhost:$ApiPort/health/detail"
Write-Host ""
Write-Host "提示：进程窗口已隐藏。如遇问题，可查看 logs/ 或手动运行："
Write-Host "  cd $Root"
Write-Host "  uv run --with-requirements backend\requirements.txt uvicorn backend.app.main:app --host 0.0.0.0 --port $ApiPort"