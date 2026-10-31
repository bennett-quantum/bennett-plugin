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
