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

Set `BENNETT_ARITH_BITCODE` to the absolute path of the published bennett-arith
LLVM bitcode for the LLVM major being run. The plugin links that explicit input
before analysis and follows introduced numerical helpers through materialisation
and production launches. The input SHA-256 is retained in the module and build
record; repeating the same comparison link is idempotent. An incompatible helper
signature is an input error.

`-bennett-comparison` emits the normalised native comparison module and requires
its soft-float entry points to have definitions. Missing definitions fail loudly
with `unavailable: §13.1 missing entry point <name>` and the bitcode input name.
The plugin contains no replacement numerical library. Tests use clearly marked
integer-only ABI fixtures to check the link path independently of numerical
conformance.
