#!/usr/bin/env bash
# Update ausrollen – auf dem Server als root ausführen:  cd /opt/hr3000 && bash scripts/rollout.sh
# (Ersteinrichtung eines neuen Servers: scripts/bootstrap_server.sh + scripts/deploy.sh.)
#
# 1. Code holen (git pull; ohne GitHub-Zugang aus /tmp/hr3000.bundle)   4. Caddyfile prüfen
# 2. Datenbank sichern (scripts/backup_db.sh)                           5. Migrationen auf Kopie (migtest)
# 3. Images bauen – Backend- und Frontend-Tests laufen im Build          6. Neustart + Healthcheck
# Jeder Fehler in 1–5 bricht ab, bevor etwas neu gestartet wird: die alte Version läuft weiter.
# Siehe docs/betrieb.md, Abschnitt 5.
set -uo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n=== %s\n' "$*"; }
fail() { printf '\nABBRUCH: %s\n' "$*" >&2; exit 1; }

# Shell-Befehle im MySQL-Container mit Root-Zugang über eine kurzlebige Optionsdatei ($cnf) statt
# per -p (sonst wäre das Passwort in der Prozessliste sichtbar). Argument in einfachen Anführungs-
# zeichen übergeben – $cnf und $MYSQL_DATABASE werden erst im Container aufgelöst.
mysql_root() {
  docker compose exec -T mysql sh -c 'umask 077; cnf=$(mktemp); trap "rm -f $cnf" EXIT
printf "[client]\nuser=root\npassword=\"%s\"\n" "$MYSQL_ROOT_PASSWORD" > "$cnf"
'"$1"
}

step "1/6 Code holen"
if git pull -q --ff-only 2>/dev/null; then
  echo "per GitHub"
elif [ -f /tmp/hr3000.bundle ]; then
  git fetch -q /tmp/hr3000.bundle main && git merge -q --ff-only FETCH_HEAD || fail "Bundle passt nicht zum Stand auf dem Server."
  echo "aus /tmp/hr3000.bundle"
else
  fail "git pull fehlgeschlagen und kein Bundle unter /tmp/hr3000.bundle (siehe docs/betrieb.md)."
fi
rm -f /tmp/hr3000.bundle
git log --oneline -1
# Öffentliche Doku (hr3000.de/doku) muss zu docs/*.md passen – sonst nur Warnung, kein Abbruch.
python3 scripts/build_website_docs.py --check || echo "WARNUNG: Website-Doku veraltet (lokal scripts/build_website_docs.py ausführen und committen)."

step "2/6 Datenbank sichern"
bash scripts/backup_db.sh || fail "Sicherung fehlgeschlagen."

step "3/6 Bauen und testen (dauert einige Minuten)"
if ! docker compose build >/tmp/hr3000-build.log 2>&1; then
  grep -aE "FAILED|failed|Error|error TS" /tmp/hr3000-build.log | tail -20
  fail "Build oder Tests rot – vollständiges Log: /tmp/hr3000-build.log. Die alte Version läuft weiter."
fi
grep -aE "[0-9]+ passed|Tests .*passed" /tmp/hr3000-build.log | sed -E 's/\x1b\[[0-9;]*m//g' | tail -4

step "4/6 Caddyfile prüfen"
CADDY_ID=$(docker compose ps -q caddy 2>/dev/null)
CADDY_IMG=$( [ -n "$CADDY_ID" ] && docker inspect --format '{{.Config.Image}}' "$CADDY_ID" || echo caddy:2-alpine)
docker run --rm --env-file .env -v "$PWD/Caddyfile":/etc/caddy/Caddyfile:ro "$CADDY_IMG" \
  caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/tmp/hr3000-caddy.log 2>&1 \
  || { tail -5 /tmp/hr3000-caddy.log; fail "Caddyfile ungültig."; }
echo "gültig"

step "5/6 Migrationen auf einer Kopie der Produktivdatenbank testen"
mysql_root 'mysql --defaults-extra-file="$cnf" -e "DROP DATABASE IF EXISTS migtest; CREATE DATABASE migtest"
mysqldump --defaults-extra-file="$cnf" --single-transaction --routines "$MYSQL_DATABASE" | mysql --defaults-extra-file="$cnf" migtest
echo "Produktiv: $(mysql --defaults-extra-file="$cnf" -N -e "SELECT version_num FROM $MYSQL_DATABASE.alembic_version")"' \
  || fail "Kopie der Datenbank fehlgeschlagen."
if ! docker compose run --rm --no-deps -T backend sh -c \
  'export DATABASE_URL="mysql+asyncmy://root:${MYSQL_ROOT_PASSWORD}@mysql:3306/migtest"
   alembic upgrade head >/tmp/migtest.log 2>&1 || { tail -30 /tmp/migtest.log; exit 1; }
   echo "Kopie nach Migration: $(alembic current 2>/dev/null | tail -1)"'; then
  mysql_root 'mysql --defaults-extra-file="$cnf" -e "DROP DATABASE IF EXISTS migtest"'
  fail "Migration auf der Kopie fehlgeschlagen – Produktion unverändert."
fi
mysql_root 'mysql --defaults-extra-file="$cnf" -e "DROP DATABASE migtest"'

step "6/6 Neu starten"
docker compose up -d
# Caddyfile ist als einzelne Datei eingebunden: git ersetzt die Datei (neuer Inode), der Container
# sähe weiter die alte Fassung. Bei Abweichung Caddy neu erzeugen.
if ! docker compose exec -T caddy cat /etc/caddy/Caddyfile | cmp -s - Caddyfile; then
  echo "Caddyfile geändert – Caddy wird neu erzeugt."
  docker compose up -d --force-recreate --no-deps caddy
fi
healthy=no
for _ in $(seq 1 40); do
  if docker compose exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
    healthy=yes; break
  fi
  sleep 3
done
[ "$healthy" = yes ] || fail "Backend nicht gesund – docker compose logs backend"
mysql_root 'echo "Migrationsstand: $(mysql --defaults-extra-file="$cnf" -N -e "SELECT version_num FROM $MYSQL_DATABASE.alembic_version")"'
# Täglicher Lösch-Lauf (gekündigte Firmen nach Ablauf der Exportfrist, unbestätigte
# Selbstregistrierungen nach 7 Tagen) – siehe backend/app/tools/purge_tenants.py.
PURGE_CRON=/etc/cron.d/hr3000-purge
if [ -d /etc/cron.d ] && [ ! -f "$PURGE_CRON" ]; then
  printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n30 4 * * * root cd %s && docker compose exec -T backend python -m app.tools.purge_tenants >> /var/log/hr3000-purge.log 2>&1\n' "$PWD" > "$PURGE_CRON"
  chmod 644 "$PURGE_CRON"
  echo "Lösch-Cron eingerichtet: $PURGE_CRON (04:30)"
fi
ADMIN_HOST=$(grep -E '^SUPER_ADMIN_HOSTNAME=' .env | cut -d= -f2-)
[ -n "$ADMIN_HOST" ] && curl -fsS --max-time 30 "https://$ADMIN_HOST/api/health" >/dev/null && echo "https://$ADMIN_HOST erreichbar"
echo
echo "Fertig: $(git log --oneline -1)"
