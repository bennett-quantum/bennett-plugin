# Pin-plugin review, round 1

Verdict: **BLOCK**. P0: none. P1: **P1-1 / bp-lfb**, **P1-2 / bp-88d**.

Reviewed `main...job/pin-plugin`: merge base `5a092cded3ba3351ba8cc2977a7eaf3b40f46526`, commits `2a5dfa95f981d324f9d1edc256dd10021e74e575` and **`dff993fbd8d0d7810cf947d619bd54fb3fafbea4`** (reviewed head). Main advanced during review; the merge base and two-commit diff stayed unchanged.

1. **P1-1 — CMake arithmetic defaults depend on caller cwd (bp-lfb).** `SPEC_VERSIONS.toml:12,14`, `scripts/build:10-13`: the resolved `arith_paths` reach only the llvm-config fallback. CMake still embeds the newly relative TOML paths. Calling either CMake-built plugin from another directory without a `BENNETT_*` override fails to read the existing, hash-correct pinned arithmetic library. Both LLVM majors exit 0 from the repo root and 1 from a temporary cwd, reporting `BENNETT_ARITH_BITCODE could not be read: .tmp/gate/cache/...`. Main's defaults were absolute. The new build test forces the fallback, so it misses the normal CMake branch. Require both build paths to use the resolved publication independently of caller cwd, with a regression test.

   Ran `timeout 60s cmake -S . -B .tmp/rev-pin-plugin-r1/tmp/cmake18 -DLLVM_DIR=/usr/lib/llvm-18/lib/cmake/llvm -DCMAKE_EXPORT_COMPILE_COMMANDS=ON`: fresh generated flags confirm the relative default. The execution probe below used the existing CMake-built libraries on both majors, whose flags match; no full rebuild.

2. **P1-2 — ISA contract validation became self-referential (bp-88d).** `tests/contracts.py:31-35`: changing both consumer ISA fields to `999` leaves `drift()` false even though the immutable dialect registry declares ISA `0.8`. Main explicitly rejected ISA values other than `0.8`. The new corruption tests mutate dialect/version/hash/commit but never ISA, allowing unsupported contract metadata through the gate. Require validation against the independent accepted contract and an ISA-corruption regression. The probe below printed `drift()= False`, then failed its assertion (exit 1).

Reproduction commands run from the reviewed worktree, with DISPLAY, WAYLAND_DISPLAY, DBUS_SESSION_BUS_ADDRESS and BROWSER unset, TMPDIR=`$PWD/.tmp/rev-pin-plugin-r1/tmp`, CARGO_TARGET_DIR=`$PWD/.tmp/rev-pin-plugin-r1/target`, and PYTHONDONTWRITEBYTECODE=1:

```bash
timeout 65s python3 -B - <<'PY'
import os, subprocess, tempfile
from pathlib import Path
root=Path.cwd()
env={k:v for k,v in os.environ.items() if not k.startswith('BENNETT_')}
with tempfile.TemporaryDirectory() as d:
    p=Path(d)/'probe.ll'
    p.write_text('define double @f(double %x, double %y) { %z = fadd double %x, %y\n ret double %z }\n')
    for major in (18,23):
        command=[f'/usr/lib/llvm-{major}/bin/opt','-load-pass-plugin='+str(root/f'build/libbennett-plugin-{major}.so'),'-passes=bennett','-bennett-dialect=0.2.13','-bennett-comparison',str(p),'-disable-output']
        for cwd in (str(root), d):
            result=subprocess.run(command,cwd=cwd,env=env,capture_output=True,text=True,timeout=20)
            print('major',major,'cwd',cwd,'exit',result.returncode,'stderr',result.stderr[:2500],flush=True)
PY

timeout 65s python3 -B - <<'PY'
import tempfile
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, 'tests')
import contracts as c
with tempfile.TemporaryDirectory() as d:
    root=Path(d)
    source=(c.ROOT/'SPEC_VERSIONS.toml').read_text()
    (root/'SPEC_VERSIONS.toml').write_text(source.replace('isa = "0.8"', 'isa = "999"').replace('"bennett-isa-spec" = "0.8"', '"bennett-isa-spec" = "999"'))
    with patch.object(c, 'ROOT', root):
        actual=c.drift()
        print('ISA metadata=999; pinned registry ISA=0.8; drift()=',actual,flush=True)
        assert actual, 'unsupported ISA metadata bypasses drift check'
PY
```

Focused verification: `timeout 120s python3 -B tests/pin_policy.py -v` **18/18 pass**; `timeout 60s python3 -B tests/contract_policy.py` and `timeout 60s python3 -B tests/gate_policy.py` **pass**; `timeout 150s python3 -B tests/build_fallback.py --probe-only` **2/2 compiler probes pass**; `timeout 120s python3 -B tests/native_comparison.py --major 18` and the same command with `--major 23` **5/5 each pass**. These passing checks do not cover the two failures above. No full gate or sibling gate ran.

Pin audit: read the pinned registries with `git show`, resolved all eight checkout HEADs, checked every declared file digest, and compared each pin against current `git ls-remote --heads origin` refs using `git merge-base --is-ancestor`. All pins are on origin; VM `805f0ec` is contained only in `wip/session-end-2026-11-03`, not origin/main. Dialect `023f5a7` has the wrong contract; `95a4b8d` has the accepted 0.2.13 text but a stale 0.2.10 registry; `1c29c8d` corrects the registry and retains the consumed spec/header/corpus bytes. Runtime alias `248e468` supplies the pre-existing support/checker hashes while allocator `2076014` stays fixed. VM supplies the launch library; targets `dd03671` supplies the target JSON; conformance `6e6a6f1` supplies the three C fixtures and manifest. The latter two inputs are byte-identical to `3ef86a56` / `e39501e3`. All added pins have consumers; ISA/arith/allocator pins are unchanged.

P2+ nits, one bead **bp-cwl**: inherited stale/duplicated README contract and relocation instructions; plan item 9 quality baseline/ratchet absent and item 10 HANDOFF retirement/meta-handoff link absent (also tracked docs/PROGRESS.md), for quality-plugin followup; stale job-runner explanation at tests/pin_policy.py:18.

Coverage: read all 23 changed-file diffs closely, resolver/policy/build paths and gate_policy.py in full; skimmed surrounding unchanged consumer bodies. Read main-side contracts/build/policy code: empty-live/changed-registry and legacy-override tests would fail there; ran them at head without branch switching or new worktrees. Checked every COMMON anti-slop rule: dispatch/state/predicates/constants/altitude/wrappers add no blocking issue; independent fixture/hash oracles and real assertions are present; the ISA self-comparison is P1-2; process prose/stale docs are nits; no added tracked cache/log/lock/scratch litter, over-300-line function, owned-path violation or capability narrowing. src/ was excluded; bp-exw and bp-w9a were not re-filed.

Provenance: implementer gpt-6.1-sol; reviewer gpt-6.1-sol, fresh session, D9.
