"""
NyayaDesk AI Provider Base Interface
Defines the standard contract for Live and Demo AI providers.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel

class BaseAIProvider(ABC):
    """Abstract interface that all AI providers (Gemini, Demo, etc.) must implement."""

    def __init__(self, name: str, model_name: str):
        self.name = name # 'gemini' or 'demo'
        self.model_name = model_name

    @abstractmethod
    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        **kwargs
    ) -> str:
        """Generate unstructured text output."""
        pass

    @abstractmethod
    def generate_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        **kwargs
    ) -> Dict[str, Any]:
        """Generate structured JSON output validated against a schema."""
        pass

    @abstractmethod
    def embed(self, text: str, **kwargs) -> List[float]:
        """Generate vector embedding for semantic search / clustering."""
        pass

    @abstractmethod
    def transcribe(self, audio_source: Any, **kwargs) -> str:
        """Transcribe spoken audio proceedings to text."""
        pass

    @abstractmethod
    def is_healthy(self) -> Tuple[bool, str]:
        """Healthcheck checking connectivity and credentials."""
        pass
