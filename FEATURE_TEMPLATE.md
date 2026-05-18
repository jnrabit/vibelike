# Feature Request Template

Kopiere diese Vorlage für neue Feature-Anfragen an Claude.

---

## Feature: [Feature Name]

### 🎯 Briefing
**Was soll gemacht werden?**

[1-2 Sätze Beschreibung der Aufgabe]

Beispiel:
```
"Füge einen GitHub-Harvester hinzu, der README-Files von den Top 50 
Python-Repositories sammelt und zum Code-Vault hinzufügt."
```

---

### 🔍 Kontext
**Warum brauchst du das? Wie passt es ins System?**

[Erklärung, warum das Feature wichtig ist und wie es zum Gesamtsystem passt]

Beispiel:
```
Das Vault hat derzeit 718 Dokumente. Um mehr Input-Variabilität 
zu haben und Best Practices aus echten GitHub-Projekten zu sammeln, 
brauchst wir eine GitHub-Quelle.
```

---

### 📋 Ziele
**Akzeptanzkriterien**

- [ ] Feature ist implementiert
- [ ] Tests bestehen 100%
- [ ] Git-Commit ist sauber
- [ ] Code folgt dem bestehenden Style
- [ ] Dokumentation ist aktualisiert

---

### 💡 Beispiel
**Wie soll es verwendet werden?**

```python
# Beispiel aus Benutzerperspektive
python3.12 harvest_worker.py --full-mode --limit 200
# Should now include GitHub README harvesting

# Oder direkter:
scheduler.schedule_github_harvest(repos=50, priority=1)
```

---

### 📦 Abhängigkeiten
**Was wird benötigt?**

- [ ] Neue Python Libraries? (z.B. `requests`)
- [ ] Neue Konfigurationen?
- [ ] API Keys / Credentials?
- [ ] Datenbank-Schema Updates?

---

### 🔗 Verwandte Dateien
**Welche Dateien sind betroffen?** (Optional, Claude findet das raus)

- `harvest.py` - neue Harvester-Funktion
- `harvest_scheduler.py` - neue Schedule-Methode
- `tests/test_*.py` - neue Tests

---

### ⚠️ Edge Cases / Anforderungen
**Was könnte schiefgehen?**

- Rate Limits von GitHub API
- Große README-Files
- Private Repositories
- API Errors / Network Timeouts

---

### 📝 Notizen
[Weitere Anmerkungen oder Anforderungen]

---

## Status: BRIEFING → [Warte auf Plan]

**Nächste Schritte:**
1. Claude analysiert Projekt
2. Claude schlägt Plan vor
3. Du genehmigst oder fragst nach Änderungen
4. Execution beginnt
