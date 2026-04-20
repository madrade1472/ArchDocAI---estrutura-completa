"""
Pricing tables and token estimation for cost preview.

Prices are USD per 1M tokens. Last reviewed 2026-04 — confirm against the
provider's pricing page before relying on this for production billing.
"""

from dataclasses import dataclass


# USD per 1,000,000 tokens
MODEL_PRICING: dict[str, dict[str, float]] = {
    # OpenAI
    "gpt-4o":              {"input": 2.50,  "output": 10.00},
    "gpt-4o-mini":         {"input": 0.15,  "output": 0.60},
    "gpt-4-turbo":         {"input": 10.00, "output": 30.00},
    "gpt-4":               {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo":       {"input": 0.50,  "output": 1.50},

    # Anthropic
    "claude-opus-4-7":     {"input": 15.00, "output": 75.00},
    "claude-opus-4-6":     {"input": 15.00, "output": 75.00},
    "claude-sonnet-4-6":   {"input": 3.00,  "output": 15.00},
    "claude-sonnet-4-5":   {"input": 3.00,  "output": 15.00},
    "claude-haiku-4-5":    {"input": 1.00,  "output": 5.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
}

# Conservative upper bound for the analysis JSON the LLM produces.
# Real responses are usually 1.5–3k tokens; using 4k keeps the estimate honest.
DEFAULT_OUTPUT_TOKENS = 4000


@dataclass
class CostEstimate:
    model: str
    provider: str
    input_tokens: int
    output_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_known: bool

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "provider": self.provider,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "input_cost_usd": round(self.input_cost_usd, 4),
            "output_cost_usd": round(self.output_cost_usd, 4),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "pricing_known": self.pricing_known,
        }


def count_tokens(text: str, model: str = "") -> int:
    """Count tokens in text. Uses tiktoken when available, else falls back to chars/4.

    The chars/4 heuristic is roughly accurate for English/Portuguese mixed code+prose.
    """
    try:
        import tiktoken
        try:
            enc = tiktoken.encoding_for_model(model)
        except (KeyError, Exception):
            enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // 4)


def estimate_cost(
    input_text: str,
    model: str,
    provider: str,
    output_tokens: int = DEFAULT_OUTPUT_TOKENS,
) -> CostEstimate:
    """Estimate the USD cost of a single LLM call given the prompt text.

    Falls back gracefully when the model is not in the pricing table — the
    estimate becomes None-priced but token counts remain accurate.
    """
    input_tokens = count_tokens(input_text, model)

    pricing = MODEL_PRICING.get(model)
    pricing_known = pricing is not None
    if not pricing_known:
        pricing = {"input": 0.0, "output": 0.0}

    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]

    return CostEstimate(
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
        pricing_known=pricing_known,
    )
