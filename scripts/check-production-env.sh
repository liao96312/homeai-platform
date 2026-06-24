#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${1:-.env.production}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

required_keys=(
  APP_ENV
  AUTO_MIGRATE_ON_STARTUP
  EXPOSE_API_DOCS
  POSTGRES_PASSWORD
  REDIS_PASSWORD
  JWT_SECRET_KEY
  CORS_ORIGINS
  SEED_ADMIN_PASSWORD
  DEEPSEEK_API_KEY
  CADDY_DOMAIN
)

bad_patterns=(
  "replace-with"
  "change-me"
  "your-domain.example.com"
  "admin@example.com"
  "sk-test"
)

for key in "${required_keys[@]}"; do
  if ! grep -Eq "^${key}=.+" "$ENV_FILE"; then
    echo "Missing required key: $key" >&2
    exit 1
  fi
done

for pattern in "${bad_patterns[@]}"; do
  if grep -Eiq "$pattern" "$ENV_FILE"; then
    echo "Production env still contains placeholder pattern: $pattern" >&2
    exit 1
  fi
done

if ! grep -Eq '^APP_ENV=production$' "$ENV_FILE"; then
  echo "APP_ENV must be production" >&2
  exit 1
fi

if ! grep -Eq '^AUTO_MIGRATE_ON_STARTUP=false$' "$ENV_FILE"; then
  echo "AUTO_MIGRATE_ON_STARTUP must be false in production; run migrations in the deploy step" >&2
  exit 1
fi

if ! grep -Eq '^EXPOSE_API_DOCS=false$' "$ENV_FILE"; then
  echo "EXPOSE_API_DOCS must be false in production" >&2
  exit 1
fi

if grep -Eq '^EMBEDDING_PROVIDER=hash$' "$ENV_FILE" && ! grep -Eq '^HASH_EMBEDDING_KEY=.+$' "$ENV_FILE"; then
  echo "HASH_EMBEDDING_KEY is required when EMBEDDING_PROVIDER=hash" >&2
  exit 1
fi

echo "Production env check passed: $ENV_FILE"
