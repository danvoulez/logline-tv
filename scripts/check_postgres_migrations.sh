#!/usr/bin/env bash
set -euo pipefail
docker compose up -d db
docker compose run --rm migrate
docker compose ps
docker compose logs migrate --tail 80
docker compose exec -T db psql -U postgres -d voulezvous -c '\dt'
