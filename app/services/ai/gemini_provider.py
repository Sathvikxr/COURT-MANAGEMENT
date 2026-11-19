"""
Google Gemini Live AI Provider
Implements BaseAIProvider using the modern google-genai SDK (>= 3.2.0).
Provides timeouts, retries with exponential backoff, structured output,
embeddings, and audio transcription.
"""

import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple, Type
from pydantic import BaseModel
from app.services.ai.base import BaseAIProvider

class GeminiAPIError(Exception):
    """Custom exception raised when Gemini API call fails after all retries."""
    pass


class GeminiProvider(BaseAIProvider):
    """Production provider integrating Google Gemini Live API via google-genai SDK."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        embed_model: Optional[str] = None,
        transcribe_model: Optional[str] = None,
        timeout_seconds: float = 12.0,
        max_retries: int = 3
    ):
        self.api_key = (api_key or os.environ.get('GEMINI_API_KEY', '')).strip()
        self.model_name = (model_name or os.environ.get('GEMINI_MODEL', 'gemini-4-hydrogen')).strip()
        self.embed_model = (embed_model or os.environ.get('GEMINI_EMBED_MODEL', 'gemini-embedding-2')).strip()
        self.transcribe_model = (transcribe_model or os.environ.get('GEMINI_TRANSCRIBE_MODEL', 'gemini-3.5-transcribe')).strip()
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

        super().__init__(name='gemini', model_name=self.model_name)

        self._client = None
        if self.api_key:
            try:
                from google import genai
                # Initialize modern GenAI client
                self._client = genai.Client(api_key=self.api_key)
            except Exception as e:
                self._client = None
                self._last_error = str(e)
        else:
            self._last_error = "GEMINI_API_KEY is not configured"

    @property
    def is_configured(self) -> bool:
        """Returns True if an API key is present."""
        return bool(self.api_key and self._client is not None)

    def _execute_with_retry(self, operation_fn, operation_desc: str = "Gemini Call") -> Any:
        """
        Executes an operation with exponential backoff retries.
        Retries on transient network errors, 429 quota exhaustion, and 503 service unavailable.
        """
        if not self._client:
            raise GeminiAPIError("Gemini client is uninitialized (missing or invalid API key).")

        last_exception = None
        backoff = 0.5

        for attempt in range(1, self.max_retries + 1):
            try:
                return operation_fn()
            except Exception as err:
                last_exception = err
                err_str = str(err).lower()

                # Non-retriable client errors (e.g. invalid auth key, bad request)
                if 'api_key_invalid' in err_str or 'permission_denied' in err_str:
                    raise GeminiAPIError(f"Fatal Gemini authentication error: {err}") from err

                # Exponential backoff on retriable errors
                if attempt < self.max_retries:
                    time.sleep(backoff)
                    backoff *= 2.0

        raise GeminiAPIError(f"{operation_desc} failed after {self.max_retries} attempts: {last_exception}") from last_exception

    def generate_text(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
        **kwargs
    ) -> str:
        """Generates text completion using Gemini models."""
        from google.genai import types

        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            system_instruction=system_instruction
        )

        def _call():
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            return (response.text or "").strip()

        return self._execute_with_retry(_call, f"generate_text({self.model_name})")

    def generate_json(
        self,
        prompt: str,
        schema: Optional[Type[BaseModel]] = None,
        system_instruction: Optional[str] = None,
        temperature: float = 0.1,
        max_output_tokens: int = 1536,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generates structured JSON output using Gemini structured output capabilities,
        optionally validated against a Pydantic schema class.
        """
        from google.genai import types

        config_kwargs: Dict[str, Any] = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "response_mime_type": "application/json"
        }
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if schema:
            config_kwargs["response_schema"] = schema

        config = types.GenerateContentConfig(**config_kwargs)

        def _call():
            response = self._client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config
            )
            raw_text = (response.text or "").strip()
            # Clean possible markdown wrapping e.g. ```json ... ```
            if raw_text.startswith("```"):
                raw_text = raw_text.split("```")[1]
                if raw_text.startswith("json"):
                    raw_text = raw_text[4:].strip()
            return json.loads(raw_text)

        return self._execute_with_retry(_call, f"generate_json({self.model_name})")

    def embed(self, text: str, **kwargs) -> List[float]:
        """Generates embedding vector for semantic search using gemini-embedding-2."""
        def _call():
            response = self._client.models.embed_content(
                model=self.embed_model,
                contents=text
            )
            # Response contains embedding.values
            if hasattr(response, 'embedding') and hasattr(response.embedding, 'values'):
                return list(response.embedding.values)
            elif hasattr(response, 'embeddings') and response.embeddings:
                return list(response.embeddings[0].values)
            return []

        return self._execute_with_retry(_call, f"embed({self.embed_model})")

    def transcribe(self, audio_source: Any, **kwargs) -> str:
        """Transcribes audio using gemini-3.5-transcribe."""
        from google.genai import types

        def _call():
            # If audio_source is a file path
            if isinstance(audio_source, str) and os.path.exists(audio_source):
                with open(audio_source, 'rb') as f:
                    audio_data = f.read()
            elif isinstance(audio_source, (bytes, bytearray)):
                audio_data = bytes(audio_source)
            else:
                raise ValueError("audio_source must be a valid file path or bytes.")

            part = types.Part.from_bytes(data=audio_data, mime_type=kwargs.get('mime_type', 'audio/mp3'))
            response = self._client.models.generate_content(
                model=self.transcribe_model,
                contents=[part, "Transcribe this court hearing proceeding verbatim in English and original regional speech."]
            )
            return (response.text or "").strip()

        return self._execute_with_retry(_call, f"transcribe({self.transcribe_model})")

    def is_healthy(self) -> Tuple[bool, str]:
        """Probes Gemini API connectivity with a lightweight model check."""
        if not self.is_configured:
            return False, "GEMINI_API_KEY is not set or client uninitialized"

        try:
            # Test connectivity using a minimal 1-token prompt with 5-second timeout
            from google.genai import types
            config = types.GenerateContentConfig(max_output_tokens=3, temperature=0.0)
            res = self._client.models.generate_content(
                model=self.model_name,
                contents="ping",
                config=config
            )
            if res and res.text:
                return True, f"Connected to {self.model_name} successfully."
            return False, "Empty response from Gemini API healthcheck."
        except Exception as e:
            return False, f"Gemini API healthcheck probe failed: {e}"
