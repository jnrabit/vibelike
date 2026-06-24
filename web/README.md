# Vibelike Kommandozentrale (Tier 1)

Visualisiert den Live-Zustand: Workflow-Läufe, ossifikat-Staging (inkl. Brücken), Health.

**Hybrid-API**: Primär read-only für das Dashboard, aber mit Token-Auth geschützte
Admin-Endpunkte für Wissensgraph-Verwaltung (confirm/park/archive/restore/reject).
Der Workflow ist `input()`-gebunden; Workflow-Start bleibt Tier 2 (Kontrollfluss-Inversion
hinter `Approver`-Interface). Bewusst ohne React/Build-Kette: FastAPI + selbsttragende
HTML-Seite, gestylt mit den `terminal.css`-Design-Tokens ("Editorial Dark").

## Start

```bash
cd /home/jnrabit/opencode/vibelike
uvicorn vibelike.web.server:app --host 127.0.0.1 --port 8800
# oder:  python3 -m vibelike.web.server   (Port 8000)
```

Dann im Browser: <http://127.0.0.1:8800>

> Hinweis: Port 8000 hält evtl. noch ein alter (root-owned) vibelikevibe-Server.
> Aufräumen: `sudo fuser -k 8000/tcp`. Deshalb läuft diese Version auf 8800.

## Datenquellen (alle pro Request frisch gelesen → immer aktuell)

| Quelle | zeigt |
|---|---|
| `logs/workflows.jsonl` | 6-Phasen-Läufe: Status, Healthpoint-Drift, mitte-Verdict, geschriebene Dateien |
| `data/ossifikat.db` | Staging-Tripel (Kandidaten-Brücken, warten auf Ratifizierung) |
| `data/bridge_rationales.jsonl` | Brücken-Begründung (zum Tripel gemerged) |

## API

### Public Endpoints (read-only)

- `GET /api/health` — Counts
- `GET /api/workflows` — Liste (neueste zuerst)
- `GET /api/workflows/{id}` — Detail (Phasen, Healthpoint, Verification-Output)
- `GET /api/ossifikat/staging` — Staging-Tripel + Rationale

### Admin Endpoints (Token-Auth, Wissensgraph-Verwaltung)

- `POST /api/ossifikat/confirm/{triple_id}` — Tripel ratifizieren
- `POST /api/ossifikat/park/{triple_id}` — Tripel parken (reversible Hold)
- `POST /api/ossifikat/archive/{triple_id}` — Tripel archivieren
- `POST /api/ossifikat/restore/{triple_id}` — Archiviertes Tripel wiederherstellen
- `POST /api/ossifikat/reject/{triple_id}` — Tripel ablehnen

**Authentifizierung:** Bearer Token über `Authorization: Bearer <token>` Header.

## Nicht enthalten (bewusst)

Workflow-Start, LLM-Query aus dem Browser. Diese sind über `terminal.py` (CLI) oder direkt
`/api/query` (POST) verfügbar. Siehe Tier-2-Notiz oben.

---

# ==== GEMINI-FLASH + MISTRAL INTEGRATION - BEGIN ====

## API-Rat-Modi (CLI Terminal)

Das Terminal unterstützt 5 Antwort-Modi über Präfixe:

| Präfix | Modus | Zusammensetzung | API-Key |
|--------|-------|----------------|---------|
| (kein) | Normal | lokal nur | - |
| `??h` | Haiku-Rat | lokal + **Claude-Haiku** + Sonnet-Synthese | `ANTHROPIC_API_KEY` |
| `??g` | Gemini-Rat | lokal + **gemini-2.5-flash** + gemini-2.5-pro-Synthese | `GEMINI_API_KEY` |
| `??m` | Mistral-Rat | lokal + **mistral-large** + mistral-large-Synthese | `MISTRAL_API_KEY` |
| `??a` | ALL-IN Rat | lokal + Haiku + **gemini-2.5-flash** + **mistral-large** + Synthese | alle 3 Keys |

### Einrichtung für Gemini:

```bash
# 1. Paket installieren
pip install google-genai

# 2. API-Key setzen (für Terminal)
export GEMINI_API_KEY="dein_gemini_api_key_hier"

# 3. (Optional) Codegen-Backend auf Gemini umstellen
export VIBELIKE_CODEGEN_BACKEND="gemini"
export VIBELIKE_CODEGEN_MODEL="gemini-2.5-flash"
```

### Einrichtung für Mistral:

```bash
# 1. Paket installieren
pip install mistralai

# 2. API-Key setzen (für Terminal)
export MISTRAL_API_KEY="dein_mistral_api_key_hier"

# 3. (Optional) Codegen-Backend auf Mistral umstellen
export VIBELIKE_CODEGEN_BACKEND="mistral"
export VIBELIKE_CODEGEN_MODEL="mistral-large-latest"
```

### Umgebungvariablen:

**Gemini:**
- `GEMINI_API_KEY` — Pflicht für alle Gemini-Modi
- `VIBELIKE_GEMINI_COUNCIL_MODEL` — Default: `gemini-2.5-flash`
- `VIBELIKE_GEMINI_SYNTH_MODEL` — Default: `gemini-2.5-pro`

**Mistral:**
- `MISTRAL_API_KEY` — Pflicht für alle Mistral-Modi
- `VIBELIKE_MISTRAL_COUNCIL_MODEL` — Default: `mistral-large-latest`
- `VIBELIKE_MISTRAL_SYNTH_MODEL` — Default: `mistral-large-latest`

**Allgemein:**
- `VIBELIKE_CODEGEN_BACKEND` — Werte: `"claude"`, `"gemini"`, `"mistral"`, oder `"ollama"`

### RÜCKGÄNGIG MACHEN:

**Nur Mistral entfernen:**
1. Alle `MISTRAL_*` Umgebungsvariablen entfernen
2. In `terminal.py` und `workflow_agent.py` alle Blöcke zwischen
   `# ==== MISTRAL INTEGRATION - BEGIN ====` und
   `# ==== MISTRAL INTEGRATION - END ====` löschen
3. Paket deinstallieren: `pip uninstall mistralai`

**Gemini + Mistral entfernen:**
1. Alle `GEMINI_*` und `MISTRAL_*` Umgebungsvariablen entfernen
2. In `terminal.py` und `workflow_agent.py` alle Blöcke zwischen
   `# ==== GEMINI-FLASH INTEGRATION - BEGIN ====` und
   `# ==== GEMINI-FLASH + MISTRAL INTEGRATION - END ====` löschen
3. Pakete deinstallieren: `pip uninstall google-genai mistralai`

# ==== GEMINI-FLASH + MISTRAL INTEGRATION - END ===
