# Shared global state at native launch boundaries

Round-2 finding `bp-acm` requires a contract decision about the native caller
adapter. This document requests that decision; it does not adopt a new protocol
or claim that the bug is fixed.

Dialect 0.2.10 §4.3 requires one classical memory shared by H, CC, R and L
entry state. Section 19.4 preserves native H callers unless pointer-rich sharing
requires promotion. The mixed-object requirement `bennett-4ht` also preserves
ordinary native callers and multiple selected module entries.

The ISA 0.8 §10 C API supplies program/run ownership, typed arguments/results,
host requests, reversal and close/unload. Its published header has no operation
to bind, import or export a classical memory range. A layout image supplies
initial data, not shared native storage. Using a native pointer as an ISA
integer address does not connect the two memories.

The regression `tests/review_regressions.py --major M --case global-counter`
links the emitted host bitcode with the published VM library and tests three
observations on both LLVM 18 and 23:

| Native caller actions | Required output | Current output |
| --- | --- | --- |
| Call `top` twice | `1 2 host_global=2` | `1 1 host_global=0` |
| Call `top`, set native `g=40`, call again | `1 41 host_global=41` | `1 1 host_global=40` |
| Call `top`, then another marked entry sharing `g` | `1 2 host_global=2` | `1 1 host_global=0` |

The first row alone could tempt a program cache. A cache still leaves native
`g` unchanged and cannot import the intervening H write. Separate caches for
entries also retain separate device copies of the same source global. Neither
is a fix for §4.3. Promoting every native caller would change §19.4 placement.

The requested decision is the supported classical-state bridge for this
boundary: may the producer publish a versioned copy-in/writeback service using
existing ISA host requests, or should the launch contract supply explicit
memory-transfer/binding operations? Existing integer arguments/results could
also carry bytes through a generated adapter, but that would still need a
published mapping and ownership convention, not an unchecked host-pointer cast.

Whichever route is selected, its publication must specify:

- Source global identity, selected component ownership and native/device
  address correspondence, including globals shared by several entries.
- Copy-in of current H bytes and copy-out of device writes, including aliases,
  with the §19.4 promotion rule for pointer-rich reachable storage.
- Program context lifetime, compatible component linking, and handle/token
  namespaces; a function-local static cache cannot decide these for the native
  container.
- Memory ownership while a run is active, writeback of completed or faulted
  prefixes, and how reversal restores the host-visible state before subsequent
  H mutation or reuse.
- The adapter service/schema or C API, and the component metadata that lets
  plugin, driver, runtime and executor independently implement the same bridge.

This requests the smallest bridge needed to implement the existing shared
memory semantics. It does not request whole-process-only placement, private
access to VM memory, a change to the ISA 0.8 inner object grammar, or a silent
ISA upgrade. The general mixed-object audit is deferred; the determining
blocker here is the concrete P0 loss of an ordinary shared scalar global.
