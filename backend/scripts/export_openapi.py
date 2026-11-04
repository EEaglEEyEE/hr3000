"""Exportiert die aktuelle OpenAPI-Spec als JSON, Grundlage für den
generierten TypeScript-Client der hr-webapp (siehe hr-webapp/package.json
"generate:api"). Aufruf: python scripts/export_openapi.py [output_path]
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402

if __name__ == "__main__":
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "openapi.json"
    output_path.write_text(json.dumps(app.openapi(), indent=2))
    print(f"OpenAPI-Spec exportiert nach {output_path}")
