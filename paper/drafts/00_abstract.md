# Abstract

> NOTE: budget ~150 words. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

A customer who pays for an LLM API pays for a named model, but nothing in the response proves which
model answered. A gateway can quietly send some requests to a cheaper model and still charge full
price. We built SHIM, a drop-in API gateway that can cheat in twelve ways and secretly records which
model answered, and ARENA, which runs five published detectors and one new combined detector against
it under thresholds fixed before testing. Two detectors cannot run on most of 11 real free endpoints
(0 and 4 of 11). In simulation, a gateway that answers honestly only when a request looks like a test
beats every detector as published (AUROC $\le$ 0.61); on 172k real chat requests this evasion gives
up under 1% of the cheater's saving. In post-hoc checks, disguising tests as ordinary requests restores
detection in simulation at five times the cost, and audits that judge each session alone cannot
catch cheating on fewer than 10–15% of requests, while pooling sessions catches 2–3% for under
40 cents. Timing-based detectors flag honest load balancing more often than fraud whenever honest
providers differ in speed.
