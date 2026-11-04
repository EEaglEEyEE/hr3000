#!/usr/bin/env bash
# Auf dem Server im Repo-Verzeichnis (/opt/hr3000) ausführen.
# Erster Lauf: erzeugt .env mit zufälligen Secrets (nur auf dem Server, nie im Repo).
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s|^MYSQL_ROOT_PASSWORD=.*|MYSQL_ROOT_PASSWORD=$(openssl rand -hex 24)|" .env
  sed -i "s|^MYSQL_PASSWORD=.*|MYSQL_PASSWORD=$(openssl rand -hex 24)|" .env
  sed -i "s|^JWT_SECRET_KEY=.*|JWT_SECRET_KEY=$(openssl rand -hex 48)|" .env
  sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$(openssl rand -base64 32 | tr '+/' '-_')|" .env
  chmod 600 .env
  echo ".env neu erzeugt (Secrets zufällig). Hosts/SMTP ggf. in .env prüfen, dann erneut ausführen, um zu starten."
  exit 0
fi

# Bestehende Installation ohne ENCRYPTION_KEY: den bisher implizit aus dem JWT-Secret
# abgeleiteten Schlüssel explizit festschreiben (identischer Wert -> nichts wird unlesbar,
# und eine spätere Rotation des JWT-Secrets betrifft die Verschlüsselung nicht mehr).
if ! grep -q '^ENCRYPTION_KEY=' .env; then
  # Wie python-dotenv: umschließende Anführungszeichen gehören nicht zum Wert.
  JWT=$(grep '^JWT_SECRET_KEY=' .env | cut -d= -f2- | sed -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/")
  KEY=$(printf 'hr3000-secret-box:%s' "$JWT" | openssl dgst -sha256 -binary | base64 | tr '+/' '-_')
  printf '\nENCRYPTION_KEY=%s\n' "$KEY" >> .env
  echo "ENCRYPTION_KEY in .env ergänzt (aus bisherigem JWT-Secret abgeleitet) – bitte off-server sichern."
fi

# Tägliches Backup (03:15) einrichten, falls noch nicht vorhanden. Ablage: /opt/hr3000-backups,
# 14 Tage Aufbewahrung (siehe backup_db.sh). Für echte Ausfallsicherheit zusätzlich off-server kopieren.
CRON_FILE=/etc/cron.d/hr3000-backup
if [ ! -f "$CRON_FILE" ] && [ -d /etc/cron.d ]; then
  REPO_DIR=$(pwd)
  printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n15 3 * * * root %s/scripts/backup_db.sh >> /var/log/hr3000-backup.log 2>&1\n' "$REPO_DIR" > "$CRON_FILE"
  chmod 644 "$CRON_FILE"
  chmod +x scripts/backup_db.sh
  echo "Täglicher Backup-Cron eingerichtet: $CRON_FILE"
fi

# Vor jedem Update mit Migrationen die DB sichern (außer beim allerersten Start).
if docker compose ps --status running mysql 2>/dev/null | grep -q mysql; then
  bash scripts/backup_db.sh
fi

# Ohne Git-Remote (erstes Deployment per Bundle) gibt es nichts zu ziehen.
if git remote | grep -q .; then git pull --ff-only; fi
docker compose build
docker compose up -d
# Caddyfile ist als einzelne Datei eingebunden: git ersetzt die Datei (neuer Inode), der Container
# sieht dann weiter die alte Fassung. Bei Abweichung den Caddy-Container neu erzeugen.
if ! docker compose exec -T caddy cat /etc/caddy/Caddyfile | cmp -s - Caddyfile; then
  echo "Caddyfile geändert – Caddy wird neu erzeugt."
  docker compose up -d --force-recreate --no-deps caddy
fi

echo "Warte auf Backend ..."
for i in $(seq 1 30); do
  if docker compose exec -T backend python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')" 2>/dev/null; then
    echo "Backend gesund."; break
  fi
  sleep 3
done
# Passwort über eine kurzlebige Optionsdatei statt per -p (sonst in der Prozessliste sichtbar).
docker compose exec -T mysql sh -c 'umask 077; cnf=$(mktemp); trap "rm -f \$cnf" EXIT
printf "[client]\nuser=root\npassword=\"%s\"\n" "$MYSQL_ROOT_PASSWORD" > "$cnf"
mysql --defaults-extra-file="$cnf" -N -e "SELECT version_num FROM $MYSQL_DATABASE.alembic_version"'
echo "Super-Admin-Einmalpasswort (nur beim allerersten Start): docker compose logs backend | grep -A3 'Super-Admin angelegt'"
