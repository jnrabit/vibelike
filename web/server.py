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

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ossifikat"))
sys.path.insert(0, str(HERE))  # damit `from auth/terminal_ws import` unter beiden Startarten lädt

WORKFLOWS_JSONL = ROOT / "logs" / "workflows.jsonl"
OSSIFIKAT_DB = ROOT / "data" / "ossifikat.db"
BRIDGE_RATIONALES = ROOT / "data" / "bridge_rationales.jsonl"
STATIC = HERE / "static"

app = FastAPI(title="Vibelike Kommandozentrale", docs_url="/api/docs")

# PTY-Web-Terminal (hinter Token-Auth + 'terminal'-Capability)
from terminal_ws import router as terminal_router  # noqa: E402
app.include_router(terminal_router)

# P3.4: Backend-Management API
from api_manager import router as api_router  # noqa: E402
app.include_router(api_router)

from auth import device_for_token, capabilities_for  # noqa: E402
import ratification  # noqa: E402  (reversible park/archiv-Zustände überm Staging)


class QueryRequest(BaseModel):
    query: str


def _require_ratify(authorization: str = Header(default=None)) -> str:
    """Ratifizieren ist ein Schreib-Akt → Token Pflicht. Akzeptiert 'ratify' ODER
    'terminal' (ein shell-vertrautes Gerät darf erst recht ein Tripel bestätigen).
    Gibt die verifizierte device_id zurück (landet als confirmed_by im append-only Log)."""
    token = authorization[7:].strip() if authorization and authorization.startswith("Bearer ") else None
    device = device_for_token(token)
    if not device:
        raise HTTPException(401, "ungültiges oder fehlendes Token")
    caps = capabilities_for(device)
    if "ratify" not in caps and "terminal" not in caps:
        raise HTTPException(403, "Device darf nicht ratifizieren ('ratify' oder 'terminal' nötig)")
    return device


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


def _payload_id(payload: dict) -> int:
    try:
        return int(payload.get("id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "id fehlt/ungültig")


@app.get("/api/ossifikat/staging")
def ossifikat_staging(view: str = "queue") -> JSONResponse:
    """Staging-Tripel nach Ratifizier-Sicht: queue | parked | archived.
    Liefert auch counts aller drei Sichten (für die Tab-Badges)."""
    empty = {"triples": [], "count": 0, "view": view,
             "counts": {"queue": 0, "parked": 0, "archived": 0}}
    if not OSSIFIKAT_DB.exists():
        return JSONResponse({**empty, "error": "no ossifikat db"})
    from ossifikat.store import OssifikatStore
    s = OssifikatStore(str(OSSIFIKAT_DB))
    rationales = _load_rationales()
    overlay = ratification.states()
    counts = {"queue": 0, "parked": 0, "archived": 0}
    triples = []
    try:
        for t in s.list_staging():
            st = overlay.get(str(t.id), {}).get("state", "queue")
            counts[st] = counts.get(st, 0) + 1
            if st != view:
                continue
            triples.append({
                "id": t.id,
                "subject": t.subject,
                "predicate": t.predicate,
                "object": t.object,
                "confidence": t.confidence,
                "source": t.source,
                "created_at": getattr(t, "created_at", ""),
                "rationale": rationales.get(t.id, ""),
                "state": st,
            })
    finally:
        s.close()
    return JSONResponse({"triples": triples, "count": len(triples), "view": view, "counts": counts})


@app.post("/api/ossifikat/confirm")
def ossifikat_confirm(payload: dict, device: str = Depends(_require_ratify)) -> JSONResponse:
    """Tripel verbürgen (ossifikat staging=0 + append-only Confirmation). Overlay wird geräumt."""
    if not OSSIFIKAT_DB.exists():
        raise HTTPException(404, "keine ossifikat db")
    tid = _payload_id(payload)
    note = payload.get("note")
    from ossifikat.store import OssifikatStore
    s = OssifikatStore(str(OSSIFIKAT_DB))
    try:
        s.confirm(tid, confirmed_by=device, confirmation_type="web", note=note)
    finally:
        s.close()
    ratification.clear_state(tid)
    return JSONResponse({"ok": True, "id": tid, "confirmed_by": device})


@app.post("/api/ossifikat/park")
def ossifikat_park(payload: dict, device: str = Depends(_require_ratify)) -> JSONResponse:
    """Zurückstellen — später entscheiden (reversibel, nichts verloren)."""
    tid = _payload_id(payload)
    ratification.set_state(tid, "parked", device)
    return JSONResponse({"ok": True, "id": tid, "state": "parked"})


@app.post("/api/ossifikat/archive")
def ossifikat_archive(payload: dict, device: str = Depends(_require_ratify)) -> JSONResponse:
    """Verwerfen OHNE Löschen — reversibel (ersetzt das harte reject)."""
    tid = _payload_id(payload)
    ratification.set_state(tid, "archived", device)
    return JSONResponse({"ok": True, "id": tid, "state": "archived"})


@app.post("/api/ossifikat/restore")
def ossifikat_restore(payload: dict, device: str = Depends(_require_ratify)) -> JSONResponse:
    """Zurück in die Queue (Overlay entfernen)."""
    tid = _payload_id(payload)
    ratification.clear_state(tid)
    return JSONResponse({"ok": True, "id": tid, "state": "queue"})


@app.post("/api/ossifikat/reject")
def ossifikat_reject(payload: dict, device: str = Depends(_require_ratify)) -> JSONResponse:
    """Endgültig löschen (nur bewusst aus dem Archiv). Unwiderruflich."""
    if not OSSIFIKAT_DB.exists():
        raise HTTPException(404, "keine ossifikat db")
    tid = _payload_id(payload)
    from ossifikat.store import OssifikatStore
    s = OssifikatStore(str(OSSIFIKAT_DB))
    try:
        s.reject(tid)
    finally:
        s.close()
    ratification.clear_state(tid)
    return JSONResponse({"ok": True, "id": tid, "deleted": True})


# ── Query API (Hybrid Vault-Mode) ────────────────────────────────────────────

@app.post("/api/query")
async def api_query(request: QueryRequest):
    """
    Hybrid-Mode Query:
    - Claude macht Deep Analysis (20 Top + 10 Random docs)
    - Alle 3 Models antworten mit Vault-Context
    - Consensus wählt Winner
    """
    try:
        import asyncio
        query = request.query.strip()
        if not query:
            return JSONResponse({"error": "query erforderlich"}, status_code=400)

        # Imports (lazy, damit server schnell startet)
        sys.path.insert(0, str(ROOT))
        from terminal import (
            QwenCoder, ClaudeCoder, MistralCoder,
            CodeRetriever, analyze_deep, COUNCIL_MODEL
        )
        from agent_pool import AgentResult
        from consensus import Consensus

        print(f"\n[API-QUERY] {query[:80]}")

        # 1. Retrieve vault context
        retriever = CodeRetriever()
        search_result = retriever.search(query, k=30)
        # search() gibt tuple zurück: (docs, state_before, state_after)
        if isinstance(search_result, tuple):
            context = search_result[0] if search_result else []
        else:
            context = search_result if search_result else []
        print(f"[RETRIEVE] {len(context)} docs")

        # 2. Deep Analysis (Claude)
        analysis_summary = ""
        try:
            claude_analyzer = ClaudeCoder(model=COUNCIL_MODEL)
            analysis_summary = analyze_deep(query, context, claude_analyzer)
            if analysis_summary:
                print(f"[ANALYSIS] {len(analysis_summary)} chars")
        except Exception as e:
            print(f"[WARN] Analysis failed: {e}")

        # 3. System-Prompt mit Vault-Context
        sys_full = f"""Du bist ein Experte für Wissensfragen. Nutze folgende Vault-Analyse und antworte präzise:

{analysis_summary if analysis_summary else "Keine Vault-Analyse verfügbar"}

Frage: {query}"""

        # 4. Alle 3 Models parallel mit Vault-Context
        models_to_query = [
            ("qwen", QwenCoder(model="qwen2.5-coder:1.5b")),
            ("claude", ClaudeCoder(model="claude-haiku-4-5-20251001")),
            ("mistral", MistralCoder(model="mistral-small-latest"))
        ]

        async def query_model(name, model_coder):
            try:
                answer = model_coder.generate(query, system=sys_full, stream=False)
                return (name, answer, None)
            except Exception as e:
                return (name, "", str(e))

        # Parallel queries
        tasks = [query_model(name, coder) for name, coder in models_to_query]
        results = await asyncio.gather(*tasks)

        # Convert zu response_dict
        response_dict = {}
        for model_name, answer, error in results:
            if error:
                response_dict[model_name] = AgentResult(
                    model=model_name,
                    answer="",
                    error=error
                )
            else:
                response_dict[model_name] = AgentResult(
                    model=model_name,
                    answer=answer,
                    vault_hits=len(context) if context else 0
                )

        # 5. Consensus
        consensus = Consensus()
        result = await consensus.evaluate_and_fill(response_dict, query, None)

        # Response
        return JSONResponse({
            "query": query,
            "winner": result.winner,
            "winner_score": result.winner_score,
            "winner_answer": result.winner_answer,
            "all_answers": {
                name: {
                    "answer": ar.answer,
                    "error": ar.error,
                    "score": result.scores.get(name, 0)
                }
                for name, ar in response_dict.items()
            },
            "vault_hits": len(context),
            "analysis_length": len(analysis_summary)
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status_code=500)


# ── Statische Seite ──────────────────────────────────────────────────────────

@app.get("/")
def index() -> FileResponse:
    return FileResponse(str(STATIC / "index.html"))


app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
