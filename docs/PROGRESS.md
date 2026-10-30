# Progress — 2026-10-30

**M1 is not complete.** The verified implementation slice is committed; the epic
bp-a41 remains open. No push. Contract: dialect 0.2.6,
ff249d597f767f8034176bbb6c0f86dea3b90270; ISA 0.8.

## Verified implementation

- `scripts/build`: libbennett-plugin-18.so and libbennett-plugin-23.so build/load
  using installed llvm-config/g++. No CMake executable exists on this offline
  machine: the CMake superbuild still needs configure/build validation (bp-ahz).
- `tests/smoke.py`: both majors load the explicit module pass; pre-link is inert
  even with invalid dialect/options/marker definitions. All 23 published header
  prototypes compile and pass recognition, and 23 malformed signatures per major
  produce BD-E-MARKER-SIGNATURE. Content keys ignore function names and retain
  referenced global images.
- `tests/recognition.py --major {18,23}`: **61/61 on each major**, extracted from
  the pinned published examples. Includes bitwise pointer/integer and memory
  copies, field/lane provenance, dynamic lanes, handle errors and containment,
  indirect calls, region candidates, aliases/thunks, deferred measurement and
  measurement rejections. PT6 byte reconstruction and partial-load TOP facts are
  asserted, not just successful exit codes.
- `tests/scalars.py --major {18,23}`: **9/9 on each major** pass the ISA reference
  binary's `check`, reproduce each complete published object byte for byte,
  reproduce interface hashes, and pass every stated run/budget vector (including
  classical ARG vectors). A plain C inc8 through clang O3 produces the same object.
- ISA `step-check --exhaustive`: inc8 and switch5 each pass **256 inputs** and
  target/fault XOR delivery. The optional add2 exhaustive step-check exceeded
  60 seconds; its check/hash and all stated run vectors pass. It is not claimed
  exhaustively step-checked.

## Pinned corpus gate

There are **62 cases and 4 controls** at the pin (66 total, enumerated from git).
The independent driver runs all of them through the opt envelope plus bennett.
The published harness exposes no plugin option, so it is run opaquely in a scratch
copy only to obtain test-runtime binaries/baseline metadata. No sibling checker,
interpreter, harness or runtime implementation is read/imported. No sibling is edited.

| LLVM | Cases run | Agree | Diverge | Cells run | Cells agree | Cells diverge |
|---|---:|---:|---:|---:|---:|---:|
| 18 | 66 | 63 | 3 | 924 | 892 | 32 |
| 23 | 66 | 63 | 3 | 792 | 764 | 28 |

Every divergence, on **both** majors:

| Case | §21.1 property | Pipelines | Evidence / remaining work |
|---|---|---|---|
| fp-rot-fastmath-reassoc | L5: codegen retains the dynamic sequence/operand values | default<O0>, strip, strip-nondebug, mergefunc | llc O0/O3 traces differ while fast-math survives; full materialised FP normalisation is not implemented (M2, §12 N2 / §13) |
| spec-sem2-adj | L1 and L5 | all 14 pipelines on 18; all 12 on 23 | black-box runtime exits 87 before/after the plugin; ABI 0.2 runtime/harness issue bp-c2i |
| spec-sem2-compute | L1 and L5 | all 14 pipelines on 18; all 12 on 23 | same black-box ABI 0.2 runtime failure, bp-c2i |

The attribute/dereference negative controls fail with their stated diagnostics.
The source pure-attribute lie is diagnosed as required by §3.8 (EXPECT: probe).
`control-region-twin` passes content identity: its historical negative label is
incompatible with §7.3, recorded as bp-tye rather than reintroducing symbol identity.

The gate records immutable plugin SHA-256 values. During work the dialect moved to
**95c3cd332f5f72c07fd5f2515f328deaa40c08b9**. Tests use `git show` at ff249d5;
the gate materialises pinned fixture blobs and reports newer text/HEAD as drift,
with nonzero exit. No automatic re-pin was made (bp-y3l).

**Verification limits:** L1 currently compares the optimised module immediately
before/after bennett. L4 checks content identity across the plugin; it does not
establish cross-stock-pipeline materialised equivalence. Full §12 normalisation,
frontend LTO/rustc/Julia envelopes and full production objects are not claimed.
These limits are part of the result, not silent skips or full conformance passes.

Raw final cells: `.tmp/corpus-gate.json`. Stable counts, pipeline lists, plugin hashes,
all object/interface hashes and run results: [verification.json](verification.json).

## Scalar oracle interface hashes

Each object below is independently generated on both majors, checked with the
reference binary, and byte-identical to its pinned §16 fixture. `object_hash` and
L1 lproc hashes are also retained in verification.json.

| Object | @ref interface hash |
|---|---|
| oracle-empty-output | `358a1b87139653df3c5a82465215f8af96a12d0e8ad02610e04696c2d588a91c` |
| oracle-empty-fault | `863fd42e300d5bba79d561ceca8c8b72ee1ad384d60f770d961cf25a8e258181` |
| oracle-discard-return | `622ca26e17519d6e64af5f64f8e0f9c3d9af6c5d36a97740de5d6cbc2b2f62f3` |
| pointer-as270 | `62693b6dfefab4480cce6de8257132bcc9fead16250518602c354083332dd16a` |
| gep-index-obj | `5b3c7d1f368fcc8c24286cc303a71c12b5b615f467149f29928099befd3de534` |
| gep-index-const | `591f1b48288e000c626c349165ead9ff9158c05c472c9c569bfec3dac42de091` |
| inc8 | `151baad5625b3605eadf87005a19ea6e012e4347d6dfe096dbc4edcf2b68b94a` |
| add2 | `5b4c6624e0f20b5d60780fd8f27056f3f7efd4d27b9d47af8a70c8126100a10a` |
| switch5 | `0575354a0ecceee58d8dfbcc5cb9a9b8851c5c2b3193bf543395bed13604ce80` |

## Remaining M1 work and milestone order

- Validate CMake builds (bp-ahz) and complete the legality gate's full materialised
  comparison obligations; resolve the upstream trace-runtime dependency.
- Finish the reference-analysis audit beyond the 61 witnesses: byval copy objects,
  packed bit resegmentation/composite operations, atomics, exact host/boundary
  variant seeding and generation-sensitive reversible tiers. Unsupported paths
  fail explicitly; full §5 conformance is not asserted.
- Content keys are currently computed before full materialisation. Complete the
  §7.3 materialised-key contract together with the full normaliser.
- Integrate the scalar map with recognised marker descriptors and production
  launch/object outputs. The current scalar interface emits reference objects;
  it does not implement the driver's descriptor synthesis or whole-program launch.
- M2: complete normalisation, lifted memory/calls, FP/vector/wide lowering.
  M3: generation, TDL, CC/R, controlled/adjoint bodies and bounded blocker paths.
  M4: full integration/rungs 4–8. M5: remove ISA dependencies after acceptance.

Only the plan task bp-a41.1 is closed. The four implementation/gate tasks remain
in progress with verified evidence and remaining work in their descriptions.
Blockers stay explicit: bp-2tw (BLK-1), bp-2bi (BLK-2), bp-ckk (BLK-4), bp-is0
(BLK-5). No status-3 blocked compilation is claimed without actual blocker-trap
objects. Unavailable production lowering uses explicit unimplemented diagnostics,
never a fabricated dialect rejection or silent native-marker fallback.
