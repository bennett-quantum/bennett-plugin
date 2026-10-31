# Seventh pass final evidence — 2026-10-31

**bp-2zv remains OPEN; this pass does not complete M1 or any full acceptance
group.** Base 32427ed; implementation commits 55d3b0d, ba7f0d8, c8b477b.
No push, sibling modifications, repin, remaining-lift/key-audit expansion or new
deferrals. Accepted dialect 0.2.10 @ 023f5a7 and ISA 0.8 are unchanged.

| Group | Landed | LLVM 18 and 23 tests | Commit |
|---|---|---|---|
| 1 descriptors/environments | OUT/MEM_IN, CLOCK/BLOCK/CONSOLE production bindings, same-layout distinct scalar references, direct handle/scalar block parameters | 7/7 new objects check/run per major; four binding references full-byte exact | 55d3b0d |
| 2 budget tables | JCS table parsing, per-component key/symbol precedence, unmatched/raw/explicit frozen maxima, once-only identity overlays, explicit precedence | 4/4 table objects check/run per major; published sstack vector still red (bp-piq) | ba7f0d8 |
| 3 records | Supplementary artifact SHA-256/size inventories and every emitted instruction's coverage | 5/5 record cases per major; 30/30 existing metadata sidecars byte-stable; checked certificates still incomplete (bp-o7f) | c8b477b |

The before and after **full headless pre-push gates both exit 0** against fixed
binaries. No build occurred during either corpus phase.

| run/agree/deferred/blocked/diverge | Before | After | cells agree/run |
|---|---|---|---|
| LLVM 18 | 66/65/1/0/0 | 66/65/1/0/0 | 920/924 |
| LLVM 23 | 66/65/1/0/0 | 66/65/1/0/0 | 788/792 |

Sole corpus deferral: fp-rot-fastmath-reassoc / bp-7ni (existing M2 §13).
All 16 scalar goldens / 40 vectors per major, C O3 inc8, descriptor-reference
inc8, four binding lifts and five production inc8 references remain exact.
Measured inc8: 6/6 runs per major plus the unmodified published fixture; native
ABI and protocol mocks pass. They still are not linked launch-library acceptance.
All 34 prior sixth-pass per-file digests are unchanged. All 30 build/certificate/
CC-coverage sidecars captured before group 3 remain byte-identical afterwards.

## Exact remaining acceptance obligations

- **bp-dw4:** finite descriptor/candidate/kind/mode/width dispatch and invalid-field
  runtime traps; general handle memory/static files/generation tags/call/result
  environments; combined devices/null console, multiple output slices, heterogeneous
  region/data layout linking and production inplace/INOUT. Fresh finite-kind and
  memory-handle probes both exit 1 on both majors, respectively at §8.4 finite
  dispatch and `%slot = alloca ptr`. Determining §8.4: “the caller's tier reads the
  descriptor and selects the compiled shape with the compare tree of §14.2”.
  §17.4 requires marker calls with “the handle register environment of §6.5”.
  These are plugin implementation gaps, not missing ISA capabilities.
- **bp-piq:** published budget-stage-runtime still exits 1 on both majors at
  `store i8 %x, ptr %p` (entry-state replay/shadow-stack memory). Its H16→H32
  selection/final hashes and 316-row vector are not reproduced. Determining §9.2
  step 3: provisional objects use “baseline `sstack` and other baseline wrapper
  inputs”; step 4: “Apply this overlay once only. Generate the final object using
  the resolved values”. Shadow-stack runtime lowering/final regeneration and
  general finite/launch-supplied budget token selection remain required.
- **bp-o7f:** checked target/schedule-bound executable claims, complete build/runtime/
  arith/asm/snapshot provenance and real linked launch-library acceptance remain
  unimplemented. Dialect §19.9 requires “the certificate (ISA §12)” and the resolved
  build record. ISA §12.3: executable claims “bind to `schedule_hash` through their
  subject”; §9.2 requires closure-hash bindings. Published D-expected-oracle-claim
  itself marks the checker/ref expansion unavailable (b-isa-spec-8r4/bennett-vm-47t).
  Only negative f_cert_unknown_field bears a certificate section; no positive
  published certificate-bearing LLVM/object pair can currently be reproduced.
  This publication gap does not discharge the plugin implementation obligations.
- **bp-95o:** paired published production CC golden remains absent. Determining
  §17.4 says CC/R lowering “is plugin-defined and constrained by §18.7”. Useful
  cross-major equality and independent execution do not invent published bytes.

The artifact records explicitly say metadata_only / checked_executable_claims=false.
The existing certificate sidecar still has empty regions; none is called proof.
No North-Star capability is excluded. Remaining lifts and the key audit were not
expanded; Grover over unmodified SQLite remains core.

## Complete byte-for-byte inventory

Each row compares the full object file on LLVM 18 and 23. **51/51 pairs equal**;
**27** match a complete published golden and **24** have no paired golden for the
lowering/resolved layout. Full per-major paths, sizes and SHA-256 values, independent
check/run outputs, table resolutions and red probes are in verification.json
`seventh_pass`. “Absent” is not a published-byte acceptance claim.

| Object | Published full bytes | 18 vs 23 | SHA-256 (both majors) |
|---|---|---|---|
| `scalar/oracle-empty-output` | exact oracle-empty-output | equal | `b5755ea206e8c3607294260c17a2f01de8ac93325d89103e5856bfcc319770c3` |
| `scalar/oracle-empty-fault` | exact oracle-empty-fault | equal | `9921c79836b9be667edaa6aa162127237ac99c5256c3973b03479cae2bd3f559` |
| `scalar/oracle-discard-return` | exact oracle-discard-return | equal | `0217762689e4944d8d959a516b95c335d6ea688e8ccad2fd7f87f7ccaab70eb8` |
| `scalar/atomic-nand` | exact atomic-nand | equal | `b7dca42645f46355312ed0d359f1ec72b7de899ee79b5914a5ea46f0f395af28` |
| `scalar/pointer-as270` | exact pointer-as270 | equal | `2c731bbcbf282cfd0119bc42feb53efcf624cdf1fa60942c0a9199222a8fa6bc` |
| `scalar/gep-index-obj` | exact gep-index-obj | equal | `364640c0f4a947a93dc7d85db13ce68eba270ed435a1e6ee950e9b2a35542bcb` |
| `scalar/gep-index-const` | exact gep-index-const | equal | `7e465780032222ca1d36c3a37295ad4ca9a86ee3f571db69c65f760688fb30e2` |
| `scalar/binding-out-byte` | exact binding-out-byte | equal | `94642c83d654e907ea6cb34af7bc3849d06b8fc3b127f56a235f1fff934d3581` |
| `scalar/binding-clock-read` | exact binding-clock-read | equal | `ced3e13e4bc7af8325b951b93cc8b87b54437f6cbe2b8b5156074309faba8e6e` |
| `scalar/binding-block-byte` | exact binding-block-byte | equal | `a0dbb16a79d34b95af199a6bf1fe3394589b8896e5556db9475460365a3d146c` |
| `scalar/binding-console-byte` | exact binding-console-byte | equal | `c396e3caa70f02c3f2ef1cd26ea7b565013a6798c45fea920f50da7a303237bf` |
| `scalar/indirectbr-two-blocks` | exact indirectbr-two-blocks | equal | `92802f732ce75ad94733a3c67e97fec44a4d2cc26099c3338379218bb01b9718` |
| `scalar/inc8` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `scalar/add2` | exact add2 | equal | `a9660ece18422bc64557cb19f02d980339b44fa77b572e81dbc543716606f5d1` |
| `scalar/switch5` | exact switch5 | equal | `1adefd004c93443ff7814b939dc85dd609104ada65d54e5b98398f1448208280` |
| `scalar/fp-aggregate` | exact fp-aggregate | equal | `1b06c23f4f195a7f8b6c2cc556c8f50495ddd7c395b55c1754dc54c980b7ce5a` |
| `scalar/c-O3-inc8` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `descriptor-reference/inc8` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `descriptor-production/smoke/launch.bennett` | absent | equal | `54be8166989d5b58916aacdc041f25c6563f69de369a61868a57c1d47b686075` |
| `descriptor-production/smoke/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/0/launch.bennett` | absent | equal | `d5ae5d065001cf94ab65611f58f68f89b06fc9a61aa66d29be4447229e8eeb25` |
| `production/0/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/7/launch.bennett` | absent | equal | `c28286b6553e8898e0a46da18fa6fb026b53bb6a73f35b98f546b635a3421cbf` |
| `production/7/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/255/launch.bennett` | absent | equal | `e982723ef9cc4dd66e82a61c1b24f62c6290dbdbc4d62a695f94f4356321f1ae` |
| `production/255/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/published/launch.bennett` | absent | equal | `fcb11ca7194f835598ba8d2cae2133eacc628634baca2f2fc205915e7f042eb6` |
| `production/published/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/abi/launch.bennett` | absent | equal | `848f2628b2b5d9c5f64428b3e4cd0f25537622ee799691a467294f8b1d5149a3` |
| `production-shapes/binding-out-byte/launch.bennett` | absent | equal | `7b5e193670571ef6099ab43d45256e64cc5751a9a9855576dbfda8453a38a37d` |
| `production-shapes/binding-out-byte/oracle-0/ref.bennett` | exact binding-out-byte | equal | `94642c83d654e907ea6cb34af7bc3849d06b8fc3b127f56a235f1fff934d3581` |
| `production-shapes/binding-clock-read/launch.bennett` | absent | equal | `be97b2e3111edea3c82092bacdf521ef723c96794a5004e37f73454699f05a45` |
| `production-shapes/binding-clock-read/oracle-0/ref.bennett` | exact binding-clock-read | equal | `ced3e13e4bc7af8325b951b93cc8b87b54437f6cbe2b8b5156074309faba8e6e` |
| `production-shapes/binding-block-byte/launch.bennett` | absent | equal | `493f49f47c21104c3acc2804e53a5b90f4b42e43a94f850cd6ad21734804990c` |
| `production-shapes/binding-block-byte/oracle-0/ref.bennett` | exact binding-block-byte | equal | `a0dbb16a79d34b95af199a6bf1fe3394589b8896e5556db9475460365a3d146c` |
| `production-shapes/binding-console-byte/launch.bennett` | absent | equal | `3f557329da95e54c7fe78bebfedd24ef12c69bd127bae774d1f47160b69f3963` |
| `production-shapes/binding-console-byte/oracle-0/ref.bennett` | exact binding-console-byte | equal | `c396e3caa70f02c3f2ef1cd26ea7b565013a6798c45fea920f50da7a303237bf` |
| `production-shapes/mem-in/launch.bennett` | absent | equal | `9bf3598072a685bf3f89519105ad1bbf2c9339d6bad09ba4f3642a67851771c7` |
| `production-shapes/mem-in/oracle-0/ref.bennett` | absent | equal | `9915a0b7cc0b73a87bb5a60ef9496f393df92be7bbda0a8d56d85ce2d4c09801` |
| `production-shapes/two-regions/launch.bennett` | absent | equal | `fc93758d35d26c7d22354a460f167c7b4658e16ff59fc62eaf1aaab358ec16d8` |
| `production-shapes/two-regions/oracle-0/ref.bennett` | absent | equal | `177dc4fb7351433086dbe19fffe4438e5ff909a3a0868cd56ebac9c30080bacf` |
| `production-shapes/two-regions/oracle-1/ref.bennett` | absent | equal | `bca59c9f01201d288c8c62c10661fffbc95c5c3f974d31374114d297eea499ee` |
| `production-shapes/handle-phi/launch.bennett` | absent | equal | `0f6ed34c62b4742b0df3928dbafb8426ab829fdbe5d768c590ecbf391dd235d1` |
| `production-budgets/baseline/launch.bennett` | absent | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/baseline/oracle-0/ref.bennett` | absent | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/identity-once/launch.bennett` | absent | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/identity-once/oracle-0/ref.bennett` | absent | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/key-priority/launch.bennett` | absent | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/key-priority/oracle-0/ref.bennett` | absent | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/explicit-precedence/launch.bennett` | absent | equal | `970cd2de98b9c795e10b02b39bfe36113da562cdd485962570b93ebb63c9f242` |
| `production-budgets/explicit-precedence/oracle-0/ref.bennett` | absent | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |

---

# Seventh pass implementation notes — 2026-10-31 (historical sequence)

Base 32427ed. Unchanged full headless gate exits 0: both majors
66/65/1/0/0 run/agree/deferred/blocked/diverge; cells 920/924 (18),
788/792 (23). No new deferrals, push, sibling changes or repin.

Group 1 red→green on LLVM 18 and 23: four production binding descriptors
(OUT, CLOCK, BLOCK, CONSOLE), MEM_IN, two distinct scalar reference symbols
sharing a layout, and direct handle/scalar phi block environments. Seven new
objects independently check and execute per major, with equal cross-major bytes.
Four emitted binding references equal the complete published bytes; the existing
16 scalar objects / 40 vectors and three measured inc8 fixtures also pass.
The five production inc8 references remain exact. The absent paired CC golden
is still bp-95o; cross-major equality does not replace published-byte equality.

Group 1 is partial acceptance: finite descriptor/candidate dispatch (§8.4),
static register files and general memory/call environments (§6.5), combined device
bindings/null console (§8.3), multiple output slices (§8.6), and heterogeneous
multi-region layout linking (§16.3) remain implementation obligations. Determining
§17.4: “marker calls lower to the region calls and `qreg.*` instructions of §18.3
with the handle register environment of §6.5”. No capability is out of scope.
Group 2: staged JSON table input now resolves component-wise region-key/symbol
precedence, unmatched-entry maxima, a once-only identity overlay, and explicit
record precedence. Four independent table launch cases pass per major. Frozen
capacities are computed before any shape, including explicit static records.
The inc8 fixture now supplies its published linkmap defaults explicitly, so
freezing all effective defaults does not accidentally enlarge its golden layout.
OUT/CONSOLE allocation capacity is a maximum, not an addition to budget capacity.
No-table build/certificate metadata bytes retain their schema and values.

**Published budget-stage remains red**, both majors: entry-state replay /
shadow-stack memory at `store i8 %x, ptr %p`. New bp-piq tracks the exact M1
obligation: §9.2 step 3 requires the provisional reference object “with baseline
`sstack` and other baseline wrapper inputs”; the staged shadow-stack H16→H32
hashes and 316-row vector are not reproduced. This is missing plugin mechanics,
not a spec blocker or a new M2 deferral. Group 2 is therefore partial acceptance.
Group 3: supplementary launch-record.json binds final host/device bitcode,
launch manifest, all oracle references and sidecars by full SHA-256/size.
all-coverage.json enumerates every emitted CC/oracle/lproc/action instruction.
Five inventory/coverage cases pass on each major. All **30/30 existing build,
certificate and CC coverage sidecars are byte-stable** across this group.
These additions do not claim certificate acceptance: launch records explicitly
say metadata_only and checked_executable_claims=false.

**Executable certificates remain incomplete** (bp-o7f): ISA §12.3 requires
“Executable claims … bind to `schedule_hash` through their subject”, and §9.2
requires closure bindings. The published D-expected-oracle-claim marks its checker
and ref@0.8 expansion unavailable upstream (b-isa-spec-8r4/bennett-vm-47t);
only the negative f_cert_unknown_field object bears a certificate section.
There is no positive published certificate-bearing LLVM/object pair to reproduce.
The plugin also still needs actual target/schedule-bound checked claims, complete
runtime/build provenance and real linked launch-library acceptance. These plugin
obligations remain required independently of the publication gap.

---

# Sixth pass — 2026-10-31 (scalar CC launches landed; bp-2zv acceptance still open)

Started at **a2bce18**. Implementation **bc14d48**, native ABI fix **563ca6a**.
Accepted dialect **0.2.10 @ 023f5a7**, ISA **0.8** unchanged. No push, sibling
modification, key-audit/remaining-lift expansion or new M2 deferral.
**This is partial completion of bp-2zv, not full production or M1 acceptance.**

## Actual red → green implementation

- Production probes on LLVM 18 and 23: **exit 1/no artifacts → exit 0/launch
  artifacts**. Both the C-built descriptor and the unchanged published
  `oracle-inc8` LLVM fixture lower. Their reference objects equal the complete
  published inc8 bytes; the published fixture also runs COMPLETED/CLOSED.
- CC has direct fixed-width handle bindings, `qreg.new any`/`qreg.free`, scalar
  integer arguments/results/arithmetic/select/branches, host-minted token
  parameters and `oracle_call`. Singleton IN/ARG descriptors are read at the
  call; local record storage is elided only after checking its complete uses.
  Default budgets and constant explicit records use the published layouts.
- Fixed-index one-wire gates become action calls. Measurement copies the named
  wire into a fresh one-wire register and measures the copy, leaving the source
  handle live as the marker ABI requires. Three measured inc8 launches test
  **0→1, 7→8, 255→0**, each with five-step and four-step oracle tokens: **6/6
  executions per major**, plus the published fixture. Repeating the oracle
  cleans target/fault before free; input preparation is also undone.
- Host entries are replaced by stubs using the actual launch 0.8 C ABI:
  load/args/budget/run/wait/result/close/unload. They embed the generated ISA
  bytes and read target JCS from `BENNETT_TARGET`. Native integer parameter and
  result ABI attributes survive replacement (signext regression red→green).
  Three compiled native protocol witnesses per major verify calls, values,
  cleanup and embedded bytes. They are **mock launch-library witnesses**, not
  linked launch-library execution; the independent ISA CLI executes the objects.
- Outputs include host/device bitcode, per-entry ISA object, launch manifest,
  build record, hash-bound certificate metadata, coverage and blocker sidecars.
  Object/interface/closure/build hash bindings are independently checked.
  **The certificate metadata has no checked claims and is not a complete
  target/schedule-bound executable certificate.**

The initial full gate was invalidated by the ABI rebuild during its corpus
phase; the digest guard exited 1. It is not a valid passing or failing corpus
baseline. The final full gate is rerun against fixed binaries and recorded in
verification.json. Before means the fresh unchanged-binary corpus command,
not a fresh full unchanged-code pre-push run.

| Corpus totals (run/agree/deferred/blocked/diverge) | Before | After stable full gate |
|---|---|---|
| LLVM 18 | 66/65/1/0/0 | 66/65/1/0/0 |
| LLVM 23 | 66/65/1/0/0 | 66/65/1/0/0 |

Final headless `scripts/pre-push`: **exit 0**. The sole corpus deferral
remains fp-rot-fastmath-reassoc (bp-7ni, M2 §13). Sixteen complete scalar golden
objects and all **40/40** published vectors per major remain exact/passing;
C O3 inc8 and descriptor-reference inc8 stay exact. The four remaining lifts
and two object-only obligations are untouched and still required.

## Byte evidence: published references versus generated CC objects

| Object(s), each on LLVM 18 and 23 | Published full bytes | Cross-major bytes |
|---|---|---|
| inc8 lift, C O3 inc8, descriptor-reference inc8 | exact | equal |
| binding-out-byte | exact | equal |
| binding-clock-read | exact | equal |
| binding-block-byte | exact | equal |
| binding-console-byte | exact | equal |
| production references: C descriptor smoke, measured 0/7/255, published oracle-inc8 | exact inc8, five separately emitted objects per major | equal |
| CC: C descriptor smoke | no paired published golden | equal |
| CC: measured-0 | no paired published golden | equal |
| CC: measured-7 | no paired published golden | equal |
| CC: measured-255 | no paired published golden | equal |
| CC: published-oracle-inc8 | no paired published golden | equal |
| CC: integer-ABI allocation/free witness | no paired published golden | equal |

Every emitted launch object is checked against ISA syntax/identity and its
executed semantics; the ABI-only object additionally verifies the host IR.
The C descriptor smoke has a single oracle followed by free of its dirty target:
compilation is valid but that source's run must trap; it is not substituted for
the clean, twice-invoked execution fixtures. Per-file full SHA-256, byte counts,
checker hashes and exact paths are in verification.json's `sixth_pass`.
There is **no published CC-byte equality claim**: §17.4 makes CC/R lowering
plugin-defined, and the pin supplies oracle/lproc references rather than a
paired CC lowering golden. New **bp-95o** tracks that exact acceptance evidence
requirement. ISA suite-G launch vectors validate the launch ABI; their objects
are not published as the lowering of the dialect's scalar descriptor fixtures.

## Exact remaining bp-2zv sub-items (all M1, none out of scope)

1. Production scalar OUT/MEM_IN and device descriptors (including launch paths
   for the four already-exact reference binding lifts), multiple distinct
   shapes/regions, finite dispatch and general handle/CC SSA-memory/call
   environments. These paths still diagnose unimplemented. Determining dialect
   §17.4: “marker calls lower to the region calls and `qreg.*` instructions of
   §18.3 with the handle register environment of §6.5”; §8.2/§8.3 define these
   bindings. The implemented singleton IN/ARG path does not waive the others.
2. Full §9.2 budget-table selector/identity overlays and frozen componentwise
   maxima. Defaults/constant explicit records now work, but the table-input
   path is missing. Determining sentence: freeze capacities using maxima of
   effective defaults, every raw table entry and non-sentinel statically
   supplied fields; then apply the identity overlay once.
3. Checked target/schedule-bound executable certificates, complete coverage
   and build-record acceptance, and real linked launch-library acceptance.
   Current certificate sidecars contain bindings/producer metadata and an empty
   regions map, with no target/schedule binding. Determining dialect §19.9
   requires “the certificate (ISA §12)” and the coverage/resolved build record;
   ISA §9.2 requires executable certificates to bind to closure hashes, and
   §12.1 requires executable claims to name their realisation. Metadata alone
   does not discharge these requirements.
4. A paired published CC byte golden (bp-95o). The determining §17.4 sentence
   makes the representation plugin-defined; no accepted golden currently
   establishes the requested CC-byte comparison. Cross-major equality and
   independent execution are recorded separately, without inventing a fixture.

bp-2zv remains **OPEN**, updated with the above. `.beads/issues.jsonl` is exported
and committed by path. The general key/address audit (bp-3w4/bp-tr5), remaining
entry-replay/rung minis/listsum lifts, entry-stack/arena-o1 and Grover over
unmodified SQLite remain required; no North-Star capability is narrowed.

---

# Fifth pass — 2026-10-31 (four binding objects complete; production launch still open)

Started at **91a0d7d**. Binding implementation/tests: **384dd54**. Hook repair:
**c91c288**. Accepted dialect **0.2.10 @ 023f5a7**, ISA **0.8**; no re-pin,
no new M2 deferral, no push. **This pass does not complete the requested Item A
or M1.** The fourth-pass record below is historical.

| Requested item | Actual result on LLVM 18 and 23 |
|---|---|
| A: production scalar descriptor/CC launches, host replacement, records (bp-2zv) | **Still red.** Production exits 1 at CC/marker event lowering and emits no files. No production implementation landed. Descriptor-reference inc8 remains exact. |
| B: four device-binding lifts (bp-311) | **Green: 0/4 → 4/4**, untrimmed bytes equal, independent check/hash valid, **5/5** published vectors pass per major. |
| Hook bug bp-zk2 | **Green.** Inherited GIT_DIR reproducer exit 128; actual `git push --dry-run` now exits 0 after the full dual-major gate. |

The new OUT path allocates the private buffer and delivers its loaded byte.
CLOCK, BLOCK and CONSOLE emit the published device-state prologues; BLOCK also
gets its input interface region and layout. The entry dependency check precedes
private allocation: OUT/model-private pointers are distinguished from arbitrary
caller pointers, which still require replay. These are the four materialised
binding microvectors; general runtime/model/helper closure remains with bp-311.

The console witness requires constant operands in LLVM operand order (store
value before pointer). Device prologues may name globals absent from the callee:
lproc hashes therefore use their own named-global closure; oracle hashes include
the whole object layout and references in first-appearance order. The BLOCK CLI
adapter now translates the published `mem=k0:hex` to `--mem k0=hex`; both input
images execute instead of merely being indexed.

| Object | LLVM 18 full published bytes | LLVM 23 full published bytes | Vectors per major |
|---|---|---|---:|
| inc8, including descriptor-reference | exact | exact | 6 |
| binding-out-byte | exact | exact | 1 |
| binding-clock-read | exact | exact | 1 |
| binding-block-byte | exact | exact | 2 |
| binding-console-byte | exact | exact | 1 |

Whole scalar inventory: **12/20 → 16/20** exact objects, **35/35 → 40/40**
published run vectors per major; C O3 inc8 also stays exact. Remaining scalar
lifts: entry-replay-byte, rung4-mini, rung8-mini, listsum. Entry-stack and
arena-o1 remain object-only obligations. Nothing is declared out of scope.

| Corpus gate (run/agree/deferred/blocked/diverge) | Before, unchanged binaries | After, dry-run hook |
|---|---|---|
| LLVM 18 | 66/65/1/0/0 | 66/65/1/0/0 |
| LLVM 23 | 66/65/1/0/0 | 66/65/1/0/0 |

The fresh before **corpus** command exited 0. The initial pre-push encountered
the newly strict binding tests with unchanged binaries and exited 1 (TDD red)
before reaching the corpus suite; it is not recorded as a passing baseline
pre-push. The after full headless gate, invoked by `git push --dry-run`, exited
0: cells agree/run **920/924** (18), **788/792** (23). The sole corpus deferral
remains fp-rot-fastmath-reassoc (bp-7ni, M2 §13).

Other fresh checks: recognition **73/73**, **74/74**; analysis **17/17** each;
reference images **6/6** each; materialisation and selected key checks **14/14**
(18), **15/15** (23). Full materialised-key acceptance remains historically red
at **18/49**, **19/50** from the fourth pass, not rerun or relabelled this pass.

## Item A failure: determining requirements and tracked root cause

The root cause is the missing implementation in this repository, not a missing
source capability or an ISA classification. bp-2zv is updated and remains open.
`tests/descriptors.py --major 18 --require-production` and major 23 both exit 1;
their isolated production directories are empty. The default descriptor
regression still exits 0 by explicitly checking the reference path and the loud
production failure; it is **not** a production acceptance verdict.

The determining accepted dialect §17.4 sentence requires that "marker calls lower
to the region calls and `qreg.*` instructions of §18.3 with the handle register
environment of §6.5". §19.9 requires "the host module with device entries replaced
by launch stubs", plus device bitcode, ISA objects, certificate, coverage and
resolved build records. ISA 0.8 §10: "A run executes a device CC entry". The
current production branch instead calls `unimplemented` for CC/marker lowering;
there is no host replacement or launch-record emitter. These requirements remain
unmet. The pinned dialect publishes inc8's **reference oracle/lproc** object and
no CC launch-object golden; §17.4 says CC/R lowering is plugin-defined. This
fixture distinction does not waive production implementation or ABI execution.

## Hook verification and evidence

Unsetting `GIT_DIR`, `GIT_WORK_TREE`, `GIT_INDEX_FILE` alone still failed the first
actual dry-run: the installed hook symlink lives under `.git/hooks`, and root
discovery there fails even with those variables unset. Resolving the symlink
before `git rev-parse` fixes that second cause. The next actual
`git -C /home/tobias/Projects/bennett-workspace/bennett-plugin push --dry-run`
ran all gate suites and exited 0. **No push occurred.** bp-zk2 is closed;
bp-311 is updated for the four completed lifts and stays open for its remaining
outputs; bp-qql is unchanged. Exported `.beads/issues.jsonl` is committed by path.

All commands used the headless unset-display prefix and project-local TMPDIR;
no LLVM viewer passes or sibling modifications. verification.json records actual
plugin digests, full-object hashes/symbols/vectors, both production diagnostics,
the initial red gate and final dry-run exit. M1's broader fourth-pass audit,
production launches, replay/calls/arena outputs, and Grover over unmodified
SQLite remain required.

---

# Fourth pass — 2026-10-31 (partial item 1; M1 acceptance open)

Code/tests landed in **95fa83f**. Accepted dialect remains **0.2.10 @ 023f5a7**, ISA **0.8**. No re-pin,
no new M2 deferral, no push. This pass extends item 1; it does **not** finish
item 1 or claim delivery of items 2–3. Production descriptor/CC launches,
host replacement and records remain unimplemented (bp-2zv). All eight missing
lifts and both object-only vectors remain acceptance obligations.

## New red→green evidence

- Analysis edges: **12/12 → 17/17** per major. Pointer atomic xchg now
  stores FN/ROOT operands; min/max use the unconditional N9/PT3 select union;
  undefined shuffle masks select lane zero; runtime memmove/memset have the
  same PT8 transfer as their intrinsic spellings.
- Address images: **0/3 → 6/6** per major, including host-escape, pointer round-trip
  and PT3 address-space-copy checks. Constant GEPs with a narrow index retain aligned low-bit wrap images
  (I=8, alignment=16, +16 gives offsets 16 and -240). Narrow pointer
  representations and widened pointer integers retain originating object `*`,
  numerical EXT and top. Numerical EXT slots do not establish host escape.
  This is a tested slice, not the full symbolic/residue image construction.
- Published materialisation: **5 → 14** fixtures on LLVM 18, **5 → 15** on 23.
  Added the N0 widenable lowering, N7/N15 lane chains, N9 cmpxchg/integer
  min/max/wrap/usub, N11 faults, N12/count helpers and N26 memory helpers.
  Expected instructions are parsed and printed by the same LLVM major without
  optimisation, so i2 `2`/`-2` spellings compare as the same bit pattern.
- Key regressions: **3 → 14** assertions on 18, **3 → 15** on 23. Keys match
  independently published materialised closures for flags, shifts, lane chains,
  count helpers, traps, memory helpers and atomics; H is preserved. N3 retains
  `!bennett.rstep`; N14 recognises V7's existing guard instead of wrapping it again.
- The independent **all-fixture key audit still fails: 18/49 (18), 19/50 (23)**.
  These totals include four base assertions and all 45/46 applicable published
  normalise pairs, not just selected scalar fixtures. Its exit is 1, recorded
  separately from the legality regression gate. R-mode/platform requirements
  are marked unsupported even if stripping would otherwise hide a difference.

Commands for that acceptance audit (same headless prefix/TMPDIR as HANDOFF):
`python3 tests/region_keys.py --major 18 --all-fixtures` and major 23.
`tests/reference_images.py` is now part of pre-push. The full-fixture key audit
is a deliberately incomplete acceptance audit; it is not called a passing gate.

## General §4/§5 audit: every rule and its witness

A witness establishes only its stated case. An open row is not an M2 deferral.

| Rule | Witness in the executed suites | Audit result / remaining M1 work |
|---|---|---|
| §4.1 order and graph | recognition `unwind-invoke`, `effect-lie`; indirectbr object; region reports | S1–S5 slices exercised; full variant graph/order audit open |
| §4.2 tiers | analysis `host-tiers`; `handle-host-param`, `handle-param-cross-entry` | ordinary H closure exercised; exact host/address/entry and generation/coherent seeding open |
| §4.3 variants/shared globals | key `host_preserved`; smoke global-image key | H preserved; production device clones/shared global identity not complete |
| §4.4 function addresses | `pointer-as270`, `indirectbr-two-blocks` objects | fixed-layout scalar cases exact; general comparison-link address integration open |
| §4.5 calls out | `handle-to-external`; PT8 runtime helper tests | escape diagnostics/recognition exercised; production shim/hostcall/trap coverage records open |
| §5.1 objects, atoms, K | zero stack/heap; byval; masked widths | tested object classes; complete allocation-family/representation audit open |
| PT1 | `pt6-zero-stack`, `pt6-zero-heap`, `zero-symbolic-large` | zero extents and allocation-site witnesses pass |
| PT2 | `pt2-wrap`, `PT2-low-index-wrap`, `PT2-numerical-not-host-escape` | constant narrow-index wrap fixed; finite multi-index, symbolic/residue and wide images/extent exits remain open |
| PT3 | `pt3-pack257/256/unpack`; `subbyte`, `cartesian`, fixed-vscale pack | finite Cartesian geometry passes; general unknown bits/object/ROOT bitcast expansion remains open |
| PT4 | `handle-int-roundtrip`, `handle-truncate`, `pt4-wide-wrap`, `PT4-narrow-address` | tested width-preserving/narrowing cases pass; all originating representations and constant-expression cases not exhausted |
| PT5 | `pt5-int-wrap`, `pt5-range[-load]`, `PT5-widen-address` | finite/mask/range removal and widening fallback pass; full-width modular pointer arithmetic, commuted operands and symbolic images remain open |
| PT6 | `pt6-unknown-address`, `pt6-byte-width`, `pt6-subrange`, zero tests | explicit top/interval/zero witnesses pass; full image/representation audit remains open |
| PT7 | `byval`, `cmpxchg-success/failure`, aggregate recognition | unioned stores/fields exercised; general unknown-address/composite store audit open |
| PT8 | `handle-memcpy`, `pt8-zero-copy`, `runtime-memmove`, `runtime-memset` | known whole/cropped zero copies and repeated-byte fills pass; general symbolic/partial copy audit open |
| PT9 | `byval`, `pt12-root-return`, `handle-indirect` | direct/indirect bindings exercised; all composite call and recursive closures not exhausted |
| PT10 | `shuffle-undef-mask`, `handle-aggregate`, `handle-vector-lane`, `pt10-lane-zero` | total lane/shuffle witnesses pass; full composite transport audit open |
| PT11 | `handle-host-param`, `handle-param-cross-entry`, `host-tiers` | boundary root pruning exercised; exact host-used addresses versus device-only uses and leaf seeding open |
| PT12 | `atomic-xchg-pointer`, `atomic-min-select`, `atomic`, cmpxchg pair, `pt12-root-return` | these fixed transfers pass; S2 wrap/usub/FP atomics and all undefined-callee effects remain open |
| §5.3 value sets | `operand-phi-codes`, `operand-width-masked`, `pt5-range[-load]` | tested finite domains pass; full dispatch/descriptor shape audit open |
| §5.4 consumers | region key/candidate reports; descriptor inc8 | tested report consumers pass; production read sets/arena/budget consumers remain open |

## Materialised-key audit by normalisation/validator rule

The independent residual validator V1–V16 is still unimplemented. Matching one
key fixture does not establish that validator or every case of its N rule.

| Rule | Witness / status |
|---|---|
| N0 | `n-lower-widenable` materialises exactly; source/normalised key mismatch is bp-tr5; other lowering families open |
| N1 | `n-flags`, matching materialised key |
| N2 | `n-flags`; full FP materialisation open |
| N3 | `n-flags`, rstep preservation/difference assertion |
| N4 | `n-flags`; complete ABI attribute audit open |
| N5 | identity/no-effect intrinsic families implemented; exhaustive family witness suite open |
| N6 | lifetime/invariant deletion implemented; exhaustive token-use witness suite open |
| N7 | `n-undef`, constant lane cases; full aggregates/shuffle materialisation open |
| N8 | freeze key equality and H preservation |
| N9 | NAND/cmpxchg/wrap/usub materialisation and keys; FP rewrites open |
| N10 | `n-query`; full query/dispatch mirror audit open |
| N11 | `n-trap` exact/key; cond.loop open |
| N12 | `n-defined-zero` exact/key |
| N13 | replaced by N26 (memory helper witness) |
| N14 | `n-shift` exact/key and repeated-pattern guard |
| N15 | `n-constant-lane`, `n-dynamic-lane`, `n-narrow-lane` exact/key |
| N16 | `n-fmuladd` key mismatch remains |
| N17 | replaced by N32/N33, open |
| N18 | replaced by §4.5, production call closure open |
| N19 | N32 soft-float work remains open |
| N20 | replaced by N24, open |
| N21 | selected lane chains exact; `n-vector`, bitcast/VP/i24 key mismatches remain |
| N22 | `n-wide-sub`, `n-wideint`, `n-wide-intrinsics` key mismatches remain |
| N23 | `n-varargs` key mismatch remains |
| N24 | `n-shadow-stack`, `n-budget-stage` key mismatches remain |
| N25 | `n-byval-copy` key mismatch remains |
| N26 | `n-memintrinsics` exact/key; full atomic/pattern/address-space family open |
| N27 | `n-defined-zero` exact/key; `n-intrinsics` and wide helper ABI open |
| N28 | `n-eh` key mismatch remains |
| N29 | setjmp/longjmp: no completed materialised-key witness |
| N30 | fibers: no completed materialised-key witness |
| N31 | `n-asm` key mismatch remains |
| N32 | `n-fcmp`, `n-fpconv-wide` key mismatches remain |
| N33 | FP80/libm and all target-format key mismatches remain |
| N34 | rstep preservation passes; `n-rstep-return` generation mode open |
| N35 | `n-platform-mmio` platform mode open |
| V1 | `n-flags` witness; validator open |
| V2 | `n-flags`/rstep witnesses; validator open |
| V3 | `n-flags` attributes witness; validator open |
| V4 | count/trap/memory witnesses; full intrinsic residual validator open |
| V5 | `n-undef` witness; validator open |
| V6 | atomics/fence witness; FP atomic and validator open |
| V7 | guarded `n-shift` witness; validator open |
| V8 | dynamic/narrow lane witnesses; validator open |
| V9 | `n-fcmp` missing; validator open |
| V10 | FP80/libm missing; validator open |
| V11 | shadow stack missing; validator open |
| V12 | helper closure validation missing |
| V13 | complete vector elimination missing |
| V14 | wide limb elimination missing |
| V15 | varargs/EH/sjlj elimination missing |
| V16 | asm/target elimination missing |

## Contract question and exact remaining acceptance

New **bp-tr5** names the conflicting ordering: §7.2 says a forwarding thunk
resolves to its call target, and an undefined candidate is F(8); the published
`n-lower-widenable` is precisely such a thunk to a declared intrinsic. N0 instead
materialises that function to `ret i1 true`, and §5.2 requires normalisation
value effects before candidate sets freeze. Clarify the virtual materialisation /
resolve ordering and preservation of source dispatch addresses. No arbitrary
intrinsic exception or M2 classification was introduced.

**M1 is incomplete.** Remaining: the open audit cases above, the 31 failed
all-fixture key comparisons listed in verification.json (bp-3w4/bp-tr5), complete
scalar production descriptors/CC launches/stubs/records (bp-2zv), and all ten
missing example outputs below. The full gate remains a regression gate, not
M1 acceptance. The existing sole corpus deferral is still
`fp-rot-fastmath-reassoc`, M2 §13 / bp-7ni. No new source capability was removed.
Grover over unmodified SQLite remains core.

The third-pass record below supplies the unchanged 22-example inventory and
published interface hashes. Fourth-pass verification.json records fresh gate,
object/hash/vector results, both key audits and all 22 equality statuses.

---

# Third pass — 2026-10-31 (M1c; M1 acceptance still open)

Accepted contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**;
ISA **0.8**. Round-8 freeze receipt: spec SHA-256
`d4f3c1a88391cc147f8c8fa4f80f82852e3ebe6f880610fc16cd5151f33d7206`.
The sibling worktree is draft 0.2.11; it is not the accepted compatibility unit.
The drift gate checks the accepted-release registry and pinned blob digest, and
reports working draft/HEAD differences separately. Cases, header, opaque harness
and runtime now come from one immutable commit, with a pin-specific baseline cache.

## Current verification and acceptance

The headless CMake 3.28.3 superbuild/load is verified on both majors. The gate
uses the full required unset-display/project-local TMPDIR prefix, with no viewer
passes. Exact results, plugin digests, all symbol hashes and vectors are recorded
in `verification.json` from the actual local artefacts.

| Check | LLVM 18 | LLVM 23 |
|---|---:|---:|
| Published recognition examples | 73/73 | 74/74 |
| Analysis edge/domain regressions | 12/12 | 12/12 |
| Published materialisation instruction lists | 5/5 | 5/5 |
| Scalar region key/H-preservation assertions | 3/3 | 3/3 |
| Complete reference objects, exact untrimmed bytes/hash/check | 12/20 | 12/20 |
| All stated vectors for those objects | 35/35 | 35/35 |
| C O3 inc8 and descriptor-derived inc8 | exact | exact |
| Production descriptor launch | unimplemented | unimplemented |

| LLVM | Before run/agree/deferred/blocked/diverge | After | Cells agree/run |
|---|---|---|---|
| 18 | 66/63/1/2/0 (gate exit 1: drift) | 66/65/1/0/0 (exit 0) | 920/924 (before 892/924) |
| 23 | 66/63/1/2/0 (gate exit 1: drift) | 66/65/1/0/0 (exit 0) | 788/792 (before 764/792) |

The sole remaining non-agreement is **fp-rot-fastmath-reassoc**, L5 at
`default<O0>`, `strip`, `strip-nondebug`, `mergefunc`: **deferred M2 (§13;
bp-7ni)**. A new failed property, changed runtime exit or absent check is still a
real divergence. No deferred/blocked case is counted as agreement.

## Brief 1b items 3–5

| Item | Landed | Still required |
|---|---|---|
| 3 | Zero images, geometry/constant/fixed-vscale bitcasts, total lane domains, N9 cmpxchg regression, local descriptor reaching-store proof; scalar materialised keys | **Open M1:** general PT2/PT4/PT5 images, full composites/atomics and boundary/generation tier audit; all-rule keys (bp-3w4); production descriptor/CC launches, host stubs and records (bp-2zv) |
| 4 | Inventory of every spec-* case and all 20 lift blocks; 12 exact objects/35 vectors per major, including indirectbr; untrimmed byte comparisons | Eight lifts and two object-only integration examples below remain missing; not marked complete |
| 5 | PLAN, PROGRESS, verification.json and HANDOFF updated from actual runs | M1 remains in progress; next work is item 3 production/general audit |

No M1 requirement was newly moved to M2. Existing mechanics remain explicit
scheduled work, with determining contract sentences in PLAN and beads. The green
reference/legality gate is not production acceptance or full §21 conformance.
Grover over unmodified SQLite remains the core target.

## Byte-for-byte scalar reproduction

Each yes means complete object bytes equal the published accepted fixture on both
majors, reference `check`, every stated interface hash and every run vector pass.

| Object | LLVM 18 | LLVM 23 | @ref interface hash |
|---|---|---|---|
| oracle-empty-output | yes | yes | `358a1b87139653df3c5a82465215f8af96a12d0e8ad02610e04696c2d588a91c` |
| oracle-empty-fault | yes | yes | `863fd42e300d5bba79d561ceca8c8b72ee1ad384d60f770d961cf25a8e258181` |
| oracle-discard-return | yes | yes | `622ca26e17519d6e64af5f64f8e0f9c3d9af6c5d36a97740de5d6cbc2b2f62f3` |
| atomic-nand | yes | yes | `21917fb6f3a0cc9bd14651126bb3fecaadcdccbed30b854170c7ba10741adac4` |
| pointer-as270 | yes | yes | `62693b6dfefab4480cce6de8257132bcc9fead16250518602c354083332dd16a` |
| gep-index-obj | yes | yes | `5b3c7d1f368fcc8c24286cc303a71c12b5b615f467149f29928099befd3de534` |
| gep-index-const | yes | yes | `591f1b48288e000c626c349165ead9ff9158c05c472c9c569bfec3dac42de091` |
| indirectbr-two-blocks | yes | yes | `a2580fd9aee33acb7501709e08ccc38d57944b716c9aca371f0b2fc93554362c` |
| inc8 | yes | yes | `151baad5625b3605eadf87005a19ea6e012e4347d6dfe096dbc4edcf2b68b94a` |
| add2 | yes | yes | `5b4c6624e0f20b5d60780fd8f27056f3f7efd4d27b9d47af8a70c8126100a10a` |
| switch5 | yes | yes | `0575354a0ecceee58d8dfbcc5cb9a9b8851c5c2b3193bf543395bed13604ce80` |
| fp-aggregate | yes | yes | `1139edfe71a34500be515f3ff61380020ab781c254339eafbad172a94e095d69` |

| Missing example | Both majors: root cause and required §16 row | Bead |
|---|---|---|
| binding-out-byte | §16.2 OUT allocation/delivery and §16.4 indirect buffer load/store | bp-311 |
| binding-clock-read | §16.2/§11.3 device-state prologue, stores and linked model calls | bp-311 |
| binding-block-byte | §16.2 device bindings, §16.4 memory and helper calls | bp-311 |
| binding-console-byte | §16.2 output buffers/projections, §16.4 stores/calls | bp-311 |
| entry-replay-byte | §8.5 entry snapshot/replay, §16.4 mutable-global stores and calls | bp-311 |
| rung4-mini | §16.4 MEM_IN, GEP/load/store/direct and indirect calls/comparison layout | bp-311 |
| rung8-mini | §16.2 ENTROPY prologue, §16.4 model helper calls and memory | bp-311 |
| listsum | §16.4 alloc/free, direct lift.call closure, heap/allocator entry state | bp-311 |
| entry-stack (object-only, no lift source) | §8.5/§17.3 replay/adoption helper closure; §16.4 calls/memory | bp-311 |
| arena-o1 (object-only, no lift source) | TDL-4 arena/action outlining, §16.2 hidden arena pointer, §16.4 memory | bp-qql |

All eight missing lifts are actually attempted; each emits an explicit
unimplemented diagnostic, never a passing fixture. The two object-only vectors
are inventoried and not claimed compiler outputs. The six `spec-*` corpus
programs are quantum action adj/compute/ctrl examples; the scalar oracle subset
is empty. All six execute in the legality gate on both majors.

## Observed behavioural changes from 0.2.7

- §5.2/PT1/PT6: alloca and allocation-site zero initial images survive stores.
  `pt6-zero-stack` and `pt6-zero-heap` now give raw/idx `{0,1}`, widths `{1,3}`;
  the old analysis omitted zero (and opaque `free` incorrectly tainted heap bytes).
- PT8: clipped byte-image copies carry zero into a nonzero-initialised global;
  `pt8-zero-copy` now gives the same `{0,1}` / `{1,3}` domains. Full interval
  stores still union with these initial bytes.
- PT3: equal geometry copies lanes; changed geometry packs/resegments bit patterns
  in DataLayout order. The earlier pass already passed byte-lane 257/256/unpack3;
  this pass fixes sub-byte bit positions and constant-expression bitcasts and
  checks Cartesian lane alternatives (257/258/513/514), little and big endian.
- PT10/N15: out-of-range dynamic extraction contributes zero; published lane-zero
  width domain changes from `{2,4}` to `{1,2,4}`.
- PT4/PT5: the new wide-wrap witness exposed an APInt assertion on a 2^64
  displacement. Low pointer-width modular displacement now retains the table
  candidate instead of crashing. General represented-address images remain M1.
- map 0.2.9/§16.3: globals are 1-based; atomic-nand's G0 becomes G1. Object
  and closure hashes change, while its payload 63/code0/16 steps stays equal.
- Zero initial images also reach descriptor allocas. Reference emission uses an
  independent local reaching-store proof at the call rather than deleting zeros
  from normative S2 domains; ambiguous paths retain explicit unimplemented errors.
- The pinned harness now selects ABI 0.2 for spec-sem2-adj/compute; both former
  exit-87 upstream blockers execute successfully and become agreements. Historical
  ABI-v0 cases remain unchanged. No EXPECT line was edited.
- Normaliser/map subversions advance to 0.2.8/0.2.9; budget-stage selection/final
  fixture identities also change with corrected G1 naming. This plugin does not
  yet emit those budget/certificate products, so no execution claim is made.
- N33 own-format libm carrier corrections are part of the pin; arithmetic/helper
  closure materialisation remains explicit M2 work, not claimed implemented here.

## Symbolic extents and fixed-vscale bitcasts

Two extra audit checks were red (10/12) then green **12/12 per major**:
zero-byte symbolic initial extents now cover the full represented address domain,
including the read beyond 2^60 that exposed a finite internal cap; widened interval
arithmetic prevents signed overflow in overlap/containment and clipped copies.
Scalable vectors use the prescribed fixed-vscale=1 lane geometry during S2;
`<vscale x 2 x i8>` to `<vscale x 1 x i16>` now packs to 256. Pointer integer
addition/subtraction uses APInt modular arithmetic rather than C++ signed overflow.
These regressions do not close the remaining general PT2/PT4/PT5 image audit.

## Materialised scalar region keys and N15

Keys now run the implemented scalar normalisation slice on a private cloned
closure before stripping/printing. Red 1/3 → green 3/3 per major: nsw/plain
closures have equal keys, freeze/plain closures have equal keys, and original
H IR retains its flags/freeze. The existing name/global-image smoke checks pass.
This fixes scalar keys; it does not claim all N0–N35/V1–V16 closure keys complete.
N15 constant totalisation plus constant lane renaming reproduces the complete
`n-constant-lane` instruction lists on both majors (materialisation 5/5).
LLVM23 branch emission uses CondBrInst/UncondBrInst; clean incremental builds
produce no deprecation warnings and the reference object text is unchanged.

## Additional scalar map delivery

`indirectbr-two-blocks` was red as a required scalar object, then green on both
majors: complete untrimmed fixture bytes, all symbol hashes, `check`, and the
three published vectors (4096→7/9 steps, 4097→9/12, 4098→fault4/10).
§14.9 block ordinals use layout order and the comparison-layout backing global;
short domains use §14.2's linear leaf tree. Balanced large domains and general
comparison-link supplied layouts remain explicit M2 mechanics, not a rejection.
The complete supported-object count becomes 12, with eight lift fixtures still
explicitly unavailable. This does not complete brief 1b item 4.

## Contract policy mutation guard

Five assertions cover a live accepted pin, an unaccepted working draft, a newly
accepted release, pinned-byte corruption and a version-only local/registry repin
that leaves the old blob. The last mutation was red before adding consistent
version/commit/digest checks. The corpus gate now imports the single PIN constant
from contracts.py rather than maintaining a second copy.

## Baseline provenance and red→green evidence

Stable 07f942c sources were rebuilt in `.tmp/before-build`; both majors reproduced
66 run / 63 agree / 1 deferred / 2 blocked / 0 diverge; the old pin-drift gate
exited 1. A first overlapping build/gate attempt was invalidated by the existing
plugin-digest guard and discarded; only the isolated rerun supplies these totals.
The first accepted 0.2.10 corpus run is 66/65/1/0/0 on each major (exit 0).
New domain assertions were red 4/7 then published recognition passed 73/73 (18)
and 74/74 (23). Constant-expression packing was independently red 1/8.

**M1 remains open.** No general audit, full materialised keys or production launch
completion is claimed by these checks. The earlier pass record follows for history;
its pin, runtime blocker, CMake and G0 statements are superseded by this section.

---

# Historical M1b record — superseded above

# Progress — 2026-10-30 (M1b)

**M1 remains incomplete.** Epic bp-a41 and its implementation tasks remain open.
No push. Contract: dialect **0.2.7**, **95c3cd332f5f72c07fd5f2515f328deaa40c08b9**;
ISA **0.8**. The authorized re-pin is committed; current published text/HEAD match.

## Verified implementation

- `scripts/build`: both major plugins build/load with llvm-config/g++; CMake is
  absent and its superbuild remains **unverified**, bp-ahz.
- `tests/smoke.py`: both majors, pre-link inert; all 23 header prototypes accepted
  and 23 malformed signatures diagnosed. Region keys ignore function names and
  retain referenced global images.
- `tests/recognition.py`: **63/63 LLVM 18**, **64/64 LLVM 23** published examples.
  `pt5-range` is explicitly published for LLVM 23 only. New assertions check
  `pt2-wrap` offset/candidates and both applicable PT5 witnesses' exact `{1,3}`
  sets. The load-!range assertion failed before removing erased range evidence.
- `tests/analysis_edges.py`: **4/4 per major**, from 1/4 before implementation:
  PT9 separate byval copy objects, PT10 equal-bit packed 2xi32→i64,
  PT12 finite integer-nand transfer, and ordinary host closure tiers. These
  witnesses do not establish the remaining general analysis cases below.
- `tests/materialisation.py`: **4/4 per major**. Instruction lists match the
  published `n-flags`, `n-shift`, `n-query`, `n-atomic-nand` outputs. The M1 scalar
  N1–N10/N14 slice is applied to a private module before reference lowering;
  `materialised.bc` is emitted. The original H module is preserved. This is
  not the complete N0–N35/V1–V16 normaliser/validator.
- `tests/scalars.py`: **all 20 published lift blocks are attempted**, with **11
  complete objects checked per major**, exact fixture bytes, explicitly compared
  published hashes, and **all stated run/budget/ARG vectors**. `fp-aggregate`
  adds FP carriers and padding-free constant aggregate returns; `atomic-nand`
  adds scalar global images, bounds checks, loads/stores and closure hashes.
  Plain C inc8 at clang O3 still reproduces the published object.
- `tests/descriptors.py`: a descriptor built by ordinary C stores using the ABI
  header derives the inc8 reference shape/object on **both majors**. Explicit
  `-bennett-descriptor-reference` is non-production; the same module in production
  mode still fails loudly at unavailable CC lowering. This does **not** close the
  production launch path. Device-binding syntax formerly fell through silently
  in the scalar shape parser; the all-lifts test exposed it and it now fails M2.

## Corpus gate and root causes

The authorized raw re-pin reproduced **66 run / 63 agree / 3 diverge** per major
before classification. `scripts/pre-push` now exits **0** on both majors, with:

| LLVM | Run | Agree | Deferred | Blocked | Diverge | Cells run | Cells agree |
|---|---:|---:|---:|---:|---:|---:|---:|
| 18 | 66 | 63 | 1 | 2 | 0 | 924 | 892 |
| 23 | 66 | 63 | 1 | 2 | 0 | 792 | 764 |

**Exit rule:** exit 0 only when every non-deferred, non-blocked case agrees,
with no pin drift. Deferred/blocked cases are separately counted, never agreements,
and printed with milestone/bead on **every run**. A new failing property, plugin
failure, changed ABI-probe exit, or missing check stays a real divergence, exit 1.
`tests/gate_policy.py` checks these mutation cases (seven assertions).

| Case | Property | Classification and evidence |
|---|---|---|
| spec-sem2-adj | L1/L5, all pipelines | **blocked-upstream: bp-c2i (b-dialect-spec-566)**; ABI 0.2 calls exit 87 with `FAULT host-segv` without bennett and after bennett, both codegen levels/majors |
| spec-sem2-compute | L1/L5, all pipelines | **blocked-upstream: bp-c2i (b-dialect-spec-566)**; same isolation and result |
| fp-rot-fastmath-reassoc | L5: default<O0>, strip, strip-nondebug, mergefunc | **deferred: M2 (§13 FP materialisation)**; fast-math survives and llc O0/O3 traces differ |

**ABI isolation:** local probe copies of each spec-sem2 case remove only the new
budget operand and use the v0 declaration. The **same untouched opaque runtime
binaries** then exit **0 at O0/O3 on LLVM 18/23**, versus **87** for the original
ABI 0.2 call. Null budget occupies the old runtime's env position. This isolates
an upstream ABI-v0 runtime, not a plugin rewrite. No corpus EXPECT was changed;
the probes never replace gate fixtures. Relay bp-c2i to the dialect editor.

**FP scope:** the failing case has sitofp i64 (the §13 rewrite uses i128), f64
multiply/add/divide and loop-carried FP arithmetic. It needs linked deterministic
soft-float helpers and their materialised call closure/native comparison build
(§13/§17.7), beyond the bit-exact carriers/packing verified by M1. M2 owns those
mechanics; removing fast-math alone would not satisfy §13.

The three negative attribute/dereference controls retain their stated diagnostics;
`c-pure-attr-wrapper` retains §3.8's source-effect-lie diagnostic. Region-twin
content identity remains recorded under bp-tye, not changed to symbol identity.

**Gate limits remain:** L1 is optimized pre/post plugin; L4 is key stability
across the plugin, not full cross-pipeline materialised comparison. Frontend
LTO/rustc/Julia envelopes remain open. A green gate with the explicit unavailable
counts is not full §21 conformance or M1 completion.

## Scalar objects and outstanding examples

These complete objects are byte-identical on both majors and to the pin. Full
object hashes, all symbol hashes and run vectors are in `verification.json`.

| Object | @ref interface hash |
|---|---|
| oracle-empty-output | `358a1b87139653df3c5a82465215f8af96a12d0e8ad02610e04696c2d588a91c` |
| oracle-empty-fault | `863fd42e300d5bba79d561ceca8c8b72ee1ad384d60f770d961cf25a8e258181` |
| oracle-discard-return | `622ca26e17519d6e64af5f64f8e0f9c3d9af6c5d36a97740de5d6cbc2b2f62f3` |
| atomic-nand | `c55111b84ee5e99801d9947547fcec2dbaf65dd0d76d4f8d61eb22f501c6da85` |
| pointer-as270 | `62693b6dfefab4480cce6de8257132bcc9fead16250518602c354083332dd16a` |
| gep-index-obj | `5b3c7d1f368fcc8c24286cc303a71c12b5b615f467149f29928099befd3de534` |
| gep-index-const | `591f1b48288e000c626c349165ead9ff9158c05c472c9c569bfec3dac42de091` |
| inc8 | `151baad5625b3605eadf87005a19ea6e012e4347d6dfe096dbc4edcf2b68b94a` |
| add2 | `5b4c6624e0f20b5d60780fd8f27056f3f7efd4d27b9d47af8a70c8126100a10a` |
| switch5 | `0575354a0ecceee58d8dfbcc5cb9a9b8851c5c2b3193bf543395bed13604ce80` |
| fp-aggregate | `1139edfe71a34500be515f3ff61380020ab781c254339eafbad172a94e095d69` |

The pin has **six spec-* corpus programs**, all quantum action/generation
programs (adj/compute/ctrl in ABI v0 and 0.2); there is **no scalar oracle
spec-* case to omit**. They all run in the legality gate; action-object generation
is M3. Their inventory is in verification.json.

Every remaining scalar-typed lift is explicitly attempted and reports unavailable
M2 mechanics. These examples have scalar signatures but exceed pure scalar
integer/FP-carrier lowering; they remain promised, not rejected:

| Example | Needed §16.4 rows / associated mechanism |
|---|---|
| binding-out-byte | wrapper OUT allocation/delivery; indirect buffer load/store (§8.2/§16.2) |
| binding-clock-read | device-state prologue/store and supplied comparison layout (§11.3/§16.2) |
| binding-block-byte | device state, load/store, linked helper calls (§11.3) |
| binding-console-byte | OUT-like device buffer/projections, loads/stores, linked calls (§11.3) |
| entry-replay-byte | snapshot/replay prologue, direct calls and mutable-global entry state (§8.5) |
| indirectbr-two-blocks | blockaddress encoding plus indirectbr compare tree (§14.9) |
| rung4-mini | MEM_IN, GEP/load/store, direct/indirect calls and comparison layout |
| rung8-mini | ENTROPY binding/prologue and linked model calls |
| listsum | primitive alloc/free, direct lift.call closure, heap memory and entry allocator state |

Two executed object-only integration vectors have no `llvm lift` source:
`arena-o1` needs TDL arena outlining/hidden pointer (M3); `entry-stack` needs the
fixed linked replay/adoption helper closure (§8.5/§17.3, M2). They are inventoried,
not claimed lowered or silently treated as completed scalar fixtures.

The previous pass exhaustively step-checked byte-identical inc8 and switch5 for
256 inputs each. These are retained historical results, not rerun claims; add2's
60-second exhaustive timeout remains disclosed (all its stated vectors pass).

## Remaining M1 and M2 entry point

- **M1 acceptance still open:** exact reference-analysis audit, general finite-width
  PT2 image/carry behavior; nonbyte packed lanes/composite operations; complete
  atomics/cmpxchg; exact host/boundary and generation-sensitive variant seeding.
- Fully materialised region keys, full legality materialisation/native-comparison
  checks and independent residual validation remain open. Current keys still
  precede the complete normaliser.
- **Production descriptor integration remains open.** Static extraction/reference
  output is implemented; CC launches, host entry replacement, final device objects
  and full §19.9 records/certificates remain unavailable. General M3 CC work must
  supply/pull forward the scalar launch path before this M1 obligation closes.
- CMake validation requires the maintainer to install CMake (bp-ahz).
- **M2 entry:** link and materialise §13 soft-float/native comparison helpers;
  finish N0–N35/V1–V16, lifted calls/memory, descriptor shape dispatch and entry-state
  replay; then execute the nine inventoried lifts. §9.2's 0.2.7 staged identities
  and frozen capacities are required with budget-table integration, not relabelled
  as already implemented.
- M3 generation/TDL/CC-R and bounded ISA blocker realisations; M4 whole-program
  integration/rungs 4–8; M5 ISA dependency removal remain unchanged in scope.

Upstream relay also includes **bp-p26**: §16.3 says global numbering starts G1,
but atomic-nand uses G0 and binding-clock-read uses G1. The starting index or
comparison-layout override must be stated consistently before general layout
integration. Existing supported fixture hashes are retained exactly.

All results are from published text/fixtures and black-box binaries. No sibling
checker/interpreter/runtime implementation was read and no sibling repository
was edited. No HANDOFF/worklog file was written by this implementation sub-agent.
