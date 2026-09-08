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
import re
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
    # Probability of recalling/answering a known-answer item correctly. This is
    # the ONLY axis on which the mock models capability rather than style, and
    # KBF and BENCH have no signal without it: both auditors ask whether the
    # suspect gets things RIGHT as often as the reference does, which is a
    # question about ability, not formatting.
    factual_accuracy: float = 0.80

    def _categorical(self, rng: random.Random, bias: dict[Any, float], universe: list[Any]) -> Any:
        # Only bias entries that live in THIS universe count toward the listed
        # mass. word_bias carries both colour and animal preferences, so summing
        # it wholesale made the listed mass exceed 1, left zero spare probability
        # and collapsed every word cell onto its mode - a point mass where the
        # real thing has ~1 bit of entropy.
        listed = {k: v for k, v in bias.items() if k in universe}
        weights = []
        spare = max(0.0, 1.0 - sum(listed.values()))
        per_other = spare / max(1, len(universe) - len(listed))
        for v in universe:
            weights.append(listed.get(v, per_other))
        total = sum(weights) or 1.0
        r = rng.random() * total
        acc = 0.0
        for v, w in zip(universe, weights):
            acc += w
            if r <= acc:
                return v
        return universe[-1]

    # Task detection must be language-agnostic: Bruckner's battery runs the same
    # task in English, Russian, Chinese and Arabic, and a mock that only parses
    # English would silently drop 6 of 8 cells.
    _COIN_MARKERS = ("coin", "монет", "硬币", "عملة", "heads")

    def _lang_of(self, prompt: str) -> str:
        if any("Ѐ" <= c <= "ӿ" for c in prompt):
            return "ru"
        if any("一" <= c <= "鿿" for c in prompt):
            return "zh"
        if any("؀" <= c <= "ۿ" for c in prompt):
            return "ar"
        return "en"

    def answer(self, prompt: str, rng: random.Random) -> str:
        low = prompt.lower()
        lang = self._lang_of(prompt)

        # Real models carry language-dependent biases - that is precisely why the
        # battery is multilingual - so perturb the bias slightly per language
        # rather than reusing one distribution across all four cells.
        def shifted(bias: dict) -> dict:
            if lang == "en":
                return bias
            shift = {"ru": 0.75, "zh": 0.6, "ar": 0.5}[lang]
            return {k: v * shift for k, v in bias.items()}

        if "100" in low:
            val = self._categorical(rng, shifted(self.number_bias), list(range(1, 101)))
            out = str(val)
        elif any(m in low for m in self._COIN_MARKERS):
            out = self._categorical(rng, shifted({"heads": 0.55}), ["heads", "tails"])
        elif "10" in low:
            val = self._categorical(rng, shifted({k: v for k, v in self.number_bias.items() if k <= 10}),
                                    list(range(1, 11)))
            out = str(val)
        elif "colour" in low or "color" in low:
            out = self._categorical(rng, shifted(self.word_bias), ["blue", "red", "green", "purple", "teal"])
        elif "animal" in low:
            out = self._categorical(rng, shifted(self.word_bias), ["dog", "cat", "fox", "otter", "owl"])
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
#
# Concentration is calibrated to Bruckner's measurement, not invented: he reports
# a MEDIAN PER-CELL ENTROPY OF ~1.0 BIT against theoretical baselines of 1-6.6
# bits. One bit is roughly two effective answers, so real models put most of
# their mass on a handful of values.
#
# This matters more than it looks. An earlier draft spread ~56% of the mass
# uniformly across 95 values; at 30 samples per cell that produced two nearly
# disjoint sparse supports even for the SAME model, so honest-vs-honest JSD sat
# at ~0.31 and swamped the real signal. Jensen-Shannon on a sparse
# high-cardinality categorical is badly upward-biased at small n - the fix is a
# realistic distribution, not a tuned threshold.
MOCK_MODELS: dict[str, MockModel] = {
    "genuine-70b": MockModel(
        name="genuine-70b",
        number_bias={42: 0.52, 73: 0.22, 7: 0.11, 37: 0.06, 69: 0.04},
        word_bias={"blue": 0.62, "dog": 0.55},
        latency_mean_s=1.10, latency_cv=0.30,
        pad_with_period=False, tokens_per_char=0.27,
        factual_accuracy=0.86,
    ),
    "substitute-8b": MockModel(
        name="substitute-8b",
        number_bias={57: 0.48, 7: 0.24, 23: 0.13, 42: 0.08, 77: 0.04},
        word_bias={"red": 0.58, "cat": 0.51},
        latency_mean_s=0.35, latency_cv=0.22,     # smaller model: faster
        pad_with_period=True, uppercase_words=True, tokens_per_char=0.31,
        factual_accuracy=0.54,                    # and markedly less capable
    ),
    "alternate-70b": MockModel(
        name="alternate-70b",
        # Same family as genuine, slightly perturbed - a different provider of
        # the same weights, differing only by serving-stack numerics. The gap
        # here is deliberately small, which is what makes A11 (benign routing)
        # genuinely hard to separate from A3 (dilution).
        number_bias={42: 0.49, 73: 0.23, 7: 0.12, 37: 0.07, 69: 0.04},
        word_bias={"blue": 0.59, "dog": 0.53},
        latency_mean_s=0.85, latency_cv=0.45,     # different infra: more jitter
        pad_with_period=False, tokens_per_char=0.27,
        # Same weights as genuine, so the same ability. A11 must stay invisible
        # to a capability-based auditor, or it would not be a real confound.
        factual_accuracy=0.86,
    ),
    "launderer": MockModel(
        name="launderer",
        number_bias={57: 0.47, 7: 0.25, 23: 0.12},
        word_bias={"red": 0.57},
        latency_mean_s=0.25, latency_cv=0.20,
        pad_with_period=False, tokens_per_char=0.27,   # imitates genuine's surface
        factual_accuracy=0.54,
    ),
}


# A7 (laundering) sends a second, restyling pass. The mock recognises it and
# applies the NAMED TARGET's surface habits to the payload without touching the
# payload's content - which is precisely the attack: the answer stays the cheap
# model's, the surface becomes the expensive model's. Semantic auditors (OTE)
# should be unaffected; surface auditors (IRIS-lite) should be defeated.
_RESTYLE = re.compile(
    r"^restyle in the surface style of (?P<style>[\w.\-/:]+)\."
    r"\s*do not change meaning:\s*(?P<payload>.*)$",
    re.S | re.I,
)


_CHOICES = ("A", "B", "C", "D")


def answer_known_item(
    correct: str, model: MockModel, rng: random.Random
) -> str:
    """Answer an item whose ground truth the mock has been given.

    The mock is handed the answer key so it can simulate CAPABILITY: a large
    model gets an item right more often than a small one. The auditor never sees
    the key - it only sees the answers - so nothing leaks. Without this the mock
    would answer known-answer items deterministically per model, KBF and BENCH
    would separate the ladder perfectly on one probe, and both would look far
    stronger than they are.
    """
    if rng.random() < model.factual_accuracy:
        out = correct
    elif correct.upper() in _CHOICES:
        # Multiple choice: a wrong answer is one of the other letters.
        wrong = [c for c in _CHOICES if c != correct.upper()]
        out = rng.choice(wrong)
    elif correct.lstrip("-").replace(".", "", 1).isdigit():
        # Numeric: plausible near-misses, not random noise. Real models fail
        # arithmetic by small margins far more often than by orders of magnitude.
        try:
            v = float(correct)
        except ValueError:
            return correct
        delta = rng.choice([-3, -2, -1, 1, 2, 3, 10, -10])
        out = str(int(v + delta)) if v == int(v) else f"{v + delta:.2f}"
    else:
        out = f"unknown-{rng.randrange(1000)}"

    if model.uppercase_words and out.isalpha():
        out = out.capitalize()
    if model.pad_with_period:
        out = out + "."
    return out


def apply_surface(text: str, target: MockModel | None) -> str:
    """Rewrite `text`'s surface conventions to match `target`. Content preserved."""
    core = text.strip().rstrip(".").strip()
    if core.isalpha():
        core = core.capitalize() if (target and target.uppercase_words) else core.lower()
    if target and target.pad_with_period:
        core = core + "."
    return core


class MockBackend:
    """Drop-in stand-in for LiveBackend. Never touches the network."""

    def __init__(
        self,
        models: dict[str, MockModel] | None = None,
        *,
        simulate_latency: bool = False,
        session_seed: int = 0,
        answer_key: dict[str, str] | None = None,
    ):
        self.models = models or MOCK_MODELS
        self.simulate_latency = simulate_latency
        self.session_seed = session_seed
        # prompt -> correct answer, for the KBF and BENCH suites.
        self.answer_key = answer_key or {}
        self.calls = 0
        # Per-(model, prompt) call counter. A real endpoint at temperature 1
        # returns a DIFFERENT sample each time you send the same prompt; without
        # this counter the mock returns the same answer forever, honest-vs-honest
        # divergence collapses to exactly 0, and the null distribution every
        # threshold depends on becomes an artefact.
        self._seen: dict[str, int] = {}

    def _rng(self, endpoint: Endpoint, prompt: str, nonce: int) -> random.Random:
        key = f"{endpoint.model}|{prompt}"
        draw = self._seen.get(key, 0)
        self._seen[key] = draw + 1
        seed_src = f"{self.session_seed}|{key}|{nonce}|{draw}"
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

        restyle = _RESTYLE.match(prompt.strip())
        known = self.answer_key.get(prompt.strip())
        if restyle:
            text = apply_surface(
                restyle.group("payload"), self.models.get(restyle.group("style"))
            )
        elif known is not None:
            text = answer_known_item(known, model, rng)
        else:
            text = model.answer(prompt, rng)
        latency = model.latency(rng)

        # Temperature actually bites: low temperature collapses onto the mode.
        # This is what makes arm A4 (sampler retune) a genuine specificity test -
        # the distribution moves while the weights stay the same.
        temp = payload.get("temperature")
        if not restyle and known is None and temp is not None and temp < 0.3:
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
