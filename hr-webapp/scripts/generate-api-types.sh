#!/usr/bin/env bash
# Regeneriert src/api/schema.d.ts aus der aktuellen OpenAPI-Spec des Backends.
# Aufruf: npm run generate:api
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBAPP_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$WEBAPP_DIR/../backend"

# HR3000_VENV: venv außerhalb des OneDrive-Baums (OneDrive zerstört dort Symlinks)
source "${HR3000_VENV:-$BACKEND_DIR/.venv}/bin/activate"
python "$BACKEND_DIR/scripts/export_openapi.py" "$WEBAPP_DIR/openapi.json"

cd "$WEBAPP_DIR"
npx openapi-typescript openapi.json -o src/api/schema.d.ts
rm openapi.json

echo "src/api/schema.d.ts aktualisiert."
