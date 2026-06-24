$ErrorActionPreference = "Stop"

function Write-Check($name, $ok, $detail = "") {
  $mark = if ($ok) { "OK" } else { "FAIL" }
  Write-Host "[$mark] $name $detail"
}

$docker = Get-Command docker -ErrorAction SilentlyContinue
Write-Check "Docker CLI on Windows" ([bool]$docker) ($(if ($docker) { $docker.Source } else { "not found" }))

if ($docker) {
  try {
    $version = docker --version
    Write-Check "Docker version" $true $version
    docker compose version | Out-Host
  } catch {
    Write-Check "Docker compose" $false $_.Exception.Message
  }
}

$wsl = Get-Command wsl -ErrorAction SilentlyContinue
Write-Check "WSL command" ([bool]$wsl) ($(if ($wsl) { $wsl.Source } else { "not found" }))

if ($wsl) {
  try {
    $list = wsl -l -v
    $list | Out-Host
    if ($list -match "\s1\s*$") {
      Write-Host "WSL distro appears to be version 1. Docker Engine normally requires WSL 2 or Docker Desktop WSL integration."
      Write-Host "Try: wsl --update"
      Write-Host "Then: wsl --set-version Ubuntu 2"
    }
  } catch {
    Write-Check "WSL list" $false $_.Exception.Message
  }

  try {
    wsl -- docker --version | Out-Host
  } catch {
    Write-Check "Docker CLI inside WSL" $false "not found or not runnable"
  }
}
