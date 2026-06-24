"""
Abstract base class for LLM model wrappers.

Eliminates duplication between QwenCoder, ClaudeCoder, GeminiCoder, MistralCoder.
Provides:
- Unified generation interface
- Error handling with retries
- Streaming support
- Token counting
- Health checks
"""

from abc import ABC, abstractmethod
from typing import Optional, Iterator, AsyncIterator, Dict, Any
import logging

logger = logging.getLogger(__name__)


class ModelBackendError(Exception):
    """Base exception for model backend errors."""
    pass


class ModelUnavailableError(ModelBackendError):
    """Model or API is unavailable."""
    pass


class ModelTimeoutError(ModelBackendError):
    """Model request timed out."""
    pass


class ModelBackend(ABC):
    """Abstract base for LLM model backends."""
    
    def __init__(self, model_name: str, **kwargs):
        """
        Initialize model backend.
        
        Args:
            model_name: Identifier for the model (e.g., "gpt-4", "claude-3-sonnet")
            **kwargs: Backend-specific options
        """
        self.model_name = model_name
        self.is_usable = False
        self._health_checked = False
    
    @abstractmethod
    async def health_check(self) -> bool:
        """Check if model is available and working."""
        pass
    
    @abstractmethod
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        **kwargs
    ) -> str:
        """
        Generate text from prompt.
        
        Args:
            prompt: User prompt
            system_prompt: System instruction
            max_tokens: Max output tokens
            temperature: Sampling temperature
            top_p: Nucleus sampling p
            **kwargs: Model-specific options
            
        Returns:
            Generated text
            
        Raises:
            ModelUnavailableError: Model not available
            ModelTimeoutError: Request timed out
        """
        pass
    
    @abstractmethod
    def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Iterator[str]:
        """
        Stream text generation.
        
        Yields:
            Text chunks as they arrive
        """
        pass
    
    @abstractmethod
    async def async_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Async version of generate."""
        pass
    
    @abstractmethod
    async def async_stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """Async streaming generation."""
        pass
    
    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        pass
    
    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(model_name={self.model_name!r}, usable={self.is_usable})"


class RetryableModelBackend(ModelBackend):
    """Model backend with automatic retry logic."""
    
    def __init__(
        self,
        model_name: str,
        max_retries: int = 3,
        retry_backoff: float = 1.0,
        **kwargs
    ):
        """
        Initialize with retry strategy.
        
        Args:
            model_name: Model identifier
            max_retries: Max retry attempts
            retry_backoff: Backoff multiplier (exponential)
            **kwargs: Passed to parent
        """
        super().__init__(model_name, **kwargs)
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
    
    async def _retry_async(
        self,
        async_fn,
        *args,
        **kwargs
    ):
        """Retry async function with exponential backoff."""
        import asyncio
        
        last_error = None
        backoff = self.retry_backoff
        
        for attempt in range(self.max_retries):
            try:
                return await async_fn(*args, **kwargs)
            except (ModelTimeoutError, ModelUnavailableError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    wait_time = backoff ** attempt
                    logger.warning(
                        f"Attempt {attempt+1}/{self.max_retries} failed. "
                        f"Retrying in {wait_time:.1f}s... ({e})"
                    )
                    await asyncio.sleep(wait_time)
        
        raise last_error or ModelBackendError(
            f"Failed after {self.max_retries} retries"
        )


class ModelRegistry:
    """Factory and registry for model backends."""
    
    _backends: Dict[str, type] = {}
    _instances: Dict[str, ModelBackend] = {}
    
    @classmethod
    def register(cls, name: str, backend_class: type):
        """Register a model backend."""
        cls._backends[name] = backend_class
    
    @classmethod
    def get_backend(
        cls,
        model_name: str,
        backend_type: str = "auto",
        **kwargs
    ) -> ModelBackend:
        """
        Get or create model backend instance.
        
        Args:
            model_name: Model identifier
            backend_type: "ollama", "anthropic", "gemini", "mistral", or "auto"
            **kwargs: Backend-specific options
            
        Returns:
            ModelBackend instance
        """
        # Return cached instance if available
        cache_key = f"{backend_type}:{model_name}"
        if cache_key in cls._instances:
            return cls._instances[cache_key]
        
        # Auto-detect backend from model name
        if backend_type == "auto":
            backend_type = cls._detect_backend(model_name)
        
        # Get backend class
        if backend_type not in cls._backends:
            raise ValueError(f"Unknown backend type: {backend_type}")
        
        backend_class = cls._backends[backend_type]
        instance = backend_class(model_name, **kwargs)
        
        cls._instances[cache_key] = instance
        return instance
    
    @staticmethod
    def _detect_backend(model_name: str) -> str:
        """Auto-detect backend from model name."""
        if "claude" in model_name.lower():
            return "anthropic"
        elif "gemini" in model_name.lower():
            return "gemini"
        elif "mistral" in model_name.lower():
            return "mistral"
        else:
            return "ollama"  # Default to Ollama
