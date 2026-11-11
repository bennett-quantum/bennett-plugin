#!/usr/bin/env python3
"""Real argv/envp bytes are imported, relocated and reversed with the R run."""

import argparse
import json
import os
from pathlib import Path
import shutil

from contracts import ROOT, arith_path, run_checked, sibling


def payload(argv, envp, pointer_bytes=8):
    strings = [item.encode() + b"\0" for item in argv + envp]
    start = 24 + (len(argv) + len(envp) + 2) * pointer_bytes
    offsets = []
    for item in strings:
        offsets.append(start)
        start += len(item)
    table = offsets[:len(argv)] + [0] + offsets[len(argv):] + [0]
    return (len(argv).to_bytes(4, "little") + bytes(4) + len(envp).to_bytes(8, "little")
            + start.to_bytes(8, "little")
            + b"".join(item.to_bytes(pointer_bytes, "little") for item in table)
            + b"".join(strings))


def runtime_process(tool, work, major, ref, reply):
    directory = work / "runtime"
    directory.mkdir()
    runtime = sibling("bennett-runtimes") / f"dist/llvm{major}/bennett-runtimes.bc"
    source = ROOT / "tests/probes/r-process-arguments.c"
    run_checked([tool / "clang", "-O2", "-nostdinc", "-isystem", runtime.parent / "musl-sysroot/include",
                 "-emit-llvm", "-c", source, "-o", directory / "input.bc"])
    run_checked([tool / "llvm-link", directory / "input.bc", runtime, arith_path(major),
                 "--only-needed", "-o", directory / "linked.bc"])
    run_checked([tool / "opt", "-passes=lto<O3>", directory / "linked.bc", "-o", directory / "postlink.bc"])
    out = directory / "out"
    run_checked([tool / "opt", "-load-pass-plugin=" + str(ROOT / f"build/libbennett-plugin-{major}.so"),
                 "-passes=bennett", "-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
                 "-bennett-tier=reversible", "-bennett-entry=main",
                 "-bennett-budget-default=100000,262144,4096,32,65536",
                 "-bennett-out=" + str(out), directory / "postlink.bc", "-disable-output"])
    obj = out / "main/launch.bennett"
    run_checked([ref, "check", obj])
    replies = directory / "replies.json"
    replies.write_text(json.dumps([
        dict(service="bennett.argv.bytes", payload="00" * 24, reply=reply.hex()),
        dict(service="bennett.argv.bytes", payload="00" * len(reply), reply=reply.hex()),
    ]))
    for reverse in (False, True):
        result = json.loads(run_checked([ref, "run-program", obj, "main", "--budget", "1000000,262144,4096,32",
                                         "--replies", replies, *(["--reverse"] if reverse else [])]).stdout)
        assert result["results"] == [dict(type="i32", value="7")] and not result["faults"], result
        assert b"".join(bytes.fromhex(row["bytes"]) for row in result["tape"]) == b"abc\nbye\n", result
        if reverse:
            assert result["equals_entry"] and result["memory_equals_entry"], result


def argument_edges(tool, work, major, ref):
    source = work / "edges.c"
    source.write_text('''int main(int argc, char **argv, char **envp) {
  if (!argv || !envp || argv[argc]) return 90;
  int status=10+argc;
  for (char **p=envp; *p; ++p) ++status;
  if (argc && argv[0][0]) return 91;
  return status;
}
''')
    for width, triple in ((32, "i386-unknown-linux-gnu"), (64, "x86_64-unknown-linux-gnu")):
        directory = work / f"edges-{width}"
        directory.mkdir()
        bitcode = directory / "input.bc"
        run_checked([tool / "clang", "--target=" + triple, "-O1", "-emit-llvm", "-c", source, "-o", bitcode])
        out = directory / "out"
        run_checked([tool / "opt", "-load-pass-plugin=" + str(ROOT / f"build/libbennett-plugin-{major}.so"),
                     "-passes=bennett", "-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
                     "-bennett-tier=reversible", "-bennett-entry=main",
                     "-bennett-budget-default=100000,131072,4096,32,65536",
                     "-bennett-out=" + str(out), bitcode, "-disable-output"])
        obj = out / "main/launch.bennett"
        run_checked([ref, "check", obj])
        for argv, envp in (([], []), ([""], []), ([], ["X=y", "Z="])):
            reply = payload(argv, envp, width // 8)
            replies = directory / "replies.json"
            replies.write_text(json.dumps([
                dict(service="bennett.argv.bytes", payload="00" * 24, reply=reply.hex()),
                dict(service="bennett.argv.bytes", payload="00" * len(reply), reply=reply.hex()),
            ]))
            result = json.loads(run_checked([ref, "run-program", obj, "main", "--budget", "1000000,131072,4096,32",
                                             "--replies", replies, "--reverse"]).stdout)
            assert result["results"] == [dict(type="i32", value=str(10+len(argv)+len(envp)))], result
            assert not result["faults"] and result["equals_entry"] and result["memory_equals_entry"], result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True)
    args = parser.parse_args()
    work = ROOT / f".tmp/r-process-arguments/{args.major}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    tool = Path(f"/usr/lib/llvm-{args.major}/bin")
    source = work / "input.c"
    source.write_text('''extern void __bennett_effect_console_write(const void *, unsigned long);
__attribute__((noinline)) unsigned long observe_address(void *p) { return (unsigned long)p; }
int main(int argc, char **argv, char **envp) {
  char local[16] __attribute__((aligned(16)));
  if (observe_address(local) & 15) return 94;
  if (argc != 2 || argv[2] || envp[1]) return 90;
  if (argv[0][0] != 'p' || argv[0][1] || argv[1][3]) return 91;
  if (envp[0][0] != 'X' || envp[0][1] != '=' || envp[0][3]) return 92;
  __bennett_effect_console_write(argv[1], 3);
  __bennett_effect_console_write(envp[0], 3);
  argv[1][0] = '!';
  return 7;
}
''')
    bitcode = work / "input.bc"
    run_checked([tool / "clang", "-O1", "-emit-llvm", "-c", source, "-o", bitcode])
    out = work / "out"
    run_checked([tool / "opt", "-load-pass-plugin=" + str(ROOT / f"build/libbennett-plugin-{args.major}.so"),
                 "-passes=bennett", "-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
                 "-bennett-tier=reversible", "-bennett-entry=main",
                 "-bennett-budget-default=100000,131072,4096,32,65536",
                 "-bennett-out=" + str(out), bitcode, "-disable-output"])
    build = json.loads((out / "main/build.json").read_text())
    assert build["entry_initialisation"]["arguments"] == "bennett-argv-bytes-1"
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    obj = out / "main/launch.bennett"
    run_checked([ref, "check", obj])
    reply = payload(["p", "abc"], ["X=y"])
    replies = work / "replies.json"
    replies.write_text(json.dumps([
        dict(service="bennett.argv.bytes", payload="00" * 24, reply=reply.hex()),
        dict(service="bennett.argv.bytes", payload="00" * len(reply), reply=reply.hex()),
    ]))
    for reverse in (False, True):
        result = json.loads(run_checked([ref, "run-program", obj, "main", "--budget", "1000000,131072,4096,32",
                                         "--replies", replies, *(["--reverse"] if reverse else [])]).stdout)
        assert result["results"] == [dict(type="i32", value="7")] and not result["faults"], result
        assert b"".join(bytes.fromhex(row["bytes"]) for row in result["tape"]) == b"abcX=y", result
        if reverse:
            assert result["equals_entry"] and result["memory_equals_entry"] and result["console_hex"] == "", result
    # Run the generated host stub against the pinned VM, with real vectors.
    # Rename only its native object symbol so a harness can supply exact envp.
    native = work / "host.o"
    run_checked([tool / "clang", "-c", out / "host.bc", "-o", native])
    run_checked([tool / "llvm-objcopy", "--redefine-sym", "main=argument_entry", native])
    harness = work / "host.c"
    harness.write_text('''extern int argument_entry(int, char **, char **);
int main(void) {
  char a[]="p", b[]="abc", e[]="X=y";
  char *argv[]={a,b,0}, *envp[]={e,0};
  int result=argument_entry(2,argv,envp);
  return b[0]=='a' ? result : 93;
}
''')
    library = sibling("bennett-vm") / "target/release/libbennett_vm.so"
    exe = work / "host"
    run_checked([tool / "clang", harness, native, library, "-Wl,-rpath," + str(library.parent), "-o", exe])
    target = sibling("bennett-targets") / "targets/ideal-all-to-all.json"
    environment = dict(os.environ, BENNETT_TARGET=target.read_text(), BENNETT_VM_ENGINE="interpreter")
    run_checked([exe], code=7, env=environment)
    for file in ("device.bc", "host.bc"):
        run_checked([tool / "opt", "-passes=verify", out / file, "-disable-output"])
    argument_edges(tool, work, args.major, ref)
    runtime_process(tool, work, args.major, ref, reply)
    print(json.dumps(dict(major=args.major, passed=8, cases=8)))


if __name__ == "__main__":
    main()
