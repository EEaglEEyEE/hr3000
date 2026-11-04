FROM python:3.12-slim AS base

WORKDIR /app

# WeasyPrint (PDF-Export des Schichtplans, siehe app/services/shift_plan_pdf_service.py)
# braucht Pango/HarfBuzz als Systembibliotheken (nicht per pip installierbar);
# gdk-pixbuf/cairo sind seit WeasyPrint 53+ nicht mehr nötig.
RUN apt-get update && apt-get install --no-install-recommends -y \
    libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 \
    shared-mime-info fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Exakt gepinnte Versionen (requirements.lock), damit jeder Build dieselben getesteten Pakete installiert.
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

# Testlauf als eigene Stufe: läuft bei jedem Build mit geänderten Quellen, gegen SQLite im
# Speicher (keine echten Daten, keine Secrets). Schlägt ein Test fehl, bricht der Build ab und
# scripts/deploy.sh rollt nicht aus – die laufende Version bleibt. Die Tests selbst landen nicht
# im fertigen Image.
FROM base AS test
COPY pytest.ini .
COPY tests ./tests
# -n auto: parallel auf allen Kernen (pytest-xdist), sonst dauert der Lauf auf dem Server ~12 Min.
RUN python -m pytest -q -n auto -p no:cacheprovider && touch /tmp/backend-tests-passed

FROM base
# Abhängigkeit auf die Teststufe erzwingen (BuildKit baut sonst nur benötigte Stufen).
COPY --from=test /tmp/backend-tests-passed /tmp/backend-tests-passed

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
