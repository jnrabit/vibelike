# inkonsistence — Verständnis-Stand nach Klärung

**Status:**     Synthese-Snapshot
**Datum:**      2026-05-19
**Bezug:**      `inkonsistence.md`, `inkonsistence.py`
**Zweck:**      Festhalten, wie das Modell nach den drei Klärungs-Runden steht.
                Anschluss-Dokument, kein Ersatz für `inkonsistence.md`.

---

## Inhaltsverzeichnis

1. [Kernbild — wie das System jetzt aussieht](#1-kernbild)
2. [Der Healthpoint-Wandler (Klärung 1)](#2-healthpoint-wandler)
3. [Gates als Logik-Primitive (Klärung 2)](#3-gates-als-logik-primitive)
4. [Wartepunkte und non-final Postconditions (Klärung 3)](#4-wartepunkte)
5. [Was sich gegenüber inkonsistence.md verschoben hat](#5-verschiebungen)
6. [Was offen bleibt](#6-offen)
7. [Begriffs-Glossar](#7-glossar)

---

## 1. Kernbild

Das System besteht aus vier Schichten, jede mit klarer Verantwortung:

```
┌───────────────────────────────────────────────────────────────┐
│  HEALTHPOINT (high-level Spezifikation)                       │
│  Einmal definiert, stabil über Workflow-Lebensdauer           │
└──────────────────────────┬────────────────────────────────────┘
                           │
                  [ Wandler / Compiler ]   ← einmal teuer
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│  PREDICATE-BUNDLE (low-level, billig)                         │
│   ├─ struct_check     (O(1) — Struktur-Form)                  │
│   ├─ constraint_eval  (O(n) — Constraints, Triples)           │
│   └─ semantic_fallback (teuer, nur bei Unentscheidbarkeit)    │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           │ wird von ALLEN Phasen genutzt
                           ▼
┌───────────────────────────────────────────────────────────────┐
│  PHASEN mit GATES (Logik-Primitive)                           │
│                                                                │
│   Phase A         Phase B         Phase C                     │
│   Hauptpfad       Hauptpfad       Hauptpfad                   │
│      │               │               │                        │
│   ┌──┴──┐         ┌──┴──┐         ┌──┴──┐                    │
│   │Gate1│         │Gate1│         │Gate1│  ← fundamentale     │
│   │Gate2│         │Gate2│         │Gate2│    Logik-Formen     │
│   │ ❄   │         │ ❄   │         │ ❄   │    aus Gate-Algebra │
│   └─────┘         └─────┘         └─────┘                    │
└──────────────────────────┬────────────────────────────────────┘
                           │
                           ▼
┌───────────────────────────────────────────────────────────────┐
│  WARTEPUNKT (Continuation, non-final Postcondition)           │
│  Zustand "gut genug zum Warten", noch nicht "gut genug zum    │
│  Fortschreiten". Wiederverwendbar, kippbar bei User-Eingriff.  │
└──────────────────────────┬────────────────────────────────────┘
                           │
                  [ finale Bestätigung ]
                           │
                           ▼
                       EXECUTE
```

---

## 2. Healthpoint-Wandler

**Problem in der ersten Fassung:** `Healthpoint.matches()` war ein NotImplementedError-Stub.
Wenn das in der Praxis ein LLM-Call wird, frisst es das Energie-Argument auf — die teuerste
Operation läuft bei jeder Phase mehrfach.

**Klärung:** Statt jeden Aufruf einzeln zu prüfen, wird der Healthpoint einmal
**kompiliert** (im Sinne von Numba: AOT-Compilation mit Spezialisierung) in ein
**Predicate-Bundle** aus mehreren günstigen Prüfvorschriften.

### Eskalations-Hierarchie

Die kompilierten Predicates sind nach Kosten gestaffelt:

| Stufe | Kosten | Was wird geprüft | Beispiel |
|-------|--------|------------------|----------|
| `struct_check`     | O(1)  | Strukturelle Form, schnell prüfbare Eigenschaften | "hat Quellenanker?" |
| `constraint_eval`  | O(n)  | Constraints über Daten, Triple-Konsistenz | "alle behaupteten Quellen existieren in Vault?" |
| `semantic_fallback`| LLM   | Bedeutungs-Prüfung, nur bei Unentscheidbarkeit | "entspricht die Antwort dem Intent?" |

Das System fragt zuerst billig, eskaliert nur bei Bedarf. Wie Numba im
`nopython`-Modus zuerst Native-Code versucht und nur bei Bedarf zurückfällt.

### Konsequenzen

- Der Healthpoint ist nicht mehr Freitext, sondern eine **Spezifikation in strukturierter Form**.
- `matches()` ist kein einzelner Call, sondern ein **PredicateBundle**, das zur
  Workflow-Initialisierung gebaut wird.
- Die "teuer-genau-richtig"-Spannung wird über die Hierarchie aufgelöst: meist
  reicht billig, semantisch wird nur befragt, wenn nötig.

### Anknüpfung an bestehende Projekte

Das passt direkt zu **Ossifikat**: der Healthpoint kann selbst als Triple-Form
ausgedrückt werden, der `struct_check` läuft als Triple-Match gegen den Store.

---

## 3. Gates als Logik-Primitive

**Verschiebung gegenüber `inkonsistence.md`:** Gates wurden dort als
"alternative Pfade" beschrieben. Das war ungenau. Die korrekte Charakterisierung:

> Gates sind **fundamentale Logik-Skizzen**, nicht Entscheidungsfindungs-Optionen.

Ein Gate ist nicht *"vielleicht so oder so"*, sondern *"an dieser Stelle existiert
eine logische Form, die unter Bedingung X aktiv wird"*.

### Was das ändert

- Gates sind **klein**, **abgeschlossen**, **wiederverwendbar**.
- Es gibt nicht beliebig viele Gates pro Workflow — es gibt eine **Gate-Algebra**,
  aus der gewählt wird.
- Gates sind in eingefrorenem Zustand **deklarative Formen**, kein toter Code.
  Erst der Trigger ruft den Interpreter.

### Beispielhafte Gate-Primitiven

Konkrete Bausteine sind noch offen, aber das Genre wäre etwa:

- **Negation-Gate** — Hauptpfad behauptet X, Gate hält die Form ¬X bereit
- **Constraint-Verschärfung** — wenn Hauptpfad zu locker, härtere Bedingung aktivieren
- **Quellen-Wechsel** — wenn Vault-Antwort schwach, anderen Index befragen
- **Disjunktion-Auflösung** — wenn Hauptpfad mehrdeutig, eine Disjunkt-Form festlegen
- **Reformulierung** — wenn Hauptpfad strukturell ok aber semantisch off, Form umschreiben

Eine geschlossene Liste wird sich erst beim Implementieren herauskristallisieren.

### Verwandte Konzepte zur Verortung

- **Algebraic Effects** (PL-Forschung) — kleine Logik-Bausteine, getrennt von Interpreter
- **Tagless-Final-Encoding** (Haskell/OCaml) — deklarative Form ohne sofortige Ausführung
- **Combinator-Bibliotheken** — kleine Primitive, komponierbar zu größeren Strukturen

---

## 4. Wartepunkte

**Klärung zum Master-Check:** nach dem Kollaps wartet der Zustand
**im Logik-Kern**. Die Frage "erfüllt das den Healthpoint?" ist
gleichzeitig "darf ich von hier weitermachen?".

### Eigenschaften des Wartepunkts

- Der Zustand ist **wiederverwendbar** — kann auch in eine *neue* Richtung kippen,
  ohne kompletten Rollback.
- Es ist eine **non-final Postcondition**: "gut genug zum Warten",
  noch nicht "gut genug zum Fortschreiten".
- Solange keine finale Bestätigung kommt, bleibt der Zustand offen.

### Warum das das Mutabilitäts-Problem löst

Eine der offenen Fragen in `inkonsistence.md` war: was passiert, wenn der User
mid-Workflow die Anforderung präzisiert?

Die Antwort fällt aus dieser Struktur natürlich heraus:

- Der **Healthpoint selbst** bleibt stabil.
- Eine User-Präzisierung **erweitert nicht den Healthpoint**, sondern
  **verfeinert die Predicates** im Bundle.
- Alle Wartepunkte werden mit dem neuen Predicate-Bundle nochmal geprüft.
- Wer durchfällt, kollabiert ein anderes Gate — ohne dass der Workflow von vorn beginnt.

Das ist sparsam: die Investition in den Hauptpfad bleibt erhalten, nur die
Konfiguration der Bewertung wird justiert.

### Verwandte Konzepte zur Verortung

- **Continuation** (Scheme, Functional Programming) — eingefrorener Berechnungspunkt
  mit mehreren möglichen Fortsetzungen
- **Checkpoint mit offenem Outcome** (Temporal, Cadence, Workflow-Engines) —
  persistierter Zustand, nicht commited
- **Two-Phase Commit** (Datenbanken) — Vorbereitungs-Phase getrennt von finaler
  Bestätigung; hier auf Reasoning übertragen

---

## 5. Verschiebungen

Was sich gegenüber `inkonsistence.md` substanziell verschoben hat:

| Aspekt | Vorher (inkonsistence.md) | Jetzt (nach Klärung) |
|--------|---------------------------|---------------------|
| Healthpoint-Prüfung | `NotImplementedError`, vermutlich LLM-Call | Kompiliertes Predicate-Bundle, gestaffelt nach Kosten |
| Gate-Natur | "Alternativer Pfad" | Fundamentale Logik-Primitive aus einer Algebra |
| Mid-Workflow-Präzisierung | Offene Frage | Verfeinerung der Predicates, Wartepunkte werden neu geprüft |
| Master-Check-Rücksprung | Offene Frage | Kein Rücksprung nötig — Wartepunkte sind kippbar |
| Energie-Argument | Postuliert, ungeprüft | Hängt empirisch an Skizze-Kosten vs. voller Generierung |

---

## 6. Offen

Was nach diesen Klärungen noch wirklich offen ist:

### Zur Skizze-Erzeugung

- Wie billig können Gate-Skizzen gehalten werden, damit der Energie-Vorteil bleibt?
- Können Skizzen aus Nebenprodukten der Hauptgenerierung gewonnen werden
  (Log-Probs, Attention-Divergenz)? Dann wären sie quasi gratis.

### Zur Gate-Algebra

- Welche Primitive gehören wirklich rein? Welche sind redundant?
- Sind Gates komponierbar? Lässt sich ein Gate aus zwei kleineren bauen?

### Zur Predicate-Compilation

- Wer compiliert den Healthpoint? Mensch? LLM? Hybrid?
- Wie wird ein "Predicate-Bundle" geprüft auf Vollständigkeit
  (deckt es alle Aspekte des Healthpoints ab)?

### Zur empirischen Validierung

- Auf welchem Mini-Problem lässt sich der Token-Gewinn messen?
- Bei welchem Skizze/Voll-Verhältnis dreht der Vorteil ins Negative?

---

## 7. Glossar

Begriffe, die in den Klärungen aufgetaucht sind und die du für Anschluss-Gespräche
gebrauchen kannst:

### State Machine

Ein System mit endlich vielen klar benannten **Zuständen** und definierten
**Übergängen** zwischen ihnen. Zu jedem Zeitpunkt ist das System in genau einem
Zustand. Übergänge werden durch Ereignisse oder Bedingungen ausgelöst.

In deinem Modell: jede Phase + ihr Wartepunkt bilden zusammen eine State Machine
mit den Zuständen `Hauptpfad-läuft → Hauptpfad-fertig → Gate-getriggert →
Gate-kollabiert → Wartepunkt → bestätigt → execute`.

### Transition System

Eine allgemeinere Form der State Machine, formal: ein Tripel `(S, →, S₀)` mit
einer Zustandsmenge `S`, einer Übergangs-Relation `→` (welcher Zustand kann zu
welchem werden) und einem Startzustand `S₀`. Transition Systems sind die Basis
für formale Verifikation und Model Checking.

In deinem Modell: der ganze Workflow ist ein Transition System.
Die Übergangs-Relation wird durch das Predicate-Bundle bestimmt — was zählt
als gültiger Übergang ist, was die Predicates akzeptieren.

### Reachability Graph

Der Graph aller Zustände, die von einem Startzustand aus durch erlaubte
Übergänge erreicht werden können. Aus einer State Machine oder einem
Transition System konstruierbar.

In deinem Modell: der Reachability Graph zeigt dir alle möglichen
Workflow-Verläufe — welche Gates können in welcher Reihenfolge kollabieren,
welche Wartepunkte können erreicht werden. Wenn der Reachability Graph endlich
und überschaubar ist, kannst du Invarianten beweisen — etwa: "es gibt keinen
Pfad, der zum Execute führt ohne finale Bestätigung". Das ist mit Werkzeugen
wie TLA+ oder Spin tatsächlich machbar.

---

## Schluss

Drei Klärungen haben aus drei offenen Fragen drei greifbare Konzepte gemacht:

- **Predicate-Bundle** statt undefiniertem `matches()`
- **Gate-Algebra** statt loser Alternativ-Listen
- **Wartepunkte** statt Master-Check-Rücksprung

Das Modell ist runder geworden und hat die Worte gefunden, die ihm gefehlt haben.
Was bleibt, ist die empirische Frage: lohnt sich der ganze Apparat gegenüber
naivem Regenerieren? Die Antwort liegt nicht in mehr Architektur, sondern in
einem kleinen, falsifizierbaren Test an einem echten Problem.
