"""Probe suites for KBF, BENCH and IRIS-lite.

Three suites, three different questions about the same endpoint:

  KBF   - does it RECALL the same facts? Numeric items near the knowledge
          boundary, where a smaller model degrades first.
  BENCH - does it REASON as well? Benchmark-style items with known answers.
  IRIS  - does it FORMAT the same way? Content is irrelevant; only the visible
          string matters, so the prompts just need to produce varied output.

**The BENCH items are benchmark-STYLE, not the benchmarks.** MMLU, GPQA and GSM8K
are not redistributed here. Against real endpoints you would swap in the real
items; the point being demonstrated does not depend on which items are used, only
on the fact that they are public and finite. Which is precisely arm A10's thesis:
every BENCH stem below also appears in config/canaries.txt, so a gateway holding a
static lookup table serves those requests honestly and BENCH sees clean accuracy
while everything else gets the cheap model. That is not a contrived coincidence -
it is what public benchmarks let an adversary do, and it is why accuracy-based
detection is the most easily defeated family in this literature.
"""

from __future__ import annotations

from .base import Probe

# ----------------------------------------------------------------------
# KBF - knowledge-boundary fingerprinting
#
# Items are chosen to sit where recall starts to fail: specific enough that a
# smaller model guesses, common enough that a larger one should know. An item
# every model answers correctly carries no information about which model it is.
# ----------------------------------------------------------------------

KBF_PROBES: list[Probe] = [
    Probe("kbf.year", "In what year was the Eiffel Tower completed? Reply with only the year.", answer="1889"),
    Probe("kbf.year2", "In what year did the Chernobyl disaster occur? Reply with only the year.", answer="1986"),
    Probe("kbf.year3", "In what year was the first iPhone released? Reply with only the year.", answer="2007"),
    Probe("kbf.year4", "In what year did the Berlin Wall fall? Reply with only the year.", answer="1989"),
    Probe("kbf.year5", "In what year was the Treaty of Westphalia signed? Reply with only the year.", answer="1648"),
    Probe("kbf.num1", "How many bones are in the adult human body? Reply with only the number.", answer="206"),
    Probe("kbf.num2", "How many elements are in the second period of the periodic table? Reply with only the number.", answer="8"),
    Probe("kbf.num3", "At what temperature in Celsius does water boil at sea level? Reply with only the number.", answer="100"),
    Probe("kbf.num4", "How many chromosomes does a human somatic cell contain? Reply with only the number.", answer="46"),
    Probe("kbf.num5", "How many moons does Mars have? Reply with only the number.", answer="2"),
    Probe("kbf.num6", "How many keys are on a standard piano? Reply with only the number.", answer="88"),
    Probe("kbf.num7", "What is the atomic number of gold? Reply with only the number.", answer="79"),
    Probe("kbf.num8", "How many time zones does Russia span? Reply with only the number.", answer="11"),
    Probe("kbf.num9", "In what year was the Rosetta Stone discovered? Reply with only the year.", answer="1799"),
    Probe("kbf.num10", "How many players are on the field per team in rugby union? Reply with only the number.", answer="15"),
]


# ----------------------------------------------------------------------
# BENCH - accuracy-based detection (Cai et al.)
#
# Every stem here appears in config/canaries.txt. See the module docstring.
# ----------------------------------------------------------------------

BENCH_PROBES: list[Probe] = [
    # --- GSM8K-style ---
    Probe("bench.gsm1",
          "Natalia sold clips to 48 of her friends in April, and then she sold half as "
          "many clips in May. How many clips did Natalia sell altogether? "
          "Reply with only the number.", answer="72"),
    Probe("bench.gsm2",
          "Weng earns $12 an hour for babysitting. Yesterday she did 50 minutes of "
          "babysitting. How many dollars did she earn? Reply with only the number.",
          answer="10"),
    Probe("bench.gsm3",
          "Betty is saving money for a new wallet which costs $100. Betty has half the "
          "money she needs. Her parents give her $15, and her grandparents give twice as "
          "much as her parents. How many more dollars does Betty need? "
          "Reply with only the number.", answer="5"),
    Probe("bench.gsm4",
          "Janet's ducks lay 16 eggs per day. She eats three for breakfast and bakes "
          "muffins with four. She sells the rest at $2 each. How many dollars does she "
          "make daily? Reply with only the number.", answer="18"),
    Probe("bench.gsm5",
          "A robe takes 2 bolts of blue fiber and half that much white fiber. How many "
          "bolts does it take in total? Reply with only the number.", answer="3"),
    # --- MMLU-style ---
    Probe("bench.mmlu1",
          "Which of the following is the body cavity that contains the pituitary gland? "
          "A) Abdominal B) Cranial C) Pleural D) Spinal. Reply with only the letter.",
          answer="B"),
    Probe("bench.mmlu2",
          "What is the difference between a male and a female catheter? "
          "A) Bore size B) Male catheters are longer C) Female catheters are longer "
          "D) No difference. Reply with only the letter.", answer="B"),
    Probe("bench.mmlu3",
          "In contrast to alkanes, alkenes A) contain only single bonds "
          "B) contain a carbon-carbon double bond C) are fully saturated "
          "D) are always gaseous. Reply with only the letter.", answer="B"),
    Probe("bench.mmlu4",
          "The energy for all forms of muscle contraction is provided by A) ATP "
          "B) ADP C) phosphocreatine D) oxidative phosphorylation. "
          "Reply with only the letter.", answer="A"),
    Probe("bench.mmlu5",
          "Which of these branches of the trigeminal nerve contain somatic motor "
          "fibres? A) Ophthalmic B) Maxillary C) Mandibular D) None. "
          "Reply with only the letter.", answer="C"),
    # --- GPQA-style ---
    Probe("bench.gpqa1",
          "Two quantum states with energies E1 and E2 have a lifetime of 1e-9 and 1e-8 "
          "seconds respectively. Which energy difference allows them to be clearly "
          "resolved? A) 1e-4 eV B) 1e-8 eV C) 1e-9 eV D) 1e-11 eV. "
          "Reply with only the letter.", answer="A"),
    Probe("bench.gpqa2",
          "Astronomers are studying a system of five exoplanets with circular orbits. "
          "Which planet has the largest equilibrium temperature? A) The innermost "
          "B) The outermost C) The most massive D) The least massive. "
          "Reply with only the letter.", answer="A"),
]


# ----------------------------------------------------------------------
# IRIS - visible-string formatting
#
# Open-ended on purpose. IRIS reads formatting habits, so what matters is that
# responses are long and varied enough for surface features to differ, not that
# any particular answer is correct. No answer key: there is nothing to be right
# about.
# ----------------------------------------------------------------------

IRIS_PROBES: list[Probe] = [
    Probe("iris.colour", "Name a colour. Reply with only one word."),
    Probe("iris.animal", "Name an animal. Reply with only one word."),
    Probe("iris.rand", "Name a random number between 1 and 100. Reply with only the number."),
    Probe("iris.coin", "Flip a coin. Answer with only one word: heads or tails."),
]


SUITES: dict[str, list[Probe]] = {
    "kbf": KBF_PROBES,
    "bench": BENCH_PROBES,
    "iris": IRIS_PROBES,
}


def suite(name: str) -> list[Probe]:
    return SUITES[name]
