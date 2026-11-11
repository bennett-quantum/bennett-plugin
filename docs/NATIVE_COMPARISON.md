# Materialised native comparison adapter

`bennett-native-comparison` adapts an emitted `device.bc` for native codegen.
It checks the selected entry and the exact device/build artifacts against that
entry's `launch-record.json`. It also rejects IR transformed before adaptation.
The original artifacts remain the source of materialised identity. Codegen,
native transports and launch-context storage belong to the comparison backend.

For example, with the matching LLVM major:

```sh
opt -load-pass-plugin=build/libbennett-plugin-18.so \
  -passes=bennett-native-comparison \
  -bennett-native-record=out/ht_demo_basic/launch-record.json \
  -bennett-native-entry=ht_demo_basic \
  -bennett-native-report=native.json out/device.bc -o native.bc
```

The entry name is configurable. The adapter does not replace process startup
or assume the marked module contains `main`. An ordinary host module can link
against the resulting component. Its source globals retain one definition.
The adapter creates aliases for private and unnamed definitions, with their
source keys, types, sizes and alignments recorded in `native.json`.

The report's `binding_symbol` names a function with C type
`void (bennett_program_t *)`. The caller loads the actual ISA object through
the public launch API, binds its program, and keeps that program alive while
calling the native component. The caller owns entry ordering and context
lifetime. Register allocation/free call the real `bennett_qreg_new/free`
functions; source marker symbols receive no replacement definitions.
An unbound component or backend infrastructure failure calls the published
native infrastructure callback. Invalid source register operations retain
their semantic fault path.

For a reversible entry, binding also calls its materialised shadow-stack
initialiser with the exact size in the checked build record and initialises
the source-step state. Source-step enforcement, exit propagation and R tape
semantics remain separate requirements. In particular ISA 0.8 R artifacts
still report `BD-B-ISA7`; native hello output cannot upgrade that verdict.

Console calls in the component use the published
`__bennett_rt_native_console_write` transport. When ordinary host code and its
production runtime are linked afterwards, run `bennett-native-host-imports`
before final native-support closure. It adapts newly imported host console
calls. It refuses markers introduced into protected materialised functions.
Materialised functions retain their bodies when runtime libraries are linked;
only the documented native primitive/transport overrides are applicable.

## Resolved addresses

Link a native comparison image without PIE, function folding or constant
merging. Read each report alias from the final ELF symbol table. Include
ordinary host data, runtime data and backend data when resolving the image's
data end and first following heap page. The host must use the same layout
whenever pointers cross its marked-module boundary.

The driver supplies `-bennett-comparison-layout=resolved-layout.json` on the
production invocation. The adapter's native report supplies the fingerprint
and symbol correspondence for this JSON format:

```json
{
  "schema": "bennett-comparison-layout-1",
  "ptr_width": 64,
  "materialised_structure_sha256": "<from native.json>",
  "data_end": 12345,
  "heap_base": 16384,
  "globals": {
    "name:example": {
      "address": 12288, "size": 8, "alignment": 8,
      "native_symbol": "<alias from native.json>"
    }
  },
  "functions": {
    "entry": {"address": 4198400, "native_symbol": "<alias from native.json>"}
  }
}
```

The numbers above only illustrate the schema. Actual numbers come from the
resolved link. The plugin checks source correspondence, object size/alignment,
overlaps, distinct function addresses and the heap page. Every required source
global/function must have a mapping. There is no sequential-address fallback
when a map is configured. The map drives CC and scalar images, pointer
relocations and indirect-call dispatch. Its digest is recorded in CC launch
records. Without this option the existing default layout remains unchanged.

The structural fingerprint removes comparison address metadata, omits the
input-path ModuleID and uses the matching LLVM bitcode reader's ABI defaults.
`-bennett-comparison-structure-report=PATH` writes the canonical IR for an audit.
The driver remains responsible for the truth of its ELF addresses and for
keeping addresses fixed when it embeds final objects and configuration tables.
For a production mixed object, differing H stubs and device bodies also need
the same logical function addresses. The future driver link must reserve
stable function slots or emit fixed-address forwarding functions, route each
tier's direct calls to its selected body, and keep stored function pointers at
the common logical address. That publication and address audit belongs to
bp-a2r; this adapter supplies the materialised component and real symbol map.

## Verification and remaining acceptance

`tests/native_comparison.py` checks native arithmetic and real register calls.
`tests/native_layout.py` compares actual native and ISA pointer values, global
pointer initialisers and indirect calls, checks invalid maps, and verifies
unchanged default output. `tests/native_fixtures.py` uses the unchanged public
hashtable and golden harness; `--host-link before` also reproduces the larger
whole-program analysis path tracked by bp-xv0. `tests/native_hello.py` uses the
actual R hello materialisation while retaining its ISA-7 blocker.

The test linker uses an ordinary host launcher. It flushes the actual program
runtime before returning to its host CRT, isolates program libc symbols from
the launch-library DSO, and fills fixed-size native-only tables after resolving
the ELF. It does not certify the driver's freestanding startup path. The
native-only support bytes are separately pinned and never replace the
production runtime pin.

For external memory and division checking, add `-bennett-native-prepare-only`
to the first invocation. This publishes aliases and provenance without adding
backend globals/functions. Run the matching published `native-check` binary on
that result, then `-passes=bennett-native-comparison-finalise` with a native
report output path. Finalisation checks the prepared source correspondence and
adds register/transport adapters afterwards. The external checker owns its
receipt; finalisation alone never certifies that checks were applied.
`tests/native_checked.py` exercises legal allocation padding and actual native
and ISA faults for dead/out-of-range memory, without instrumenting backend
bookkeeping. Machine code uses `llc -O2` without a second source IR optimisation
pipeline.

Receipts distinguish these checks from complete comparison acceptance. The
driver still owns complete instrumentation, original-source definedness
classification, startup and outcome comparison. General H/device tier
selection and the full mixed-object publication remain bp-a2r obligations.
The original materialised bodies, unmarked host modules and shared globals
must remain identifiable through that work.

The proposed isolated gate dependencies are in
[`native-comparison-gate.toml`](native-comparison-gate.toml). They use a separate
alias for native-only runtime support/tools, the actual VM C library, target
data and public C fixtures. `BENNETT_NATIVE_SUPPORT_PINNED_ROOT`,
`BENNETT_NATIVE_TOOL_ROOT` and `BENNETT_VM_NATIVE_LIBRARY` select those
publications. The native support/tool digests are in `SPEC_VERSIONS.toml`.

## R device-global correspondence

R production publishes `build.json.native_global_mapping` with schema
`bennett-device-native-globals-1` and a `globals` object keyed by the exact
ISA device-global ID. Each value contains `source_key` (the same identity as
native report global rows), `base` and `size` (the fixed ISA layout values).
The producer records this association when assigning device IDs, including
pointer-initializer dependencies. It is adapter metadata, outside ISA `layout`.
The selected entry's launch record authenticates the build file, device bitcode
and launch object by SHA-256; consumers must verify those artifact bindings.

For R entries, both preparation and finalisation reports additionally retain
`device_globals`, keyed by those device IDs, with the same three fields plus
`native_symbol` from the explicitly matching `symbols` row. `launch_sha256`,
`record_sha256`, `materialised_sha256` and `entries` bind the mapping to the
selected immutable publication. The adapter checks completeness, unique source
identities, sizes and fixed bases against the authenticated build layout before
publishing aliases. Additional native/library symbols have no implied device ID.
Consumers must use these explicit associations to reserve their native addresses;
row order, object numbering and byte/size matching are not correspondence rules.
This report does not by itself resolve a native link or certify address equality.
