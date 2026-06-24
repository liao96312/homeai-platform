#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
PROFILE_ARGS=()

if [[ "${ENABLE_WECOM:-false}" == "true" ]]; then
  PROFILE_ARGS=(--profile wecom)
fi

cd "$PROJECT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE. Copy .env.production.example and fill real values first." >&2
  exit 1
fi

bash scripts/check-production-env.sh "$ENV_FILE"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  git pull --ff-only
fi

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${PROFILE_ARGS[@]}" build
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" up -d --wait postgres redis
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" run --rm backend python -m alembic upgrade head
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${PROFILE_ARGS[@]}" up -d
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" "${PROFILE_ARGS[@]}" ps
docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend \
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read()"
echo "Backend health check passed"
