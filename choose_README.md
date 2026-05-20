# choose — das Atom

**Version 0.1** — erstes vollständiges Atom, Spec aus
`CC_PROMPT_choose_atom.md` umgesetzt, alle Abnahme-Kriterien erfüllt.

Eine winzige Python-Bibliothek mit genau einer Operation: **deterministische
Wahl mit Eskalations-Hierarchie**.

Gegeben eine geordnete Liste von Predicates (billig zuerst) und eine Liste
von Kandidaten: gib den ersten Kandidaten zurück, den ein Predicate
akzeptiert. Wenn keiner entschieden werden kann, sag das ehrlich — kollabiere
nicht stillschweigend auf einen Default.

## Beispiel

```python
from choose import choose, Predicate, PredicateBundle, Verdict

predicates = [
    Predicate(
        name="ist null",
        evaluate=lambda x: Verdict.ACCEPT if x == 0 else Verdict.DEFER,
    ),
    Predicate(
        name="ist gerade",
        evaluate=lambda x: Verdict.ACCEPT if x % 2 == 0 else Verdict.REJECT,
    ),
]
bundle = PredicateBundle(predicates)
result = choose(bundle, candidates=[0, 1, 2, 3])

# result.outcome           == Decided(0)
# result.deciding_predicate == "ist null"
# result.unused_predicates  == ("ist gerade",)
```

## Die drei Verdicts

| Verdict  | Bedeutung                                                    |
|----------|--------------------------------------------------------------|
| `ACCEPT` | Dieses Predicate akzeptiert diesen Kandidaten. Wahl steht.   |
| `REJECT` | Dieses Predicate lehnt diesen Kandidaten aktiv ab.           |
| `DEFER`  | Dieses Predicate kann es nicht entscheiden — eskaliere.      |

`DEFER` ist kein Implementierungsdetail, sondern der Kern: ohne den dritten
Zustand gibt es keine Eskalation.

## Wenn keine Wahl möglich ist

Statt eines Defaults kommt `Undecidable` mit einem Grund zurück. Der Aufrufer
entscheidet, wie reagiert wird:

| Reason                      | Was tun?                                  |
|-----------------------------|-------------------------------------------|
| `ALL_PREDICATES_DEFERRED`   | Stärkere Predicates hinzufügen.           |
| `NO_CANDIDATE_ACCEPTED`     | Neue Kandidaten generieren.               |
| `EMPTY_CANDIDATES`          | Programmierfehler beim Aufrufer.          |
| `EMPTY_BUNDLE`              | Programmierfehler beim Aufrufer.          |

Siehe `tests/examples/demo_iteration.py` für ein lauffähiges Beispiel,
in dem der Aufrufer auf `Undecidable` reagiert.

## Determinismus

`choose()` ist eine reine Funktion: kein Zufall, keine Zeit, keine
Seiteneffekte. Jeder Aufruf liefert einen `reproducibility_hash`, der die
Kombination aus Bundle und Kandidaten eindeutig identifiziert — gleiche
Eingabe ⇒ gleicher Hash ⇒ gleiche Wahl.

Der Hash baut auf `repr()` der Kandidaten auf. Wenn ein Kandidat das
Default-`object.__repr__` erbt (Memory-Adresse), wirft `choose()` einen
`ValueError`: ohne stabile Repr wäre der Hash nicht reproduzierbar.
Verwende dataclasses, NamedTuples, frozensets oder eigene `__repr__` für
Custom-Objekte.

## Predicate-Reihenfolge

`PredicateBundle` respektiert die übergebene Reihenfolge, solange alle
Predicates den Default-`cost_hint` (`100`) verwenden. Sobald ein Predicate
einen abweichenden `cost_hint` hat, wird stable nach `cost_hint` aufsteigend
sortiert (billig zuerst).

## Was das Atom *nicht* ist

- Kein Gate, kein Healthpoint, kein Workflow — nur eine Wahl.
- Keine LLM-Calls, keine externen Services — reines Python.
- Keine Loops innerhalb von `choose()` — Iteration ist Sache des Aufrufers
  (siehe Demo).
- Kein Logging, keine CLI, keine Config-Dateien — Bibliothek, nicht
  Anwendung.
- Kein Caching — wer cachen möchte, nutzt den `reproducibility_hash`.

## Tests

```bash
pip install -e ".[test]"
pytest
python -m tests.examples.demo_iteration
```
