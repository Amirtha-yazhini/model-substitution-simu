# Abstract

> NOTE: budget ~150 words. Synced from sections/*.tex after the plain-language rewrite; edit here and send back.

Nothing in an LLM API response proves which model answered, so a gateway can serve a cheaper model on
some requests and still charge full price. We built SHIM, a drop-in gateway that cheats in twelve
ways and logs which model answered, and ARENA, which runs five published detectors and a new combined
one against it under thresholds sealed before testing. Two detectors cannot run on most of 11 real
free endpoints. In the sealed simulated comparison, a gateway that answers honestly only to
test-shaped requests beats every detector (AUROC $\le$ 0.61), single-session audits miss cheating on
fewer than 10–15% of requests, and timing-based detectors flag honest load balancing more than fraud.
Post-hoc checks show the evasion costs under 1% of the cheater's saving on real chat traffic, and
that pooling hundreds of sessions catches 5% cheating while flagging one honest load-balancing audit
in ten.
