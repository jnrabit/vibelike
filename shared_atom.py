#!/usr/bin/env python3
"""
SharedAtom: Primitive Accumulator-Instanz mit festen Stacks.

Concept: Mehrere vordefinierte Stacks mit festen Größen.
Jeder Treffer = +1 auf dem Stack mit exponentieller zeitlicher Decay.
Hohe Stacks bleiben als Signal stehen → flüssige Einbindung in Entscheidungen.
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, List


@dataclass
class StackConfig:
    """Konfiguration eines Stacks."""
    name: str                    # z.B. "model:qwen:success"
    size: float                  # max Höhe (z.B. 5.0)
    decay_tau: float             # Decay time constant (Sekunden)
    weight: float = 1.0          # Gewichtung in Multi-Signal-Entscheidungen
    reset_behavior: str = "sticky"  # "sticky" (bleibt bei max) | "cycle" (normal)


# Vordefinierte Stacks — KONSTANTEN
STACK_CONFIGS: Dict[str, StackConfig] = {
    # Model-Success-Stacks (HYBRID: slow decay 20-30min)
    "model:qwen:success": StackConfig(
        name="model:qwen:success",
        size=5.0,
        decay_tau=1200,  # 20 Minuten
        weight=1.0,
        reset_behavior="sticky"
    ),
    "model:claude:success": StackConfig(
        name="model:claude:success",
        size=5.0,
        decay_tau=1200,  # 20 Minuten
        weight=1.0,
        reset_behavior="sticky"
    ),

    # Tool-Success-Stacks (HYBRID: fast decay 5-10min)
    "tool:search_vault:hits": StackConfig(
        name="tool:search_vault:hits",
        size=3.0,
        decay_tau=420,  # 7 Minuten
        weight=0.8,
        reset_behavior="cycle"
    ),
    "tool:query_ossifikat:hits": StackConfig(
        name="tool:query_ossifikat:hits",
        size=3.0,
        decay_tau=420,  # 7 Minuten
        weight=0.8,
        reset_behavior="cycle"
    ),

    # Query-Complexity (5min decay — schneller Trend)
    "query:complex:detected": StackConfig(
        name="query:complex:detected",
        size=4.0,
        decay_tau=300,  # 5 Minuten
        weight=0.7,
        reset_behavior="cycle"
    ),
    "query:simple:detected": StackConfig(
        name="query:simple:detected",
        size=3.0,
        decay_tau=300,  # 5 Minuten
        weight=0.5,
        reset_behavior="cycle"
    ),

    # Tool-Effectiveness (Rate-Tracking)
    "tool:effectiveness:high": StackConfig(
        name="tool:effectiveness:high",
        size=5.0,
        decay_tau=600,  # 10 Minuten
        weight=1.0,
        reset_behavior="sticky"
    ),
    "tool:effectiveness:low": StackConfig(
        name="tool:effectiveness:low",
        size=2.0,
        decay_tau=300,  # 5 Minuten
        weight=0.4,
        reset_behavior="cycle"
    ),

    # Fallback-Frequency (wie oft nötig?)
    "fallback:triggered": StackConfig(
        name="fallback:triggered",
        size=3.0,
        decay_tau=420,  # 7 Minuten
        weight=0.6,
        reset_behavior="cycle"
    ),

    # Result-Quality (Automatische oder User-Feedback)
    "result:quality:good": StackConfig(
        name="result:quality:good",
        size=5.0,
        decay_tau=900,  # 15 Minuten
        weight=1.1,
        reset_behavior="sticky"
    ),
    "result:quality:poor": StackConfig(
        name="result:quality:poor",
        size=2.0,
        decay_tau=300,  # 5 Minuten
        weight=0.5,
        reset_behavior="cycle"
    ),

    # Strategy-Stacks (20-30min decay)
    "strategy:parallel:works": StackConfig(
        name="strategy:parallel:works",
        size=4.0,
        decay_tau=1500,  # 25 Minuten
        weight=1.2,
        reset_behavior="sticky"
    ),
    "strategy:fallback:needed": StackConfig(
        name="strategy:fallback:needed",
        size=2.0,
        decay_tau=420,  # 7 Minuten
        weight=0.5,
        reset_behavior="cycle"
    ),
}


class SharedAtom:
    """Primitive Instanz mit festen Stacks + exponentieller Decay."""

    def __init__(self):
        """Initialisiere mit leeren Hit-Listen."""
        # self.stacks[stack_name] = {"hits": [timestamp, timestamp, ...]}
        self.stacks: Dict[str, Dict] = {
            stack_name: {"hits": []}
            for stack_name in STACK_CONFIGS.keys()
        }
        self.created_at = time.time()

    def push(self, stack_name: str) -> bool:
        """
        Treffer auf einen Stack hinzufügen (mit Timestamp für Decay).

        Returns: True wenn erfolgreich, False wenn Stack unbekannt.
        """
        if stack_name not in self.stacks:
            print(f"[WARN] SharedAtom.push(): Stack '{stack_name}' nicht definiert")
            return False

        now = time.time()
        self.stacks[stack_name]["hits"].append(now)

        # Optional: alte Hits entfernen (älter als 3x decay_tau)
        config = STACK_CONFIGS[stack_name]
        cutoff = now - (3 * config.decay_tau)
        self.stacks[stack_name]["hits"] = [
            h for h in self.stacks[stack_name]["hits"] if h > cutoff
        ]

        return True

    def get_height(self, stack_name: str) -> float:
        """
        Berechne aktuelle Stack-Höhe mit exponentiellem Decay.

        height = sum(exp(-(now - hit_time) / tau)) für alle hits
        """
        if stack_name not in self.stacks:
            return 0.0

        config = STACK_CONFIGS[stack_name]
        now = time.time()
        hits = self.stacks[stack_name]["hits"]

        if not hits:
            return 0.0

        # Exponentieller Decay: neuere Hits zählen mehr
        height = sum(
            math.exp(-(now - hit_time) / config.decay_tau)
            for hit_time in hits
        )

        return height

    def get_signal(self, stack_name: str) -> Optional[Dict]:
        """
        Aktuelle Stack-Höhe mit Metadaten.

        Returns: {
            "name": str,
            "height": float (0.0 - size),
            "is_full": bool,
            "weight": float,
            "normalized": float (0.0 - 1.0),
        } oder None wenn Stack unbekannt
        """
        if stack_name not in STACK_CONFIGS:
            return None

        config = STACK_CONFIGS[stack_name]
        height = self.get_height(stack_name)
        normalized = min(height / config.size, 1.0)  # Cap at 1.0

        return {
            "name": stack_name,
            "height": height,
            "size": config.size,
            "is_full": height >= config.size,
            "weight": config.weight,
            "normalized": normalized,  # 0.0 - 1.0
            "decay_tau": config.decay_tau,
            "reset_behavior": config.reset_behavior,
        }

    def get_all_signals(self) -> Dict[str, Dict]:
        """Alle Stacks + ihre aktuellen Signale."""
        return {
            stack_name: signal
            for stack_name in STACK_CONFIGS.keys()
            if (signal := self.get_signal(stack_name)) is not None
        }

    def stats(self) -> Dict:
        """Statistiken für Debugging."""
        signals = self.get_all_signals()
        return {
            "created_at": self.created_at,
            "session_duration": time.time() - self.created_at,
            "total_hits": sum(len(h["hits"]) for h in self.stacks.values()),
            "stacks": signals,
        }

    def reset(self, stack_name: Optional[str] = None):
        """Reset einen Stack oder alle."""
        if stack_name:
            if stack_name in self.stacks:
                self.stacks[stack_name]["hits"] = []
        else:
            for name in self.stacks:
                self.stacks[name]["hits"] = []

    def track_query_complexity(self, query: str):
        """Auto-detect Query-Komplexität und update Stacks."""
        # Einfache Heuristik: Länge, Keywords, Fragen
        is_complex = (
            len(query) > 100 or
            sum(1 for c in query if c in '?!;') > 1 or
            any(kw in query.lower() for kw in ["warum", "wie", "vergleich", "unterschied", "explain"])
        )
        if is_complex:
            self.push("query:complex:detected")
        else:
            self.push("query:simple:detected")

    def track_tool_effectiveness(self, success: bool, tool_name: str = None):
        """Track ob ein Tool erfolgreich war."""
        if success:
            self.push("tool:effectiveness:high")
            if tool_name:
                self.push(f"tool:{tool_name}:hits")
        else:
            self.push("tool:effectiveness:low")

    def track_result_quality(self, quality: str):
        """
        Track Result-Qualität.
        quality: "good" | "poor" | "neutral"
        """
        if quality == "good":
            self.push("result:quality:good")
        elif quality == "poor":
            self.push("result:quality:poor")

    def track_fallback_triggered(self):
        """Fallback-Strategie wurde nötig."""
        self.push("fallback:triggered")
        self.push("strategy:fallback:needed")


# Globale Instanz (Pro Session)
_instance: Optional[SharedAtom] = None


def get_shared_atom() -> SharedAtom:
    """Singleton für die Session."""
    global _instance
    if _instance is None:
        _instance = SharedAtom()
    return _instance


def reset_shared_atom():
    """Test-Helper: reset Singleton."""
    global _instance
    _instance = None


if __name__ == "__main__":
    # Quick test
    atom = SharedAtom()

    print("=" * 60)
    print("SharedAtom — Quick Test")
    print("=" * 60)

    # Simuliere ein paar Treffer
    atom.push("model:qwen:success")
    atom.push("model:qwen:success")
    atom.push("model:qwen:success")
    atom.push("tool:search_vault:hits")

    print("\nAktuelle Höhen:")
    for name, signal in atom.get_all_signals().items():
        print(f"  {name:30} → {signal['height']:.2f}/{signal['size']:.1f} (normalized: {signal['normalized']:.1%})")

    print("\nStats:")
    stats = atom.stats()
    print(f"  Session duration: {stats['session_duration']:.2f}s")
    print(f"  Total hits: {stats['total_hits']}")

    print("=" * 60 + "\n")
