#!/usr/bin/env python3
"""0.3-r1 production faults: ISA §§4.9/5.4/10 and dialect §§17.6/19.9.

Expected causes and prefixes below are hand-derived, using the accepted
r-contract corpus as a contract, not an executor-generated golden file.
"""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from contracts import ROOT, run_checked, sibling


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--case", choices=("versions", "faults", "all"), default="all")
    args = parser.parse_args()
    tool = Path(f"/usr/lib/llvm-{args.major}/bin")
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    work = ROOT / f".tmp/r3-typed-faults/{args.major}"
    work.mkdir(parents=True, exist_ok=True)
    base = [tool / "opt", f"-load-pass-plugin={plugin}", "-passes=bennett"]
    profile = ["-bennett-dialect=0.3-r1", "-bennett-isa=0.9"]
    source = work / "version.ll"
    body = "define i32 @main() { ret i32 0 }\n"

    if args.case in ("versions", "all"):
        source.write_text(body)
        run_checked([*base, *profile, "-bennett-analysis-only", "-disable-output", source])
        for dialect, isa in [("0.3", "0.9"), ("0.3-r1", "0.8"), ("0.2.13", "0.9"), ("unknown", "0.9")]:
            result = run_checked([*base, f"-bennett-dialect={dialect}", f"-bennett-isa={isa}",
                                  "-bennett-analysis-only", "-disable-output", source], code=1)
            assert "BD-E-VERSION" in result.stderr and "§19.9" in result.stderr, result.stderr
        for flag, code in [("0.3-r1", 0), ("0.2.13", 1), ("0.3", 1)]:
            source.write_text(body + '!llvm.module.flags = !{!0}\n'
                              + f'!0 = !{{i32 1, !"bennett.dialect", !"{flag}"}}\n')
            result = run_checked([*base, *profile, "-bennett-analysis-only", "-disable-output", source], code=code)
            if code:
                assert "BD-E-VERSION" in result.stderr and "§19.9" in result.stderr
        # Query the same library with each explicit option profile parsed. LLVM
        # libraries and option state must live in separate processes per major.
        libraries = run_checked([tool / "llvm-config", "--link-shared", "--libfiles"]).stdout.split()
        loader = '''import ctypes,json,sys
for path in json.loads(sys.argv[1]): ctypes.CDLL(path,mode=ctypes.RTLD_GLOBAL)
class Info(ctypes.Structure):
 _fields_=[('api',ctypes.c_uint32),('name',ctypes.c_char_p),('version',ctypes.c_char_p),('callback',ctypes.c_void_p)]
p=ctypes.CDLL(sys.argv[2]);p.llvmGetPassPluginInfo.restype=Info
llvm=ctypes.CDLL(json.loads(sys.argv[1])[0])
argv=[b'identity',b'-bennett-dialect='+sys.argv[3].encode(),b'-bennett-isa='+sys.argv[4].encode()]
llvm.LLVMParseCommandLineOptions(len(argv),(ctypes.c_char_p*len(argv))(*argv),b'')
print(p.llvmGetPassPluginInfo().version.decode())
'''
        for dialect, isa in [("0.2.13", "0.8"), ("0.3-r1", "0.9")]:
            result = run_checked([sys.executable, "-c", loader, json.dumps(libraries), plugin, dialect, isa])
            assert result.stdout.strip() == f"dialect-{dialect};isa-{isa}", result.stdout

    if args.case == "versions":
        print(f"LLVM {args.major}: profile negotiation and identity passed")
        return

    contract = sibling("bennett-r-contract-dialect")
    faults = json.loads((contract / "corpus/legality/r-contract/faults.json").read_text())
    assert faults["codes"] == [0, 1, 2, 3, 5, 6, 7, 8, 10, 2**64-1]
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    replies = work / "replies.json"
    replies.write_text(json.dumps([dict(service="bennett.argv", payload="00"*20, reply="00"*20)]))
    declarations = '''
extern void __bennett_effect_console_write(const void *, unsigned long);
extern void __bennett_effect_entropy_read(void *, unsigned long);
extern void __bennett_nz_fault(unsigned long);
extern void *__bennett_nz_alloc(unsigned long);
extern void __bennett_nz_free(void *);
extern void *__bennett_rt_ss_push(unsigned long, unsigned long);
__attribute__((noinline)) void __bennett_rt_fail(unsigned long code) {
  __bennett_nz_fault(code);
}
__attribute__((noinline)) void *__bennett_rt_allocate(unsigned long size) {
  return __bennett_nz_alloc(size);
}
static char prefix[] = "x";
'''

    def produce(name, body, steps=10000, runtime="", code=0):
        directory = work / name
        directory.mkdir(exist_ok=True)
        source = directory / "input.c"
        source.write_text(declarations + runtime + body)
        bitcode = directory / "input.bc"
        run_checked([tool / "clang", "-O1", "-fno-builtin", "-fno-optimize-sibling-calls", "-emit-llvm", "-c", source, "-o", bitcode])
        result = run_checked([*base, *profile, "--bennett-tier=reversible", "--bennett-entry=main",
                             f"-bennett-budget-default={steps},131072,4096,32,65536",
                             f"-bennett-out={directory / 'out'}", "-disable-output", bitcode], code=code)
        if code:
            assert "unimplemented" in result.stderr and "§17.6" in result.stderr, result.stderr
            assert not (directory / "out/main/launch.bennett").exists()
            return
        assert "BD-B-ISA7" not in result.stderr, result.stderr
        out = directory / "out"
        for file in ("device.bc", "host.bc"):
            run_checked([tool / "opt", "-passes=verify", out / file, "-disable-output"])
            text = run_checked([tool / "llvm-dis", out / file, "-o", "-"]).stdout
            assert '!"bennett.dialect", !"0.3-r1"' in text, text
        selected = out / "main"
        obj = selected / "launch.bennett"
        run_checked([ref, "check", obj])
        run_checked([ref, "hash", obj])
        build_bytes = (selected / "build.json").read_bytes().rstrip(b"\n")
        build = json.loads(build_bytes)
        cert = json.loads((selected / "certificate.json").read_text())
        assert build_bytes == canonical(build)
        assert (build["dialect_version"], build["isa_version"], build["replay_profile"]) == ("0.3-r1", "0.9", "saved-tape-v1")
        assert cert["producer"]["version"] == "0.3-r1+build." + digest(build_bytes)
        assert cert["bindings"]["dialect_mapping_version"] == "0.3"
        assert cert["versions"] == {"isa": "0.9", "cert": "0.9"}
        assert build["object_hash"] == cert["bindings"]["object_hash"] == digest(obj.read_bytes())
        assert json.loads((selected / "blockers.json").read_text()) == []
        assert json.loads((out / "launches.json").read_text())[0]["verdict"] == "accept"
        for file in ("coverage.json", "all-coverage.json"):
            entries = json.loads((selected / file).read_text())["entries"]
            assert entries and all(e["source"].startswith("dialect-0.3-r1:") for e in entries)
        return obj

    def execute(obj, expected, prefix="78"):
        command = [ref, "run-program", obj, "main", "--budget", "1000000,131072,4096,32", "--replies", replies]
        forward = json.loads(run_checked(command).stdout)
        assert forward["status"] == ("COMPLETED" if expected is None else "FAILED"), forward
        assert forward["console_hex"] == prefix, forward
        assert forward["effect_tape_length"] == (1 if prefix else 0), forward
        if expected is None:
            assert forward["faults"] == []
        else:
            assert forward["results"] == [] and len(forward["faults"]) == 1, forward
            assert int(forward["faults"][0]["code"]) == expected, forward
        reverse = json.loads(run_checked([*command, "--reverse"]).stdout)
        assert reverse["status"] == "REVERSED" and reverse["equals_entry"] and reverse["memory_equals_entry"], reverse
        assert reverse["console_hex"] == "" and reverse["effect_tape_length"] == 0, reverse

    # §17.5 effective code: 0 -> 4, all other u64 values preserved. The
    # successor 'y' write and status 99 must never become observable.
    for code in [*faults["codes"], 4, 9, 2**63+17]:
        obj = produce(f"literal-{code}", f'''int main(void) {{
 __bennett_effect_console_write(prefix,1);
 __bennett_rt_fail({code}UL);
 __bennett_effect_console_write("y",1); return 99;
}}''')
        execute(obj, code or 4)

    # Exactly two materialised instructions: effect and ret. Counter checks
    # do not count themselves (§17.6's 0/1/2 boundary witness).
    for steps, expected, prefix in [(0, 1, ""), (1, 1, "78"), (2, None, "78")]:
        obj = produce(f"steps-{steps}", 'int main(void) { __bennett_effect_console_write(prefix,1); return 0; }', steps)
        execute(obj, expected, prefix)

    # Real source operations exercise the ISA's implicit fault rules, as
    # distinct from the materialised runtime's explicit fault primitive.
    for name, code, argc, operation in [
        ("div0", 5, 0, "return 10 / argc;"),
        ("signed-overflow", 6, -1, "return (-2147483647 - 1) / argc;"),
        ("invalid-memory", 7, 0, "return *(int *)(unsigned long)argc;"),
        ("unmodelled", 8, 0, "missing_service(); return 99;"),
        ("entropy", 10, 0, "__bennett_effect_entropy_read(entropy,1); return 99;"),
        ("heap", 2, 0, "__bennett_rt_allocate(131073); return 99;"),
        ("shadow-stack", 2, 0, "__bennett_rt_ss_push(65537,8); return 99;"),
    ]:
        obj = produce(name, 'int main(int argc, char **argv) { '
                      + '__bennett_effect_console_write(prefix,1); ' + operation + ' }',
                      runtime='extern void missing_service(void); static char entropy[1];\n')
        replies.write_text(json.dumps([dict(service="bennett.argv", payload="00"*20,
                                           reply=argc.to_bytes(4,"little",signed=True).hex()+"00"*16)]))
        execute(obj, code)

    # A recursive SCC must have fresh ISA 0.9 identities, and the terminal
    # record must preserve all open activations for FAILED reversal.
    obj = produce("recursive-fault", '''int main(void) {
 __bennett_effect_console_write(prefix,1); return __bennett_rt_recurse(2);
}''', runtime='''__attribute__((noinline)) int __bennett_rt_recurse(int n) {
 if (!n) { __bennett_nz_fault(3); return 99; }
 return __bennett_rt_recurse(n-1)+1;
}
''')
    replies.write_text(json.dumps([dict(service="bennett.argv", payload="00"*20, reply="00"*20)]))
    execute(obj, 3)

    # Finite dynamic literal dispatch must retain 64 bits (§17.6).
    for argc, code in [(0, 0), (1, 2), (2, 2**64-1)]:
        obj = produce(f"dynamic-{argc}", '''int main(int argc, char **argv) {
 __bennett_effect_console_write(prefix,1);
 __bennett_rt_fail(argc == 0 ? 0UL : argc == 1 ? 2UL : 18446744073709551615UL);
 return 99;
}''')
        replies.write_text(json.dumps([dict(service="bennett.argv", payload="00"*20,
                                           reply=argc.to_bytes(4,"little").hex()+"00"*16)]))
        execute(obj, code or 4)
    produce("unbounded", 'int main(int argc, char **argv) { __bennett_rt_fail((unsigned long)argc); return 0; }', code=1)
    print(f"LLVM {args.major}: exact typed faults, source-step boundaries, identities and FAILED reversal passed")


if __name__ == "__main__":
    main()
