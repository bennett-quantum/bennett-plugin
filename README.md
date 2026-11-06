# bennett-plugin

The LLVM module-pass plugin of the Bennett compiler core, built for LLVM 18 and 23.
It performs whole-program analysis, region outlining, controlled/adjoint body generation
and lowering to the virtual ISA. Scheduler integration is a binary edge.

Accepted contracts are dialect **0.2.13** and ISA **0.8**, recorded in
[SPEC_VERSIONS.toml](SPEC_VERSIONS.toml). Every sibling input resolves through its
immutable [gate.toml](gate.toml) pin; live sibling working trees are never fallback inputs.

Build with `scripts/build`, then run `timeout 180 scripts/test`.
The full slow integration suite is `scripts/gate`; the push gate owns that run.
See [BUILD](docs/BUILD.md) and [measured quality evidence](docs/quality.md).

Native/device shared globals remain promised and pending the native-sharing contract.
Until it publishes, affected native launch adapters print that diagnostic and exit 125.
The promised execution tests remain available with `--promised-bp-acm` in
`tests/review_regressions.py`.

The ecosystem handoff is [bennett/HANDOFF.md](../bennett/HANDOFF.md).
