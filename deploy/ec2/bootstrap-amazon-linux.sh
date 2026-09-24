#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$HOME/Alibi}"

sudo dnf update -y
sudo dnf install -y git docker nginx

sudo systemctl enable --now docker
sudo systemctl enable --now nginx

sudo usermod -aG docker "$USER" || true

if ! docker compose version >/dev/null 2>&1; then
  sudo mkdir -p /usr/local/lib/docker/cli-plugins
  sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone https://github.com/ohhamin/Alibi.git "$APP_DIR"
fi

cd "$APP_DIR"
git checkout master
git pull --ff-only origin master

if [[ ! -f backend/.env.production ]]; then
  cp backend/.env.production.example backend/.env.production
  chmod 600 backend/.env.production
  echo
  echo "Created backend/.env.production."
  echo "Edit DATABASE_URL and OPENAI_API_KEY before starting the backend:"
  echo "  nano $APP_DIR/backend/.env.production"
  echo
fi

sudo cp deploy/nginx/alibi.conf /etc/nginx/conf.d/alibi.conf
sudo nginx -t
sudo systemctl reload nginx

echo
echo "Bootstrap complete."
echo "After editing backend/.env.production, run:"
echo "  cd $APP_DIR"
echo "  docker compose -f docker-compose.prod.yml up -d --build"
echo "  curl http://127.0.0.1:8000/health"
echo "  curl http://localhost/health"
