$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot

Push-Location $Root
try {
  python -m alembic upgrade head
}
finally {
  Pop-Location
}
