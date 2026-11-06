#!/usr/bin/env python3
"""N22 limb semantics against Python integers, including loop/ABI/bitcast edges."""

import argparse, ctypes, json, os, random, re, subprocess
from scalars import REF
from contracts import validate_normalisation, plugin_command, ROOT as R

p = argparse.ArgumentParser()
p.add_argument("--major", type=int, required=True)
a = p.parse_args()
d = R / f".tmp/wide/{a.major}"
d.mkdir(parents=True, exist_ok=True)
tool = f"/usr/lib/llvm-{a.major}/bin/"
rows = []
from functools import partial
from contracts import run_checked

run = partial(run_checked, timeout=90)
ops = [
    "add",
    "sub",
    "mul",
    "and",
    "or",
    "xor",
    "shl",
    "lshr",
    "ashr",
    "udiv",
    "urem",
    "sdiv",
    "srem",
]
source = []
for n in [129, 192, 257, 512]:
    for op in ops:
        source.append(
            f"define void @f{n}_{op}(ptr %p,ptr %q,ptr %r) {{ %a = load i{n}, ptr %p, align 1\n %b = load i{n}, ptr %q, align 1\n %v = {op} i{n} %a,%b\n store i{n} %v,ptr %r,align 1\n ret void }}"
        )
    for pred in ["eq", "ne", "ult", "ule", "ugt", "uge", "slt", "sle", "sgt", "sge"]:
        source.append(
            f"define i1 @f{n}_{pred}(ptr %p,ptr %q) {{ %a = load i{n},ptr %p,align 1\n %b = load i{n},ptr %q,align 1\n %v = icmp {pred} i{n} %a,%b\n ret i1 %v }}"
        )
    # Self loop, wide parameters/results, selects, partial sign extension and truncation.
    source.append(f"""define internal i{n} @step{n}(i{n} %a,i1 %c) {{
 entry: br label %loop
 loop: %v = phi i{n} [ %a, %entry ], [ %next, %loop ]
 %i = phi i32 [ 0, %entry ], [ %j, %loop ]
 %next = add i{n} %v,1
 %j = add i32 %i,1
 %done = icmp eq i32 %j,3
 br i1 %done,label %exit,label %loop
 exit: %out = select i1 %c,i{n} %next,i{n} %a
 ret i{n} %out
 }}
 define void @abi{n}(ptr %p,ptr %q) {{ %a = load i{n},ptr %p,align 1
 %v = call i{n} @step{n}(i{n} %a,i1 true)
 store i{n} %v,ptr %q,align 1
 ret void }}
 define void @cast{n}(ptr %p,ptr %q) {{ %a = load i65,ptr %p,align 1
 %v = sext i65 %a to i{n}
 store i{n} %v,ptr %q,align 1
 ret void }}""")
source.append("""define i64 @pointer(i64 %x) { %p = inttoptr i64 %x to ptr
 %a = ptrtoint ptr %p to i257
 %b = inttoptr i257 %a to ptr
 %r = ptrtoint ptr %b to i64
 ret i64 %r }
define void @constantshift(ptr %p,ptr %q) { %a = load i192,ptr %p,align 1
 %v = shl i192 %a,64
 store i192 %v,ptr %q,align 1
 ret void }""")
source.append(
    "define void @nonbyte(ptr %p,ptr %q) { %a = load i7,ptr %p,align 1\n %b = load i65,ptr %q,align 1\n store i7 %a,ptr %q,align 1\n ret void }"
)
source.append("""define void @bits(ptr %p,ptr %q) { %a = load <8 x i32>,ptr %p,align 1
 %v = bitcast <8 x i32> %a to i256
 %b = bitcast i256 %v to <4 x i64>
 store <4 x i64> %b,ptr %q,align 1
 ret void }
define void @agg(ptr %p,ptr %q) { %v = load {i7,[2 x i24],i129},ptr %p,align 1
 store {i7,[2 x i24],i129} %v,ptr %q,align 1
 ret void }
""")
src = d / "in.ll"
src.write_text("\n".join(source))
out = d / "out.ll"
e = dict(os.environ)
e["BENNETT_ARITH_BITCODE"] = ""
z = subprocess.run(
    [
        *plugin_command(a.major),
        "-bennett-normalise-only",
        "-S",
        str(src),
        "-o",
        str(out),
    ],
    capture_output=True,
    text=True,
    env=e,
)
assert z.returncode == 0, z.stderr
validate_normalisation(
    a.major,
    "define void @memory(ptr %p, ptr %q) { %v = load i129, ptr %p, align 1\n store i129 %v, ptr %q, align 1\n ret void }",
    d,
)
# Runtime slots get a test-only stack allocator; arithmetic definitions come from the plugin.
runtime = d / "stack.c"
runtime.write_text(
    "#include <stdint.h>\n#include <unistd.h>\nstatic unsigned char s[1048576];static uint64_t sp;void *__bennett_rt_ss_push(uint64_t n,uint64_t a){sp=(sp+a-1)&-a;void*p=s+sp;sp+=n;return p;}void __bennett_rt_ss_pop(void*p){sp=(unsigned char*)p-s;}void __bennett_nz_fault(uint64_t n){_exit((int)n);}"
)
so = d / "wide.so"
run([tool + "clang", "-shared", "-fPIC", "-O0", out, runtime, "-o", so])
lib = ctypes.CDLL(str(so))
rng = random.Random(9022)


def buf(x, n):
    return ctypes.create_string_buffer(
        x.to_bytes((n + 7) // 8, "little"), 8 * ((n + 63) // 64)
    )


def signed(x, n):
    return x - (1 << n) if x >> (n - 1) else x


for n in [129, 192, 257, 512]:
    mask = (1 << n) - 1
    vectors = [
        (0, 1),
        (mask, 1),
        (1 << (n - 1), 3),
        ((1 << 64) - 1, (1 << 64) + 1),
        (0, mask),
    ] + [(rng.getrandbits(n), rng.getrandbits(n) or 1) for _ in range(15)]
    for op in ops:
        fn = getattr(lib, f"f{n}_{op}")
        fn.argtypes = [ctypes.c_void_p] * 3
        for x, y in vectors:
            if op in ["shl", "lshr", "ashr"]:
                ys = [0, 1, 63, 64, 65, n - 1, n, n + 1, mask]
            else:
                ys = [y]
            for y in ys:
                sx, sy = signed(x, n), signed(y, n)
                if op in ["sdiv", "srem"] and (
                    not y or (sx == -(1 << (n - 1)) and sy == -1)
                ):
                    continue
                if op in ["udiv", "urem"] and not y:
                    continue
                if op == "add":
                    v = x + y
                elif op == "sub":
                    v = x - y
                elif op == "mul":
                    v = x * y
                elif op == "and":
                    v = x & y
                elif op == "or":
                    v = x | y
                elif op == "xor":
                    v = x ^ y
                elif op == "shl":
                    v = x << y if y < n else 0
                elif op == "lshr":
                    v = x >> y if y < n else 0
                elif op == "ashr":
                    v = sx >> y if y < n else 0
                elif op == "udiv":
                    v = x // y
                elif op == "urem":
                    v = x % y
                else:
                    q = abs(sx) // abs(sy) * (-1 if (sx < 0) != (sy < 0) else 1)
                    v = q if op == "sdiv" else sx - q * sy
                output = buf(0, n)
                fn(buf(x, n), buf(y, n), output)
                got = int.from_bytes(output.raw[: (n + 7) // 8], "little")
                assert got == v & mask, (n, op, x, y, got, v & mask)
        rows.append(f"{n}/{op}")
    for pred in ["eq", "ne", "ult", "ule", "ugt", "uge", "slt", "sle", "sgt", "sge"]:
        fn = getattr(lib, f"f{n}_{pred}")
        fn.argtypes = [ctypes.c_void_p] * 2
        fn.restype = ctypes.c_bool
        for x, y in vectors + [(mask, mask), (0, 0)]:
            sx, sy = (signed(x, n), signed(y, n)) if pred.startswith("s") else (x, y)
            op = pred[1:] if pred[0] in "su" else pred
            expected = {
                "eq": sx == sy,
                "ne": sx != sy,
                "lt": sx < sy,
                "le": sx <= sy,
                "gt": sx > sy,
                "ge": sx >= sy,
            }[op]
            assert fn(buf(x, n), buf(y, n)) == expected, (n, pred, x, y)
        rows.append(f"{n}/{pred}")
    for x, y in vectors:
        fn = getattr(lib, f"abi{n}")
        output = buf(0, n)
        fn(buf(x, n), output)
        assert int.from_bytes(output.raw[: (n + 7) // 8], "little") == (x + 3) & mask
        fn = getattr(lib, f"cast{n}")
        output = buf(0, n)
        x &= (1 << 65) - 1
        fn(buf(x, 65), output)
        assert (
            int.from_bytes(output.raw[: (n + 7) // 8], "little") == signed(x, 65) & mask
        )
    rows.extend([f"{n}/ABI-loop-select", f"{n}/sext65"])
x = bytes(range(32))
outbuf = ctypes.create_string_buffer(32)
lib.bits(ctypes.create_string_buffer(x), outbuf)
assert outbuf.raw == x
rows.append("N21-bitcast256")
fn = lib.pointer
fn.argtypes = [ctypes.c_uint64]
fn.restype = ctypes.c_uint64
for x in (
    [0, 1, 0xFFFFFFFFFFFFFFFF]
    + [1 << bit for bit in range(64)]
    + [rng.getrandbits(64) for _ in range(16)]
):
    assert fn(x) == x
rows.append("pointer-carrier-width")
for x in [1, (1 << 192) - 1]:
    output = buf(0, 192)
    lib.constantshift(buf(x, 192), output)
    assert int.from_bytes(output.raw, "little") == (x << 64) & ((1 << 192) - 1)
rows.append("constant-shift-slot-ABI")
# Padding is left alone; non-byte high representation bits are zeroed.
x = ctypes.create_string_buffer(bytes([255]) * 40)
y = ctypes.create_string_buffer(bytes([170]) * 40)
lib.agg(x, y)
assert (
    y.raw[0] == 127
    and y.raw[1:4] == bytes([170]) * 3
    and y.raw[4:7] == bytes([255]) * 3
    and y.raw[8:11] == bytes([255]) * 3
    and y.raw[28] == 1
    and y.raw[29:32] == bytes([170]) * 3
), y.raw.hex()
rows.append("aggregate-intervals-padding")
y = ctypes.create_string_buffer(bytes([255]) * 16)
lib.nonbyte(x, y)
assert y.raw[0] == 127
rows.append("nonbyte-zero-high")
# Fault branches execute, including the partial-top signed MIN / -1 case.
for n in [129, 192, 257, 512]:
    for op, x, y in [
        ("udiv", 1, 0),
        ("urem", 1, 0),
        ("sdiv", 1 << (n - 1), (1 << n) - 1),
        ("srem", 1 << (n - 1), (1 << n) - 1),
    ]:
        pid = os.fork()
        if pid == 0:
            getattr(lib, f"f{n}_{op}")(buf(x, n), buf(y, n), buf(0, n))
            os._exit(0)
        status = os.waitpid(pid, 0)[1]
        assert os.waitstatus_to_exitcode(status) == (6 if op.startswith("s") else 5), (
            n,
            op,
            status,
        )
    rows.append(f"{n}/faults5-6")
# The N22 slot runtime must also lower to an executable ISA object.
prod = d / "production.ll"
prod.write_text("""define internal i1 @wideprod(ptr %p) { %a = load i192,ptr %p,align 1
 %b = add i192 %a,1
 %c = mul i192 %b,3
 %r = icmp eq i192 %c,6
 ret i1 %r }\n!llvm.module.flags = !{!0}\n!0 = !{i32 1, !"bennett.sstack", i64 128}""")
obj = d / "production"
run(
    [
        *plugin_command(a.major),
        "-bennett-oracle=wideprod",
        "-bennett-scalar-shape=MEM_IN(32);tgt=1",
        "-bennett-scalar-stack=4096",
        "-bennett-scalar-heap=4096",
        "-bennett-out=" + str(obj),
        "-disable-output",
        prod,
    ]
)
run([REF, "check", obj / "ref.bennett"])
for value in [0, 1, (1 << 192) - 1]:
    data = json.loads(
        run(
            [
                REF,
                "run-oracle",
                obj / "ref.bennett",
                "ref",
                "--input",
                "",
                "--mem",
                "m0=" + value.to_bytes(32, "little").hex(),
                "--budget",
                "1000000,4096,4096,128",
            ]
        ).stdout
    )
    assert data["code"] == 0 and data["payload"] == int(value == 1), data
rows.append("production-N22-runtime-execute")
result = dict(major=a.major, cases=len(rows), passed=len(rows), results=rows)
(R / f".tmp/wide-{a.major}.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
