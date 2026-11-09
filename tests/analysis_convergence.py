#!/usr/bin/env python3
"""Exact modular pointer closure: fixed work bounds, independent of CPU speed.

The embedded LLVM 18 musl-1.2.5 census fixtures retain all 24 gai_strerror
and 22 strcmp instructions and the complete @msgs initializer. Only metadata,
attribute groups and ThinLTO summaries are removed for cross-major parsing.
"""

import argparse
import json
import subprocess
import os
from pathlib import Path

from contracts import ROOT, run

# These bounds count complete scans of this fixed graph, including cached
# dispatches. The production CPU allowance is unchanged; an injected frozen
# thread clock makes the regression predicate depend exclusively on work.
MAX_ROUNDS = 64
MAX_GAI_DISPATCHES = 1536
FIXTURES = {
    'gai_strerror': r'''
source_filename = "musl-1.2.5/src/network/gai_strerror.c"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-musl"

@msgs = internal constant [252 x i8] c"Invalid flags\00Name does not resolve\00Try again\00Non-recoverable error\00Name has no usable address\00Unrecognized address family or invalid length\00Unrecognized socket type\00Unrecognized service\00Unknown error\00Out of memory\00System error\00Overflow\00\00Unknown error\00", align 16

; Function Attrs: nounwind
define dso_local ptr @gai_strerror(i32 noundef %0) local_unnamed_addr {
  %2 = add nsw i32 %0, 1
  %3 = icmp eq i32 %2, 0
  br i1 %3, label %18, label %4

4:                                                ; preds = %14, %1
  %5 = phi i32 [ %16, %14 ], [ %2, %1 ]
  %6 = phi ptr [ %15, %14 ], [ @msgs, %1 ]
  %7 = load i8, ptr %6, align 1
  %8 = icmp eq i8 %7, 0
  br i1 %8, label %18, label %9

9:                                                ; preds = %9, %4
  %10 = phi ptr [ %11, %9 ], [ %6, %4 ]
  %11 = getelementptr inbounds i8, ptr %10, i64 1
  %12 = load i8, ptr %11, align 1
  %13 = icmp eq i8 %12, 0
  br i1 %13, label %14, label %9

14:                                               ; preds = %9
  %15 = getelementptr inbounds i8, ptr %10, i64 2
  %16 = add nsw i32 %5, 1
  %17 = icmp eq i32 %16, 0
  br i1 %17, label %18, label %4

18:                                               ; preds = %14, %4, %1
  %19 = phi ptr [ @msgs, %1 ], [ %15, %14 ], [ %6, %4 ]
  %20 = load i8, ptr %19, align 1
  %21 = icmp eq i8 %20, 0
  %22 = zext i1 %21 to i64
  %23 = getelementptr inbounds i8, ptr %19, i64 %22
  %24 = tail call ptr @__lctrans_cur(ptr noundef nonnull %23)
  ret ptr %24
}

declare hidden ptr @__lctrans_cur(ptr noundef) local_unnamed_addr

''',
    'strcmp': r'''
source_filename = "musl-1.2.5/src/string/strcmp.c"
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-musl"

; Function Attrs: nofree norecurse nosync nounwind memory(read, inaccessiblemem: none)
define dso_local i32 @strcmp(ptr nocapture noundef readonly %0, ptr nocapture noundef readonly %1) local_unnamed_addr {
  %3 = load i8, ptr %0, align 1
  %4 = load i8, ptr %1, align 1
  %5 = icmp ne i8 %3, %4
  %6 = icmp eq i8 %3, 0
  %7 = or i1 %6, %5
  br i1 %7, label %18, label %8

8:                                                ; preds = %8, %2
  %9 = phi ptr [ %12, %8 ], [ %1, %2 ]
  %10 = phi ptr [ %11, %8 ], [ %0, %2 ]
  %11 = getelementptr inbounds i8, ptr %10, i64 1
  %12 = getelementptr inbounds i8, ptr %9, i64 1
  %13 = load i8, ptr %11, align 1
  %14 = load i8, ptr %12, align 1
  %15 = icmp ne i8 %13, %14
  %16 = icmp eq i8 %13, 0
  %17 = or i1 %16, %15
  br i1 %17, label %18, label %8

18:                                               ; preds = %8, %2
  %19 = phi i8 [ %3, %2 ], [ %13, %8 ]
  %20 = phi i8 [ %4, %2 ], [ %14, %8 ]
  %21 = zext i8 %19 to i32
  %22 = zext i8 %20 to i32
  %23 = sub nsw i32 %21, %22
  ret i32 %23
}

''',
}


def frozen_clock(directory):
    clock = directory / "frozen-clock.so"
    result = run(["cc", "-shared", "-fPIC", "-x", "c", "-o", clock, "-"], input=r"""
#define _GNU_SOURCE
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
int clock_gettime(clockid_t clock, struct timespec *time) {
  if (clock != CLOCK_THREAD_CPUTIME_ID)
    return syscall(SYS_clock_gettime, clock, time);
  time->tv_sec = 0;
  time->tv_nsec = 0;
  return 0;
}
""")
    assert result.returncode == 0, result.stderr
    return dict(os.environ, LD_PRELOAD=str(clock.absolute()))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path, default=ROOT / ".tmp/analysis-convergence")
    args = parser.parse_args(argv)
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    plugin = args.plugin or ROOT / f"build/libbennett-plugin-{args.major}.so"
    environment = frozen_clock(directory)
    receipts = []
    failures = []
    # Run the healthy control first so a red gai result still records it.
    for name in ("strcmp", "gai_strerror"):
        source = directory / f"{name}.ll"
        source.write_text(FIXTURES[name])
        report = directory / f"{name}.json"
        report.unlink(missing_ok=True)
        result = run([
            f"/usr/lib/llvm-{args.major}/bin/opt", f"-load-pass-plugin={plugin}",
            "-passes=bennett", "-bennett-dialect=0.2.13", "-bennett-analysis-only",
            f"-bennett-analysis-max-rounds={MAX_ROUNDS}",
            f"-bennett-report={report}", "-disable-output", source,
        ], env=environment)
        data = json.loads(report.read_text())
        work = data["analysis_work"]
        receipt = {"case": name, "exit": result.returncode, "work": work}
        receipts.append(receipt)
        (directory / f"{name}.stderr").write_text(result.stderr)
        print(json.dumps(receipt), flush=True)
        if result.returncode:
            failures.append((name, result.stderr))
            continue
        assert data["analysis_rounds"] == work["rounds_completed"] <= MAX_ROUNDS, data
        bound = MAX_GAI_DISPATCHES if name == "gai_strerror" else 22 * MAX_ROUNDS
        assert work["worklist_pops"] <= bound, work
        assert work["cpu_ms"]["value"] == 0, work
    (directory / "results.json").write_text(json.dumps(receipts, indent=2) + "\n")
    assert not failures, failures
    return {"major": args.major, "cases": len(receipts), "passed": len(receipts)}


if __name__ == "__main__":
    try:
        print(json.dumps(main()))
    except subprocess.TimeoutExpired as error:
        print(f"UNKNOWN/TIMEOUT: {error.cmd}")
        raise SystemExit(124)
