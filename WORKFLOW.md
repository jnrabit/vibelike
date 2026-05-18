# Vibelike Feature Development Workflow

Ein strukturierter 5-Phasen-Prozess für neue Features und Verbesserungen.

## 📋 Die 5 Phasen

### Phase 1️⃣: BRIEFING
**Du beschreibst die Aufgabe**

Beispiel:
```
Aufgabe: "Füge einen GitHub-Harvester hinzu, der README-Files von beliebten Repos sammelt"
```

Claude wird:
- Bestehende Dateien analysieren
- Projektstruktur verstehen
- Abhängigkeiten prüfen

---

### Phase 2️⃣: PLANUNG
**Claude schlägt einen Plan vor**

Du siehst:
```
Betroffene Dateien:
  ├─ harvest.py (neue Funktion harvest_github_readme)
  ├─ harvest_scheduler.py (neue schedule_github_harvest Methode)
  ├─ harvest_worker.py (update --full-mode)
  └─ tests/test_github_harvest.py (neue Tests)

Tests:
  ├─ test_github_api_connection
  ├─ test_readme_parsing
  ├─ test_rate_limit_handling
  └─ test_integration

Dependencies:
  └─ requests library (für GitHub API)
```

**Du nickst ab:** "Looks good, go ahead" oder "Change X to Y first"

---

### Phase 3️⃣: EXECUTION
**Claude implementiert**

- Neue Code-Funktionen mit `edit_file()`
- Tests schreiben
- Integration in bestehende Systeme
- Keine bestehende Logik zerstören

**Status:** Work in progress...

---

### Phase 4️⃣: VERIFIKATION
**Automatische Tests im Hintergrund**

```bash
python3.12 run_tests.py

✓ GitHub Harvest Tests    3/3 passed
✓ Integration Tests       1/1 passed
✓ Queue Tests             1/1 passed
✓ ALL TESTS PASSED       18/18
```

Bei Fehlern: Claude behebt und testet erneut.

---

### Phase 5️⃣: COMMIT
**Automatischer Git-Commit**

```bash
git log --oneline
  a1b2c3d Add GitHub README harvester for Code-Vault
  
  - Collects README files from trending GitHub repos
  - Configurable API rate limits and caching
  - Integrates with existing harvest_scheduler
  - Adds 500+ documents per run to vault
  - Includes full test coverage
```

---

## 🎯 Template für eine Feature-Anfrage

Kopier-Paste für neue Features:

```markdown
## Feature: [Name]

### Briefing
[Kurze Beschreibung der Aufgabe, 1-2 Sätze]

### Ziele
- [ ] Ziel 1
- [ ] Ziel 2
- [ ] Ziel 3

### Kontext
[Warum brauchst du das? Wie passt es ins System?]

### Beispiel
[Wie soll es verwendet werden?]

---

**Status:** Briefing → [Warte auf Plan]
```

---

## 📊 Workflow für verschiedene Task-Typen

### Für neue HARVESTER-QUELLEN
1. **Briefing:** "Füge [Quelle] Harvester hinzu"
2. **Plan:** Neue harvest_*_worker Funktion
3. **Execute:** Implementierung + Tests
4. **Verify:** run_tests.py
5. **Commit:** Beschreib die neue Quelle

### Für FEATURES in existierenden Systemen
1. **Briefing:** "Verbessere [System] mit [Feature]"
2. **Plan:** Welche Dateien ändern sich
3. **Execute:** Edit + Integration
4. **Verify:** Tests für das Feature
5. **Commit:** Beschreib die Verbesserung

### Für BUGFIXES
1. **Briefing:** "Behebe Bug in [Komponente]: [Beschreibung]"
2. **Plan:** Root Cause + Fix-Strategie
3. **Execute:** Minimal change, maximal safety
4. **Verify:** Test für den Bug
5. **Commit:** Bug-Fix mit Ursache

---

## ✅ Checklist pro Phase

### Phase 1: Briefing ✅
- [ ] Aufgabe ist klar formuliert
- [ ] Kontext ist verständlich
- [ ] Akzeptanzkriterien sind definiert

### Phase 2: Planning ✅
- [ ] Plan wird vorgeschlagen
- [ ] Du genehmigst oder fragst nach Änderungen
- [ ] Dependencies sind geklärt

### Phase 3: Execution 🔄
- [ ] Code wird geschrieben
- [ ] Tests werden geschrieben
- [ ] Keine bestehende Logik wird kaputt gemacht
- [ ] Documentation wird aktualisiert

### Phase 4: Verification ✅
- [ ] Alle Tests bestehen (100%)
- [ ] Edge Cases sind getestet
- [ ] Integration funktioniert

### Phase 5: Commit ✅
- [ ] Git-Commit ist aussagekräftig
- [ ] Alle Änderungen sind committed
- [ ] Branch ist sauber

---

## 🚀 Starten mit dem Workflow

### Für eine neue Feature:
```
"Briefing: [Aufgabe beschreiben]"
```

### Für Planung genehmigen:
```
"Plan sieht gut aus, los geht's!"
```

### Wenn Phase fertig:
```
"Nächste Phase?"
```

---

## 📌 System Status für Workflows

Aktuell verfügbar:
- ✅ Harvest System (Wikipedia, RFCs, PEPs, Tools)
- ✅ Queue Management (enqueue, dequeue, fail, complete)
- ✅ Sandbox Execution (tool running, output collection)
- ✅ Test Framework (run_tests.py mit 18 Tests)
- ✅ Git Integration (commits, branches)

Können hinzugefügt werden:
- 🟡 Neue Harvest-Quellen (GitHub, Stack Overflow, Docs, etc.)
- 🟡 Neue Adapter (für ossifikat Integation)
- 🟡 Neue Tools (in tools/ Verzeichnis)
- 🟡 Monitoring & Analytics
