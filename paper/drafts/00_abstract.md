# Abstract

> NOTE: budget ~150 words. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

When a customer pays for an LLM API, they pay for a named model, but nothing in the response proves
which model actually answered. A gateway between the customer and the provider can quietly send
some requests to a cheaper model and still charge full price. At least eight methods have been
proposed to catch this, but each was tested on its own data against its own simulated cheater. We
built SHIM, a drop-in API gateway that can cheat in twelve ways and secretly records which model
really answered, and ARENA, which runs five published detectors and one new combined detector
against it. All thresholds were fixed and fingerprinted before any test ran. Two detectors cannot
run on most real free endpoints (0 and 4 of 11). A gateway that answers honestly only when a request
looks like a test beats every detector (AUROC $\le$ 0.61, near a coin flip). Audits cost under one
cent, yet no detector catches cheating on fewer than 10% of requests without too many false alarms,
and that still saves the gateway 8.8% of the bill. Timing-based detectors also flag honest load
balancing more often than real cheating.
