#!/usr/bin/env python3
"""N23: native/normalised bytes and admitted, executable R objects on both majors."""

import argparse
import json
import re

from contracts import (
    ROOT, dialect_text, plugin_command, run, run_checked,
)
from production import REF


def no_va_ops(body):
    assert not re.search(r"\bva_arg\b|@llvm\.va_(?:start|copy|end)", body), body[-2000:]


def normalise(major, source, output):
    run_checked([*plugin_command(major), "-bennett-normalise-only", "-S", source, "-o", output])
    tool = f"/usr/lib/llvm-{major}/bin/"
    run_checked([tool + "opt", "-passes=verify", output, "-disable-output"])
    body = output.read_text()
    no_va_ops(body)
    return body


def mixed(major, directory, production):
    tool = f"/usr/lib/llvm-{major}/bin/"
    source = ROOT / "tests/probes/varargs-mixed.c"
    native = directory / "native"
    run_checked([tool + "clang", "-O1", "-fno-inline", "-DNATIVE", source, "-o", native])
    expected = run_checked([native]).stdout
    assert expected == "iplqudez\n" * 6, expected
    raw = directory / "mixed.ll"
    run_checked([tool + "clang", "-O1", "-fno-inline", "-S", "-emit-llvm", source, "-o", raw])
    output = directory / "mixed-out.ll"
    body = normalise(major, raw, output)
    for name in ("mixed", "other"):
        signature = re.search(r"define [^\n]*@" + name + r"\(([^)]*)\)", body)
        assert signature and "..." not in signature[1] and "nz.va" in signature[1], signature
    # Only the console transport is supplied by the host, outside the transformed module.
    transport = directory / "transport.c"
    transport.write_text("#include <unistd.h>\nvoid __bennett_effect_console_write(const void *p, unsigned long n) { if (write(1,p,n)!=n) _exit(99); }\n")
    executable = directory / "normalised"
    run_checked([tool + "clang", output, transport, "-o", executable])
    assert run_checked([executable]).stdout == expected
    if not production:
        return
    out = directory / "production"
    result = run_checked([
        *plugin_command(major), "-bennett-tier=reversible", "-bennett-entry=main",
        "-bennett-budget-default=1000000,262144,8192,64,131072",
        "-bennett-out=" + str(out), raw, "-disable-output",
    ], code=3, timeout=180)
    # The current producer explicitly reports ISA-7 even for executable successful paths.
    blockers = json.loads((out / "main/blockers.json").read_text())
    assert [b["code"] for b in blockers] == ["BD-B-ISA7"], (result.stderr, blockers)
    for name in ("host", "device"):
        run_checked([tool + "opt", "-passes=verify", out / f"{name}.bc", "-disable-output"])
    device = run_checked([tool + "llvm-dis", out / "device.bc", "-o", "-"]).stdout
    no_va_ops(device)
    obj = out / "main/launch.bennett"
    run_checked([REF, "check", obj])
    replies = directory / "argv.json"
    replies.write_text(json.dumps([dict(service="bennett.argv", payload="00" * 20, reply="00" * 20)]))
    oracle = REF.parent.parent / "release/bennett-isa-ref"
    for reverse in (False, True):
        execution = json.loads(run_checked([
            oracle, "run-program", obj, "main", "--budget", "5000000,262144,8192,64",
            "--replies", replies, *(["--reverse"] if reverse else []),
        ], timeout=180).stdout)
        assert execution["status"] == "COMPLETED" and not execution["faults"], execution
        assert execution["results"] == [dict(type="i32", value="0")], execution
        tape = b"".join(bytes.fromhex(e["bytes"]) for e in execution["tape"])
        assert tape == expected.encode(), execution
        if reverse:
            assert execution["equals_entry"] and execution["memory_equals_entry"], execution
            assert execution["console_hex"] == "", execution
        else:
            assert bytes.fromhex(execution["console_hex"]) == expected.encode(), execution


def witness(major, directory):
    text = dialect_text()
    source = re.search(r"```llvm normalise-in=n-varargs\n(.*?)```", text, re.S)[1]
    native = re.findall(r"top\((-?\d+)\) = (-?\d+)", re.search(r"```text native=n-varargs\n(.*?)```", text, re.S)[1])
    calls = "".join(
        f" %r{n} = call i32 @top(i32 {x})\n call i32 (ptr, ...) @printf(ptr @fmt, i32 %r{n})\n"
        for n, (x, _) in enumerate(native)
    )
    raw = directory / "witness.ll"
    raw.write_text('target triple = "x86_64-unknown-linux-gnu"\n' + source + '\n@fmt = constant [4 x i8] c"%d\\0A\\00"\ndeclare i32 @printf(ptr, ...)\ndefine i32 @main() {\n' + calls + ' ret i32 0\n}\n')
    output = directory / "witness-out.ll"
    normalise(major, raw, output)
    assert run_checked([f"/usr/lib/llvm-{major}/bin/lli", output]).stdout.split() == [v for _, v in native]


def cursor_rows(major, directory):
    # IR va_arg and va_copy can occur in a nonvariadic helper, with no va_start
    # in that function. The result (7 + 11) is independent of the producer.
    for triple, record in (("x86_64-unknown-linux-gnu", 24),
                           ("aarch64-unknown-linux-gnu", 32),
                           ("riscv64-unknown-linux-gnu", 8)):
        raw = directory / f"{triple}.ll"
        raw.write_text(f'''target triple = "{triple}"
target datalayout = "e-p:64:64-i64:64-i128:128-f80:128"
declare void @llvm.va_start(ptr)
declare void @llvm.va_copy(ptr, ptr)
declare void @llvm.va_end(ptr)
define i32 @read(ptr %ap) {{
 %copy = alloca [{record} x i8], align 8
 call void @llvm.va_copy(ptr %copy, ptr %ap)
 %a = va_arg ptr %copy, i32
 %b = va_arg ptr %copy, i64
 %c = trunc i64 %b to i32
 %sum = add i32 %a, %c
 call void @llvm.va_end(ptr %copy)
 ret i32 %sum
}}
define i32 @sum(i32 %unused, ...) {{
 %ap = alloca [{record} x i8], align 8
 call void @llvm.va_start(ptr %ap)
 %r = call i32 @read(ptr %ap)
 call void @llvm.va_end(ptr %ap)
 ret i32 %r
}}
define i32 @main() {{
 %r = call i32 (i32, ...) @sum(i32 0, i32 7, i64 11)
 %status = sub i32 %r, 18
 ret i32 %status
}}
''')
        output = raw.with_suffix(".out.ll")
        normalise(major, raw, output)
        run_checked([f"/usr/lib/llvm-{major}/bin/lli", "-mtriple=x86_64-unknown-linux-gnu", output])
    # An isolated indirect call still needs the ABI even without a local variadic definition.
    raw = directory / "indirect-only.ll"
    raw.write_text('define i32 @f(ptr %callee) {\n %r = call i32 (i32, ...) %callee(i32 0, i32 7)\n ret i32 %r\n}\n')
    body = normalise(major, raw, raw.with_suffix(".out.ll"))
    assert "..." not in body and "nz.vb" in body, body


def residual(major, directory):
    for name, declaration, instruction in (
        ("arg", "", "%r = va_arg ptr %ap, i32"),
        ("start", "declare void @llvm.va_start(ptr)", "call void @llvm.va_start(ptr %ap)"),
        ("copy", "declare void @llvm.va_copy(ptr, ptr)", "call void @llvm.va_copy(ptr %ap, ptr %ap)"),
        ("end", "declare void @llvm.va_end(ptr)", "call void @llvm.va_end(ptr %ap)"),
    ):
        raw = directory / f"residual-{name}.ll"
        raw.write_text(declaration + "\ndefine void @f(ptr %ap) {\n " + instruction + "\n ret void\n}\n")
        result = run([*plugin_command(major), "-bennett-validate-only", raw, "-disable-output"])
        assert result.returncode != 0 and "§14.3 N23" in result.stderr, result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, choices=(18, 23), required=True)
    parser.add_argument("--normalise-only", action="store_true")
    args = parser.parse_args()
    directory = ROOT / f".tmp/varargs/{args.major}"
    directory.mkdir(parents=True, exist_ok=True)
    mixed(args.major, directory, not args.normalise_only)
    witness(args.major, directory)
    cursor_rows(args.major, directory)
    residual(args.major, directory)
    print(f"varargs LLVM {args.major}: native/normalised bytes agree" + ("; R admitted, executed and reversed" if not args.normalise_only else ""))


if __name__ == "__main__":
    main()
