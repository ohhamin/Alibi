#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/Alibi}"

cd "$APP_DIR"
git fetch origin master
git checkout master
git pull --ff-only origin master

if [[ ! -f backend/.env.production ]]; then
  echo "Missing backend/.env.production"
  echo "Copy backend/.env.production.example and fill DATABASE_URL / OPENAI_API_KEY."
  exit 1
fi

docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

echo "Waiting for backend health..."
for i in {1..20}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then
    echo "Backend is healthy."
    curl -fsS http://127.0.0.1:8000/health
    echo
    exit 0
  fi
  sleep 2
done

echo "Backend health check failed."
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs --tail=100 backend
exit 1
