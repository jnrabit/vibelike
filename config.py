"""
Configuration management for Vibelike.

Single source of truth for all settings (paths, models, env vars).
Pydantic v2 Settings for validation and type safety.

Usage:
    from vibelike.config import settings
    settings.analysis_model  # "claude-haiku-4-5-20251001"
    settings.queue_db        # Path object
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


class VibelikeSettings(BaseSettings):
    """Central configuration for Vibelike."""
    
    # ─────────────────────────────────────────────────────────────────
    # ROOT & PATHS
    # ─────────────────────────────────────────────────────────────────
    
    root_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    
    # Data & Database paths
    queue_db: Path = Field(
        default_factory=lambda: Path(__file__).parent / "logs" / "queue.db"
    )
    log_db: Path = Field(
        default_factory=lambda: Path(__file__).parent / "logs" / "execution.db"
    )
    ossifikat_db: Path = Field(
        default_factory=lambda: Path(__file__).parent / "ossifikat" / "data" / "ossifikat.db"
    )
    
    # Sandbox & tools
    sandbox_base: Path = Field(
        default_factory=lambda: Path(__file__).parent / "sandbox"
    )
    # Sandbox-Prozess-Identität (von der Pydantic-Migration verloren → wieder ergänzt,
    # sandbox/manager.py + reqqueue/worker.py importieren SANDBOX_USER_UID/GID).
    sandbox_user_uid: int = Field(default=10000)
    sandbox_user_gid: int = Field(default=10000)
    tools_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent / "tools"
    )
    tools_cache_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent / "cache"
    )
    results_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent / "logs" / "results"
    )
    
    # Logging paths
    log_file: Path = Field(
        default_factory=lambda: Path(__file__).parent / "logs" / "triplets.jsonl"
    )
    workflow_log: Path = Field(
        default_factory=lambda: Path(__file__).parent / "logs" / "workflows.jsonl"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # LLM MODELS & BACKENDS
    # ─────────────────────────────────────────────────────────────────
    
    # Coder model (code generation, local Ollama)
    coder_model: str = Field(
        default="deepseek-coder:6.7b-instruct",
        description="Local Ollama model for code generation"
    )
    
    # Validator model (parallel critic, smaller)
    validator_model: str = Field(
        default="deepseek-coder:6.7b-instruct",
        description="Small model for parallel validation"
    )
    
    # Analysis model (reasoning, planning — use frontier models)
    analysis_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Reasoning model for briefing/planning"
    )
    
    # Code generation backend
    codegen_backend: Literal["claude", "gemini", "mistral", "council", "ollama"] = Field(
        default="claude",
        description="LLM backend for code generation"
    )
    
    # Specific code-gen model (API-based)
    codegen_model: str = Field(
        default="claude-sonnet-4-6",
        description="API-based model for code generation"
    )
    
    # Council mode (multi-model consensus)
    council_model: str = Field(
        default="claude-haiku-4-5-20251001",
        description="Council mode reasoning model"
    )
    synth_model: str = Field(
        default="claude-sonnet-4-6",
        description="Council mode synthesis model"
    )
    
    # Gemini integration
    gemini_council_model: str = Field(
        default="gemini-2.5-flash",
        description="Gemini council model"
    )
    gemini_synth_model: str = Field(
        default="gemini-2.5-pro",
        description="Gemini synthesis model"
    )
    
    # Mistral integration
    mistral_council_model: str = Field(
        default="mistral-large-latest",
        description="Mistral council model"
    )
    mistral_synth_model: str = Field(
        default="mistral-large-latest",
        description="Mistral synthesis model"
    )
    
    # Knowledge answer model (Q&A over vaults) — GENERALIST, nicht der Coder!
    # Wissensfragen (Mathe/Physik/Fakten) brauchen Synthese, kein Code-Modell.
    # deepseek-coder ignoriert den Vault-Kontext + gibt Generik-Antworten.
    knowledge_answer_model: str = Field(
        default="qwen3:8b",
        description="Generalist-Model für Wissens-Q&A über die Vaults (NICHT der Coder)"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # VAULTS & RETRIEVAL
    # ─────────────────────────────────────────────────────────────────
    
    code_vault_file: Path = Field(
        default_factory=lambda: Path(__file__).parent / "data" / "code_archive.monolith",
        description="Code vault path"
    )
    code_cache_file: Path = Field(
        default_factory=lambda: Path(__file__).parent / "data" / "code_embedding_cache.pkl",
        description="Code vault embedding cache"
    )
    
    # Knowledge vault (large corpus)
    # Default: Try to find it in /home/jnrabit/collect/ (common location)
    # Can override with VIBELIKE_KNOWLEDGE_VAULT env var
    knowledge_vault_file: Optional[Path] = Field(
        default=None,  # Will be set in model_post_init if env var or fallback path exists
        description="Optional knowledge vault (260K docs)"
    )
    knowledge_cache_file: Optional[Path] = Field(
        default=None,  # Will be set in model_post_init if env var or fallback path exists
        description="Knowledge vault embedding cache"
    )
    
    # Dual vault search (default enabled)
    dual_vault: bool = Field(
        default=True,
        description="Search both code + knowledge vault"
    )
    
    # Query decomposition (for multi-aspect queries)
    query_decompose: bool = Field(
        default=True,
        description="Decompose complex queries into sub-queries"
    )
    
    # Ground on facts from ossifikat
    ground_on_facts: bool = Field(
        default=True,
        description="Use confirmed facts from ossifikat for grounding"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # ARCHITECTURE & MODES
    # ─────────────────────────────────────────────────────────────────
    
    # Architecture mode: "default" (Claude), "mitte" (Claude plans, deepseek codes)
    arch: Literal["default", "mitte"] = Field(
        default="default",
        description="Workflow architecture"
    )
    
    # Deepseek-Max: all phases local (no API)
    deepseek_max: bool = Field(
        default=False,
        description="Use deepseek:6.7b for all phases (offline mode)"
    )
    
    # Power user mode (enables old prefixes: briefing:, ??, ??h, etc.)
    power_user: bool = Field(
        default=False,
        description="Enable power-user mode"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # WORKER & HEALTH
    # ─────────────────────────────────────────────────────────────────
    
    health_check_file: Path = Field(
        default="/tmp/vibelike_queue_health",
        description="Health check sentinel file"
    )
    health_check_max_age: int = Field(
        default=30,
        description="Max age (seconds) for health check"
    )
    poll_interval: float = Field(
        default=5.0,
        description="Worker poll interval (seconds)"
    )
    health_check_interval: int = Field(
        default=30,
        description="Health check interval (seconds)"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # SANDBOX
    # ─────────────────────────────────────────────────────────────────
    
    sandbox_uid: int = Field(
        default=10000,
        description="Sandbox user UID"
    )
    sandbox_gid: int = Field(
        default=10000,
        description="Sandbox user GID"
    )
    sandbox_timeout: int = Field(
        default=300,
        description="Sandbox execution timeout (seconds)"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # OSSIFIKAT & FEATURES
    # ─────────────────────────────────────────────────────────────────
    
    ossifikat_enabled: bool = Field(
        default=True,
        description="Enable ossifikat knowledge graph"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # OLLAMA & EXTERNAL SERVICES
    # ─────────────────────────────────────────────────────────────────
    
    ollama_url: str = Field(
        default="http://localhost:11434/api/generate",
        description="Ollama API endpoint"
    )
    
    # Optional: Retrieval daemon URL
    retrieval_url: Optional[str] = Field(
        default=None,
        description="Optional external retrieval service"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # EMBEDDING & RETRIEVAL
    # ─────────────────────────────────────────────────────────────────
    
    embedding_device: Literal["cuda", "cpu"] = Field(
        default="cuda",
        description="Device for embeddings"
    )
    
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        description="Embedding model"
    )
    
    embedding_dim: int = Field(
        default=384,
        description="Embedding dimension"
    )
    
    # ─────────────────────────────────────────────────────────────────
    # VALIDATION & LOGGING
    # ─────────────────────────────────────────────────────────────────
    
    @field_validator('knowledge_answer_model', mode='before')
    @classmethod
    def fallback_knowledge_answer_model(cls, v, info):
        """Leeres Feld → Generalist (qwen3:8b), NICHT der Coder. Ein Code-Modell
        beantwortet Wissensfragen schlecht (ignoriert Vault-Kontext)."""
        if not v:
            return "qwen3:8b"
        return v
    
    def model_post_init(self, __context):
        """Create necessary directories and resolve knowledge vault paths."""
        # Create necessary directories
        paths = [
            self.queue_db.parent,
            self.log_db.parent,
            self.ossifikat_db.parent,
            self.sandbox_base,
            self.tools_dir,
            self.results_dir,
        ]
        for path in paths:
            path.mkdir(parents=True, exist_ok=True)
        
        # Resolve knowledge vault paths
        # Priority: env var → fallback path (if exists)
        knowledge_fallback = Path("/home/jnrabit/collect/data/monolith_archive.monolith")
        cache_fallback = Path("/home/jnrabit/collect/data/monolith_embedding_cache.pkl")
        
        if self.knowledge_vault_file is None:
            env_vault = os.environ.get("VIBELIKE_KNOWLEDGE_VAULT")
            if env_vault:
                self.knowledge_vault_file = Path(env_vault)
            elif knowledge_fallback.exists():
                self.knowledge_vault_file = knowledge_fallback
        
        if self.knowledge_cache_file is None:
            env_cache = os.environ.get("VIBELIKE_KNOWLEDGE_CACHE")
            if env_cache:
                self.knowledge_cache_file = Path(env_cache)
            elif cache_fallback.exists():
                self.knowledge_cache_file = cache_fallback
    
    class Config:
        """Pydantic config."""
        env_file = ".env"
        env_file_encoding = "utf-8"
        env_prefix = "VIBELIKE_"
        case_sensitive = False


# Global settings instance
settings = VibelikeSettings()


def __getattr__(name: str):
    """Rückwärts-Kompat-Shim (PEP 562): alte Modul-Konstanten auf settings mappen.

    Vor der Pydantic-Migration exportierte config.py Konstanten wie TOOLS_DIR,
    QUEUE_DB, TOOLS_CACHE_DIR direkt. Mehrere Importer (tools/registry.py,
    reqqueue/manager.py, tools/cache.py) nutzen `from config import GROSSNAME`
    noch. Dieser Hook leitet GROSSNAME → settings.grossname um, statt jeden
    Aufrufer einzeln umzubauen. Neuer Code sollte `settings.feld` nutzen.
    """
    if name.isupper():
        field = name.lower()
        if hasattr(settings, field):
            return getattr(settings, field)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
