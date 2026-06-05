"""
web/server.py — Read-only Kommandozentrale (Tier 1).

Visualisiert den LIVE-Zustand von vibelike: Workflow-Läufe (logs/workflows.jsonl),
ossifikat-Staging (data/ossifikat.db, inkl. Brücken) und Health. KEINE Steuerung —
der Workflow ist input()-gebunden; Steuerung wäre Tier 2 (Kontrollfluss-Inversion).

Bewusst ohne React/Build-Kette: FastAPI + eine selbsttragende HTML-Seite (web/static),
gestylt mit Claudes terminal.css-Design-Tokens. Jede Quelle wird pro Request frisch
gelesen → immer aktuell, kein Cache-Drift.

Start:  uvicorn web.server:app --reload --port 8000
        # oder:  python3 web/server.py
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ossifikat"))

WORKFLOWS_JSONL = ROOT / "logs" / "workflows.jsonl"
OSSIFIKAT_DB = ROOT / "data" / "ossifikat.db"
BRIDGE_RATIONALES = ROOT / "data" / "bridge_rationales.jsonl"
STATIC = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Vibelike Kommandozentrale", docs_url="/api/docs")


# ── Datenquellen (read-only, pro Request frisch) ───────────────────────────

def _load_workflows() -> list[dict]:
    if not WORKFLOWS_JSONL.exists():
        return []
    out = []
    for line in WORKFLOWS_JSONL.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _derive_status(wf: dict) -> str:
    """Ein Status-Label aus den echten Phasen-Ergebnissen ableiten."""
    phases = wf.get("phases", {})
    ver = phases.get("verification") or {}
    commit = phases.get("commit") or {}
    strat = phases.get("planning_strategy") or {}
    detail = phases.get("planning_detailed") or {}
    if strat.get("approved") is False or detail.get("approved") is False:
        return "aborted"
    if ver.get("tests_passed") is True and commit.get("committed"):
        return "success"
    if ver.get("tests_passed") is True:
        return "tests-ok"
    if "verification" in phases and ver.get("tests_passed") is False:
        return "tests-failed"
    return "partial"


def _summarize(wf: dict) -> dict:
    checks = wf.get("healthpoint_checks") or []
    drift = [c for c in checks if not c.get("aligned", True)]
    phases = wf.get("phases", {})
    briefing = phases.get("briefing") or {}
    return {
        "id": wf.get("id"),
        "task": wf.get("task", ""),
        "task_type": wf.get("task_type", ""),
        "iteration": wf.get("iteration", 0),
        "parent_id": wf.get("parent_id"),
        "status": _derive_status(wf),
        "tests_passed": (phases.get("verification") or {}).get("tests_passed"),
        "committed": bool((phases.get("commit") or {}).get("committed")),
        "mitte_verdict": (wf.get("mitte") or {}).get("review_verdict"),
        "drift_count": len(drift),
        "phase_count": len(phases),
        "timestamp": briefing.get("timestamp") or wf.get("id"),
        "files_written": (phases.get("execution") or {}).get("files_written") or [],
    }


def _load_rationales() -> dict[int, str]:
    out = {}
    if not BRIDGE_RATIONALES.exists():
        return out
    for line in BRIDGE_RATIONALES.read_text(encoding="utf-8").splitlines():
        try:
            d = json.loads(line)
            out[int(d["triple_id"])] = d.get("rationale", "")
        except (json.JSONDecodeError, KeyError, ValueError, TypeError):
            continue
    return out


# ── API ────────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health() -> JSONResponse:
    wfs = _load_workflows()
    staging = confirmed = 0
    ok = OSSIFIKAT_DB.exists()
    if ok:
        try:
            from ossifikat.store import OssifikatStore
            s = OssifikatStore(str(OSSIFIKAT_DB))
            staging = len(s.list_staging())
            try:
                confirmed = len(s.query())
            except Exception:
                confirmed = 0
            s.close()
        except Exception:
            ok = False
    return JSONResponse({
        "status": "ok",
        "workflows": len(wfs),
        "ossifikat_staging": staging,
        "ossifikat_confirmed": confirmed,
        "ossifikat_ok": ok,
    })


@app.get("/api/workflows")
def list_workflows() -> JSONResponse:
    wfs = _load_workflows()
    summaries = [_summarize(w) for w in wfs]
    summaries.reverse()  # neueste zuerst
    return JSONResponse({"workflows": summaries, "count": len(summaries)})


@app.get("/api/workflows/{wf_id}")
def workflow_detail(wf_id: str) -> JSONResponse:
    for wf in _load_workflows():
        if str(wf.get("id")) == wf_id:
            phases = wf.get("phases", {})
            # Verification-Output kappen (kann lang sein)
            ver = dict(phases.get("verification") or {})
            if isinstance(ver.get("output"), str) and len(ver["output"]) > 6000:
                ver["output"] = ver["output"][-6000:]
            detail = {
                "summary": _summarize(wf),
                "healthpoint_checks": wf.get("healthpoint_checks") or [],
                "briefing": {
                    "analysis": (phases.get("briefing") or {}).get("analysis", ""),
                    "focused_files": (phases.get("briefing") or {}).get("focused_files", []),
                },
                "strategy": (phases.get("planning_strategy") or {}).get("strategy", ""),
                "plan": (phases.get("planning_detailed") or {}).get("plan", ""),
                "hallucinated_files": (phases.get("planning_detailed") or {}).get("hallucinated_files", []),
                "execution": {
                    "files_written": (phases.get("execution") or {}).get("files_written", []),
                    "code_review": (phases.get("execution") or {}).get("code_review", ""),
                    "self_heal": (phases.get("execution") or {}).get("self_heal"),
                },
                "verification": ver,
                "commit": phases.get("commit") or {},
            }
            return JSONResponse(detail)
    raise HTTPException(status_code=404, detail=f"workflow {wf_id} not found")


@app.get("/api/ossifikat/staging")
def ossifikat_staging() -> JSONResponse:
    if not OSSIFIKAT_DB.exists():
        return JSONResponse({"triples": [], "count": 0, "error": "no ossifikat db"})
    from ossifikat.store import OssifikatStore
    s = OssifikatStore(str(OSSIFIKAT_DB))
    rationales = _load_rationales()
    triples = []
    try:
        for t in s.list_staging():
            triples.append({
                "id": t.id,
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "confidence": t.confidence,
                "source": t.source,
                "created_at": getattr(t, "created_at", ""),
                "rationale": rationales.get(t.id, ""),
            })
    finally:
        s.close()
    return JSONResponse({"triples": triples, "count": len(triples)})


# ── Statische Seite ──────────────────────────────────────────────────────────

@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
