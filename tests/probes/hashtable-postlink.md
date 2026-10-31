# Hashtable S2 performance fixtures

`hashtable-postlink-{18,23}.ll` are byte-for-byte copies of the rung-2
`bennett-conformance/ladder/rung-2/evidence/first-run/{18,23}/postlink.ll`
inputs. These are **unlinked diagnostic inputs**, not §19.1 production evidence.
They retain the unabridged C hashtable and its two direct marker pairs.
`tests/analysis_performance.py` bounds completion to 20 seconds and 100 rounds,
and forces both iteration and elapsed-time exhaustion to verify loud diagnostics.
The normative integer threshold remains K=4096; no pointer distinctions are widened.

The linked pipeline measurements and the next production diagnostic are recorded
in `docs/verification.json`; they use published runtimes and pinned arith bitcode,
`llvm-link --only-needed`, then `lto<O3>`, then the plugin.
