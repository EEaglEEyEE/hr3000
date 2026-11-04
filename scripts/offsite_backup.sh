#!/usr/bin/env bash
# Kopie der lokalen Backups (DB-Dumps, Personalakten-Dokumente aus /opt/hr3000-backups) verschlüsselt
# auf die Hetzner Storage Box (restic über SFTP, Port 23). Läuft nachts nach backup_db.sh
# (Cron /etc/cron.d/hr3000-offsite, eingerichtet von setup_offsite_backup.sh activate).
#
# Bewusst NICHT mitgesichert: die .env-Kopien (hr3000-env-*) – sie enthalten den ENCRYPTION_KEY der
# Dokumente; Schlüssel und verschlüsselte Daten gehören an getrennte Orte (Passwort-Manager).
set -euo pipefail

CONF=/root/.config/hr3000-offsite/env
if [ ! -f "$CONF" ]; then
  echo "Offsite-Backup nicht eingerichtet ($CONF fehlt) – siehe scripts/setup_offsite_backup.sh"
  exit 0
fi
# shellcheck source=/dev/null
. "$CONF"
export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE

restic backup --host hr3000 --tag nightly --exclude 'hr3000-env-*' /opt/hr3000-backups
# Aufbewahrung: 30 Tage täglich, 8 Wochen wöchentlich, 12 Monate monatlich
restic forget --host hr3000 --keep-daily 30 --keep-weekly 8 --keep-monthly 12 --prune
# Sonntags eine Stichprobe der gespeicherten Daten wirklich lesen und prüfen
if [ "$(date +%u)" = "7" ]; then
  restic check --read-data-subset=5%
fi
echo "Offsite-Backup OK $(date -Is)"
