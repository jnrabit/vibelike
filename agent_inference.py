#!/usr/bin/env python3
"""
P0.2: Agent Inference — qwen3:8b wählt Actions statt Heuristik.

Das Modell sieht: Query + verfügbare Tools + letzte Steps (Kontext).
Und entscheidet: welches Tool sollte ich jetzt aufrufen?

Architektur:
- Prompt: Query + Tools-Liste + recent Steps als Kontext
- Parsing: Modell-Output → (action_name, params)
- Fallback: bei Parse-Fehler oder Müll-Output → Heuristik
"""

import json
import sys
from typing import Optional, Tuple, Dict, Any
from pathlib import Path

ROOT = Path(__file__).parent


class ModelCoder:
    """Wrapper um qwen3:8b via Ollama (lokal)."""

    def __init__(self, model: str = "qwen3:8b"):
        self.model = model
        self.client = None
        self._init_ollama()

    def _init_ollama(self):
        """Initialisiere Ollama-Client (mit Verfügbarkeitsprüfung)."""
        try:
            import ollama
            # Test: Ollama-Server erreichbar?
            try:
                # Schneller Check: rufe list() auf (dauert Millisekunden wenn Server läuft)
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(("localhost", 11434))
                sock.close()
                if result == 0:
                    self.client = ollama
                    print(f"[OK] ModelCoder: Ollama-Server erreichbar (model={self.model})")
                else:
                    print(f"[WARN] ModelCoder: Ollama-Server nicht erreichbar (localhost:11434)")
                    self.client = None
            except Exception as e:
                print(f"[WARN] ModelCoder: Ollama-Check fehlgeschlagen: {e}")
                self.client = None
        except ImportError:
            print(f"[WARN] ModelCoder: ollama-Paket nicht installiert")
            self.client = None

    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 200) -> str:
        """Generiere Text via qwen."""
        if self.client is None:
            return ""
        try:
            response = self.client.generate(
                model=self.model,
                prompt=prompt,
                stream=False,
                think=False,  # qwen3:8b Extended Thinking ausschalten → response-Feld gefüllt
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens,
                }
            )
            # GenerateResponse ist ein Objekt, kein Dict → .response Attribut
            text = getattr(response, "response", None) or ""
            return text.strip()
        except Exception as e:
            print(f"[WARN] ModelCoder.generate() fehlgeschlagen: {e}")
            return ""


class ClaudeCoder:
    """Wrapper um Claude API (Anthropic)."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001"):
        self.model = model
        self.client = None
        self._init_claude()

    def _init_claude(self):
        """Initialisiere Claude-Client."""
        try:
            from anthropic import Anthropic
            import os
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            if api_key:
                self.client = Anthropic(api_key=api_key)
                print(f"[OK] ClaudeCoder: Claude API verfügbar (model={self.model})")
            else:
                print(f"[WARN] ClaudeCoder: ANTHROPIC_API_KEY nicht gesetzt")
                self.client = None
        except Exception as e:
            print(f"[WARN] ClaudeCoder: Initialisierung fehlgeschlagen: {e}")
            self.client = None

    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 600) -> str:
        """Generiere Text via Claude API."""
        if self.client is None:
            return ""
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()
        except Exception as e:
            print(f"[WARN] ClaudeCoder.generate() fehlgeschlagen: {e}")
            return ""


class GeminiModelCoder:
    """Wrapper um Gemini API (cloud fallback)."""

    def __init__(self, model: str = "gemini-2.5-flash"):
        self.model = model
        self.client = None
        self._init_gemini()

    def _init_gemini(self):
        """Initialisiere Gemini-Client via BackendRegistry."""
        try:
            from agent_backends import get_registry
            registry = get_registry()
            self.client = registry.get_gemini_client()
            if self.client:
                print(f"[OK] GeminiModelCoder: Gemini API verfügbar (model={self.model})")
            else:
                print(f"[WARN] GeminiModelCoder: Gemini API nicht verfügbar")
        except Exception as e:
            print(f"[WARN] GeminiModelCoder: Initialisierung fehlgeschlagen: {e}")
            self.client = None

    def generate(self, prompt: str, temperature: float = 0.3, max_tokens: int = 600) -> str:
        """Generiere Text via Gemini API."""
        if self.client is None:
            return ""
        try:
            from agent_backends import get_registry
            registry = get_registry()
            return registry.generate_with_gemini(prompt, temperature, max_tokens)
        except Exception as e:
            print(f"[WARN] GeminiModelCoder.generate() fehlgeschlagen: {e}")
            return ""


class ModelCoderFactory:
    """Factory für ModelCoder-Instanzen."""

    _cache = {}

    @classmethod
    def get(cls, model_name: str):
        """Hole oder erstelle den richtigen Coder für ein Modell."""
        if model_name in cls._cache:
            return cls._cache[model_name]

        coder = None
        if "qwen" in model_name.lower() or "2.5-coder" in model_name.lower():
            coder = ModelCoder(model=model_name)
        elif "claude" in model_name.lower() or "haiku" in model_name.lower():
            coder = ClaudeCoder(model=model_name)
        elif "gemini" in model_name.lower():
            coder = GeminiModelCoder(model=model_name)
        else:
            # Default zu Qwen
            coder = ModelCoder(model=model_name)

        cls._cache[model_name] = coder
        return coder


class ActionDecider:
    """Wähle die nächste Action via LLM (Cloud → Lokal Fallback)."""

    def __init__(self, model: str = "qwen3:8b"):
        self.local_coder = ModelCoder(model)
        self.gemini_coder = GeminiModelCoder()
        from agent_backends import get_registry
        self.registry = get_registry()

    def _get_best_backend_for_actions(self):
        """Bestimme bestes Backend für Action-Inference (Cloud → Lokal)."""
        backend = self.registry.get_for_action_inference()
        if backend.name == "qwen3:8b (Ollama lokal)":
            return self.local_coder
        elif "Gemini" in backend.name:
            return self.gemini_coder
        return self.local_coder

    def decide(
        self,
        query: str,
        available_tools: list[str],
        recent_steps: list[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """Entscheide Action + Params via Modell-Inferencing (mit Fallback-Kette).

        Rückgabe: (action_name, params) oder (None, {}) bei Fehler/Heuristik-Fallback.
        """
        recent_steps = recent_steps or []

        # Prompt bauen
        prompt = self._build_prompt(query, available_tools, recent_steps)

        # Try backends in priority order: Cloud → Lokal
        for coder in [self.gemini_coder, self.local_coder]:
            if coder.client is None:
                continue
            output = coder.generate(prompt, temperature=0.2, max_tokens=300)
            if output:
                action, params = self._parse_output(output, available_tools)
                if action is not None:
                    return action, params

        # Fallback: Heuristik (wenn alle Modelle Müll liefern)
        return self._heuristic_action(query, available_tools)

    def _build_prompt(
        self,
        query: str,
        available_tools: list[str],
        recent_steps: list[Dict[str, Any]],
    ) -> str:
        """Baue den Prompt für die Action-Wahl."""
        tools_str = "\n".join(f"  - {t}" for t in available_tools)

        recent_context = ""
        if recent_steps:
            recent_context = "LETZTE STEPS (Kontext):\n"
            for s in recent_steps[-3:]:  # Letzte 3
                action = s.get("action", "?")
                result = s.get("result", "")[:100]
                recent_context += f"  - {action}: {result}\n"

        prompt = f"""Du bist ein Agent, der entscheiden muss, welches Tool zu verwenden ist.

QUERY (was der Nutzer fragt):
{query}

VERFÜGBARE TOOLS:
{tools_str}
  - done: Beantworte die Frage direkt — nur wenn du genug Infos aus den letzten Steps hast

{recent_context}

AUFGABE:
Wähle das BESTE Tool für die Query. Wenn genug Informationen vorhanden sind → wähle 'done'.
Antworte im JSON-Format (nur JSON, keine anderen Worte):
{{
  "action": "<tool-name oder done>",
  "reasoning": "<kurz warum>",
  "params": {{"<param-name>": "<wert>"}}
}}

Für 'done': params muss 'answer' enthalten:
{{"action": "done", "reasoning": "genug Infos", "params": {{"answer": "Die Antwort ist..."}}}}

ANTWORTE NUR MIT JSON:"""

        return prompt

    def _parse_output(self, output: str, available_tools: list[str]) -> Tuple[Optional[str], Dict[str, Any]]:
        """Parse Modell-Output (JSON) → (action, params)."""
        try:
            # Versuche JSON zu extrahieren (könnte im Text eingebettet sein)
            start = output.find("{")
            end = output.rfind("}") + 1
            if start == -1 or end == 0:
                return None, {}

            json_str = output[start:end]
            data = json.loads(json_str)

            action = data.get("action", "").strip()
            if action not in available_tools:
                return None, {}

            params = data.get("params", {})
            return action, params
        except (json.JSONDecodeError, ValueError):
            return None, {}

    def _heuristic_action(self, query: str, available_tools: list[str]) -> Tuple[str, Dict[str, Any]]:
        """Fallback-Heuristik wenn Modell-Output Müll ist."""
        # Einfache Regeln basierend auf Keywords
        q_lower = query.lower()
        if "search" in q_lower or "find" in q_lower or "look" in q_lower:
            return ("search_vault", {"query": query})
        elif "read" in q_lower or "file" in q_lower or "show" in q_lower:
            return ("read_file", {"path": "terminal.py"})
        elif "verify" in q_lower or "check" in q_lower or "syntax" in q_lower:
            return ("verify", {"statement": query, "method": "syntax"})
        elif "ossifikat" in q_lower or "fact" in q_lower:
            return ("query_ossifikat", {"query": query})
        else:
            # Default
            return ("query_ossifikat", {"query": query})


# ═══ Test / Demo ═══

if __name__ == "__main__":
    print("═══ P0.2: Model-Based Action Decision ═══\n")

    decider = ActionDecider(model="qwen3:8b")
    available = ["search_vault", "read_file", "run_sandboxed", "query_ossifikat", "verify"]

    test_queries = [
        "Suche nach Chaos-Retrieval Code",
        "Lies terminal.py",
        "Verifiziere die agent_loop.py Syntax",
        "Was sind confirmte Fakten?",
        "Führe einen Python-Befehl aus",
    ]

    for query in test_queries:
        print(f"[QUERY] {query}")
        action, params = decider.decide(query, available)
        print(f"  → Action: {action}")
        print(f"  → Params: {params}\n")
