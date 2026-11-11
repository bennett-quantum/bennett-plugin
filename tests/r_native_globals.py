#!/usr/bin/env python3
"""R device IDs retain explicit source/native correspondence through checking."""

import argparse
import copy
import hashlib
import json
import shutil

from contracts import ROOT, run_checked


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True)
    args = parser.parse_args()
    work = ROOT / f".tmp/r-native-globals/{args.major}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / "input.c"
    source.write_text('''char unused[] = "hi\\n";
static char message[] = "hi\\n";
static char duplicate[] = "hi\\n";
char *pointer = duplicate;
unsigned long observed;
extern void __bennett_effect_console_write(const void *, unsigned long);
int main(void) {
  __bennett_effect_console_write(message, 3);
  observed = (unsigned long)pointer;
  return 0;
}
''')
    bitcode = work / "input.bc"
    run_checked([f"/usr/lib/llvm-{args.major}/bin/clang", "-O1", "-emit-llvm", "-c", source, "-o", bitcode])
    tool = f"/usr/lib/llvm-{args.major}/bin/opt"
    plugin = "-load-pass-plugin=" + str(ROOT / f"build/libbennett-plugin-{args.major}.so")
    out = work / "out"
    run_checked([tool, plugin, "-passes=bennett", "-bennett-dialect=0.3-r1",
                 "-bennett-isa=0.9", "-bennett-tier=reversible", "-bennett-entry=main",
                 "-bennett-out=" + str(out), bitcode, "-disable-output"])
    entry = out / "main"
    record_path = entry / "launch-record.json"
    record = json.loads(record_path.read_text())
    build = json.loads((entry / "build.json").read_text())
    mapping = build["native_global_mapping"]
    assert mapping["schema"] == "bennett-device-native-globals-1"
    globals_ = mapping["globals"]
    assert set(globals_) == set(build["layout"]["globals"])
    keys = {row["source_key"] for row in globals_.values()}
    assert {"name:message", "name:duplicate", "name:pointer", "name:observed"} <= keys
    assert "name:unused" not in keys
    original = {str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()}
    for path, artifact in record["artifacts"].items():
        assert sha(out / path) == artifact["sha256"]
    report = work / "prepared.json"
    prepared = work / "prepared.bc"
    command = [tool, plugin, "-passes=bennett-native-comparison", "-bennett-native-prepare-only",
               "-bennett-native-record=" + str(record_path), "-bennett-native-entry=main",
               "-bennett-native-report=" + str(report), out / "device.bc", "-o", prepared]
    transformed = [str(item).replace("-passes=bennett-native-comparison", "-passes=function(instnamer),bennett-native-comparison") for item in command]
    assert "BD-E-NATIVE-INPUT" in run_checked(transformed, code=1).stderr
    run_checked(command)
    meta = json.loads(report.read_text())
    assert meta["record_sha256"] == sha(record_path)
    assert meta["materialised_sha256"] == sha(out / "device.bc")
    assert meta["launch_sha256"] == sha(entry / "launch.bennett")
    rows = {row["source_key"]: row for row in meta["symbols"] if row["kind"] == "global"}
    assert "name:unused" in rows  # Additional symbols must never be zipped to device IDs.
    for name, row in globals_.items():
        native = meta["device_globals"][name]
        assert native == dict(row, native_symbol=rows[row["source_key"]]["native_symbol"])
        assert row["base"] == build["layout"]["globals"][name]["base"]
        assert row["size"] == rows[row["source_key"]]["size"]
    final = work / "final.json"
    run_checked([tool, plugin, "-passes=bennett-native-comparison-finalise",
                 "-bennett-native-report=" + str(final), prepared, "-o", work / "final.bc"])
    assert json.loads(final.read_text())["device_globals"] == meta["device_globals"]
    assert original == {str(p.relative_to(out)): sha(p) for p in out.rglob("*") if p.is_file()}
    selected = next(name for name, row in globals_.items() if row["source_key"] == "name:message")
    for field, value in [("base", 123456), ("source_key", "name:missing"), ("size", 999)]:
        altered = copy.deepcopy(build)
        altered["native_global_mapping"]["globals"][selected][field] = value
        (entry / "build.json").write_text(json.dumps(altered))
        record["artifacts"]["main/build.json"]["sha256"] = sha(entry / "build.json")
        record_path.write_text(json.dumps(record))
        result = run_checked(command, code=1)
        assert "BD-E-NATIVE-INPUT" in result.stderr, result.stderr
    altered = copy.deepcopy(build)
    del altered["native_global_mapping"]["globals"][selected]
    (entry / "build.json").write_text(json.dumps(altered))
    record["artifacts"]["main/build.json"]["sha256"] = sha(entry / "build.json")
    record_path.write_text(json.dumps(record))
    assert "BD-E-NATIVE-INPUT" in run_checked(command, code=1).stderr
    (entry / "build.json").write_text(json.dumps(build))
    record["artifacts"]["main/build.json"]["sha256"] = sha(entry / "build.json")
    record_path.write_text(json.dumps(record))
    obj = entry / "launch.bennett"
    obj.write_text(obj.read_text() + "\n")
    assert "BD-E-NATIVE-INPUT" in run_checked(command, code=1).stderr
    print(json.dumps(dict(major=args.major, passed=1, cases=1)))


if __name__ == "__main__":
    main()
