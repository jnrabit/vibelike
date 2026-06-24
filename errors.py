"""
Structured error types for Vibelike.

Replaces string-based error returns like "[ERR] ..." with typed exceptions
that can be caught, logged, and handled programmatically.

Usage:
    try:
        vault.search(query)
    except VaultError as e:
        logger.error(f"Vault search failed: {e}", exc_info=e)
        return {"error": str(e), "error_type": e.__class__.__name__}
"""

from typing import Optional
from enum import Enum


class ErrorSeverity(str, Enum):
    """Error severity levels."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class VibelikeError(Exception):
    """Base exception for Vibelike."""
    
    severity: ErrorSeverity = ErrorSeverity.ERROR
    
    def __init__(
        self,
        message: str,
        severity: Optional[ErrorSeverity] = None,
        context: Optional[dict] = None,
    ):
        """
        Initialize error.
        
        Args:
            message: Error message
            severity: Error severity level
            context: Additional context dict (for debugging)
        """
        super().__init__(message)
        self.message = message
        if severity:
            self.severity = severity
        self.context = context or {}
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "severity": self.severity.value,
            "context": self.context,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Vault & Retrieval Errors
# ═══════════════════════════════════════════════════════════════════════════

class VaultError(VibelikeError):
    """Base error for vault operations."""
    severity = ErrorSeverity.ERROR


class VaultNotFoundError(VaultError):
    """Vault file not found."""
    pass


class VaultCorruptedError(VaultError):
    """Vault file is corrupted or cannot be loaded."""
    pass


class VaultEmptyError(VaultError):
    """Vault is empty (no documents)."""
    severity = ErrorSeverity.WARNING


class RetrievalError(VibelikeError):
    """Error during document retrieval."""
    pass


class QueryDecompositionError(RetrievalError):
    """Error decomposing multi-aspect query."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Model & LLM Errors
# ═══════════════════════════════════════════════════════════════════════════

class ModelError(VibelikeError):
    """Base error for model operations."""
    pass


class ModelNotAvailableError(ModelError):
    """Model or API is unavailable."""
    pass


class ModelTimeoutError(ModelError):
    """Model request timed out."""
    pass


class ModelQuotaExceededError(ModelError):
    """API quota exceeded (rate limiting, account limits)."""
    severity = ErrorSeverity.CRITICAL


class InvalidModelNameError(ModelError):
    """Model name is invalid or not recognized."""
    pass


class ModelInferenceError(ModelError):
    """Error during model inference."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Workflow & Agent Errors
# ═══════════════════════════════════════════════════════════════════════════

class WorkflowError(VibelikeError):
    """Base error for workflow operations."""
    pass


class WorkflowPhaseError(WorkflowError):
    """Error in a specific workflow phase."""
    
    def __init__(self, phase: str, message: str, **kwargs):
        """Initialize with phase info."""
        super().__init__(f"[{phase}] {message}", **kwargs)
        self.phase = phase


class TaskClassificationError(WorkflowError):
    """Error classifying task type."""
    pass


class VerificationFailedError(WorkflowError):
    """Tests or verification failed."""
    severity = ErrorSeverity.WARNING


class MaxRetriesExceededError(WorkflowError):
    """Max retry attempts exceeded."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Knowledge Graph & Ossifikat Errors
# ═══════════════════════════════════════════════════════════════════════════

class OssifikatError(VibelikeError):
    """Base error for ossifikat operations."""
    pass


class TripleStorageError(OssifikatError):
    """Error storing triple in ossifikat."""
    pass


class TripleValidationError(OssifikatError):
    """Triple validation failed."""
    severity = ErrorSeverity.WARNING


class KnowledgeGraphInconsistencyError(OssifikatError):
    """Inconsistency detected in knowledge graph."""
    severity = ErrorSeverity.WARNING


# ═══════════════════════════════════════════════════════════════════════════
# Configuration & Environment Errors
# ═══════════════════════════════════════════════════════════════════════════

class ConfigError(VibelikeError):
    """Base error for configuration issues."""
    pass


class EnvVarMissingError(ConfigError):
    """Required environment variable is missing."""
    
    def __init__(self, var_name: str, **kwargs):
        """Initialize with var name."""
        super().__init__(f"Environment variable missing: {var_name}", **kwargs)
        self.var_name = var_name


class InvalidConfigError(ConfigError):
    """Configuration is invalid (type, format, constraints)."""
    pass


class DatabaseConnectionError(ConfigError):
    """Cannot connect to database."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Tool & Sandbox Errors
# ═══════════════════════════════════════════════════════════════════════════

class SandboxError(VibelikeError):
    """Base error for sandbox execution."""
    pass


class SandboxTimeoutError(SandboxError):
    """Sandbox execution timed out."""
    pass


class SandboxSecurityError(SandboxError):
    """Security violation in sandbox."""
    severity = ErrorSeverity.CRITICAL


class ToolExecutionError(VibelikeError):
    """Error executing a tool."""
    pass


class ToolNotFoundError(ToolExecutionError):
    """Tool is not available."""
    pass


# ═══════════════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════════════

def format_error_for_output(error: VibelikeError) -> str:
    """Format error for terminal/UI output."""
    severity_icon = {
        ErrorSeverity.DEBUG: "🔍",
        ErrorSeverity.INFO: "ℹ️",
        ErrorSeverity.WARNING: "⚠️",
        ErrorSeverity.ERROR: "❌",
        ErrorSeverity.CRITICAL: "🚨",
    }
    icon = severity_icon.get(error.severity, "❓")
    return f"{icon} {error.__class__.__name__}: {error.message}"
