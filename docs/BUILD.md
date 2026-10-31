# Building and testing

The source tree targets LLVM **18 and 23**, dialect **0.2.10** (023f5a7), ISA **0.8**.
Builds and tests are offline and headless. All scripts unset DISPLAY,
WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER and use this repo's `.tmp`.
No LLVM graphical view pass is used.

```
scripts/build
```

With CMake installed this invokes a superbuild, configuring the same sources
against `/usr/lib/llvm-18/lib/cmake/llvm` and `/usr/lib/llvm-23/lib/cmake/llvm`.
Outputs are `build/libbennett-plugin-18.so` and `build/libbennett-plugin-23.so`.
A single-major build accepts `-DLLVM_DIR=...`. Without CMake, the script uses
`llvm-config --cxxflags` and g++ directly, with content-digest incremental builds.
The CMake 3.28.3 superbuild was configured, built and loaded on both majors in
the third pass (2026-10-31); bp-ahz is closed. The fallback remains available.

```
/usr/lib/llvm-18/bin/opt -load-pass-plugin=build/libbennett-plugin-18.so \
  -passes='lto<O3>,bennett' -bennett-dialect=0.2.10 -bennett-out=.tmp/out input.bc -o host.bc
```

The plugin registers only an explicit module pass, with no front-end/pre-link
extension callback. `-bennett-pre-link` makes an explicit pre-link invocation inert,
including version checks. Identity is `bennett`, `dialect-0.2.10;isa-0.8`.

Development interfaces (no whole-program production conformance claim):

- `-bennett-analysis-only -bennett-report=<file>` runs recognition/device analysis
  and handle/region checks, emits JSON facts, and leaves marker execution available
  to the test runtime. It emits no device artefact or accept verdict.
- `-bennett-legality-audit` additionally recognises the historical spike ABI from
  the published corpus header. It requires analysis-only and is never a production
  compatibility mode. ABI 0.2 is still checked exactly without it (§21.1).
- `-bennett-oracle=<function> -bennett-scalar-shape='IN(8,zext);tgt=8'
  -bennett-scalar-stack=7 -bennett-out=<dir>` emits `ref.bennett`, a scalar reference
  object. The shape/layout options are test inputs for the canonical map. They do
  not implement the driver's descriptor synthesis, launch stubs or certificates.

## LLVM API adapters

- LLVM 23 moved PassPlugin.h from `llvm/Passes` to `llvm/Plugins`.
- LLVM 23's GEP collectOffset takes SmallMapVector instead of MapVector.
- LLVM 23's Module::setTargetTriple takes Triple rather than a string.
- LLVM 23 uses CondBrInst/UncondBrInst; LLVM 18 uses BranchInst. Both emit the
  same reference branch rows without LLVM23 deprecation warnings.

All LLVM headers remain under `src/`; plugins resolve LLVM symbols from opt.
No dependency on a sibling's implementation or LLVM-linked scheduler is introduced.

## Gates

```
python3 tests/recognition.py --major 18
python3 tests/recognition.py --major 23
python3 tests/scalars.py --major 18
python3 tests/scalars.py --major 23
python3 tests/corpus_gate.py
scripts/install-hooks.sh
scripts/pre-push
```

The published legality harness exposes no plugin argument (`matrix --help` checked).
The independent gate therefore invokes opt itself with each §21.1 opt pipeline
followed by bennett. It bootstraps opaque test-runtime objects by running a copy of
the published harness beneath `.tmp/blackbox`, and reads only generated metadata,
binaries and traces. It does not import or read any harness or runtime source.
It never runs sibling scripts in a mode that writes into the sibling repository.
Each divergence retains its case, pipeline, major, diagnostic and L1–L6 property in
`.tmp/corpus-gate.json`. An unavailable check is never silently skipped. The old ABI-v0 runtime
failures are resolved by the pinned ABI-selecting runtime; the FP arithmetic/native-comparison gap is
deferred: M2 (§13). These are separately counted and printed on every run. Any
other failing property or changed runtime exit is a real divergence (exit 1).
Exit 0 requires all non-deferred/non-blocked cases to agree and no pin drift.

The gate's present dynamic baseline compares the optimised module immediately
before/after bennett; L5 compares llc O0/O3 plus undefined marker symbols. L4
currently checks content keys across the plugin, not semantic equivalence across
stock optimisation pipelines. Rustc/Julia frontend envelopes and clang full-LTO
links are outstanding; reports explicitly state this reduced verification coverage.
The milestone is not complete until these are covered as requested.

Contract drift is detected independently of corpus results. The tests read the
pinned spec via git show; cases/controls live beneath .tmp/contracts and the opaque
harness/runtime/header beneath .tmp/blackbox/<pin>. Drift means a changed accepted
registry or pinned blob digest. A later unaccepted draft/HEAD is reported separately
and does not invalidate an accepted pin. Five policy assertions cover this policy.
The gate never silently changes SPEC_VERSIONS.toml.

## M1b reference/materialisation interfaces

- `-bennett-normalise-only` is a non-production scalar normalisation fixture mode;
  it does not assert full N0–N35/V1–V16 conformance. `tests/materialisation.py`
  compares its instruction lists with five published normalise-out fixtures.
- `-bennett-descriptor-reference` derives static scalar IN/ARG shapes from the
  actual ABI descriptor memory facts (including widths from handle roots), emits
  `oracle-<n>/ref.bennett`, and explicitly reports reference-only output. Dynamic
  shape/device/CC dispatch is unavailable with its owning milestone. Production
  marker compilation still fails at unavailable CC lowering.
- The explicit scalar reference interface now emits a private `materialised.bc`
  alongside `ref.bennett`. It supports FP carriers/constant aggregate returns and
  scalar global images in the standalone fixture layout (data starts at 4096,
  heap at the following page, no heap capacity). It refuses caller-entry memory
  and externally written globals until §8.5 replay is implemented.
- `tests/scalars.py` attempts all 20 published lift blocks: 12 exact objects and
  eight explicit M2 unimplemented results. It compares published interface hashes
  independently with the reference binary and runs all stated vectors for each
  emitted object. The two object-only integration microvectors and every missing
  §16 row are listed in PROGRESS; they are not fixture passes.

The pre-push script runs gate/contract-policy assertions, analysis edges,
materialisation, scalar key and descriptor checks on both majors. The current
counts are 66/65/1/0/0 (run/agree/deferred/blocked/diverge) per major. M1 remains
open for the production/general-analysis obligations listed in PROGRESS.

Every manual build/test/run must use this prefix (create `.tmp` first):

```sh
env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=/home/tobias/Projects/bennett-workspace/bennett-plugin/.tmp /home/tobias/Projects/bennett-workspace/bennett-plugin/scripts/pre-push
```

`scripts/record-verification.py` records the actual artefacts after a successful
M1c run with `.tmp/m1c-pre-push.exit` written by its runner; it asserts the gate's
plugin hashes, accepted pin and all expected checks before updating verification.json.
