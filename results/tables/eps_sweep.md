# The confound: dilution (A3) vs benign quality routing (A11)

A3 serves a CHEAPER model on a fraction eps of requests. A11 splits traffic the same way across providers of the CORRECT model. Structurally identical; one is fraud and one is what every commercial router does openly.

A11 is a FALSE-POSITIVE arm: any **F** in its row is an auditor calling sanctioned routing fraud.

| eps | OTE | IRIS-lite | GATEOPS | KBF | BENCH | RUT | FUSE |
|---|---|---|---|---|---|---|---|
| A3 @ 0.02 | . | . | . | . | . | u | . |
| A3 @ 0.05 | . | . | . | . | . | u | . |
| A3 @ 0.1 | . | . | **F** | . | . | u | . |
| A3 @ 0.25 | . | **F** | **F** | . | . | u | **F** |
| A3 @ 0.5 | **F** | **F** | **F** | **F** | **F** | u | **F** |
| **A11 (genuine)** | . | . | **F** | . | . | u | . |
