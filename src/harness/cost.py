from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def canonical_usage(usage: dict[str, Any]) -> dict[str, int]:
    prompt_tokens = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or prompt_tokens + completion_tokens)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
    }


@dataclass(frozen=True)
class ModelPricing:
    input_cost_per_million_tokens: float = 0.0
    output_cost_per_million_tokens: float = 0.0

    def estimate(self, usage: dict[str, Any]) -> float:
        tokens = canonical_usage(usage)
        return (
            tokens["prompt_tokens"] / 1_000_000 * self.input_cost_per_million_tokens
            + tokens["completion_tokens"] / 1_000_000 * self.output_cost_per_million_tokens
        )
