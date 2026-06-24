#!/usr/bin/env python3
"""
query_api.py — Query-Engine mit echten Models (ohne terminal.py pre-load Overhead).
Läuft auf :8888, Chaosserver proxied hierhin.
"""

import os
import sys
import json
import time
import asyncio
import requests
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

ROOT = Path(__file__).resolve().parent

# Minimale QwenCoder Implementation (ohne imports von terminal.py)
class QwenCoder:
    def __init__(self, model: str = "qwen2.5-coder:latest"):
        self.model = model
        self.session = requests.Session()
        self.ollama_url = "http://localhost:11434/api/generate"

    def generate(self, prompt: str, system: str = None, temperature: float = 0.7) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "30m",
            "options": {"temperature": temperature, "top_p": 0.9},
        }
        if system:
            payload["system"] = system

        try:
            response = self.session.post(self.ollama_url, json=payload, timeout=120)
            if response.status_code == 200:
                return response.json().get("response", "")
            return f"[Ollama Error {response.status_code}]"
        except Exception as e:
            return f"[Error: {str(e)}]"


# Claude über API
class ClaudeCoder:
    def __init__(self, model: str = None):
        self.model = model or "claude-opus-4-8"
        self.usable = False
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
                self.usable = True
            except:
                pass

    def generate(self, prompt: str, system: str = None, temperature: float = 0.7) -> str:
        if not self.usable:
            return "[Claude API nicht konfiguriert]"
        try:
            msg = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                system=system or "Du bist ein hilfreicher Assistant.",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )
            return msg.content[0].text
        except Exception as e:
            return f"[Claude Error: {str(e)}]"


# Gemini über API
class GeminiCoder:
    def __init__(self, model: str = None):
        self.model = model or "gemini-2.5-flash"
        self.usable = False
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
                self.client = genai.GenerativeModel(self.model)
                self.usable = True
            except:
                pass

    def generate(self, prompt: str, system: str = None, temperature: float = 0.7) -> str:
        if not self.usable:
            return "[Gemini API nicht konfiguriert]"
        try:
            response = self.client.generate_content(
                prompt,
                generation_config={"temperature": temperature, "max_output_tokens": 2048},
            )
            return response.text
        except Exception as e:
            return f"[Gemini Error: {str(e)}]"

app = FastAPI(title="Query Engine API")

# Thread-Pool für parallele Model-Calls
executor = ThreadPoolExecutor(max_workers=3)

class QueryRequest(BaseModel):
    query: str
    models: list[str] = ["qwen"]
    priority: int = 5
    timeout_sec: int = 30


def run_coder(coder_class, query: str, model: str = None) -> dict:
    """Rufe einen Coder auf und returne {winner, score, answer}."""
    try:
        if coder_class == QwenCoder:
            coder = QwenCoder(model or "qwen2.5-coder:latest")
        elif coder_class == ClaudeCoder:
            coder = ClaudeCoder(model or "claude-opus-4-8")
            if not coder.usable:
                return {"error": "Claude API nicht konfiguriert"}
        elif coder_class == GeminiCoder and GeminiCoder:
            coder = GeminiCoder(model or "gemini-2.5-flash")
            if not coder.usable:
                return {"error": "Gemini API nicht konfiguriert"}
        else:
            return {"error": f"Model {coder_class} nicht unterstützt"}

        system = "Du bist ein hilfreicher Code-Assistant. Antworte prägnant und fachlich korrekt."
        answer = coder.generate(prompt=query, system=system, temperature=0.7)

        return {
            "model": coder_class.__name__.replace("Coder", "").lower(),
            "answer": answer,
            "score": 0.9 if not answer.startswith("[Error") else 0.3,
        }
    except Exception as e:
        return {"error": str(e), "model": coder_class.__name__}


@app.post("/api/query")
async def submit_query(req: QueryRequest):
    """Echte Consensus-Query mit parallel Model-Calls."""
    start = time.time()
    request_id = str(hash(req.query) % 10000)

    # Map model names to Coder classes
    model_map = {
        "qwen": QwenCoder,
        "claude": ClaudeCoder,
        "gemini": GeminiCoder,
        "mistral": ClaudeCoder,  # Fallback auf Claude
    }

    # Parallel Calls
    tasks = []
    for model_name in req.models:
        coder_class = model_map.get(model_name.lower())
        if coder_class:
            task = asyncio.to_thread(run_coder, coder_class, req.query, model_name)
            tasks.append(task)

    if not tasks:
        raise HTTPException(400, "Keine gültigen Models angegeben")

    # Warte auf alle Results (mit timeout)
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=req.timeout_sec
        )
    except asyncio.TimeoutError:
        raise HTTPException(504, f"Query timeout nach {req.timeout_sec}s")

    # Parse Results
    all_results = {}
    best_result = None
    best_score = -1

    for result in results:
        if isinstance(result, Exception):
            continue

        model = result.get("model", "unknown")
        if "error" in result:
            all_results[model] = f"[Error: {result['error']}]"
        else:
            answer = result.get("answer", "")
            score = result.get("score", 0.5)
            all_results[model] = answer

            if score > best_score and not answer.startswith("[Error"):
                best_score = score
                best_result = (model, answer, score)

    if not best_result:
        raise HTTPException(503, "Alle Models fehlgeschlagen")

    winner, winner_answer, winner_score = best_result
    latency_ms = int((time.time() - start) * 1000)

    return {
        "request_id": request_id,
        "winner": winner,
        "winner_score": winner_score,
        "winner_answer": winner_answer,
        "all_results": all_results,
        "latency_ms": latency_ms,
        "missing_gaps": {},
    }


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "query-engine"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8888, log_level="info")
