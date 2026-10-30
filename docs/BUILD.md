# Building and testing

The source tree targets LLVM **18 and 23**, dialect **0.2.6** (ff249d5), ISA **0.8**.
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
The offline development machine has no CMake executable: the direct builds are
verified, while the CMake superbuild still needs an actual configure/build check.

```
/usr/lib/llvm-18/bin/opt -load-pass-plugin=build/libbennett-plugin-18.so \
  -passes='lto<O3>,bennett' -bennett-dialect=0.2.6 -bennett-out=.tmp/out input.bc -o host.bc
```

The plugin registers only an explicit module pass, with no front-end/pre-link
extension callback. `-bennett-pre-link` makes an explicit pre-link invocation inert,
including version checks. Identity is `bennett`, `dialect-0.2.6;isa-0.8`.

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
- BranchInst remains available but is deprecated on 23; no semantic adapter needed.

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
`.tmp/corpus-gate.json`. An unimplemented check is a failing cell, never skipped.

The gate's present dynamic baseline compares the optimised module immediately
before/after bennett; L5 compares llc O0/O3 plus undefined marker symbols. L4
currently checks content keys across the plugin, not semantic equivalence across
stock optimisation pipelines. Rustc/Julia frontend envelopes and clang full-LTO
links are outstanding; reports explicitly state this reduced verification coverage.
The milestone is not complete until these are covered as requested.
