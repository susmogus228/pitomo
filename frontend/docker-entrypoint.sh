#!/bin/sh
set -eu

public_host=${PETSHOP_PUBLIC_HOST:-}
public_origin=${PETSHOP_PUBLIC_ORIGIN:-}
secure_cookies=${PETSHOP_SECURE_COOKIES:-false}

if [ -n "$public_host" ]; then
    if [ "${#public_host}" -gt 253 ] || ! printf '%s' "$public_host" | grep -Eq '^([a-z0-9]([a-z0-9-]*[a-z0-9])?\.)+[a-z0-9]([a-z0-9-]*[a-z0-9])?$'; then
        echo 'PETSHOP_PUBLIC_HOST must be one exact lowercase DNS hostname without scheme, port, path or wildcard.' >&2
        exit 1
    fi
    if [ "$public_origin" != "https://$public_host" ]; then
        echo 'PETSHOP_PUBLIC_ORIGIN must exactly match https://PETSHOP_PUBLIC_HOST.' >&2
        exit 1
    fi
    if [ "$secure_cookies" != true ]; then
        echo 'PETSHOP_SECURE_COOKIES must be true when PETSHOP_PUBLIC_HOST is configured.' >&2
        exit 1
    fi
elif [ -n "$public_origin" ]; then
    echo 'PETSHOP_PUBLIC_HOST is required when PETSHOP_PUBLIC_ORIGIN is configured.' >&2
    exit 1
fi

umask 077
{
    printf 'default 0;\nlocalhost 1;\n127.0.0.1 1;\n'
    if [ -n "$public_host" ]; then
        printf '%s 1;\n' "$public_host"
    fi
} > /tmp/pitomo-host-allowlist.conf

exec "$@"
