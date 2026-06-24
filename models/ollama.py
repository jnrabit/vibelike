"""
Ollama model backend implementation.

Wraps Ollama local model server with unified interface.
"""

import logging
import asyncio
import httpx
import json
from typing import Optional, Iterator, AsyncIterator

from config import settings
from .base import ModelBackend, RetryableModelBackend, ModelUnavailableError, ModelTimeoutError

logger = logging.getLogger(__name__)


class OllamaBackend(RetryableModelBackend):
    """Ollama model backend (local inference)."""
    
    def __init__(
        self,
        model_name: str = "deepseek-coder:6.7b-instruct",
        ollama_url: Optional[str] = None,
        num_predict: int = 2048,
        keep_alive: str = "30m",
        **kwargs
    ):
        """
        Initialize Ollama backend.
        
        Args:
            model_name: Ollama model identifier
            ollama_url: Ollama API endpoint
            num_predict: Max tokens to generate
            keep_alive: Keep model in memory ("30m", "1h", etc.)
            **kwargs: Passed to RetryableModelBackend
        """
        super().__init__(model_name, **kwargs)
        self.ollama_url = ollama_url or settings.ollama_url
        self.num_predict = num_predict
        self.keep_alive = keep_alive
        self._client = None
        self._async_client = None
    
    @property
    def client(self):
        """Lazy-load sync HTTP client."""
        if self._client is None:
            self._client = httpx.Client(timeout=60.0)
        return self._client
    
    @property
    async def async_client(self):
        """Lazy-load async HTTP client."""
        if self._async_client is None:
            self._async_client = httpx.AsyncClient(timeout=60.0)
        return self._async_client
    
    async def health_check(self) -> bool:
        """Check if Ollama server is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.ollama_url.rsplit('/api', 1)[0]}/api/tags")
                self.is_usable = resp.status_code == 200
                return self.is_usable
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            self.is_usable = False
            return False
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        top_p: float = 1.0,
        **kwargs
    ) -> str:
        """Generate text synchronously."""
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            payload = {
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": False,
                "num_predict": min(max_tokens, self.num_predict),
                "temperature": temperature,
                "top_p": top_p,
                "keep_alive": self.keep_alive,
            }
            payload.update(kwargs)
            
            resp = self.client.post(self.ollama_url, json=payload)
            resp.raise_for_status()
            
            result = resp.json()
            return result.get("response", "").strip()
        
        except httpx.TimeoutException as e:
            raise ModelTimeoutError(f"Ollama request timed out: {e}")
        except httpx.ConnectError as e:
            raise ModelUnavailableError(f"Cannot connect to Ollama at {self.ollama_url}: {e}")
        except Exception as e:
            raise ModelUnavailableError(f"Ollama error: {e}")
    
    def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> Iterator[str]:
        """Stream text generation."""
        try:
            full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            
            payload = {
                "model": self.model_name,
                "prompt": full_prompt,
                "stream": True,
                "num_predict": min(max_tokens, self.num_predict),
                "temperature": temperature,
                "keep_alive": self.keep_alive,
            }
            payload.update(kwargs)
            
            with self.client.stream("POST", self.ollama_url, json=payload) as resp:
                resp.raise_for_status()
                for line in resp.iter_lines():
                    if line.strip():
                        chunk = json.loads(line).get("response", "")
                        if chunk:
                            yield chunk
        
        except httpx.TimeoutException as e:
            raise ModelTimeoutError(f"Ollama stream timed out: {e}")
        except httpx.ConnectError as e:
            raise ModelUnavailableError(f"Cannot connect to Ollama: {e}")
        except Exception as e:
            raise ModelUnavailableError(f"Ollama streaming error: {e}")
    
    async def async_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> str:
        """Generate text asynchronously."""
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": False,
            "num_predict": min(max_tokens, self.num_predict),
            "temperature": temperature,
            "keep_alive": self.keep_alive,
        }
        payload.update(kwargs)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(self.ollama_url, json=payload)
                resp.raise_for_status()
                result = resp.json()
                return result.get("response", "").strip()
        
        except httpx.TimeoutException as e:
            raise ModelTimeoutError(f"Ollama async request timed out: {e}")
        except httpx.ConnectError as e:
            raise ModelUnavailableError(f"Cannot connect to Ollama: {e}")
        except Exception as e:
            raise ModelUnavailableError(f"Ollama async error: {e}")
    
    async def async_stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        **kwargs
    ) -> AsyncIterator[str]:
        """Stream text generation asynchronously."""
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        
        payload = {
            "model": self.model_name,
            "prompt": full_prompt,
            "stream": True,
            "num_predict": min(max_tokens, self.num_predict),
            "temperature": temperature,
            "keep_alive": self.keep_alive,
        }
        payload.update(kwargs)
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", self.ollama_url, json=payload) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if line.strip():
                            chunk = json.loads(line).get("response", "")
                            if chunk:
                                yield chunk
        
        except httpx.TimeoutException as e:
            raise ModelTimeoutError(f"Ollama async stream timed out: {e}")
        except httpx.ConnectError as e:
            raise ModelUnavailableError(f"Cannot connect to Ollama: {e}")
        except Exception as e:
            raise ModelUnavailableError(f"Ollama async streaming error: {e}")
    
    def count_tokens(self, text: str) -> int:
        """Estimate token count (rough approximation)."""
        # Ollama doesn't expose token counting, so use simple heuristic:
        # Average ~4 chars per token
        return len(text) // 4
    
    def __del__(self):
        """Clean up HTTP clients."""
        if self._client:
            self._client.close()
        if self._async_client:
            # Can't close async client in __del__, but httpx will handle it
            pass


# Register Ollama backend
from .base import ModelRegistry
ModelRegistry.register("ollama", OllamaBackend)
