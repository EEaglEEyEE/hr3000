#!/usr/bin/env bash
# Testumgebung neben der Produktion auf demselben Server (als root ausführen, aus /opt/hr3000):
#
#   bash scripts/staging.sh setup [ref]    einmalig: Checkout, Zugangsdaten, Start, Demo-Firma
#   bash scripts/staging.sh deploy [ref]   Stand ausrollen (Standard: origin/main; auch Branch/Commit)
#   bash scripts/staging.sh reset          Datenbank leeren, Demo-Firma neu anlegen
#   bash scripts/staging.sh status | logs | stop
#
# Eigene Container (Compose-Projekt "hr3000-staging") und eigene Datenbank mit Demo-Daten – nie
# echte Personaldaten. Erreichbar unter https://demo.<STAGING_BASE_DOMAIN> (Standard
# test.hr3000.de) über den Caddy der Produktion, siehe Caddyfile und docs/betrieb.md.
set -euo pipefail

PROD=/opt/hr3000
DIR=/opt/hr3000-staging
DOMAIN=${STAGING_BASE_DOMAIN:-test.hr3000.de}
REF=${2:-origin/main}

say() { printf '\n=== %s\n' "$*"; }
fail() { printf '\nABBRUCH: %s\n' "$*" >&2; exit 1; }
compose() { docker compose -p hr3000-staging -f "$DIR/docker-compose.staging.yml" --project-directory "$DIR" "$@"; }

checkout() {
  if [ ! -d "$DIR/.git" ]; then
    say "Checkout nach $DIR"
    git clone -q "$(git -C "$PROD" remote get-url origin)" "$DIR"
  fi
  git -C "$DIR" fetch -q origin
  git -C "$DIR" checkout -q --detach "$REF" || fail "Stand '$REF' nicht gefunden."
  git -C "$DIR" log --oneline -1
}

prod_network() {
  local caddy
  caddy=$(docker compose -f "$PROD/docker-compose.yml" --project-directory "$PROD" ps -q caddy 2>/dev/null || true)
  [ -n "$caddy" ] || fail "Caddy der Produktion läuft nicht."
  docker inspect --format '{{range $name, $net := .NetworkSettings.Networks}}{{$name}} {{end}}' "$caddy" | awk '{print $1}'
}

write_env() {
  [ -f "$DIR/.env" ] && return 0
  say "Zugangsdaten der Testumgebung erzeugen ($DIR/.env, nur root)"
  local fernet
  fernet=$(openssl rand -base64 32 | tr '+/' '-_')
  (
    umask 077
    cat >"$DIR/.env" <<EOF
# Testumgebung – automatisch erzeugt von scripts/staging.sh (nicht committen)
MYSQL_ROOT_PASSWORD=$(openssl rand -hex 24)
MYSQL_DATABASE=hr3000_staging
MYSQL_USER=hr3000
MYSQL_PASSWORD=$(openssl rand -hex 24)
JWT_SECRET_KEY=$(openssl rand -hex 32)
JWT_ALGORITHM=HS256
ENCRYPTION_KEY=$fernet
DEBUG=false
TENANT_BASE_DOMAIN=$DOMAIN
SUPER_ADMIN_HOSTNAME=admin.$DOMAIN
SELF_SIGNUP_ENABLED=false
PROD_NETWORK=$(prod_network)
EOF
  )
}

link_production() {
  # Die Produktion muss die Testumgebung kennen (Caddy-Weiterleitung, Zertifikatsfreigabe).
  if ! grep -q '^STAGING_BASE_DOMAIN=' "$PROD/.env"; then
    say "Produktion: STAGING_BASE_DOMAIN=$DOMAIN in $PROD/.env eintragen und Backend/Caddy neu starten"
    printf '\n# Testumgebung (scripts/staging.sh)\nSTAGING_BASE_DOMAIN=%s\n' "$DOMAIN" >>"$PROD/.env"
    (cd "$PROD" && docker compose up -d backend caddy)
  fi
}

wait_healthy() {
  say "Warte auf das Backend"
  for _ in $(seq 1 60); do
    if compose exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
      echo "läuft"; return 0
    fi
    sleep 5
  done
  fail "Backend nicht gesund – bash scripts/staging.sh logs"
}

build_and_start() {
  say "Bauen und starten (Tests laufen im Build, dauert einige Minuten)"
  compose up -d --build
  wait_healthy
}

seed() {
  say "Demo-Firma"
  compose exec -T backend python -m app.tools.seed_demo
}

case "${1:-}" in
  setup)
    checkout
    write_env
    link_production
    build_and_start
    seed
    echo "Fertig: https://demo.$DOMAIN (Tablet: https://kiosk.demo.$DOMAIN)"
    ;;
  deploy)
    [ -d "$DIR/.git" ] || fail "Noch nicht eingerichtet: bash scripts/staging.sh setup"
    checkout
    build_and_start
    echo "Ausgerollt: https://demo.$DOMAIN"
    ;;
  reset)
    [ -d "$DIR/.git" ] || fail "Noch nicht eingerichtet: bash scripts/staging.sh setup"
    say "Datenbank der Testumgebung leeren"
    compose down -v
    build_and_start
    seed
    ;;
  status) compose ps ;;
  logs) compose logs --tail 100 backend ;;
  stop) compose down ;;
  *)
    sed -n '2,12p' "$0"
    exit 1
    ;;
esac
