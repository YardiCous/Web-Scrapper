#!/usr/bin/env bash
# Creates the Postgres credentials Secret in every namespace that needs it. The password is generated
# once into .secrets/postgres.env (gitignored) and reused, because Postgres only reads it on first start.
. "$(dirname "$0")/lib.sh"
need kubectl openssl

env_file="$INFRA_DIR/.secrets/postgres.env"
if [ ! -f "$env_file" ]; then
  mkdir -p "$(dirname "$env_file")"
  umask 077
  printf 'PGUSER=cdc\nPGPASSWORD=%s\n' "$(openssl rand -hex 24)" > "$env_file"
  log "Generated $env_file"
fi
# One connection string as well, for services that take DATABASE_URL (the scorer does).
# Added to older files too; the hex password needs no URL escaping.
if ! grep -q '^DATABASE_URL=' "$env_file"; then
  ( . "$env_file"; printf 'DATABASE_URL=postgresql://%s:%s@postgres.data.svc:5432/cdc\n' "$PGUSER" "$PGPASSWORD" ) >> "$env_file"
fi

for ns in data pipeline scoring web; do
  kubectl -n "$ns" create secret generic postgres-credentials --from-env-file="$env_file" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
done
echo "postgres-credentials present in: data pipeline scoring web"
