"""A deterministic fake backend that behaves like different models.

Why this exists: the whole pipeline - arms, ledger, auditors, figures - can be
built and validated before a single API key arrives, and every test is exactly
reproducible.

The key property is that mock models have DIFFERENT, MODEL-SPECIFIC BIASES, so
they are genuinely distinguishable. This mirrors the real phenomenon Bruckner
documented: asked for "a random number between 1 and 100", GPT-family models
favour 42 and 73 while other families prefer 57, 37, 7. A uniform fake backend
would make every auditor trivially fail and prove nothing.

Mock models also differ in latency and surface formatting, so GATEOPS and
IRIS-lite have signal to work with too.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from typing import Any

from .types import BackendResponse, Endpoint


@dataclass
class MockModel:
    """A fake model with a characteristic fingerprint."""

    name: str
    # Weighted preferences over 1..100. Unlisted values share the remaining mass.
    number_bias: dict[int, float] = field(default_factory=dict)
    word_bias: dict[str, float] = field(default_factory=dict)
    latency_mean_s: float = 0.8
    latency_cv: float = 0.35
    # Surface habits, the substrate for IRIS-lite's visible-string features.
    pad_with_period: bool = False
    uppercase_words: bool = False
    tokens_per_char: float = 0.28

    def _categorical(self, rng: random.Random, bias: dict[Any, float], universe: list[Any]) -> Any:
        weights = []
        listed_mass = sum(bias.values())
        spare = max(0.0, 1.0 - listed_mass)
        per_other = spare / max(1, len(universe) - len(bias))
        for v in universe:
            weights.append(bias.get(v, per_other))
        total = sum(weights) or 1.0
        r = rng.random() * total
        acc = 0.0
        for v, w in zip(universe, weights):
            acc += w
            if r <= acc:
                return v
        return universe[-1]

    def answer(self, prompt: str, rng: random.Random) -> str:
        low = prompt.lower()
        if "between 1 and 100" in low or "1 and 100" in low:
            val = self._categorical(rng, self.number_bias, list(range(1, 101)))
            out = str(val)
        elif "between 1 and 10" in low or "1 and 10" in low:
            val = self._categorical(rng, {k: v for k, v in self.number_bias.items() if k <= 10},
                                    list(range(1, 11)))
            out = str(val)
        elif "coin" in low:
            out = self._categorical(rng, {"heads": 0.55}, ["heads", "tails"])
        elif "colour" in low or "color" in low:
            out = self._categorical(rng, self.word_bias, ["blue", "red", "green", "purple", "teal"])
        elif "animal" in low:
            out = self._categorical(rng, self.word_bias, ["dog", "cat", "fox", "otter", "owl"])
        else:
            # Deterministic-but-model-specific filler for open prompts.
            h = int(hashlib.sha256((self.name + prompt).encode()).hexdigest()[:8], 16)
            out = f"response-{h % 1000}"

        if self.uppercase_words and out.isalpha():
            out = out.capitalize()
        if self.pad_with_period:
            out = out + "."
        return out

    def latency(self, rng: random.Random) -> float:
        sigma = math.sqrt(math.log(self.latency_cv ** 2 + 1))
        mu = math.log(max(self.latency_mean_s, 1e-6)) - 0.5 * sigma ** 2
        return math.exp(rng.gauss(mu, sigma))


# Four mock models forming a usable ladder. The genuine/substitute pair is
# deliberately distinguishable but not trivially so, and `alternate-70b` is a
# near-twin of genuine - it is the same weights on other hardware, so A11 is
# genuinely hard to separate from A3. That difficulty is the point.
MOCK_MODELS: dict[str, MockModel] = {
    "genuine-70b": MockModel(
        name="genuine-70b",
        number_bias={42: 0.18, 73: 0.11, 7: 0.07, 37: 0.05, 69: 0.03},
        word_bias={"blue": 0.42, "dog": 0.30},
        latency_mean_s=1.10, latency_cv=0.30,
        pad_with_period=False, tokens_per_char=0.27,
    ),
    "substitute-8b": MockModel(
        name="substitute-8b",
        number_bias={57: 0.16, 7: 0.14, 23: 0.09, 42: 0.06, 77: 0.05},
        word_bias={"red": 0.36, "cat": 0.33},
        latency_mean_s=0.35, latency_cv=0.22,     # smaller model: faster
        pad_with_period=True, uppercase_words=True, tokens_per_char=0.31,
    ),
    "alternate-70b": MockModel(
        name="alternate-70b",
        # Same family as genuine, slightly perturbed - a different provider of
        # the same weights, differing only by serving-stack numerics.
        number_bias={42: 0.16, 73: 0.12, 7: 0.06, 37: 0.06, 69: 0.03},
        word_bias={"blue": 0.39, "dog": 0.28},
        latency_mean_s=0.85, latency_cv=0.45,     # different infra: more jitter
        pad_with_period=False, tokens_per_char=0.27,
    ),
    "launderer": MockModel(
        name="launderer",
        number_bias={57: 0.15, 7: 0.13},
        word_bias={"red": 0.34},
        latency_mean_s=0.25, latency_cv=0.20,
        pad_with_period=False, tokens_per_char=0.27,   # imitates genuine's surface
    ),
}


class MockBackend:
    """Drop-in stand-in for LiveBackend. Never touches the network."""

    def __init__(self, models: dict[str, MockModel] | None = None, *, simulate_latency: bool = False):
        self.models = models or MOCK_MODELS
        self.simulate_latency = simulate_latency
        self.calls = 0

    def _rng(self, endpoint: Endpoint, prompt: str, nonce: int) -> random.Random:
        seed_src = f"{endpoint.model}|{prompt}|{nonce}"
        seed = int(hashlib.sha256(seed_src.encode()).hexdigest()[:16], 16)
        return random.Random(seed)

    async def chat(
        self,
        endpoint: Endpoint,
        payload: dict[str, Any],
        *,
        nonce: int = 0,
    ) -> BackendResponse:
        self.calls += 1
        model = self.models.get(endpoint.model)
        if model is None:
            return BackendResponse(
                ok=False, body=None, latency_s=0.0, endpoint=endpoint,
                error=f"mock: unknown model {endpoint.model!r}",
            )

        messages = payload.get("messages") or []
        prompt = "\n".join(
            m.get("content", "") for m in messages
            if m.get("role") == "user" and isinstance(m.get("content"), str)
        )

        rng = self._rng(endpoint, prompt, nonce)
        text = model.answer(prompt, rng)
        latency = model.latency(rng)

        # Temperature actually bites: low temperature collapses onto the mode.
        temp = payload.get("temperature")
        if temp is not None and temp < 0.3:
            mode_rng = self._rng(endpoint, prompt, 0)
            biased = model.number_bias or model.word_bias
            if biased:
                text = model.answer(prompt, random.Random(
                    int(hashlib.sha256((model.name + prompt + "mode").encode()).hexdigest()[:16], 16)
                ))

        if self.simulate_latency:
            time.sleep(min(latency, 0.05))  # token gesture; never actually wait

        prompt_tokens = max(1, int(len(prompt) * model.tokens_per_char))
        completion_tokens = max(1, int(len(text) * model.tokens_per_char))

        body = {
            "id": f"mock-{self.calls}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": endpoint.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            "system_fingerprint": f"fp_mock_{model.name}",
        }
        return BackendResponse(
            ok=True, body=body, latency_s=latency, endpoint=endpoint,
        )
