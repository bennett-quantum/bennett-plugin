#!/usr/bin/env python3
"""N4 drops unused personalities; stock Rust retains its ordinary panic policy."""

import json
import re
import shutil
import subprocess
from pathlib import Path

from contracts import ROOT, plugin_command, run_checked, sibling


def headers(text):
    return {match[1]: match[0] for match in re.finditer(r"^define[^\n]*?@([^ (]+)[^\n]*", text, re.M)}


def check_eh(tool, plugin, work):
    source = work / "eh.ll"
    source.write_text('''declare i32 @rust_eh_personality(...)
declare void @may_throw()
declare i32 @llvm.eh.typeid.for(ptr)
@typeinfo = external global i8
define i8 @plain(i8 %x) #0 personality ptr @rust_eh_personality { ret i8 %x }
define void @cleanup() #0 personality ptr @rust_eh_personality {
  invoke void @may_throw() to label %done unwind label %unwind
done: ret void
unwind:
  %exception = landingpad {ptr, i32} cleanup
  resume {ptr, i32} %exception
}
define i32 @typeid() personality ptr @rust_eh_personality {
  %id = call i32 @llvm.eh.typeid.for(ptr @typeinfo)
  ret i32 %id
}
attributes #0 = { mustprogress }
''')
    normalised = work / "eh-normalised.ll"
    run_checked([*plugin, "-bennett-normalise-only", source, "-S", "-o", normalised])
    text = normalised.read_text()
    rows = headers(text)
    assert "personality" not in rows["plain"], rows["plain"]
    assert "personality" in rows["cleanup"] and "invoke" in text and "landingpad" in text
    assert "personality" in rows["typeid"] and "llvm.eh.typeid.for" in text
    run_checked([tool / "opt", "-passes=verify", normalised, "-disable-output"])
    result = run_checked([*plugin, "-bennett-validate-only", normalised, "-disable-output"], code=1)
    assert "V3" in result.stderr, result.stderr
    # The oracle operates on its private copy; the input/H module keeps its EH.
    retained = work / "retained.ll"
    run_checked([*plugin, "-bennett-oracle=plain", "-bennett-scalar-shape=IN(8,zext);tgt=8",
                 "-bennett-out=" + str(work / "plain"), source, "-S", "-o", retained])
    assert "personality" in headers(retained.read_text())["cleanup"]


def main():
    major = 23
    tool = Path(f"/usr/lib/llvm-{major}/bin")
    work = ROOT / ".tmp/rust-personality"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    plugin = plugin_command(major)
    check_eh(tool, plugin, work)
    fixture = sibling("bennett-conformance") / "ladder/rung-1/fixtures/rust"
    source = fixture / "scalars.rs"
    harness = fixture / "native.rs"
    before = source.read_bytes()
    native = []
    for level in (0, 2):
        library, exe = work / f"libr1-{level}.rlib", work / f"native-{level}"
        run_checked(["rustc", "--edition=2024", "--crate-type=rlib", "--crate-name=r1",
                     "-C", f"opt-level={level}", source, "-o", library])
        run_checked(["rustc", "--edition=2024", "--extern", "r1=" + str(library),
                     "-C", f"opt-level={level}", harness, "-o", exe])
        # The unchanged published harness enumerates the complete Int8 products.
        output = work / f"native-{level}.bin"
        with output.open("wb") as stream:
            subprocess.run([exe], stdout=stream, check=True, timeout=60)
        native.append(output.read_bytes())
    assert native[0] == native[1] and len(native[0]) == 2*65536+3*256
    bitcode, linked = work / "input.bc", work / "postlink.ll"
    run_checked(["rustc", "--edition=2024", "--crate-type=lib", "--emit=llvm-bc",
                 "-C", "opt-level=2", source, "-o", bitcode])
    run_checked([tool / "opt", "-passes=lto<O3>", bitcode, "-S", "-o", linked])
    original = headers(linked.read_text())
    assert all("personality" in original[name] for name in ("r1_gcd", "r1_lookup")), original
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    cases = (("r1_gcd", "IN(8,sext),IN(8,sext);tgt=8", [(0,0), (128,0), (128,128), (244,8), (127,128)], 65536),
             ("r1_lookup", "IN(8,sext);tgt=8", [(x,) for x in (0,7,8,127,128,255)], 131584))
    for name, shape, inputs, offset in cases:
        out = work / name
        run_checked([*plugin, "-bennett-oracle=" + name, "-bennett-scalar-shape=" + shape,
                     "-bennett-out=" + str(out), linked, "-disable-output"])
        obj = out / "ref.bennett"
        run_checked([ref, "check", obj])
        for values in inputs:
            result = json.loads(run_checked([ref, "run-oracle", obj, "ref", "--input", ",".join(map(str,values)),
                                             "--budget", "10000,0,32,8"]).stdout)
            index = values[0]*256+values[1] if len(values)==2 else values[0]
            assert (result["code"], result["payload"]) == (0,native[0][offset+index]), result
    assert source.read_bytes() == before
    print(json.dumps(dict(major=major, rust_entries=2, native_int8_products=131840, isa_inputs=11, passed=True)))


if __name__ == "__main__":
    main()
