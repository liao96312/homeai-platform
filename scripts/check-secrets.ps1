param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
)

$ErrorActionPreference = 'Stop'
$sensitivePaths = @('.env', 'dev.db', 'chroma_data', 'models', 'logs')
$gitDir = Join-Path $Root '.git'
$gitignore = Join-Path $Root '.gitignore'

Write-Host "Secret hygiene check: $Root"

if (-not (Test-Path $gitignore)) {
  Write-Error ".gitignore is missing"
}

$gitignoreText = Get-Content $gitignore -Raw
foreach ($path in $sensitivePaths) {
  if ($gitignoreText -notmatch [regex]::Escape($path)) {
    Write-Error ".gitignore does not include $path"
  }
}

if (Test-Path (Join-Path $Root '.env')) {
  Write-Warning ".env exists locally. Keep it out of git and rotate keys if it was ever shared."
}

$localSecretFiles = @('.env', '.env.production', 'frontend/.env')
$secretKeyNames = @(
  'DEEPSEEK_API_KEY',
  'OPENAI_API_KEY',
  'WECOM_BOT_SECRET',
  'WECOM_INTERNAL_TOKEN',
  'JWT_SECRET_KEY',
  'HASH_EMBEDDING_KEY',
  'SEED_ADMIN_PASSWORD',
  'VITE_DEMO_ADMIN_PASSWORD',
  'VITE_DEMO_SALES_PASSWORD',
  'VITE_DEMO_DESIGNER_PASSWORD',
  'VITE_DEMO_PROMO_PASSWORD'
)
$allowedPlaceholderPattern = '^(|change-me.*|local-dev.*|replace-me.*|your-.*|CHANGEME.*|example.*)$'

foreach ($relativePath in $localSecretFiles) {
  $filePath = Join-Path $Root $relativePath
  if (-not (Test-Path $filePath)) {
    continue
  }

  $lineNumber = 0
  foreach ($line in Get-Content $filePath) {
    $lineNumber += 1
    $trimmed = $line.Trim()
    if ($trimmed -eq '' -or $trimmed.StartsWith('#')) {
      continue
    }

    if ($trimmed -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$') {
      $key = $Matches[1]
      $value = $Matches[2].Trim().Trim('"').Trim("'")
      if ($secretKeyNames -contains $key) {
        if ($key -in @('DEEPSEEK_API_KEY', 'OPENAI_API_KEY') -and $value -match '^sk-[A-Za-z0-9_-]{16,}$') {
          Write-Error "Potential API key found in ${relativePath}:${lineNumber} ($key). Remove it from local files and rotate it."
        }
        if ($key -notin @('DEEPSEEK_API_KEY', 'OPENAI_API_KEY') -and $value -notmatch $allowedPlaceholderPattern) {
          Write-Error "Potential secret value found in ${relativePath}:${lineNumber} ($key). Remove it from local files and rotate it."
        }
      }
    }
  }
}

if (Test-Path $gitDir) {
  $tracked = git -C $Root ls-files .env dev.db chroma_data models logs 2>$null
  if ($tracked) {
    Write-Error "Sensitive local files are tracked by git:`n$tracked"
  }
  Write-Host "Git tracking check passed."
} else {
  Write-Host "No .git directory found; skipping tracked-file check."
}

Write-Host "Secret hygiene check passed."
