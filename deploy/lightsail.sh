#!/usr/bin/env bash
# FORMA on a fresh AWS Lightsail Ubuntu instance (22.04 or 24.04).
#
#   sudo bash lightsail.sh install [git-ref] [domain] [email]
#       First time on a new instance: packages, code, Python, the app as a
#       service behind nginx. git-ref is a tag, branch or commit (default:
#       the "live" tag if there is one, else main). With a domain and an
#       email it also turns on HTTPS.
#   sudo bash lightsail.sh update [git-ref]
#       Switch the running site to another version. Backs up first; keeps
#       saved projects, uploads and learned furniture sizes.
#   sudo bash lightsail.sh backup
#       Saved projects, uploads and furniture sizes in one file to download.
#   sudo bash lightsail.sh status | logs
#
# Nothing here reads or prints your API keys. They go in /opt/forma/.env,
# which you edit yourself (the script tells you when).

set -euo pipefail

# Public repository: fetched over HTTPS, no key needed. For a private one, run
# with REPO_URL=git@github.com:<owner>/<repo>.git and the script sets up a
# read-only deploy key.
REPO_URL="${REPO_URL:-https://github.com/shaogjintan/design-inspiration-agent.git}"
APP_DIR=/opt/forma
APP_USER=forma
SERVICE=forma
BACKUP_DIR=/home/ubuntu/forma-backups
# One worker, several threads: the app keeps a run's progress, and the plan
# trace in flight, in memory — a second worker process would not see them.
GUNICORN="gunicorn --workers 1 --threads 8 --timeout 300 --bind 127.0.0.1:8000 app:app"

say()  { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
die()  { printf '\n\033[31mError: %s\033[0m\n' "$*" >&2; exit 1; }
as_app() { sudo -u "$APP_USER" -H "$@"; }

[ "$(id -u)" -eq 0 ] || die "run with sudo: sudo bash $0 $*"

# ── Pieces ────────────────────────────────────────────────────────────────────
install_packages() {
  say "Installing system packages"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -q
  apt-get install -yq git python3 python3-venv python3-pip nginx
}

make_user() {
  id "$APP_USER" >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash "$APP_USER"
  mkdir -p "$APP_DIR" "$BACKUP_DIR"
  chown "$APP_USER:$APP_USER" "$APP_DIR"
}

# GitHub over SSH needs a key the repository trusts. The server makes its own
# and you add it to the repository once, as a read-only deploy key.
deploy_key() {
  case "$REPO_URL" in
    https://*) return ;;               # public over HTTPS: nothing to set up
  esac
  local key="/home/$APP_USER/.ssh/id_ed25519"
  if [ ! -f "$key" ]; then
    as_app mkdir -p "/home/$APP_USER/.ssh"
    as_app ssh-keygen -q -t ed25519 -N "" -C "forma-lightsail" -f "$key"
  fi
  as_app bash -c "ssh-keyscan -H github.com >> ~/.ssh/known_hosts 2>/dev/null"
  if ! as_app git ls-remote "$REPO_URL" >/dev/null 2>&1; then
    say "Add this server's key to GitHub (one time)"
    echo "GitHub → the repository → Settings → Deploy keys → Add deploy key."
    echo "Title: forma-lightsail. Leave 'Allow write access' OFF. Paste:"
    echo
    cat "$key.pub"
    echo
    read -r -p "Press Enter once it is added… " _
    as_app git ls-remote "$REPO_URL" >/dev/null 2>&1 \
      || die "GitHub still refuses this server. Check the key was added to $REPO_URL."
  fi
}

default_ref() {
  if as_app git -C "$APP_DIR" rev-parse -q --verify "refs/tags/live" >/dev/null; then echo live; else echo main; fi
}

fetch_code() {
  local ref="$1"
  if [ ! -d "$APP_DIR/.git" ]; then
    say "Downloading the code"
    as_app git clone "$REPO_URL" "$APP_DIR"
  fi
  as_app git -C "$APP_DIR" fetch --all --tags --prune --force
  [ -n "$ref" ] || ref="$(default_ref)"
  say "Switching to $ref"
  # The app writes learned furniture sizes into a file git also tracks: set
  # it aside so the checkout goes through, then put it back.
  local sizes="$APP_DIR/furniture_sizes.json" keep=""
  if [ -f "$sizes" ]; then keep="$(mktemp)"; cp "$sizes" "$keep"; fi
  as_app git -C "$APP_DIR" checkout --force "$ref"
  # A branch name follows its latest commit; a tag or commit stays put.
  if as_app git -C "$APP_DIR" show-ref -q --verify "refs/remotes/origin/$ref"; then
    as_app git -C "$APP_DIR" reset --hard "origin/$ref"
  fi
  if [ -n "$keep" ]; then cp "$keep" "$sizes"; chown "$APP_USER:$APP_USER" "$sizes"; rm -f "$keep"; fi
  echo "Now at: $(as_app git -C "$APP_DIR" log -1 --format='%h %s (%ad)' --date=short)"
}

python_env() {
  say "Installing Python packages"
  [ -d "$APP_DIR/venv" ] || as_app python3 -m venv "$APP_DIR/venv"
  as_app "$APP_DIR/venv/bin/pip" install -q --upgrade pip
  as_app "$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn
}

# The app reads .env from its own folder. Made once with a real secret key and
# blanks for the model keys; never overwritten, never printed.
env_file() {
  local env="$APP_DIR/.env"
  if [ ! -f "$env" ]; then
    say "Creating $env"
    local secret
    secret="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
    cat > "$env" <<EOF
# FORMA settings for this server. Fill in the model keys, then:
#   sudo systemctl restart $SERVICE
FLASK_SECRET_KEY=$secret

SOCLAAS_BASE_URL=
SOCLAAS_API_KEY=
SOCLAAS_MODEL=

# The older gateway, if you use it instead
LLM_GATEWAY_URL=
LLM_GATEWAY_API_KEY=
LLM_MODEL=
EOF
    chown "$APP_USER:$APP_USER" "$env"
    chmod 600 "$env"
    NEEDS_KEYS=1
  fi
}

service_unit() {
  say "Setting up the $SERVICE service"
  cat > "/etc/systemd/system/$SERVICE.service" <<EOF
[Unit]
Description=FORMA design brief app
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/$GUNICORN
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$SERVICE"
  systemctl restart "$SERVICE"
}

nginx_site() {
  local domain="${1:-_}"
  say "Setting up nginx"
  cat > /etc/nginx/sites-available/forma <<EOF
server {
    listen 80;
    server_name $domain;

    # Floor plans and inspiration photos can be large.
    client_max_body_size 50M;

    # Reading a plan and writing the brief take minutes, not seconds.
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;

    location /static/ {
        alias $APP_DIR/static/;
        expires 7d;
    }

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
  ln -sf /etc/nginx/sites-available/forma /etc/nginx/sites-enabled/forma
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl reload nginx
}

https() {
  local domain="$1" email="$2"
  say "Turning on HTTPS for $domain"
  apt-get install -yq certbot python3-certbot-nginx
  certbot --nginx --non-interactive --agree-tos -m "$email" -d "$domain" --redirect
}

backup() {
  mkdir -p "$BACKUP_DIR"
  local file="$BACKUP_DIR/forma-$(date +%Y%m%d-%H%M%S).tgz" items=()
  for f in data.json uploads furniture_sizes.json; do
    [ -e "$APP_DIR/$f" ] && items+=("$f")
  done
  if [ ${#items[@]} -eq 0 ]; then echo "Nothing saved yet to back up."; return; fi
  tar -czf "$file" -C "$APP_DIR" "${items[@]}"
  chown ubuntu:ubuntu "$file" 2>/dev/null || true
  echo "Backup: $file"
}

check() {
  sleep 2
  if curl -fsS -o /dev/null http://127.0.0.1:8000/; then
    echo "The app is answering."
  else
    echo "The app is not answering yet. See: sudo bash $0 logs"
  fi
}

where() {
  local ip
  ip="$(curl -fsS --max-time 3 https://checkip.amazonaws.com 2>/dev/null || hostname -I | awk '{print $1}')"
  echo "Open: http://$ip/"
}

# ── Commands ──────────────────────────────────────────────────────────────────
cmd="${1:-}"; shift || true
NEEDS_KEYS=0
case "$cmd" in
  install)
    ref="${1:-}"; domain="${2:-}"; email="${3:-}"
    install_packages
    make_user
    deploy_key
    fetch_code "$ref"
    python_env
    env_file
    service_unit
    nginx_site "${domain:-_}"
    [ -n "$domain" ] && [ -n "$email" ] && https "$domain" "$email"
    check
    say "Done"
    where
    if [ "$NEEDS_KEYS" = 1 ]; then
      echo
      echo "Next: add the model keys, or FORMA runs in demo mode:"
      echo "  sudo nano $APP_DIR/.env"
      echo "  sudo systemctl restart $SERVICE"
    fi
    ;;
  update)
    [ -d "$APP_DIR/.git" ] || die "not installed yet — run: sudo bash $0 install"
    say "Backing up first"
    backup
    fetch_code "${1:-}"
    python_env
    systemctl restart "$SERVICE"
    check
    ;;
  backup)
    backup
    ;;
  status)
    systemctl --no-pager status "$SERVICE" nginx | head -n 20
    echo; echo "Version: $(as_app git -C "$APP_DIR" log -1 --format='%h %s (%ad)' --date=short)"
    ;;
  logs)
    journalctl -u "$SERVICE" -n 100 --no-pager
    ;;
  *)
    sed -n '2,19p' "$0"
    exit 1
    ;;
esac
