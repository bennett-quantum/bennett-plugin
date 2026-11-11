#!/usr/bin/env python3
"""Constant-expression operands retain edge uses, link addresses and cleanup."""

import argparse
import json
import shutil
from pathlib import Path

from contracts import ROOT, run_checked, sibling
from comparison_layout import sections


SOURCE = '''target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"
@bounds = global [4 x i8] zeroinitializer, align 1
@start = alias i8, ptr @bounds
@end = alias i8, ptr getelementptr (i8, ptr @bounds, i64 4)
@cursor = global ptr getelementptr (i8, ptr @bounds, i64 2), align 8
@state = global i32 0, align 4
@constructors = constant [1 x ptr] [ptr @ctor], align 8
@finalizers = constant [1 x ptr] [ptr @fini], align 8
@ctor_end = alias ptr, ptr getelementptr ([1 x ptr], ptr @constructors, i64 1)
@fini_end = alias ptr, ptr getelementptr ([1 x ptr], ptr @finalizers, i64 1)
@c = private constant [1 x i8] c"C"
@f = private constant [1 x i8] c"F"
define void @ctor() {
  store i32 5, ptr @state
  call void @__bennett_effect_console_write(ptr @c, i64 1)
  ret void
}
define void @fini() {
  %old = load i32, ptr @state
  %new = add i32 %old, 7
  store i32 %new, ptr @state
  call void @__bennett_effect_console_write(ptr @f, i64 1)
  ret void
}
declare void @__bennett_effect_console_write(ptr, i64)
define i32 @entry(i32 %argc, ptr %argv, ptr %envp) {
  br i1 icmp ugt (ptr @ctor_end, ptr @constructors), label %construct, label %route
construct:
  %constructor = load ptr, ptr @constructors
  call void %constructor()
  br label %route
route:
  %which = icmp eq i32 %argc, 0
  br i1 %which, label %left, label %right
left:
  br i1 %which, label %join, label %right
right:
  br label %join
join:
  %edge = phi i1 [icmp ugt (ptr @end, ptr @start), %left], [icmp eq (ptr @end, ptr @start), %right]
  %aggregate = extractvalue {i1, ptr} {i1 icmp ne (ptr @ctor, ptr @fini), ptr getelementptr (i8, ptr @bounds, i64 2)}, 0
  %offset = add i64 ptrtoint (ptr getelementptr (i8, ptr @bounds, i64 2) to i64), 0
  %saved = load ptr, ptr @cursor
  %saved_bits = ptrtoint ptr %saved to i64
  %same = icmp eq i64 %offset, %saved_bits
  br i1 icmp ugt (ptr @fini_end, ptr @finalizers), label %finalize, label %return
finalize:
  %finalizer = load ptr, ptr @finalizers
  call void %finalizer()
  br label %return
return:
  %value = load i32, ptr @state
  %x = zext i1 %edge to i32
  %y = zext i1 %aggregate to i32
  %sum = add i32 %value, %x
  %result = add i32 %sum, %y
  %checked = select i1 %same, i32 %result, i32 99
  ret i32 %checked
}
define i8 @scalar() {
  %value = zext i1 icmp ugt (ptr @end, ptr @start) to i8
  ret i8 %value
}
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", type=int, required=True)
    parser.add_argument("--plugin", type=Path)
    args = parser.parse_args()
    work = ROOT / f".tmp/constant-operands/{args.major}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / "input.ll"
    source.write_text(SOURCE)
    bitcode = work / "input.bc"
    # Published runtime bitcode can contain legacy expressions that LLVM23
    # still reads, although its textual assembler no longer creates them.
    run_checked(["/usr/lib/llvm-18/bin/llvm-as", source, "-o", bitcode])
    tool = Path(f"/usr/lib/llvm-{args.major}/bin")
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    run_checked([tool / "opt", "-passes=verify", bitcode, "-disable-output"])
    # The native compiler independently evaluates the same expression graph.
    host = work / "host.c"
    host.write_text('''#include <stdio.h>
extern int entry(int, char **, char **);
void __bennett_effect_console_write(const void *p, unsigned long n) { fwrite(p,1,n,stdout); }
int main(int argc, char **argv) { return entry(argc-1,argv,0); }
''')
    exe = work / "native"
    run_checked([tool / "clang", bitcode, host, "-o", exe])
    for ac, status in ((0, 14), (1, 13)):
        native = run_checked([exe, *(["x"] if ac else [])], code=status)
        assert native.stdout == "CF", native.stdout
    ref = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    for base in (4096, 65536):
        out = work / str(base)
        run_checked([tool / "opt", "-load-pass-plugin=" + str(plugin), "-passes=bennett",
                     "-bennett-dialect=0.3-r1", "-bennett-isa=0.9", "-bennett-tier=reversible",
                     "-bennett-entry=entry", f"-bennett-layout-data-base={base}", "-bennett-layout-text-base=8388608",
                     "-bennett-budget-default=100000,131072,4096,32,65536", "-bennett-out=" + str(out), bitcode, "-disable-output"])
        obj = out / "entry/launch.bennett"
        run_checked([ref, "check", obj])
        sec = sections(obj)
        build = json.loads((out / "entry/build.json").read_text())
        mapping = build["native_global_mapping"]["globals"]
        rows = {row["source_key"]: (name, row) for name, row in mapping.items()}
        name, bounds = rows["name:bounds"]
        assert bounds["base"] == base and bounds["size"] == 4
        images = dict(line.split() for line in sec["data"].splitlines())
        cursor, placed = rows["name:cursor"]
        assert placed["base"] == base+8 and images[cursor] == (base+2).to_bytes(8,"little").hex()
        ctor, _ = rows["name:constructors"]
        fini, _ = rows["name:finalizers"]
        assert images[ctor] == (8388608).to_bytes(8,"little").hex()
        assert images[fini] == (8388624).to_bytes(8,"little").hex()
        run_checked([tool / "opt", "-passes=verify", out / "device.bc", "-disable-output"])
        for ac, status in ((0, "14"), (1, "13")):
            replies = work / "replies.json"
            replies.write_text(json.dumps([dict(service="bennett.argv", payload="00"*20,
                                                 reply=ac.to_bytes(4,"little").hex()+"00"*16)]))
            result = json.loads(run_checked([ref, "run-program", obj, "entry", "--budget", "1000000,131072,4096,32",
                                            "--replies", replies, "--reverse"]).stdout)
            assert result["results"] == [dict(type="i32", value=status)] and not result["faults"], result
            assert b"".join(bytes.fromhex(row["bytes"]) for row in result["tape"]) == b"CF", result
            assert result["equals_entry"] and result["memory_equals_entry"], result
    scalar = work / "scalar"
    run_checked([tool / "opt", "-load-pass-plugin=" + str(plugin), "-passes=bennett",
                 "-bennett-dialect=0.2.13", "-bennett-oracle=scalar", "-bennett-scalar-shape=;tgt=8",
                 "-bennett-out=" + str(scalar), bitcode, "-disable-output"])
    run_checked([ref, "check", scalar / "ref.bennett"])
    value = json.loads(run_checked([ref, "run-oracle", scalar / "ref.bennett", "ref", "--input", "", "--budget", "1000,0,32,8"]).stdout)
    assert value["payload"] == 1 and value["code"] == 0, value
    print(json.dumps(dict(major=args.major, passed=5, cases=5)))


if __name__ == "__main__":
    main()
