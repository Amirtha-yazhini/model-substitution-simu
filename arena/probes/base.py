"""The shared probe type.

A probe is one request an auditor sends. `cell` is the unit of grouping - the
auditor aggregates observations by it - and `answer`, where present, is the
ground truth for known-answer suites (KBF, BENCH).

`answer` never reaches an auditor. It is used to score correctness after the
fact, and to build the mock backend's answer key so a simulated large model can
be made more capable than a simulated small one. An auditor that could read it
would be solving a different, much easier problem than the real one.
"""

from __future__ import annotations

from dataclasses import dataclass

# max_tokens must survive hidden reasoning. Measured: 26-36 reasoning tokens on
# affected endpoints, so 16 (Bruckner's published value) returns an empty string.
# See results/tables/coverage.md.
DEFAULT_MAX_TOKENS = 256


@dataclass(frozen=True)
class Probe:
    cell: str
    prompt: str
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = 1.0
    answer: str | None = None


def answer_key(probes: list[Probe]) -> dict[str, str]:
    """prompt -> correct answer, for probes that have one.

    Consumed only by MockBackend. The live path never sees it.
    """
    return {p.prompt.strip(): p.answer for p in probes if p.answer is not None}
