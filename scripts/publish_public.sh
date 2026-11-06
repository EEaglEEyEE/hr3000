#!/usr/bin/env bash
# Zieht das öffentliche Repo github.com/EEaglEEyEE/hr3000 (AGPL-3.0) auf den Stand von main nach.
#
# Arbeitsrepo bleibt das private EEaglEEyEE/HR3000-intern. Veröffentlicht wird nur, was in PUBLIC_PATHS
# steht (Positivliste – neue interne Dateien landen nie versehentlich öffentlich): kein CLAUDE.md,
# keine Betriebsdoku (docs/betrieb.md), keine alten Konzepte. Jede Änderung wird ein Commit im
# öffentlichen Repo.
#
# Läuft automatisch per GitHub Action (.github/workflows/publish-public.yml) bei jedem Push auf
# main; von Hand:  bash scripts/publish_public.sh [Pfad zum privaten Checkout]
# In der Action kommt der Schreibschlüssel (Deploy-Key des öffentlichen Repos) aus der
# Umgebungsvariable DEPLOY_KEY (GitHub-Secret PUBLIC_REPO_DEPLOY_KEY); lokal gilt der normale
# Git-Zugang.
set -euo pipefail

SRC=$(cd "${1:-$(dirname "$0")/..}" && pwd)
PUBLIC_PATHS=(
  backend hr-webapp kiosk-app website scripts
  docs/README.md docs/handbuch-admin.md docs/handbuch-mitarbeiter.md docs/aenderungen.md docs/technik.md
  Caddyfile docker-compose.yml docker-compose.staging.yml .env.example .gitignore LICENSE README.md
)
# Sicherheitsnetz: diese Begriffe dürfen im öffentlichen Stand nicht vorkommen (interne Konten/Infra).
# Aus Teilstücken zusammengesetzt, damit dieses Skript (selbst öffentlich) nicht auf sich anschlägt.
FORBIDDEN='u3132''59|Ca''to |OneDrive-''Schwabenhaus|/Users/''johannes|BEGIN [A-Z ]*PRIV''ATE KEY'

if [ "${GITHUB_ACTIONS:-}" = "true" ] && [ -z "${DEPLOY_KEY:-}" ]; then
  # Grün bleiben (kein Fehler bei jedem Push), aber sichtbar: Warnung am Lauf und in der Zusammenfassung.
  # Sonst bleibt unbemerkt, dass der öffentliche Spiegel (AGPL) hinter dem laufenden Stand zurückbleibt.
  msg="Kein Secret PUBLIC_REPO_DEPLOY_KEY hinterlegt – öffentliches Repo NICHT nachgezogen (siehe docs/betrieb.md, Abschnitt 10)."
  echo "::warning title=Öffentliches Repo nicht aktualisiert::$msg"
  [ -n "${GITHUB_STEP_SUMMARY:-}" ] && echo "⚠️ $msg" >> "$GITHUB_STEP_SUMMARY"
  exit 0
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

if [ -n "${DEPLOY_KEY:-}" ]; then
  (umask 077 && printf '%s\n' "$DEPLOY_KEY" > "$work/key")
  export GIT_SSH_COMMAND="ssh -i $work/key -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
  PUBLIC_URL=git@github.com:EEaglEEyEE/hr3000.git
else
  PUBLIC_URL=https://github.com/EEaglEEyEE/hr3000.git
fi

git clone -q --depth 1 "$PUBLIC_URL" "$work/public"
# Alles außer .git entfernen und den Stand neu aus der Positivliste aufbauen (gelöschte Dateien
# verschwinden so auch öffentlich).
find "$work/public" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
git -C "$SRC" archive --format=tar HEAD -- "${PUBLIC_PATHS[@]}" | tar -x -C "$work/public"

if grep -rIlE "$FORBIDDEN" "$work/public" --exclude-dir=.git >/dev/null; then
  echo "ABBRUCH: interne Angaben im öffentlichen Stand gefunden:" >&2
  grep -rIlE "$FORBIDDEN" "$work/public" --exclude-dir=.git >&2
  exit 1
fi

cd "$work/public"
git add -A
if git diff --cached --quiet; then
  echo "Öffentliches Repo ist bereits aktuell."
  exit 0
fi
rev=$(git -C "$SRC" rev-parse --short HEAD)
git -c user.name="Johannes Lassner" -c user.email="johannes@lassners.de" \
  commit -q -m "Stand $(date -u +%Y-%m-%d) ($rev)"
git push -q origin HEAD:main
echo "Öffentliches Repo aktualisiert: Stand $rev"
