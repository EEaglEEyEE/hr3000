#!/usr/bin/env bash
# Einrichtung der Kopie nach außen (Hetzner Storage Box, restic) – auf dem Server als root ausführen.
#
#   bash scripts/setup_offsite_backup.sh prepare <storagebox-benutzer> <storagebox-host>
#       installiert restic (Ubuntu-Paket), legt einen eigenen SSH-Schlüssel und ein zufälliges
#       restic-Passwort an und gibt den öffentlichen Schlüssel aus. Diesen in der Storage Box
#       hinterlegen (Hetzner Console → Storage Box → SSH-Support an, Schlüssel eintragen).
#   bash scripts/setup_offsite_backup.sh activate
#       legt das Repository an (falls neu), sichert einmal, testet die Wiederherstellung und
#       richtet den nächtlichen Cron (03:45) ein.
#
# Idempotent: bereits vorhandene Schlüssel, Passwörter und Einträge werden nicht überschrieben.
# Das restic-Passwort liegt nur in /root/.config/hr3000-offsite/restic-password (chmod 600) –
# zusätzlich im Passwort-Manager ablegen, sonst sind die Sicherungen im Ernstfall nicht lesbar.
set -euo pipefail

CONF_DIR=/root/.config/hr3000-offsite
KEY=/root/.ssh/hr3000_storagebox
SSH_ALIAS=hr3000-storagebox
REPO_DIR=hr3000-restic

prepare() {
  local user="$1" host="$2"
  command -v restic >/dev/null || { apt-get update -qq && apt-get install -y -qq restic; }
  install -d -m 700 "$CONF_DIR" /root/.ssh
  if [ ! -f "$CONF_DIR/restic-password" ]; then
    (umask 077 && openssl rand -base64 32 > "$CONF_DIR/restic-password")
  fi
  [ -f "$KEY" ] || ssh-keygen -q -t ed25519 -N "" -C "hr3000-offsite-backup" -f "$KEY"
  if ! ssh-keygen -F "[$host]:23" >/dev/null 2>&1; then
    ssh-keyscan -p 23 -T 10 "$host" >> /root/.ssh/known_hosts 2>/dev/null
  fi
  if ! grep -q "^Host $SSH_ALIAS\$" /root/.ssh/config 2>/dev/null; then
    printf '\nHost %s\n    HostName %s\n    Port 23\n    User %s\n    IdentityFile %s\n    IdentitiesOnly yes\n    ServerAliveInterval 60\n' \
      "$SSH_ALIAS" "$host" "$user" "$KEY" >> /root/.ssh/config
    chmod 600 /root/.ssh/config
  fi
  (umask 077 && printf 'RESTIC_REPOSITORY=sftp:%s:%s\nRESTIC_PASSWORD_FILE=%s/restic-password\n' \
    "$SSH_ALIAS" "$REPO_DIR" "$CONF_DIR" > "$CONF_DIR/env")
  echo "restic: $(restic version | head -1)"
  echo "Öffentlicher Schlüssel für die Storage Box:"
  cat "$KEY.pub"
}

activate() {
  # shellcheck source=/dev/null
  . "$CONF_DIR/env"
  export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE
  restic cat config >/dev/null 2>&1 || restic init
  bash "$(dirname "$0")/offsite_backup.sh"
  # Wiederherstellungstest: letzten DB-Dump zurückholen und auf Vollständigkeit prüfen
  local tmp
  tmp=$(mktemp -d)
  restic restore latest --host hr3000 --target "$tmp" --include '/opt/hr3000-backups/hr3000-2*' >/dev/null
  local dump
  dump=$(find "$tmp" -name 'hr3000-2*.sql.gz' | sort | tail -1)
  if [ -z "$dump" ] || ! zcat "$dump" | tail -1 | grep -q "Dump completed"; then
    rm -rf "$tmp"
    echo "Wiederherstellungstest FEHLGESCHLAGEN – Cron wird nicht eingerichtet."
    exit 1
  fi
  echo "Wiederherstellungstest OK: $(basename "$dump")"
  rm -rf "$tmp"
  local repo
  repo=$(cd "$(dirname "$0")/.." && pwd)
  # Über bash aufrufen statt direkt: OneDrive/core.fileMode=false lässt das Ausführrecht
  # gelegentlich verloren gehen – der Cron soll davon nicht abhängen.
  printf 'SHELL=/bin/bash\nPATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\n45 3 * * * root /bin/bash %s/scripts/offsite_backup.sh >> /var/log/hr3000-offsite.log 2>&1\n' \
    "$repo" > /etc/cron.d/hr3000-offsite
  chmod 644 /etc/cron.d/hr3000-offsite
  echo "Nächtliche Kopie eingerichtet: /etc/cron.d/hr3000-offsite (03:45)"
  restic snapshots --host hr3000 --compact | tail -3
}

case "${1:-}" in
  prepare) prepare "${2:?Storage-Box-Benutzer fehlt}" "${3:?Storage-Box-Host fehlt}" ;;
  activate) activate ;;
  *) echo "Aufruf: $0 prepare <benutzer> <host> | activate"; exit 2 ;;
esac
