#!/usr/bin/env bash
# Tägliches MySQL-Backup (Cron: 0 3 * * * /opt/hr3000/scripts/backup_db.sh).
# Liegt unter /opt/hr3000-backups, 14 Tage Aufbewahrung. Für echte
# Ausfallsicherheit zusätzlich off-server kopieren (Hetzner Storage Box).
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=/opt/hr3000-backups
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d-%H%M%S)
# Passwort über eine kurzlebige Optionsdatei (nur für root lesbar) statt per -p: auf der Kommandozeile
# wäre es während des Dumps in der Prozessliste sichtbar (MYSQL_PWD gilt bei MySQL als veraltet).
docker compose exec -T mysql sh -c 'umask 077; cnf=$(mktemp); trap "rm -f \$cnf" EXIT
printf "[client]\nuser=root\npassword=\"%s\"\n" "$MYSQL_ROOT_PASSWORD" > "$cnf"
mysqldump --defaults-extra-file="$cnf" --single-transaction --routines "$MYSQL_DATABASE"' | gzip > "$DEST/hr3000-$STAMP.sql.gz"
# Personalakte-Dateien (verschlüsselt). Den ENCRYPTION_KEY aus .env bewusst NICHT hier ablegen –
# Schlüssel und verschlüsselte Daten gehören an getrennte Orte (z.B. Passwort-Manager).
if docker compose ps --status running backend 2>/dev/null | grep -q backend; then
  docker compose exec -T backend tar -C /app/data -czf - documents 2>/dev/null > "$DEST/hr3000-docs-$STAMP.tar.gz" || rm -f "$DEST/hr3000-docs-$STAMP.tar.gz"
fi
chmod 600 "$DEST"/hr3000-*-"$STAMP"* "$DEST/hr3000-$STAMP.sql.gz" 2>/dev/null || true
find "$DEST" \( -name 'hr3000-*.sql.gz' -o -name 'hr3000-docs-*.tar.gz' \) -mtime +14 -delete
echo "Backup: $DEST/hr3000-$STAMP.sql.gz"
