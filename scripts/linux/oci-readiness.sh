#!/bin/sh
# Read-only preflight for a separate OCI test instance. Run with: sh scripts/linux/oci-readiness.sh
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"

fail() {
    printf 'NOT READY: %s\n' "$1" >&2
    exit 1
}

read_env() {
    awk -v key="$1" '
        index($0, key "=") == 1 {
            value = substr($0, length(key) + 2)
            sub(/\r$/, "", value)
        }
        END { print value }
    ' .env
}

[ -f .env ] || fail '.env is missing; create a separate test configuration.'
[ "$(uname -m)" = aarch64 ] || fail 'This OCI A1 preflight expects an ARM64 (aarch64) VM.'
command -v docker >/dev/null 2>&1 || fail 'Docker Engine is not installed.'
command -v tailscale >/dev/null 2>&1 || fail 'Tailscale is not installed.'
docker info >/dev/null 2>&1 || fail 'Docker Engine is unavailable.'
docker compose version >/dev/null 2>&1 || fail 'Docker Compose plugin is unavailable.'
tailscale status >/dev/null 2>&1 || fail 'Tailscale VM is not connected to a tailnet.'

for key in POSTGRES_PASSWORD PETSHOP_DATABASE_URL PETSHOP_JWT_SECRET; do
    [ -n "$(read_env "$key")" ] || fail "$key is empty in .env."
done

host=$(read_env PETSHOP_PUBLIC_HOST)
origin=$(read_env PETSHOP_PUBLIC_ORIGIN)
[ -n "$host" ] || fail 'PETSHOP_PUBLIC_HOST is empty.'
[ "${#host}" -le 253 ] || fail 'PETSHOP_PUBLIC_HOST is too long.'
printf '%s' "$host" | grep -Eq '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]*[a-z0-9])?$' \
    || fail 'PETSHOP_PUBLIC_HOST must be one exact lowercase DNS name.'
[ "$origin" = "https://$host" ] || fail 'PETSHOP_PUBLIC_ORIGIN must be https://PETSHOP_PUBLIC_HOST.'
[ "$(read_env PETSHOP_SECURE_COOKIES)" = true ] || fail 'PETSHOP_SECURE_COOKIES must be true.'
[ "$(read_env PETSHOP_ENV)" = development ] || fail 'Test payments require PETSHOP_ENV=development.'
[ "$(read_env PETSHOP_DOCS_ENABLED)" = false ] || fail 'Disable public API docs with PETSHOP_DOCS_ENABLED=false.'

docker compose --project-name pitomo --env-file .env \
    -f docker-compose.yml -f docker-compose.frontend.yml config --quiet \
    || fail 'Docker Compose configuration is invalid.'

printf 'READY: OCI ARM64 dependencies and exact-host test configuration passed.\n'
printf 'NEXT: build/start the separate stack, then verify the real HTTPS URL from another device.\n'
