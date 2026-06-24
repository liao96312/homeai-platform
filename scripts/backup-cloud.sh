#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-$PROJECT_DIR/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-7}"
STAMP="$(date +%F-%H%M%S)"

cd "$PROJECT_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

DB_BACKUP="$BACKUP_DIR/postgres-$STAMP.sql.gz"
CHROMA_BACKUP="$BACKUP_DIR/chroma-data-$STAMP.tar.gz"
umask 077

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' | gzip > "$DB_BACKUP"

docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE" exec -T backend \
  tar -czf - -C /app/chroma_data . > "$CHROMA_BACKUP"

if [[ -n "${BACKUP_ENCRYPTION_PASSWORD:-}" ]]; then
  openssl enc -aes-256-cbc -salt -pbkdf2 -in "$DB_BACKUP" -out "$DB_BACKUP.enc" -pass env:BACKUP_ENCRYPTION_PASSWORD
  openssl enc -aes-256-cbc -salt -pbkdf2 -in "$CHROMA_BACKUP" -out "$CHROMA_BACKUP.enc" -pass env:BACKUP_ENCRYPTION_PASSWORD
  rm -f "$DB_BACKUP" "$CHROMA_BACKUP"
  DB_BACKUP="$DB_BACKUP.enc"
  CHROMA_BACKUP="$CHROMA_BACKUP.enc"
fi

find "$BACKUP_DIR" -type f \( -name 'postgres-*.sql.gz' -o -name 'postgres-*.sql.gz.enc' -o -name 'chroma-data-*.tar.gz' -o -name 'chroma-data-*.tar.gz.enc' \) -mtime "+$RETENTION_DAYS" -delete

echo "Created backups:"
echo "  $DB_BACKUP"
echo "  $CHROMA_BACKUP"
