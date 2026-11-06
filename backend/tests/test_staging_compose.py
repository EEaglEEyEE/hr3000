"""Die Testumgebung hängt im Docker-Netz der Produktion. Ihre Dienste dürfen dort nicht wie die der
Produktion heißen – sonst verteilt Prod-Caddy Anfragen auf beide (06.11.2026)."""
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_staging_services_do_not_share_names_with_production() -> None:
    staging_file = ROOT / "docker-compose.staging.yml"
    if not staging_file.exists():
        pytest.skip("nur im Repo – im Docker-Build fehlt die Compose-Datei")
    production = set(yaml.safe_load((ROOT / "docker-compose.yml").read_text())["services"])
    staging = yaml.safe_load(staging_file.read_text())["services"]
    assert not production & set(staging), production & set(staging)
    # eigene Datenbank über ihren eigenen Namen (sonst wäre "mysql" im Prod-Netz die Prod-DB)
    assert "@staging-mysql:" in staging["staging-backend"]["environment"]["DATABASE_URL"]
    # unter diesen Namen erreichen Prod-Caddy und das Prod-Backend die Testumgebung
    caddyfile = (ROOT / "Caddyfile").read_text()
    for target in ("staging-backend:8000", "staging-hr-webapp:80", "staging-kiosk-app:80"):
        assert target in caddyfile
    assert set(staging) >= {"staging-backend", "staging-hr-webapp", "staging-kiosk-app", "staging-mysql"}
