"""
Layer 2 - Analysis: LLM-agnostic client.
Supports OpenAI (GPT-4, GPT-3.5) and Anthropic (Claude) via the same interface.
Custom base_url allows self-hosted / local models (e.g. Ollama).

Reliability:
- Retry with exponential backoff on rate limit (429) and server errors (5xx)
- API key is never logged or included in error messages
"""

import time
from dataclasses import dataclass, field
from typing import Literal

from src.logger import get_logger

log = get_logger(__name__)

LLMProvider = Literal["openai", "anthropic", "custom"]

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_RETRIES = 4
_BACKOFF_BASE = 2.0      # seconds, doubles each attempt for 5xx
_RATE_LIMIT_WAIT = 62.0  # seconds to wait on 429 (rate window is 60s)


@dataclass
class LLMConfig:
    provider: LLMProvider
    api_key: str
    model: str
    base_url: str | None = None
    max_tokens: int = 16384
    temperature: float = 0.0


@dataclass
class LLMClient:
    config: LLMConfig
    _client: object = field(init=False, repr=False)

    def __post_init__(self):
        self._client = self._build_client()

    def _build_client(self):
        cfg = self.config
        if cfg.provider == "anthropic":
            import anthropic
            return anthropic.Anthropic(api_key=cfg.api_key)

        import openai
        kwargs: dict = {"api_key": cfg.api_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        return openai.OpenAI(**kwargs)

    def chat(self, system: str, user: str) -> str:
        """Send a chat message with retry/backoff on transient errors."""
        last_exc: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._call(system, user)
            except Exception as exc:
                status = self._extract_status(exc)
                if status not in _RETRYABLE_STATUS:
                    # Non-retryable (auth error, bad request, etc.)
                    # Never include api_key in the log
                    log.error("LLM call failed (non-retryable): %s", type(exc).__name__)
                    raise

                if status == 429:
                    # Rate limit: wait out the full rate window before retrying
                    wait = _RATE_LIMIT_WAIT
                else:
                    wait = _BACKOFF_BASE ** (attempt - 1)
                log.warning(
                    "LLM call failed (attempt %d/%d, status %s) - retrying in %.1fs",
                    attempt, _MAX_RETRIES, status, wait,
                )
                time.sleep(wait)
                last_exc = exc

        log.error("LLM call failed after %d attempts", _MAX_RETRIES)
        raise last_exc  # type: ignore

    def _call(self, system: str, user: str) -> str:
        cfg = self.config

        if cfg.provider == "anthropic":
            import anthropic
            client: anthropic.Anthropic = self._client  # type: ignore
            message = client.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return message.content[0].text

        import openai
        client: openai.OpenAI = self._client  # type: ignore
        response = client.chat.completions.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            temperature=cfg.temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content or ""

    def _extract_status(self, exc: Exception) -> int | None:
        """Extract HTTP status code from SDK exceptions, if available."""
        # openai.APIStatusError and anthropic.APIStatusError both have .status_code
        if hasattr(exc, "status_code"):
            return exc.status_code
        return None

    @classmethod
    def from_env(cls) -> "LLMClient":
        import os
        from dotenv import load_dotenv
        load_dotenv()

        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "gpt-4o")
        base_url = os.getenv("LLM_BASE_URL") or None

        if not api_key:
            raise ValueError("LLM_API_KEY not set. Copy .env.example to .env and add your key.")

        config = LLMConfig(
            provider=provider,  # type: ignore
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
        return cls(config=config)
