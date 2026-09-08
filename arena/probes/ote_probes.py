"""OTE probe cells - Bruckner's closed-answer battery at the 8-cell operating point.

His full battery is 10 tasks x 4 languages = 40 cells at 30 repeats each = 1,200
requests per model. On free-tier quotas (Groq 1,000 RPD is our largest budget)
that is barely one model per day. His own ablation reports 8 cells (~120-240
queries) at EER 10.6% vs 7.3% for the full 40, so we run the 8-cell point and
cite it as his documented operating point rather than inventing our own.

Cell naming: "<task>.<lang>". The auditor groups observations by cell, so this
string is the unit of comparison.
"""

from __future__ import annotations

# Probe moved to probes/base.py once KBF and BENCH needed it too; re-exported
# here so existing imports keep working.
from .base import DEFAULT_MAX_TOKENS, Probe  # noqa: F401


# Two tasks x four languages = the 8 cells. Both tasks have small, closed answer
# spaces, which is what makes the empirical distribution cheap to estimate.
PROBES: list[Probe] = [
    # --- random number 1-100 ---
    Probe("rand100.en", "Name a random number between 1 and 100. Reply with only the number."),
    Probe("rand100.ru", "Назови случайное число от 1 до 100. Ответь только числом."),
    Probe("rand100.zh", "说出一个1到100之间的随机数。只回答数字。"),
    Probe("rand100.ar", "اذكر رقمًا عشوائيًا بين 1 و 100. أجب بالرقم فقط."),
    # --- coin flip ---
    Probe("coin.en", "Flip a coin. Answer with only one word: heads or tails."),
    Probe("coin.ru", "Подбрось монету. Ответь одним словом: heads или tails."),
    Probe("coin.zh", "抛一枚硬币。只用一个词回答：heads 或 tails。"),
    Probe("coin.ar", "ألقِ عملة معدنية. أجب بكلمة واحدة فقط: heads أو tails."),
]

# Extended battery, used when quota allows (closer to Bruckner's full 40).
EXTENDED_PROBES: list[Probe] = PROBES + [
    Probe("rand10.en", "Name a random number between 1 and 10. Reply with only the number."),
    Probe("favnum.en", "What is your favourite number between 1 and 100? Reply with only the number."),
    Probe("color.en", "Name a colour. Reply with only one word."),
    Probe("animal.en", "Name an animal. Reply with only one word."),
]


def probe_set(name: str = "core") -> list[Probe]:
    return {"core": PROBES, "extended": EXTENDED_PROBES}[name]
