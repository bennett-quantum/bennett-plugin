# bennett-plugin

The C++ LLVM module-pass plugin of the Bennett compiler core, built from one source
for LLVM 18 and 23. Accepted contracts: dialect **0.2.10 @ 023f5a7**, ISA **0.8**.
The plugin is the only LLVM-linked component; scheduler integration is a binary edge.

M1 remains incomplete. The local headless gate passes on both majors with
66 run / 65 agree / 1 explicit FP deferral / 0 blocked / 0 diverge. Twelve
published reference objects reproduce exact bytes, hashes and run vectors.
General analysis, full materialised region keys and production descriptor/CC
launches remain M1 obligations; static descriptor reference output is not a
production compile. Eight lift examples remain explicitly unavailable.

See [PLAN](docs/PLAN.md), [BUILD](docs/BUILD.md), [PROGRESS](docs/PROGRESS.md) and
[actual verification results](docs/verification.json). Nothing was pushed.

### Soft-float bitcode input

`SPEC_VERSIONS.toml` pins each LLVM major’s published bennett-arith bitcode path
and SHA-256. `BENNETT_ARITH_BITCODE` overrides that input (an explicit empty value
exercises unavailable-library diagnostics). The plugin links the required closure
before analysis and follows introduced numerical helpers through materialisation
and production launches. The input SHA-256 is retained in the module and build
record; repeating the same comparison link is idempotent. An incompatible helper
signature is an input error.

`-bennett-comparison` emits the normalised native comparison module and requires
its soft-float entry points to have definitions. Missing definitions fail loudly
with `unavailable: §13.1 missing entry point <name>` and the bitcode input name.
Native comparison keeps integer-wide LLVM operations for native code generation
and supplies only non-numerical byte-move/fill/fault adapters. The real arith
`i512` core still exposes an explicit N22 production-lowering obligation (bd).
The plugin contains no replacement numerical library. Tests use clearly marked
integer-only ABI fixtures to check the link path independently of numerical
conformance.

For a gate while the sibling arith publication is being edited, extract the pinned
`dist/llvm{18,23}/bennett-arith.bc` from arith commit `249e619` to an immutable
directory, then run `BENNETT_ARITH_PINNED_ROOT=/absolute/path scripts/gate`.
The directory contains `llvm18/bennett-arith.bc` and `llvm23/bennett-arith.bc`.
The gate and the plugin still check the SHA-256 values in `SPEC_VERSIONS.toml`;
this relocates those artifacts and does not adopt a newer publication.
The test harness reads export metadata from the same immutable arith `249e619`
publication, so relocated directories need only the two bitcode files.
`BENNETT_ARITH_BITCODE` remains the explicit unpinned ABI-test library override.

Whole-program R mode is selected with `--bennett-tier=reversible --bennett-entry=main`.
At the pinned ISA 0.8 it emits artifacts and returns **3**, with `BD-B-ISA7` in
`main/blockers.json` (§1.6/§11.5). Generic traps at exhausted source-step counters
are blocker fallbacks, not typed-fault conformance. Successful R paths retain the
ISA device tape and whole-run reversal history. The launch requests `bennett.argv`;
the current supported reply is a packed little-endian argc:i32 followed by two
pointer-width fields, with unused argv/envp null. Entries using argv/envp storage
fail explicitly under bp-ivy; full argument-byte marshalling remains unfinished.

This mode is **not full rung-3 closure**. The probes cover console/reset, nested
exit propagation, indirect callbacks, reached/unreached assembly traps and the
pre-effect/return budget boundaries. The full published-musl hello is also probed:
LLVM18 stops at vector fshl scalarisation (bp-ozp); LLVM23 emits LLVM-verified R
artifacts, but the exploratory executor run faults before console output (bp-ivy).
The complete startup/normal-return exit path, argument storage and runtime-budget
plumbing remain bp-ivy obligations. No new corpus deferral or ISA repin is implied.

The historical allocator-closure probe retains its original runtime artifact pins.
When live dist contains a newer musl publication, set
`BENNETT_ALLOCATOR_PINNED_ROOT=/absolute/path` to a directory containing
`llvm{18,23}/bennett-runtimes.bc` extracted from runtimes `469246e`; both original
SHA checks remain mandatory. The R hello probe independently checks the musl
publication SHAs, so the historical allocator receipt never stands in for musl.
