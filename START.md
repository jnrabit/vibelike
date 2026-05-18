# Code-Vault Terminal - Start-Anleitung

## Struktur

```
vibelike/
├── data/
│   ├── code_archive.monolith      # Verschlüsselter Code-Vault
│   ├── code_embedding_cache.pkl    # Vektor-Cache (384D)
│   └── code_centroid.npy           # Centroid für Routing
├── framework/
│   └── quelibrium/
│       ├── core/
│       │   ├── libquelibrium.so   # C++ Engine (8D-Chaos + Cortex)
│       │   ├── paths.py           # Pfad-Definitionen
│       │   ├── protocol.py        # Hardware-Protokoll + Vault-Lader
│       │   └── vault.py           # Verschlüsselter Datenspeicher
│       └── intelligence/
│           ├── resonance.py        # Resonanzfeld (Ko-Aktivierungsmatrix)
│           └── retrieval.py        # Chaos-Retrieval
└── terminal.py                    # CLI-Terminal
```

## Voraussetzungen

1. **Ollama** mit qwen2.5-coder:
   ```bash
   ollama serve
   ollama pull qwen2.5-coder:latest
   ```

2. **Python-Pakete:**
   ```bash
   pip install sentence-transformers numpy requests
   ```

## Start

```bash
cd /home/jnrabit/vibelike
python terminal.py
```

## Befehle im Terminal

| Befehl | Beschreibung |
|--------|--------------|
| `q` | Beenden |
| `l` | Logs anzeigen (letzte 10) |
| `s` | Hardware-State anzeigen |
| `c` | Bildschirm löschen |
| `<query>` | Suche im Code-Vault und generiere mit qwen2.5-coder |

## Features

- **Code-Vault Retrieval:** C++-beschleunigte Suche mit 8D-Lorenz-Attraktor
- **Hardware-State Logging:** Lorenz-Koordinaten, Entropie, Temperatur, Cortex-Bias
- **Log-Triplets:** JSON-Lines in `logs/triplets.jsonl` mit:
  - Query + Query-Hash
  - Context (Dokument-IDs, Distanzen, Hashes, Längen)
  - Response + Response-Hash
- **Hardware-State Logs:** Separate Einträge für:
  - Lorenz-Koordinaten (x1, y1, z1, w1, x2, y2)
  - Thermodynamik (Entropie, Temperatur, Cortex-Bias)
  - Parameter (rho, sigma, beta, reason, cycle)

## Dateien

- **Daten:** Aus `/home/jnrabit/collect/data/` kopiert
- **Framework:** Vereinfacht und angepasst für Standalone-Betrieb
- **C++ Engine:** Original aus Collect, funktioniert mit Code-Vault
- **Terminal:** Minimales CLI ohne Redis/Agenten-Logik

## Anpassungen am Framework

1. **paths.py:** 
   - ROOT = `/home/jnrabit/vibelike`
   - Nur Code-Vault Pfade (kein Monolith)
   - LIB_FILE verweist auf lokale libquelibrium.so

2. **protocol.py:**
   - Funktioniert mit C++ Engine (falls verfügbar)
   - Fallback auf Shadow-Mode
   - Code-Vault spezifische Defaults

3. **resonance.py:**
   - FIELD_FILE deaktiviert (wird nicht für Code-Vault benötigt)

## Log-Format

### Triplet-Log
```json
{
  "timestamp": 1716050000.123,
  "type": "triplet",
  "query": "Beispielanfrage",
  "query_hash": 123456789,
  "context": [
    {
      "id": "doc-123",
      "distance": 12.5,
      "source": "code-vault",
      "content_hash": 987654321,
      "content_len": 256
    }
  ],
  "context_count": 5,
  "response": "Generierte Antwort...",
  "response_len": 512,
  "response_hash": 555555555
}
```

### Hardware-State-Log
```json
{
  "timestamp": 1716050000.123,
  "type": "hardware_state",
  "query": "Beispielanfrage",
  "label": "search_start",
  "lorenz": {
    "x1": 0.12, "y1": -0.34, "z1": 0.56, "w1": 0.78,
    "x2": 0.23, "y2": -0.45
  },
  "thermodynamics": {
    "entropy": 3.14,
    "temperature": 45.0,
    "cortex_bias": 0.5
  },
  "params": {
    "rho": 28.0, "sigma": 10.0, "beta": 2.666,
    "reason": 0.5, "cycle": 123
  }
}
```

## Nächste Schritte (für Thermodynamik-Integration)

1. ResonanceField und ChaosRetrieval aus retrieval.py nutzen
2. Hardware-State-Logs mit Thermodynamik-Modellen korrelieren
3. Binäre Repräsentation der Logs für effizientere Speicherung
4. Echtzeit-Visualisierung der Lorenz-Attraktoren
