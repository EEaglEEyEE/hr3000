"""/metrics ist nur für das Docker-Netz: Caddy darf den Pfad auf keinem Host weiterleiten
(weder /metrics noch /api/metrics). Geprüft am Text des Caddyfiles."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def caddyfile() -> str:
    path = ROOT / "Caddyfile"
    if not path.exists():
        pytest.skip("nur im Repo – im Docker-Build fehlt das Caddyfile")
    return path.read_text()


def _block(text: str, header: str) -> str:
    """Inhalt eines Blocks ab ``header`` bis zur passenden schließenden Klammer."""
    start = text.index(header)
    depth = 0
    for i in range(start + len(header) - 1, len(text)):  # Header endet mit der öffnenden Klammer
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            return text[start : i + 1]
    raise AssertionError(f"Block {header!r} nicht geschlossen")


def test_no_metrics_snippet_answers_404(caddyfile: str) -> None:
    block = _block(caddyfile, "(no_metrics) {")
    assert "@metrics path /metrics /metrics/*" in block
    assert "respond 404" in block


@pytest.mark.parametrize(
    "snippet",
    ["(hr_app) {", "(kiosk_app) {", "(staging_hr_app) {", "(staging_kiosk_app) {", "{$TENANT_BASE_DOMAIN:hr3000.localhost} {"],
)
def test_every_site_imports_no_metrics(caddyfile: str, snippet: str) -> None:
    assert "import no_metrics" in _block(caddyfile, snippet)


@pytest.mark.parametrize("snippet", ["(backend_api) {", "(staging_api) {"])
def test_api_metrics_blocked_before_backend(caddyfile: str, snippet: str) -> None:
    block = _block(caddyfile, snippet)
    match = re.search(r"@internal path ([^\n]+)", block)
    assert match is not None
    assert {"/internal/*", "/metrics", "/metrics/*"} <= set(match.group(1).split())
    assert block.index("respond @internal 404") < block.index("reverse_proxy")


def test_no_site_proxies_backend_without_metrics_block(caddyfile: str) -> None:
    """Jeder Weg zum Backend läuft über backend_api/staging_api oder nur /api/public/*."""
    for line in caddyfile.splitlines():
        if "reverse_proxy" in line and "backend:8000" in line:
            assert line.strip() in {"reverse_proxy backend:8000", "reverse_proxy staging-backend:8000"}
    assert caddyfile.count("reverse_proxy backend:8000") == 2  # backend_api + Website (/api/public/*)
    assert caddyfile.count("reverse_proxy staging-backend:8000") == 1
