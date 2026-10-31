# Progress

History before 2026-10-31 and per-pass evidence: `git show de4fe2c:docs/PROGRESS.md`.

## Resume

Contract: dialect **0.2.10 @ 023f5a771a814270634db3be9cfde88ded69f975**, ISA **0.8** (pinned in
`SPEC_VERSIONS.toml`; the gate checks the pin). State: **M1 complete on the plan's definition**
(2026-10-31, see `docs/PLAN.md`). Next: **M2, starting with bp-kv5**. Obligations live only in bd
(`bd ready`, `bd list --all`); this file keeps no obligation list.

Build and gate (headless, rule 11), repo root:
- Full gate (builds both majors first, `scripts/build`): `env -u DISPLAY -u WAYLAND_DISPLAY -u DBUS_SESSION_BUS_ADDRESS -u BROWSER TMPDIR=$PWD/.tmp scripts/pre-push`.
  It builds, then runs smoke, gate_policy, contract_policy, and per major 18 and 23 recognition,
  analysis_edges, reference_images, materialisation, region_keys, scalars, descriptors, production
  and production_{environments,dispatch,shapes,budgets,records}, then production_cross_major and
  corpus_gate. Sibling black boxes: `../bennett-isa-spec` reference CLI, `../bennett-dialect-spec` corpus.
- Evidence of the latest pass: `docs/verification.json` (`scripts/record-verification.py`).

Counts (LLVM 18 and 23, each): legality gate 66 run / 65 agree / 1 deferred / 0 blocked / 0 diverge
(cells 920/924 on 18, 788/792 on 23); recognition 73/73; analysis_edges 17/17; reference_images 6/6;
materialisation 14/14; region_keys 14/14; 17 scalar objects byte-exact with 40 run vectors; 97/97 object
pairs byte-identical across majors, 27 equal to published fixtures. Sole deferral:
fp-rot-fastmath-reassoc (bp-7ni).

Open beads by milestone (id: one line):
- **M1 leftovers, not moved by the ruling (need maintainer disposition):** bp-2zv: production descriptor
  and CC launch umbrella (its sub-items now sit in kv5/rbl/65x/piq/o7f). bp-3w4: general reference audit
  and all-rule materialised region keys (31 failed key assertions recorded in the fourth pass). bp-tr5:
  clarify intrinsic forwarding thunk identity (§7.2 vs N0). bp-tye: region-twin negative control.
- **M2:** bp-kv5: general descriptor dispatch (candidate pointers, widths, sizes, device model, arbitrary
  descriptor memory loads; dialect §8.4). bp-piq: budget-stage shadow-stack vector (entry-state replay and
  §17.3; H16 4162aa7c... to H32 7486a0aa...). bp-311: replay, device bindings, lifted memory/calls
  (entry-replay-byte, rung4-mini, rung8-mini, listsum, entry-stack). bp-7ni: soft-float materialisation.
- **M3:** bp-rbl: general handle environments (N(s), cyclic/recursive/persistent files, call arguments and
  results; §6.5, §17.4). bp-65x: parameterised INOUT, sampled inverse verification, budget minima (§8.7).
  bp-qql: arena-o1 outlining and hidden arena pointer. ISA blockers bp-2tw, bp-2bi, bp-ckk, bp-is0
  (BLK-1/2/4/5, upstream; M3 supplies bounded realisations).
- **M4:** bp-o7f: published executable certificate reproduction and checker fixture (upstream 8r4/47t).
- Closed with the 2026-10-31 ruling: bp-dw4 (remainder tracked by kv5/rbl/65x), bp-95o (§17.4: CC
  lowering is plugin-defined; the plugin's committed CC objects plus cross-major equality are the reference).

## Passes

### Pass 1 - 2026-10-30 - 4ef1e0c..3be37ba
Pinned dialect 0.2.x drafts and ISA 0.8; PLAN; one source tree building plugins for LLVM 18 and 23.
All 23 ABI 0.2 markers recognised with section 22 diagnostics; section 4/5 device fixpoint, section 6
bitwise handle provenance, section 7 region identity. Independent headless legality gate: 66 cases, 63 agree.
Nine scalar reference objects matching published hashes. M1 stayed open (analysis audit, production).

### Pass 2 - 2026-10-30 - f7e1b1e..716df23
Re-pinned to dialect 0.2.7; gate classifies `deferred` and `blocked-upstream` loudly (66/63/1/2/0).
Eleven scalar objects byte-exact on both majors (added atomic-nand, fp-aggregate); scalar global images,
reference shapes from ABI descriptors, descriptor-reference inc8. Filed bp-c2i (ABI v0 runtime), bp-p26 (G0/G1).
CMake 3.28.3 installed afterwards; superbuild verified.

### Pass 3 - 2026-10-31 - e1e06b8..2d5f323
Pinned accepted dialect 0.2.10 @ 023f5a7; blockers bp-c2i/bp-p26 resolved at the pin; gate 66/65/1/0/0.
Published indirectbr object and fault vectors reproduced (12 exact objects, 73/74 recognition examples);
scalar materialised closure keys, symbolic zero extents, fixed-vscale bitcasts; 12 analysis regressions.
Drift check requires consistent accepted version, commit and content. Recorded in `2d5f323`.

### Pass 4 - 2026-10-31 - 95fa83f, 91a0d7d
Analysis regressions 12 to 17 and six represented-address witnesses per major; 14/15 published
materialisation fixtures and 14/15 key assertions. Fixes: narrow-index GEP wrap, width-changing provenance,
PT3 address spaces, PT8 helper spellings, pointer xchg/N9 unions, undefined shuffle masks, repeated N14.
All-fixture key audit left red at 18/49 (LLVM 18) and 19/50 (LLVM 23): bp-3w4. Filed bp-tr5.

### Pass 5 - 2026-10-31 - 384dd54, c91c288, a2bce18
Four device-binding lifts byte-exact on both majors (binding-out-byte, clock-read, block-byte, console-byte)
with independent check/hash and five run vectors: OUT allocation/delivery, CLOCK/BLOCK/CONSOLE prologues.
Fixed pre-push under git push (inherited GIT_DIR, bp-zk2): `push --dry-run` exit 0 after the full gate.
Production scalar launch still red at that point (exit 1 at CC/marker lowering).

### Pass 6 - 2026-10-31 - bc14d48, 563ca6a, 32427ed
Scalar descriptors lowered to executable CC launch objects and host ABI stubs on both majors; measured inc8
(0, 7, 255), published-oracle inc8 and integer-ABI launches check and run via `run-program`.
Native integer ABI attributes preserved in launch stubs; native mock protocol checks pass.
First gate invalidated by a plugin digest change during the corpus run; clean rerun 66/65/1/0/0
(the recorder keeps its `plugin_sha256` digest check).

### Pass 7 - 2026-10-31 - 55d3b0d, ba7f0d8, c8b477b, c9b1b7d
Production OUT/MEM_IN and CLOCK/BLOCK/CONSOLE bindings, distinct scalar references sharing a layout,
direct handle block parameters (7 objects). JCS budget tables with per-component precedence and frozen
maxima (4 objects; published sstack vector left red: bp-piq). Artifact inventories and instruction coverage
sidecars (5 cases). Gate 66/65/1/0/0 before and after; 51 object pairs byte-equal across majors.

### Pass 8 - 2026-10-31 - a8a2d81, 5d8d1f9, 8e49ae0, 8e8118e, de4fe2c (bp-dw4)
Runtime integer descriptor kind/mode trees and ARG carriers (a8a2d81); entry-local memory handle files with
retired-tag traps (5d8d1f9); combined devices, null console, multiple/256-bit outputs (8e49ae0);
heterogeneous layouts and relocated globals (8e8118e); sole-INOUT pairs with exhaustive inverse check and
budget checks (de4fe2c). Gate 66/65/1/0/0 before and after; 97/97 object pairs byte-identical across majors.

## Byte-for-byte table (97 object pairs, LLVM 18 vs 23)

The gate (`production_cross_major.py`, `scalars.py`, `production.py`) is the reader: every pair below is
byte-identical across majors, 27 equal published fixtures. "plugin-defined (§17.4)" means CC/R lowering has no
published golden by design; the plugin's committed objects plus cross-major equality are the reference.
Per-major paths, sizes and checks are in `docs/verification.json`.

| Object | Published full bytes | 18 vs 23 | SHA-256 (both) |
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
| `descriptor-production/smoke/launch.bennett` | plugin-defined (§17.4) | equal | `54be8166989d5b58916aacdc041f25c6563f69de369a61868a57c1d47b686075` |
| `descriptor-production/smoke/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/0/launch.bennett` | plugin-defined (§17.4) | equal | `d5ae5d065001cf94ab65611f58f68f89b06fc9a61aa66d29be4447229e8eeb25` |
| `production/0/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/7/launch.bennett` | plugin-defined (§17.4) | equal | `c28286b6553e8898e0a46da18fa6fb026b53bb6a73f35b98f546b635a3421cbf` |
| `production/7/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/255/launch.bennett` | plugin-defined (§17.4) | equal | `e982723ef9cc4dd66e82a61c1b24f62c6290dbdbc4d62a695f94f4356321f1ae` |
| `production/255/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/published/launch.bennett` | plugin-defined (§17.4) | equal | `fcb11ca7194f835598ba8d2cae2133eacc628634baca2f2fc205915e7f042eb6` |
| `production/published/oracle-0/ref.bennett` | exact inc8 | equal | `8ac243f5cfec814221a859201ac78f713dbc533ed51e6d1b9287b7a234e7c1c7` |
| `production/abi/launch.bennett` | plugin-defined (§17.4) | equal | `848f2628b2b5d9c5f64428b3e4cd0f25537622ee799691a467294f8b1d5149a3` |
| `production-shapes/binding-out-byte/launch.bennett` | plugin-defined (§17.4) | equal | `7b5e193670571ef6099ab43d45256e64cc5751a9a9855576dbfda8453a38a37d` |
| `production-shapes/binding-out-byte/oracle-0/ref.bennett` | exact binding-out-byte | equal | `94642c83d654e907ea6cb34af7bc3849d06b8fc3b127f56a235f1fff934d3581` |
| `production-shapes/binding-clock-read/launch.bennett` | plugin-defined (§17.4) | equal | `be97b2e3111edea3c82092bacdf521ef723c96794a5004e37f73454699f05a45` |
| `production-shapes/binding-clock-read/oracle-0/ref.bennett` | exact binding-clock-read | equal | `ced3e13e4bc7af8325b951b93cc8b87b54437f6cbe2b8b5156074309faba8e6e` |
| `production-shapes/binding-block-byte/launch.bennett` | plugin-defined (§17.4) | equal | `493f49f47c21104c3acc2804e53a5b90f4b42e43a94f850cd6ad21734804990c` |
| `production-shapes/binding-block-byte/oracle-0/ref.bennett` | exact binding-block-byte | equal | `a0dbb16a79d34b95af199a6bf1fe3394589b8896e5556db9475460365a3d146c` |
| `production-shapes/binding-console-byte/launch.bennett` | plugin-defined (§17.4) | equal | `3f557329da95e54c7fe78bebfedd24ef12c69bd127bae774d1f47160b69f3963` |
| `production-shapes/binding-console-byte/oracle-0/ref.bennett` | exact binding-console-byte | equal | `c396e3caa70f02c3f2ef1cd26ea7b565013a6798c45fea920f50da7a303237bf` |
| `production-shapes/mem-in/launch.bennett` | plugin-defined (§17.4) | equal | `9bf3598072a685bf3f89519105ad1bbf2c9339d6bad09ba4f3642a67851771c7` |
| `production-shapes/mem-in/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `9915a0b7cc0b73a87bb5a60ef9496f393df92be7bbda0a8d56d85ce2d4c09801` |
| `production-shapes/two-regions/launch.bennett` | plugin-defined (§17.4) | equal | `fc93758d35d26c7d22354a460f167c7b4658e16ff59fc62eaf1aaab358ec16d8` |
| `production-shapes/two-regions/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `177dc4fb7351433086dbe19fffe4438e5ff909a3a0868cd56ebac9c30080bacf` |
| `production-shapes/two-regions/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `bca59c9f01201d288c8c62c10661fffbc95c5c3f974d31374114d297eea499ee` |
| `production-shapes/handle-phi/launch.bennett` | plugin-defined (§17.4) | equal | `0f6ed34c62b4742b0df3928dbafb8426ab829fdbe5d768c590ecbf391dd235d1` |
| `production-budgets/baseline/launch.bennett` | plugin-defined (§17.4) | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/baseline/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/identity-once/launch.bennett` | plugin-defined (§17.4) | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/identity-once/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/key-priority/launch.bennett` | plugin-defined (§17.4) | equal | `1937376b4e1f9eca806aaaa115fe0d2e95edef86030f29947371f3f5b00eddb2` |
| `production-budgets/key-priority/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-budgets/explicit-precedence/launch.bennett` | plugin-defined (§17.4) | equal | `970cd2de98b9c795e10b02b39bfe36113da562cdd485962570b93ebb63c9f242` |
| `production-budgets/explicit-precedence/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `4070d82d71b292edecf8e294ce20bde494373189375b59865bedf4c902ede83d` |
| `production-dispatch/finite-kind/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `7706247f043ee9473b685793bf02f902873ccba8e08a70d9fcbb31deac7c99a1` |
| `production-dispatch/finite-kind/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `20a90aa1bc248210f82e6836c6442eab176659fcf7d9ece112edac5b80f8efa3` |
| `production-dispatch/finite-kind/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `177dc4fb7351433086dbe19fffe4438e5ff909a3a0868cd56ebac9c30080bacf` |
| `production-dispatch/finite-kind/out/top/oracle-2/ref.bennett` | plugin-defined (§17.4) | equal | `2e3424c5a8a2ac8dc8fd9387382623f13895e4b61a20f2481f209398599e058e` |
| `production-dispatch/finite-kind/out/top/oracle-3/ref.bennett` | plugin-defined (§17.4) | equal | `bca59c9f01201d288c8c62c10661fffbc95c5c3f974d31374114d297eea499ee` |
| `production-dispatch/runtime-arg/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `759cb3b43245fb76b736bd87585eac26f849fd61ae6c28fbd50b34acf52a3d49` |
| `production-dispatch/runtime-arg/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `20a90aa1bc248210f82e6836c6442eab176659fcf7d9ece112edac5b80f8efa3` |
| `production-dispatch/runtime-arg/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `2e3424c5a8a2ac8dc8fd9387382623f13895e4b61a20f2481f209398599e058e` |
| `production-dispatch/runtime-kind/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `275128e17902ee722b68dadd38c644f8de08bd7cf169c010e553f811cce62e5d` |
| `production-dispatch/runtime-kind/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `20a90aa1bc248210f82e6836c6442eab176659fcf7d9ece112edac5b80f8efa3` |
| `production-dispatch/runtime-kind/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `177dc4fb7351433086dbe19fffe4438e5ff909a3a0868cd56ebac9c30080bacf` |
| `production-dispatch/runtime-kind/out/top/oracle-2/ref.bennett` | plugin-defined (§17.4) | equal | `2e3424c5a8a2ac8dc8fd9387382623f13895e4b61a20f2481f209398599e058e` |
| `production-dispatch/runtime-kind/out/top/oracle-3/ref.bennett` | plugin-defined (§17.4) | equal | `bca59c9f01201d288c8c62c10661fffbc95c5c3f974d31374114d297eea499ee` |
| `production-environments/combined-devices/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `235fc0e814958b3642e61d306304f656ab425dd3f4877110c9423364a016399d` |
| `production-environments/combined-devices/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `70c95cc6dfac0047488280bb970c0983bf7ee23b18c625635c1288b756b40d8c` |
| `production-environments/heterogeneous-layouts/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `2c8643a887177d11b45445d05630fcd3d35f5be747f0dfa5d3a9b86835737455` |
| `production-environments/heterogeneous-layouts/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `b8b93715b1c8867b5a909751a98083ab4c047848fc165af964cb9e8290f0a9be` |
| `production-environments/heterogeneous-layouts/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `ca8767b99f842d1b0886a1a4ef351ca285f5e794a4a62db5f0b2b266b77577f6` |
| `production-environments/inplace-inout/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `645e84bc332c0c0f378a4e003ab5f1a2e2accdecf035a5790b58548e17078662` |
| `production-environments/inplace-inout/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `3a96b70447a95461c2f57e3355690e0359d91b76694f9c1dd31695b3463eaa6c` |
| `production-environments/inplace-inout/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `c31ba2c0bf0e4c0c24ee446851388b7277929bd9b9e37f0fda39baf61a5bb4a7` |
| `production-environments/inplace-not-inverse/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `3a96b70447a95461c2f57e3355690e0359d91b76694f9c1dd31695b3463eaa6c` |
| `production-environments/inplace-second-small-budget/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `3a96b70447a95461c2f57e3355690e0359d91b76694f9c1dd31695b3463eaa6c` |
| `production-environments/inplace-second-small-budget/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `c31ba2c0bf0e4c0c24ee446851388b7277929bd9b9e37f0fda39baf61a5bb4a7` |
| `production-environments/inplace-small-budget/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `3a96b70447a95461c2f57e3355690e0359d91b76694f9c1dd31695b3463eaa6c` |
| `production-environments/inplace-small-budget/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `c31ba2c0bf0e4c0c24ee446851388b7277929bd9b9e37f0fda39baf61a5bb4a7` |
| `production-environments/memory-handle/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `d703537906cb579836d50387594dacd5949c4b3fde2774b11e4537beb25e46f4` |
| `production-environments/memory-layouts/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `1c115129ba9021fd05793e7e1385391b8d7e298f3ce4159e3fb74e61ef825256` |
| `production-environments/memory-layouts/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `8e769dd062adc3ee88b3d00e4e9d1c3613a1f59fbeafa4ecf81ef2516f802122` |
| `production-environments/memory-layouts/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `a468a7c63f9701870ae61226d3b9eaf7d6822df663b86e2322483d62254f8cbf` |
| `production-environments/multiple-outputs/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `7514c665a0bbbe3ec9746b0a6421227d518976f71ad9c9cedc981cc6753c46a0` |
| `production-environments/multiple-outputs/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `6a8622b95a2e7cd0df35abdfcd185388378473fe5ea6a4ec59912009b17ccc20` |
| `production-environments/multiple-outputs/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `081ec9dca3fb9a27ed0dfc3a7366d875f52b9661ebd42319ad2953f0649ebe0f` |
| `production-environments/pointer-layouts/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `c07801c41ed3291225c169da7b368deaf980ac014baf82baa50319c987f9d57e` |
| `production-environments/pointer-layouts/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `c2256e6b4cb3c866f508356a7ba6008b363090b7dac55896f2b9f72af3c18780` |
| `production-environments/pointer-layouts/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `f45d3b2a16c078ac2f156932d1d035441dc5ec289f0dce2ff7511510c9227530` |
| `production-environments/retired-handle/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `fc1c995457b322bd8d765c7730de36ad261a1a878c3ed2194e3d24f84a95d0c6` |
| `production-environments/return-console/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `3fa57ef762f56ae3ddee0d484d44a829cc97c9750035a7eed9a80c223843cfd4` |
| `production-environments/return-console/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `62820c15c570eca2e95f744a8dd31861a04a12f7a83a514979958d06dccc75e2` |
| `production-environments/return-console/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `b780ade2bade3038a2fa29d7a77b3a43a643547d0bd6b3e8d4e6eaff6eed097a` |
| `production-environments/unnamed-layouts/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `2c8643a887177d11b45445d05630fcd3d35f5be747f0dfa5d3a9b86835737455` |
| `production-environments/unnamed-layouts/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `b8b93715b1c8867b5a909751a98083ab4c047848fc165af964cb9e8290f0a9be` |
| `production-environments/unnamed-layouts/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `ca8767b99f842d1b0886a1a4ef351ca285f5e794a4a62db5f0b2b266b77577f6` |
| `production-environments/wide-output/out/top/launch.bennett` | plugin-defined (§17.4) | equal | `ece78bb1691d126e67b4340c6007b624e24614bd731c37fb65c0785b7c11dfc1` |
| `production-environments/wide-output/out/top/oracle-0/ref.bennett` | plugin-defined (§17.4) | equal | `a1842515aee6375b435751038bf1bda78b18e6a2ad25d465dcc6f1913d097635` |
| `production-environments/wide-output/out/top/oracle-1/ref.bennett` | plugin-defined (§17.4) | equal | `67e904f61fca699595efd2e56b68afa877e56fb4283c2cb87e7c87f6bbcb82f6` |
