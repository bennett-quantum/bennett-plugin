#!/usr/bin/env python3
"""N23: native/normalised bytes and admitted, executable R objects on both majors."""

import argparse
import ctypes as c
import json
import os
import re

from contracts import (
    ROOT, dialect_text, plugin_command, run, run_checked, sibling,
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
    execute_vm(obj, expected.encode())


def execute_vm(obj, expected):
    """Exercise the gate-pinned VM through its published launch/snapshot ABI."""
    os.environ["BENNETT_VM_ENGINE"] = "interpreter"
    vm = c.CDLL(str(sibling("bennett-vm") / "target/release/libbennett_vm.so"))
    pointer = c.c_void_p
    output_pointer = c.POINTER(pointer)
    u64 = c.c_uint64
    api = {
        "load": ([pointer, c.c_size_t, pointer, c.c_size_t, output_pointer], c.c_int),
        "args_new": ([c.c_size_t, output_pointer], c.c_int),
        "args_free": ([pointer], None),
        "run": ([pointer, c.c_char_p, pointer, pointer, c.c_size_t, c.POINTER(u64)], c.c_int),
        "wait": ([pointer, u64, output_pointer, output_pointer], c.c_int),
        "request_service": ([pointer], c.c_char_p),
        "request_free": ([pointer], None),
        "reply": ([pointer, u64, pointer, c.c_size_t], c.c_int),
        "result_nfaults": ([pointer], c.c_size_t),
        "result_nvalues": ([pointer], c.c_size_t),
        "result_get": ([pointer, c.c_size_t, c.POINTER(c.c_int), c.POINTER(c.c_uint32), pointer, c.c_size_t], c.c_int),
        "result_free": ([pointer], None),
        "run_snapshot": ([pointer, u64, output_pointer], c.c_int),
        "snapshot_jcs": ([pointer, c.POINTER(c.c_size_t)], pointer),
        "snapshot_free": ([pointer], None),
        "reverse": ([pointer, u64], c.c_int),
        "run_close": ([pointer, u64], c.c_int),
        "unload": ([pointer], c.c_int),
        "last_error": ([], c.c_char_p),
    }
    for name, (arguments, result) in api.items():
        function = getattr(vm, "bennett_" + name)
        function.argtypes, function.restype = arguments, result

    def checked(name, *args):
        status = getattr(vm, "bennett_" + name)(*args)
        assert status == 0, (name, status, vm.bennett_last_error())

    def snapshot():
        value, length = pointer(), c.c_size_t()
        checked("run_snapshot", program, run_id, c.byref(value))
        data = json.loads(c.string_at(vm.bennett_snapshot_jcs(value, c.byref(length)), length.value))
        vm.bennett_snapshot_free(value)
        return data

    target = (sibling("bennett-targets") / "targets/ideal-all-to-all.json").read_bytes()
    data = obj.read_bytes()
    program, arguments, run_id = pointer(), pointer(), u64()
    checked("load", data, len(data), target, len(target), c.byref(program))
    checked("args_new", 0, c.byref(arguments))
    checked("run", program, b"main", arguments, None, 0, c.byref(run_id))
    vm.bennett_args_free(arguments)
    entry = snapshot()
    result, request = pointer(), pointer()
    checked("wait", program, run_id, c.byref(result), c.byref(request))
    assert request and not result and vm.bennett_request_service(request) == b"bennett.argv"
    vm.bennett_request_free(request)
    checked("reply", program, run_id, bytes(20), 20)
    checked("wait", program, run_id, c.byref(result), c.byref(request))
    assert result and not request and vm.bennett_result_nfaults(result) == 0, snapshot()
    assert vm.bennett_result_nvalues(result) == 1
    kind, width, status = c.c_int(), c.c_uint32(), c.create_string_buffer(4)
    checked("result_get", result, 0, c.byref(kind), c.byref(width), status, 4)
    assert kind.value == 0 and width.value == 32 and status.raw == bytes(4)
    vm.bennett_result_free(result)
    forward = snapshot()
    checked("reverse", program, run_id)
    reverse = snapshot()
    (obj.parent / "vm-snapshots.json").write_text(json.dumps(dict(forward=forward, reverse=reverse), indent=2) + "\n")
    assert forward["console_hex"] == expected.hex(), forward
    assert reverse["console_hex"] == "", reverse
    assert reverse["memory_digest"] == entry["memory_digest"], (entry, reverse)
    assert reverse["tape"] == [], reverse
    checked("run_close", program, run_id)
    checked("unload", program)


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
