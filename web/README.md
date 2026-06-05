# Vibelike Kommandozentrale (Tier 1 — read-only)

Visualisiert den Live-Zustand: Workflow-Läufe, ossifikat-Staging (inkl. Brücken), Health.
**Read-only** — keine Steuerung. Der Workflow ist `input()`-gebunden; Steuerung (Gates
genehmigen, Workflows starten) wäre Tier 2 (Kontrollfluss-Inversion hinter einem
`Approver`-Interface). Bewusst ohne React/Build-Kette: FastAPI + selbsttragende
HTML-Seite, gestylt mit den `terminal.css`-Design-Tokens ("Editorial Dark").

## Start

```bash
cd /home/jnrabit/vibelike
uvicorn web.server:app --host 127.0.0.1 --port 8800
# oder:  python3 web/server.py   (Port 8000)
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

- `GET /api/health` — Counts
- `GET /api/workflows` — Liste (neueste zuerst)
- `GET /api/workflows/{id}` — Detail (Phasen, Healthpoint, Verification-Output)
- `GET /api/ossifikat/staging` — Staging-Tripel + Rationale

## Nicht enthalten (bewusst)

Steuerung, Workflow-Start, ossifikat-confirm aus dem Browser. Siehe Tier-2-Notiz oben.
