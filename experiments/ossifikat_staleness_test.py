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
sys.path.insert(0, str(ROOT / "ossifikat"))

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


if __name__ == "__main__":
    a_ok = stage_a()
    b_ok = stage_b()
    c_ok = stage_c()

    print("\n" + "=" * 70)
    print("FAZIT")
    print("=" * 70)
    print(f"  Stufe A (Idee tauglich?):              {'JA' if a_ok else 'NEIN'}")
    print(f"  Stufe B (rohe lokale Extraktion ok?):  {'JA' if b_ok else 'NEIN'}")
    print(f"  Stufe C (mit Vokabular-Scaffolding?):  {'JA' if c_ok else 'NEIN'}")
    print()
    if a_ok and not b_ok and c_ok:
        print("  → DURCHBRUCH: Idee traegt, und Canonicalization-Scaffolding schlaegt")
        print("    Modellgroesse. Autarkie-treu loesbar — Vokabular-Injektion in den")
        print("    Extractor + Live-Wiring in den Workflow lohnt sich.")
    elif a_ok and not b_ok and not c_ok:
        print("  → Idee traegt, aber selbst mit Vokabular-Scaffolding kanonisiert das")
        print("    lokale Modell nicht zuverlaessig. HIER wuerde ein staerkeres Modell")
        print("    (oder ein deterministischer Entity-Linker) den Unterschied machen.")
    elif a_ok and b_ok:
        print("  → Idee UND rohe Extraktion tragen schon. Live-Wiring lohnt direkt.")
    elif not a_ok:
        print("  → Selbst mit sauberen Claims faengt das Audit nichts. Idee ueberdenken.")
