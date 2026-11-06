#!/usr/bin/env python3
"""§14.1 real CC call frames: typed ABI, loops, recursion and full reversal."""

import argparse, hashlib, json, shutil, subprocess
from contracts import ROOT as R
from production import REF


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--major", type=int, required=True)
    a = ap.parse_args()
    rows = []
    for case in ["cc-calls", "cc-self-call"]:
        rows.append(check(a.major, case))
    result = dict(major=a.major, cases=len(rows), passed=len(rows), results=rows)
    (R / f".tmp/cc-calls-{a.major}.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result, indent=2))


def check(major, case):
    tool = f"/usr/lib/llvm-{major}/bin/"
    plugin = R / f"build/libbennett-plugin-{major}.so"
    d = R / f".tmp/cc-calls/{major}/{case}"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    from contracts import run_stdout as run

    source = R / f"tests/probes/{case}.ll"
    base = [
        tool + "opt",
        "-load-pass-plugin=" + str(plugin),
        "-passes=bennett",
        "-bennett-dialect=0.2.13",
        source,
    ]
    run(
        [
            *base,
            "-bennett-analysis-only",
            "-bennett-report=" + str(d / "recognised.json"),
            "-disable-output",
        ]
    )
    run(
        [
            *base,
            "-bennett-budget-default=100000,128,4096,32,0",
            "-bennett-out=" + str(d / "out"),
            "-disable-output",
        ]
    )
    for file in ["device.bc", "host.bc"]:
        run([tool + "opt", "-passes=verify", d / "out" / file, "-disable-output"])
    obj = d / "out/top/launch.bennett"
    run([REF, "check", obj])
    run([REF, "hash", obj])
    body = obj.read_text()
    assert body.count("fn cc @") == (6 if case == "cc-calls" else 1)
    assert body.count("call @") >= (6 if case == "cc-calls" else 1)
    assert "ret " in body
    executions = []
    heap = 128 if case == "cc-calls" else 0
    for n in [0, 1, 3, 7]:
        expected = (n if case == "cc-calls" else 17) + n * (n + 1) // 2
        data = json.loads(
            run(
                [
                    REF,
                    "run-program",
                    obj,
                    "top",
                    "--args",
                    str(n),
                    "--budget",
                    f"100000,{heap},4096,32",
                    "--reverse",
                ]
            )
        )
        assert data["status"] == "REVERSED" and data["results"] == [
            dict(type="i64", value=str(expected))
        ], data
        assert (
            data["equals_entry"]
            and data["memory_equals_entry"]
            and data["first_difference"] is None
        ), data
        assert data["memory_digest"] == data["entry_memory_digest"], data
        executions.append(dict(input=n, expected=expected, result=data))
    # §9.3: CC outside regions is genuinely dynamic, not token bounded.
    for budget in [f"100000,{heap},4096,2", f"100000,{heap},1,32"]:
        data = json.loads(
            run([REF, "run-program", obj, "top", "--args", "7", "--budget", budget])
        )
        assert data["status"] == "COMPLETED" and not data["faults"], data
        assert data["results"] == [
            dict(type="i64", value=str((7 if case == "cc-calls" else 17) + 28))
        ], data
        executions.append(dict(budget=budget, result=data))
    row = dict(
        case=case,
        ok=True,
        recognised_sha256=sha(d / "recognised.json"),
        materialised_sha256=sha(d / "out/device.bc"),
        materialised_verified=True,
        object_sha256=sha(obj),
        runs=executions,
    )
    return row


if __name__ == "__main__":
    main()
