param(
  [string]$ApiBase = "http://localhost:8000",
  [string]$AdminUsername = "admin",
  [string]$AdminPassword = $env:SEED_ADMIN_PASSWORD
)

$ErrorActionPreference = "Stop"

function Assert-True {
  param([bool]$Condition, [string]$Message)
  if (-not $Condition) {
    throw "Smoke failed: $Message"
  }
}

$health = Invoke-RestMethod -Uri "$ApiBase/health"
Assert-True ($health.status -eq "ok") "health endpoint did not return ok"

if ([string]::IsNullOrWhiteSpace($AdminPassword)) {
  throw "Smoke failed: AdminPassword is required. Pass -AdminPassword or set SEED_ADMIN_PASSWORD."
}

$login = Invoke-RestMethod `
  -Uri "$ApiBase/api/auth/login" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ username = $AdminUsername; password = $AdminPassword } | ConvertTo-Json)

Assert-True ([string]::IsNullOrWhiteSpace($login.accessToken) -eq $false) "login did not return access token"
$headers = @{ Authorization = "Bearer $($login.accessToken)" }

# /health/detail exposes internal diagnostics and now requires admin auth.
# Call it AFTER login so the smoke test still covers detailed health checks.
$healthDetail = Invoke-RestMethod -Uri "$ApiBase/health/detail" -Headers $headers
Assert-True ($healthDetail.checks.database.ok -eq $true) "database health check failed"

$bootstrap = Invoke-RestMethod -Uri "$ApiBase/api/admin/bootstrap" -Headers $headers
Assert-True ($bootstrap.roles.Count -ge 1) "bootstrap returned no roles"
Assert-True ($bootstrap.knowledgeBases.Count -ge 1) "bootstrap returned no knowledge bases"

$selfDeleteStatus = 0
try {
  Invoke-RestMethod `
    -Uri "$ApiBase/api/admin/users/$($login.user.id)" `
    -Method Delete `
    -Headers $headers | Out-Null
} catch {
  $selfDeleteStatus = $_.Exception.Response.StatusCode.value__
}

Assert-True ($selfDeleteStatus -eq 400) "current user delete should be blocked with 400"

$smokeUsername = "smoke_user"
$usersBefore = Invoke-RestMethod -Uri "$ApiBase/api/admin/users" -Headers $headers
$existingSmokeUser = $usersBefore.users | Where-Object { $_.username -eq $smokeUsername } | Select-Object -First 1
if ($null -ne $existingSmokeUser) {
  Invoke-RestMethod `
    -Uri "$ApiBase/api/admin/users/$($existingSmokeUser.id)" `
    -Method Delete `
    -Headers $headers | Out-Null
}

$smokeUser = Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/users" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{
    username = $smokeUsername
    full_name = "Smoke User"
    password = "smoke123"
    role_key = "sales"
    is_active = $true
  } | ConvertTo-Json)

$updatedSmokeUser = Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/users/$($smokeUser.id)" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ role_key = "promo"; is_active = $false; password = "smoke456" } | ConvertTo-Json)

Assert-True ($updatedSmokeUser.role.key -eq "promo") "user role update failed"
Assert-True ($updatedSmokeUser.isActive -eq $false) "user deactivate failed"

$reactivatedSmokeUser = Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/users/$($smokeUser.id)" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ role_key = "sales"; is_active = $true } | ConvertTo-Json)

Assert-True ($reactivatedSmokeUser.isActive -eq $true) "user reactivate failed"

Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/users/$($smokeUser.id)" `
  -Method Delete `
  -Headers $headers | Out-Null

$artifact = Invoke-RestMethod `
  -Uri "$ApiBase/api/artifacts" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{
    artifact_type = "lead_score"
    title = "smoke-artifact"
    source = "smoke"
    result = @{ score = 88 }
    status = "draft"
  } | ConvertTo-Json -Depth 5)

Assert-True ($artifact.status -eq "draft") "artifact create did not return draft status"

$updatedArtifact = Invoke-RestMethod `
  -Uri "$ApiBase/api/artifacts/$($artifact.id)" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ status = "completed" } | ConvertTo-Json)

Assert-True ($updatedArtifact.status -eq "completed") "artifact status update failed"

$fetchedArtifact = Invoke-RestMethod -Uri "$ApiBase/api/artifacts/$($artifact.id)" -Headers $headers
Assert-True ($fetchedArtifact.id -eq $artifact.id) "artifact detail endpoint returned wrong artifact"

Invoke-RestMethod `
  -Uri "$ApiBase/api/artifacts/$($artifact.id)" `
  -Method Delete `
  -Headers $headers | Out-Null

$search = Invoke-RestMethod `
  -Uri "$ApiBase/api/knowledge/product/search" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ query = "E0 board"; top_k = 3 } | ConvertTo-Json)

if ($search.results.Count -gt 0) {
  Assert-True ($null -ne $search.results[0].chunkId) "knowledge search returned null chunkId"
}

$businessQuery = -join @([char]0x73AF, [char]0x4FDD, [char]0x677F, [char]0x6750)
$businessSearch = Invoke-RestMethod `
  -Uri "$ApiBase/api/knowledge/product/search" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ query = $businessQuery; top_k = 3 } | ConvertTo-Json)

Assert-True ($businessSearch.results.Count -gt 0) "business query should return RAG matches"
Assert-True ($businessSearch.results[0].relevance.accepted -eq $true) "business query should pass relevance gate"
Assert-True ($businessSearch.ragStatus.code -in @("hit", "maybe")) "business query should return hit or maybe RAG status"

$irrelevantSearch = Invoke-RestMethod `
  -Uri "$ApiBase/api/knowledge/product/search" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ query = "what did you eat today"; top_k = 3 } | ConvertTo-Json)

Assert-True ($irrelevantSearch.results.Count -eq 0) "irrelevant query should not return RAG matches"
Assert-True ($irrelevantSearch.ragStatus.code -eq "miss") "irrelevant query should return miss RAG status"

$foodQuery = -join @([char]0x4F60, [char]0x4ECA, [char]0x5929, [char]0x5403, [char]0x5C0F, [char]0x9F99, [char]0x867E, [char]0x4E86, [char]0x5417)
$foodSearch = Invoke-RestMethod `
  -Uri "$ApiBase/api/knowledge/product/search" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ query = $foodQuery; top_k = 3 } | ConvertTo-Json)

Assert-True ($foodSearch.results.Count -eq 0) "food chat query should not return RAG matches"
Assert-True ($foodSearch.ragStatus.code -eq "miss") "food chat query should return miss RAG status"

$ragLogs = Invoke-RestMethod -Uri "$ApiBase/api/rag/query-logs" -Headers $headers
Assert-True ($ragLogs.logs.Count -ge 1) "RAG query log endpoint returned no logs after search"

Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/agents/sales" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ status = "online" } | ConvertTo-Json) | Out-Null

$persistMessage = "smoke persist chat " + ([guid]::NewGuid().ToString("N"))
$persistChat = Invoke-RestMethod `
  -Uri "$ApiBase/api/chat/completions" `
  -Method Post `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{
    provider = "deepseek"
    model = "deepseek-chat"
    messages = @(@{ role = "user"; content = $persistMessage })
    max_tokens = 80
    metadata = @{ conversation_key = "sales" }
  } | ConvertTo-Json -Depth 8)

Assert-True ($persistChat.choices.Count -ge 1) "persist chat did not return choices"

$salesConversation = Invoke-RestMethod -Uri "$ApiBase/api/conversations/sales" -Headers $headers
$persistedUserMessage = $salesConversation.messages | Where-Object { $_.sender -eq "me" -and $_.content -eq $persistMessage } | Select-Object -First 1
$persistedAssistantMessage = $salesConversation.messages | Where-Object { $_.sender -eq "ai" -and $_.type -eq "text" } | Select-Object -Last 1
Assert-True ($null -ne $persistedUserMessage) "chat user message was not persisted to conversation"
Assert-True ($null -ne $persistedAssistantMessage -and -not [string]::IsNullOrWhiteSpace($persistedAssistantMessage.content)) "chat assistant reply was not persisted to conversation"

Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/agents/sales" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ status = "paused" } | ConvertTo-Json) | Out-Null

$blockedStatus = 0
try {
  Invoke-RestMethod `
    -Uri "$ApiBase/api/chat/completions" `
    -Method Post `
    -Headers $headers `
    -ContentType "application/json; charset=utf-8" `
    -Body (@{
      provider = "deepseek"
      model = "deepseek-chat"
      messages = @(@{ role = "user"; content = "test" })
      max_tokens = 20
      metadata = @{ conversation_key = "sales" }
    } | ConvertTo-Json -Depth 8) | Out-Null
} catch {
  $blockedStatus = $_.Exception.Response.StatusCode.value__
}

Invoke-RestMethod `
  -Uri "$ApiBase/api/admin/agents/sales" `
  -Method Patch `
  -Headers $headers `
  -ContentType "application/json; charset=utf-8" `
  -Body (@{ status = "online" } | ConvertTo-Json) | Out-Null

Assert-True ($blockedStatus -eq 409) "paused agent did not block chat with 409"

Write-Host "Smoke passed"
