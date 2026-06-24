param(
  [string]$Model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
  [string]$CacheDir = ".\models\fastembed"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ResolvedCache = Join-Path $Root $CacheDir
New-Item -ItemType Directory -Force -Path $ResolvedCache | Out-Null

$env:EMBEDDING_PROVIDER = "fastembed"
$env:EMBEDDING_MODEL = $Model
$env:EMBEDDING_CACHE_DIR = $ResolvedCache
$env:EMBEDDING_ALLOW_DOWNLOAD = "true"

Push-Location $Root
try {
  python -c "import os; from backend.app.services.knowledge import embed_text_fastembed; v=embed_text_fastembed('local embedding init'); print({'model':os.environ['EMBEDDING_MODEL'],'cacheDir':os.environ['EMBEDDING_CACHE_DIR'],'dim':len(v)})"
}
finally {
  Pop-Location
}
