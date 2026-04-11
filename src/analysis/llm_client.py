"""
Layer 2 — Analysis: LLM-agnostic client.
Supports OpenAI (GPT-4, GPT-3.5) and Anthropic (Claude) via the same interface.
Custom base_url allows self-hosted / local models (e.g. Ollama).
"""

from dataclasses import dataclass, field
from typing import Literal


LLMProvider = Literal["openai", "anthropic", "custom"]


@dataclass
class LLMConfig:
    provider: LLMProvider
    api_key: str
    model: str
    base_url: str | None = None
    max_tokens: int = 8192
    temperature: float = 0.2


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

        # OpenAI-compatible (openai provider OR custom base_url)
        import openai
        kwargs: dict = {"api_key": cfg.api_key}
        if cfg.base_url:
            kwargs["base_url"] = cfg.base_url
        return openai.OpenAI(**kwargs)

    def chat(self, system: str, user: str) -> str:
        """Send a chat message and return the assistant's reply as a string."""
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

        # OpenAI-compatible
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

    @classmethod
    def from_env(cls) -> "LLMClient":
        """Build an LLMClient from environment variables."""
        import os
        from dotenv import load_dotenv
        load_dotenv()

        provider = os.getenv("LLM_PROVIDER", "openai").lower()
        api_key = os.getenv("LLM_API_KEY", "")
        model = os.getenv("LLM_MODEL", "gpt-4o")
        base_url = os.getenv("LLM_BASE_URL") or None

        if not api_key:
            raise ValueError(
                "LLM_API_KEY not set. Copy .env.example to .env and add your API key."
            )

        config = LLMConfig(
            provider=provider,  # type: ignore
            api_key=api_key,
            model=model,
            base_url=base_url,
        )
        return cls(config=config)
