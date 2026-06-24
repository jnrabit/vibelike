"""
ossifikat_staleness_test.py — Misst, ob ossifikats functional-conflict-Audit
veraltetes Wissen erkennt, wenn ein neuer Analyse-Lauf einem alten widerspricht.

Zweistufig (spiegelt: Idee-Tauglichkeit != modell-limitierte Ausfuehrung):

  STUFE A — Idee:     handgemachte saubere Triples aus zwei "Analyse-Laeufen".
                      Beweist deterministisch, ob das Audit Veraltung faengt,
                      WENN der Claim-Strom sauber ist.

  STUFE B — Realitaet: qwen-Extractor auf echtem Analyse-Text. Zeigt, ob das
                      lokale Modell konsistente subject+predicate-Paare liefert,
                      sodass ein Konflikt ueberhaupt detektierbar ist.

Beispiel-Veraltung: heute haben wir validator2 self-contained gemacht. Eine
fruehere Analyse haette "erbt von StaticValidator" behauptet — Widerspruch.

Lauf:  python3 experiments/ossifikat_staleness_test.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# ossifikat-Paket importierbar machen (liegt unter <root>/ossifikat/ossifikat)
ROOT = Path(__file__).resolve().parent.parent

from ossifikat.store import OssifikatStore
from ossifikat.audit import AuditView, find_functional_predicate_conflicts


# ─────────────────────────────────────────────────────────────────────────────
# WIRING — die wiederverwendbare Bruecke (wandert spaeter in den Workflow)
# ─────────────────────────────────────────────────────────────────────────────

def feed_claim(store: OssifikatStore, subject: str, predicate: str, obj: str,
               source: str, confirm: bool = True) -> int:
    """Stage + (optional) confirm einen Claim. Audits zaehlen nur Bestaetigtes."""
    tid = store.add_staging(subject=subject, predicate=predicate, object=obj,
                            source=source, confidence=1.0)
    if confirm:
        store.confirm(tid, confirmed_by=source, confirmation_type="auto",
                      note="staleness-experiment")
    return tid


def declare_functional(store: OssifikatStore, predicate: str) -> None:
    """Konvention: Praedikat ist funktional (max. 1 Wert pro Subjekt).

    Wird als bestaetigtes Meta-Triple (pred, has_cardinality, functional) abgelegt.
    """
    feed_claim(store, subject=predicate, predicate="has_cardinality",
               obj="functional", source="convention")


def feed_text(store: OssifikatStore, extractor, text: str, source: str) -> list[int]:
    """Workflow-Wiring: freien Analyse-Text -> Triples extrahieren -> stage+confirm."""
    ids = extractor.extract_and_stage(text, store, source=source)
    for tid in ids:
        store.confirm(tid, confirmed_by=source, confirmation_type="auto",
                      note="extracted-claim")
    return ids


def run_conflict_audit(db_path: str) -> list:
    view = AuditView(db_path)
    findings = find_functional_predicate_conflicts(view)
    view.close() if hasattr(view, "close") else None
    return findings


def _print_findings(findings: list) -> None:
    if not findings:
        print("    (keine Konflikte gefunden)")
        return
    for f in findings:
        print(f"    🔴 {f.object}")
        for cv in f.details.get("conflicting_values", []):
            print(f"         · {cv['object']}  (source={cv['source']})")


# ─────────────────────────────────────────────────────────────────────────────
# STUFE A — Idee: saubere handgemachte Claims aus zwei Laeufen
# ─────────────────────────────────────────────────────────────────────────────

def stage_a() -> bool:
    print("\n" + "=" * 70)
    print("STUFE A — IDEE: faengt das Audit Veraltung bei sauberem Claim-Strom?")
    print("=" * 70)

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "stage_a.db")
        store = OssifikatStore(db)

        # Konvention: ein Modul hat GENAU eine Architektur-Klassifikation
        declare_functional(store, "architecture_is")

        # Lauf 1 (vor dem Refactor heute): validator2 erbt von StaticValidator
        print("\n  [Lauf 1 — fruehere Analyse]")
        feed_claim(store, "validator2.py", "architecture_is",
                   "extends_StaticValidator", source="analysis-run-1")
        print("    gespeichert: validator2.py architecture_is = extends_StaticValidator")
        print("\n  Audit nach Lauf 1:")
        _print_findings(run_conflict_audit(db))

        # Lauf 2 (nach dem Refactor heute): validator2 ist self-contained
        print("\n  [Lauf 2 — heutige Analyse, nach dem Merge]")
        feed_claim(store, "validator2.py", "architecture_is",
                   "self_contained", source="analysis-run-2")
        print("    gespeichert: validator2.py architecture_is = self_contained")
        print("\n  Audit nach Lauf 2:")
        findings = run_conflict_audit(db)
        _print_findings(findings)

        store.close()

        ok = any("validator2.py" in f.details.get("conflict_subject", "")
                 for f in findings)
        print(f"\n  ERGEBNIS STUFE A: {'✅ Audit faengt die Veraltung' if ok else '❌ Audit fand nichts'}")
        return ok


# ─────────────────────────────────────────────────────────────────────────────
# STUFE B — Realitaet: qwen-Extraktion auf echtem Text
# ─────────────────────────────────────────────────────────────────────────────

ANALYSIS_BEFORE = """
Die Klasse StaticValidatorV2 in validator2.py erbt von StaticValidator und
nutzt dessen Basis-Methoden. validator2.py haengt damit von static_validator.py ab.
"""

ANALYSIS_AFTER = """
Die Klasse StaticValidatorV2 in validator2.py ist self-contained und erbt von
keiner Basisklasse mehr. validator2.py hat keine Abhaengigkeit zu static_validator.py.
"""


def stage_b() -> bool:
    print("\n" + "=" * 70)
    print("STUFE B — REALITAET: liefert qwen konsistente Triples (Konflikt detektierbar)?")
    print("=" * 70)

    try:
        from ossifikat.extractor import QwenExtractor
        extractor = QwenExtractor(model="qwen2.5-coder:7b")
    except Exception as e:
        print(f"  [SKIP] Extractor/Ollama nicht verfuegbar: {e}")
        return False

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "stage_b.db")
        store = OssifikatStore(db)
        declare_functional(store, "architecture_is")  # gleiche Konvention

        print("\n  [Lauf 1] extrahiere aus 'vorher'-Analyse...")
        ids1 = feed_text(store, extractor, ANALYSIS_BEFORE, source="extract-run-1")
        print(f"    {len(ids1)} Triples extrahiert+bestaetigt")

        print("\n  [Lauf 2] extrahiere aus 'nachher'-Analyse...")
        ids2 = feed_text(store, extractor, ANALYSIS_AFTER, source="extract-run-2")
        print(f"    {len(ids2)} Triples extrahiert+bestaetigt")

        # Zeige was qwen tatsaechlich produziert hat
        view = AuditView(db)
        print("\n  Extrahierte Triples (subject --[predicate]--> object):")
        for t in view.all_triples():
            if t.predicate == "has_cardinality":
                continue
            print(f"    ({t.subject}) --[{t.predicate}]--> ({t.object})")

        findings = find_functional_predicate_conflicts(view)
        print("\n  Conflict-Audit auf extrahierten Triples:")
        _print_findings(findings)
        store.close()

        print("\n  ERGEBNIS STUFE B: "
              + ("✅ Extraktion sauber genug, Konflikt detektiert"
                 if findings else
                 "⚠️  kein Konflikt — qwen lieferte keine konsistenten subject+predicate-Paare\n"
                 "      (= der Extraktions-Engpass, NICHT die Audit-Idee)"))
        return bool(findings)


# ─────────────────────────────────────────────────────────────────────────────
# STUFE C — Scaffolding: bekanntes Vokabular vor Lauf 2 injizieren
# ─────────────────────────────────────────────────────────────────────────────

_META_PREDICATES = {"has_cardinality", "retracted_at", "has_conflict", "is_orphan_retract"}


def known_vocabulary(db_path: str) -> tuple[set[str], set[str]]:
    """Liest die bisher im Graph bekannten Subjekte + Praedikate (ohne Meta)."""
    view = AuditView(db_path)
    subjects, predicates = set(), set()
    for t in view.all_triples():
        if t.predicate in _META_PREDICATES:
            continue
        subjects.add(t.subject)
        predicates.add(t.predicate)
    return subjects, predicates


def extract_with_vocab(extractor, db_path: str, text: str) -> list[dict]:
    """Extraktion wie QwenExtractor.extract, aber mit injiziertem Kanon-Vokabular.

    Reproduziert den Ollama-Call selbst (gleicher SYSTEM_PROMPT), haengt aber
    das bekannte Vokabular an den User-Prompt: "fuer Bekanntes EXAKT diese Namen".
    """
    import requests

    subjects, predicates = known_vocabulary(db_path)
    prompt = f"Extrahiere alle Triples aus diesem Text:\n\n{text}"
    if subjects or predicates:
        prompt += (
            "\n\nWICHTIG — KANONISCHES VOKABULAR:\n"
            "Wenn du eine BEREITS BEKANNTE Entitaet oder Relation meinst, nutze "
            "EXAKT diesen Namen (KEINE Varianten wie 'Klasse X', 'Datei X' oder "
            "synonyme Praedikate):\n"
            f"  Subjekte:  {', '.join(sorted(subjects))}\n"
            f"  Praedikate: {', '.join(sorted(predicates))}\n"
            "Nur fuer wirklich NEUE Dinge fuehre neue Namen ein."
        )

    resp = requests.post(
        extractor.api_endpoint,
        json={"model": extractor.model, "system": extractor.SYSTEM_PROMPT,
              "prompt": prompt, "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    return extractor._parse_json_response(resp.json().get("response", "").strip())


def _stage_and_confirm(store, triples: list[dict], source: str) -> int:
    n = 0
    for tr in triples:
        try:
            tid = store.add_staging(subject=tr.get("subject", ""),
                                    predicate=tr.get("predicate", ""),
                                    object=tr.get("object", ""),
                                    source=source, confidence=float(tr.get("confidence", 1.0)))
            store.confirm(tid, confirmed_by=source, confirmation_type="auto",
                          note="canon-claim")
            n += 1
        except Exception:
            pass
    return n


def stage_c() -> bool:
    print("\n" + "=" * 70)
    print("STUFE C — SCAFFOLDING: schlaegt Vokabular-Injektion die Modellgroesse?")
    print("=" * 70)

    try:
        from ossifikat.extractor import QwenExtractor
        extractor = QwenExtractor(model="qwen2.5-coder:7b")
    except Exception as e:
        print(f"  [SKIP] Extractor/Ollama nicht verfuegbar: {e}")
        return False

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "stage_c.db")
        store = OssifikatStore(db)
        declare_functional(store, "architecture_is")

        # Lauf 1: noch kein Vokabular bekannt -> normale Extraktion
        print("\n  [Lauf 1] extrahiere 'vorher' (kein Vokabular bekannt)...")
        t1 = extract_with_vocab(extractor, db, ANALYSIS_BEFORE)
        n1 = _stage_and_confirm(store, t1, "canon-run-1")
        print(f"    {n1} Triples")

        # Lauf 2: bekanntes Vokabular aus Lauf 1 injizieren
        subs, preds = known_vocabulary(db)
        print(f"\n  [Lauf 2] injiziere Vokabular ({len(subs)} Subj, {len(preds)} Praed), extrahiere 'nachher'...")
        t2 = extract_with_vocab(extractor, db, ANALYSIS_AFTER)
        n2 = _stage_and_confirm(store, t2, "canon-run-2")
        print(f"    {n2} Triples")

        view = AuditView(db)
        print("\n  Extrahierte Triples:")
        for t in view.all_triples():
            if t.predicate in _META_PREDICATES:
                continue
            print(f"    ({t.subject}) --[{t.predicate}]--> ({t.object})")

        findings = find_functional_predicate_conflicts(view)
        print("\n  Conflict-Audit:")
        _print_findings(findings)
        store.close()

        print("\n  ERGEBNIS STUFE C: "
              + ("✅ Vokabular-Injektion erzeugt konsistente Namen -> Konflikt detektiert"
                 if findings else
                 "⚠️  weiterhin kein Konflikt — Canonicalization-Scaffolding reicht nicht,\n"
                 "      hier haengt es wirklich an Modellfaehigkeit"))
        return bool(findings)


# ─────────────────────────────────────────────────────────────────────────────
# STUFE D — Fixes Praedikat-Schema: constrained extraction
# ─────────────────────────────────────────────────────────────────────────────
# Kern-Trick: was in Stufe C ein CROSS-Praedikat-Widerspruch war
# ("erbt_von X" vs "ist self-contained"), wird hier ein GLEICHES-Praedikat-
# Wertkonflikt: inheritance_status = "extends:X" -> "none". Das faengt das Audit.

CANONICAL_SUBJECTS = ["StaticValidatorV2", "validator2.py"]

ARCH_SCHEMA = {
    "inheritance_status":
        "Erbverhalten einer Klasse. Wert: 'extends:<Basisklasse>' ODER 'none'.",
    "dependency_static_validator":
        "Haengt die Datei von static_validator.py ab? Wert: 'yes' ODER 'no'.",
}


def _schema_system_prompt() -> str:
    pred_lines = "\n".join(f"  - {p}: {desc}" for p, desc in ARCH_SCHEMA.items())
    return (
        "Du bist ein Schema-Mapper. Ordne die Aussagen des Textes in ein FESTES "
        "Schema ein. Du extrahierst NICHT frei, du MAPPST.\n\n"
        "Erlaubte Praedikate (NUR diese, exakt geschrieben):\n"
        f"{pred_lines}\n\n"
        "Regeln:\n"
        f"- Subjekt: EXAKT einer dieser Namen: {', '.join(CANONICAL_SUBJECTS)}\n"
        "- Praedikat: NUR aus der Liste oben.\n"
        "- object: exakt in der vorgegebenen Wertform.\n"
        "- Aussage die in kein Praedikat passt: WEGLASSEN.\n"
        "- Antworte AUSSCHLIESSLICH als JSON-Array:\n"
        '  [{"subject":"...","predicate":"...","object":"...","confidence":0.9}]'
    )


def extract_schema_constrained(extractor, text: str) -> list[dict]:
    """Constrained extraction: zwingt das Modell in ARCH_SCHEMA."""
    import requests
    resp = requests.post(
        extractor.api_endpoint,
        json={"model": extractor.model, "system": _schema_system_prompt(),
              "prompt": f"Mappe diesen Text ins Schema:\n\n{text}", "stream": False},
        timeout=60,
    )
    resp.raise_for_status()
    triples = extractor._parse_json_response(resp.json().get("response", "").strip())
    # Hard filter: nur Schema-konforme Praedikate + kanonische Subjekte durchlassen
    return [t for t in triples
            if t.get("predicate") in ARCH_SCHEMA
            and t.get("subject") in CANONICAL_SUBJECTS]


def stage_d() -> bool:
    print("\n" + "=" * 70)
    print("STUFE D — FIXES SCHEMA: faengt constrained extraction die Veraltung?")
    print("=" * 70)

    try:
        from ossifikat.extractor import QwenExtractor
        extractor = QwenExtractor(model="qwen2.5-coder:7b")
    except Exception as e:
        print(f"  [SKIP] Extractor/Ollama nicht verfuegbar: {e}")
        return False

    with tempfile.TemporaryDirectory() as td:
        db = str(Path(td) / "stage_d.db")
        store = OssifikatStore(db)
        for pred in ARCH_SCHEMA:
            declare_functional(store, pred)

        print("\n  [Lauf 1] mappe 'vorher' ins Schema...")
        t1 = extract_schema_constrained(extractor, ANALYSIS_BEFORE)
        n1 = _stage_and_confirm(store, t1, "schema-run-1")
        print(f"    {n1} schema-konforme Triples")

        print("\n  [Lauf 2] mappe 'nachher' ins Schema...")
        t2 = extract_schema_constrained(extractor, ANALYSIS_AFTER)
        n2 = _stage_and_confirm(store, t2, "schema-run-2")
        print(f"    {n2} schema-konforme Triples")

        view = AuditView(db)
        print("\n  Schema-konforme Triples:")
        for t in view.all_triples():
            if t.predicate in _META_PREDICATES:
                continue
            print(f"    ({t.subject}) --[{t.predicate}]--> ({t.object})")

        findings = find_functional_predicate_conflicts(view)
        print("\n  Conflict-Audit:")
        _print_findings(findings)
        store.close()

        print("\n  ERGEBNIS STUFE D: "
              + ("✅ Constrained extraction -> gleiches Praedikat, anderer Wert -> Audit feuert"
                 if findings else
                 "⚠️  kein Konflikt — selbst ins Schema gezwungen mappt das lokale Modell\n"
                 "      nicht konsistent genug (hier braucht es ein staerkeres Modell\n"
                 "      oder einen deterministischen Mapper)"))
        return bool(findings)


_STAGES = {"a": stage_a, "b": stage_b, "c": stage_c, "d": stage_d}


if __name__ == "__main__":
    # Optional: einzelne Stufe via argv (z.B. 'python3 ...py d') fuer schnelle Iteration
    if len(sys.argv) > 1:
        for key in sys.argv[1:]:
            _STAGES[key.lower()]()
        sys.exit(0)

    a_ok = stage_a()
    b_ok = stage_b()
    c_ok = stage_c()
    d_ok = stage_d()

    print("\n" + "=" * 70)
    print("FAZIT")
    print("=" * 70)
    print(f"  Stufe A (Idee tauglich?):               {'JA' if a_ok else 'NEIN'}")
    print(f"  Stufe B (rohe lokale Extraktion?):      {'JA' if b_ok else 'NEIN'}")
    print(f"  Stufe C (Vokabular-Scaffolding?):       {'JA' if c_ok else 'NEIN'}")
    print(f"  Stufe D (fixes Schema, constrained?):   {'JA' if d_ok else 'NEIN'}")
    print()
    if not a_ok:
        print("  → Selbst mit sauberen Claims faengt das Audit nichts. Idee ueberdenken.")
    elif d_ok:
        print("  → DURCHBRUCH: fixes Praedikat-Schema schlaegt Modellgroesse. Das")
        print("    lokale Modell kann ins Schema mappen -> Audit feuert. Autarkie-treu.")
        print("    Naechster Schritt: Schema-Extractor ins ossifikat-Paket + Live-Wiring.")
    elif c_ok:
        print("  → Canonicalization-Scaffolding reicht; fixes Schema waere zusaetzlich sauberer.")
    else:
        print("  → Idee traegt, aber lokale Extraktion (auch constrained) ist zu wackelig.")
        print("    HIER wuerde ein staerkeres Modell oder ein deterministischer Mapper helfen.")
