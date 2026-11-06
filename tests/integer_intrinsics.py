#!/usr/bin/env python3
"""N27 semantics, runtime closure, and wide-slot transport against Python integers."""

import argparse, ctypes, json, os, random, re, subprocess
from contracts import validate_normalisation, plugin_command, ROOT as R
from scalars import REF

p = argparse.ArgumentParser()
p.add_argument("--major", type=int, required=True)
a = p.parse_args()
d = R / f".tmp/integer-intrinsics/{a.major}"
d.mkdir(parents=True, exist_ok=True)
tool = f"/usr/lib/llvm-{a.major}/bin/"
rows = []
from functools import partial
from contracts import run_checked

run = partial(run_checked, timeout=180)
widths = [1, 7, 8, 16, 24, 32, 64, 65, 80, 128, 129, 192, 256, 257, 512]
base = [
    "smax",
    "smin",
    "umax",
    "umin",
    "abs",
    "ctpop",
    "ctlz",
    "cttz",
    "bitreverse",
    "fshl",
    "fshr",
    "uadd.sat",
    "usub.sat",
    "sadd.sat",
    "ssub.sat",
    "sshl.sat",
    "ushl.sat",
    "uadd.with.overflow",
    "usub.with.overflow",
    "sadd.with.overflow",
    "ssub.with.overflow",
    "umul.with.overflow",
    "smul.with.overflow",
    "smul.fix",
    "umul.fix",
    "smul.fix.sat",
    "umul.fix.sat",
    "sdiv.fix",
    "udiv.fix",
    "sdiv.fix.sat",
    "udiv.fix.sat",
]
# Use the native target layout throughout: clang must not introduce a different
# wide-lane allocation stride after N21 chose scalar GEPs for an empty layout.
layout = re.search(
    r"^target datalayout = .+$",
    run([tool + "clang", "-S", "-emit-llvm", "-x", "c", "/dev/null", "-o", "-"]).stdout,
    re.M,
)[0]
source = [layout]
cases = []
vector_cases = set()
for n in widths:
    ops = (
        base
        + (["bswap"] if n % 16 == 0 else [])
        + (["scmp", "ucmp", "pdep", "pext", "clmul"] if a.major == 23 else [])
    )
    for op in ops:
        if n == 1 and ".fix" in op:
            continue
        t = f"i{n}"
        over = op.endswith(".overflow")
        ret = "{" + t + ",i1}" if over else "i8" if op in ["scmp", "ucmp"] else t
        unary = op in ["abs", "ctpop", "ctlz", "cttz", "bitreverse", "bswap"]
        types = [t] if unary else [t, t]
        if op in ["abs", "ctlz", "cttz"]:
            types += ["i1"]
        if op in ["fshl", "fshr"]:
            types += [t]
        if ".fix" in op:
            types += ["i32"]
        suffix = f"i8.i{n}" if op in ["scmp", "ucmp"] else t
        source.append(f"declare {ret} @llvm.{op}.{suffix}(" + ",".join(types) + ")")
        call = [t + " %a"]
        if not unary:
            call += [t + " %b"]
        if op in ["abs", "ctlz", "cttz"]:
            call += ["i1 false"]
        if op in ["fshl", "fshr"]:
            call += [t + " %c"]
        if ".fix" in op:
            call += ["i32 " + str(n // 2)]
        name = f"f{n}_" + op.replace(".", "_")
        cases.append((n, op, name))
        body = (
            f"define i8 @{name}(ptr %p,ptr %q,ptr %s,ptr %out) {{ %a = load {t},ptr %p,align 1\n %b = load {t},ptr %q,align 1\n %c = load {t},ptr %s,align 1\n %v = call {ret} @llvm.{op}.{suffix}("
            + ",".join(call)
            + ")\n"
        )
        if over:
            body += f" %value = extractvalue {ret} %v,0\n %flag = extractvalue {ret} %v,1\n store {t} %value,ptr %out,align 1\n %r = zext i1 %flag to i8\n ret i8 %r }}"
        elif op in ["scmp", "ucmp"]:
            body += " store i8 %v,ptr %out,align 1\n ret i8 0 }"
        else:
            body += f" store {t} %v,ptr %out,align 1\n ret i8 0 }}"
        source.append(body)
        if n in [16, 24, 128, 192]:
            # Mixed lanes exercise N21 before N27, including packed i24 storage and
            # aggregate overflow results. Scalar immargs stay scalar in each lane.
            vector_cases.add((n, op))
            vt = f"<4 x {t}>"
            flagtype = "<4 x i8>"
            vret = (
                "{" + vt + ",<4 x i1>}"
                if over
                else flagtype if op in ["scmp", "ucmp"] else vt
            )
            vtypes = [vt if ty == t else ty for ty in types]
            vsuffix = f"v4i8.v4i{n}" if op in ["scmp", "ucmp"] else f"v4i{n}"
            source.append(
                f"declare {vret} @llvm.{op}.{vsuffix}(" + ",".join(vtypes) + ")"
            )
            vcall = [
                arg.replace(t + " ", vt + " ", 1) if arg.startswith(t + " ") else arg
                for arg in call
            ]
            vbody = (
                f"define void @v{name}(ptr %p,ptr %q,ptr %s,ptr %out,ptr %flags) {{ %a = load {vt},ptr %p,align 1\n %b = load {vt},ptr %q,align 1\n %c = load {vt},ptr %s,align 1\n %v = call {vret} @llvm.{op}.{vsuffix}("
                + ",".join(vcall)
                + ")\n"
            )
            if over:
                vbody += f" %value = extractvalue {vret} %v,0\n %flag = extractvalue {vret} %v,1\n store {vt} %value,ptr %out,align 1\n %r = zext <4 x i1> %flag to {flagtype}\n store {flagtype} %r,ptr %flags,align 1\n"
            else:
                vbody += f" store {vret} %v,ptr %out,align 1\n"
            source.append(vbody + " ret void }")
source.append((R / "tests/probes/vector-funnel.ll").read_text())
src = d / "in.ll"
src.write_text("\n".join(source))
out = d / "out.ll"
run(
    [
        *plugin_command(a.major),
        "-bennett-normalise-only",
        "-S",
        src,
        "-o",
        out,
    ]
)
validate_normalisation(a.major, 'declare i8 @llvm.ctpop.i8(i8)\ndefine i8 @count(i8 %x) { %v = call i8 @llvm.ctpop.i8(i8 %x)\n ret i8 %v }', d)
runtime = d / "stack.c"
runtime.write_text(
    "#include <stdint.h>\n#include <unistd.h>\nstatic unsigned char s[1048576];static uint64_t sp;void *__bennett_rt_ss_push(uint64_t n,uint64_t a){sp=(sp+a-1)&-a;void*p=s+sp;sp+=n;return p;}void __bennett_rt_ss_pop(void*p){sp=(unsigned char*)p-s;}void __bennett_nz_fault(uint64_t n){_exit((int)n);}"
)
so = d / "n27.so"
run([tool + "clang", "-shared", "-fPIC", "-O0", out, runtime, "-o", so])
lib = ctypes.CDLL(str(so))
rng = random.Random(9027)


def buf(x, n):
    return ctypes.create_string_buffer(
        x.to_bytes((n + 7) // 8, "little"), 8 * ((n + 63) // 64)
    )


def signed(x, n):
    return x - (1 << n) if x >> (n - 1) else x


def quotient(x, y):
    return abs(x) // abs(y) * (-1 if (x < 0) != (y < 0) else 1)


for n, op, name in cases:
    mask = (1 << n) - 1
    lo = -(1 << (n - 1))
    hi = (1 << (n - 1)) - 1
    vectors = [
        (0, 1),
        (mask, 1),
        (1 << (n - 1), mask),
        (hi, hi),
        (mask, mask),
        (0, 0),
    ] + [(rng.getrandbits(n), rng.getrandbits(n)) for _ in range(5)]
    fn = getattr(lib, name)
    fn.argtypes = [ctypes.c_void_p] * 4
    fn.restype = ctypes.c_uint8
    expected = []
    for x, y in vectors:
        sx, sy = signed(x, n), signed(y, n)
        flag = 0
        z = y
        if ".fix" in op and "div" in op and not y:
            continue
        if op == "abs":
            v = abs(sx)
        elif op in ["smax", "smin", "umax", "umin"]:
            v = (max if op.endswith("max") else min)(
                *((sx, sy) if op[0] == "s" else (x, y))
            )
        elif op == "ctpop":
            v = x.bit_count()
        elif op == "ctlz":
            v = n - x.bit_length()
        elif op == "cttz":
            v = (x & -x).bit_length() - 1 if x else n
        elif op == "bitreverse":
            v = int(f"{x:0{n}b}"[::-1], 2)
        elif op == "bswap":
            v = int.from_bytes(x.to_bytes(n // 8, "little"), "big")
        elif op in ["scmp", "ucmp"]:
            xx, yy = (sx, sy) if op == "scmp" else (x, y)
            v = ((xx > yy) - (xx < yy)) & 255
        elif op in ["fshl", "fshr"]:
            shift = z % n
            v = (
                (((x << n) | y) << shift >> n)
                if op == "fshl"
                else (((x << n) | y) >> shift)
            )
        elif op in ["pdep", "pext"]:
            v = 0
            j = 0
            for k in range(n):
                if y >> k & 1:
                    if op == "pdep":
                        v |= (x >> j & 1) << k
                    else:
                        v |= (x >> k & 1) << j
                    j += 1
        elif op == "clmul":
            v = 0
            for k in range(n):
                if y >> k & 1:
                    v ^= x << k
        else:
            sign = op[0] == "s"
            xx, yy = (sx, sy) if sign else (x, y)
            lower, upper = (lo, hi) if sign else (0, mask)
            if "shl" in op:
                v = (
                    xx << y
                    if y < n
                    else (upper + 1 if xx > 0 else lower - 1 if xx < 0 else 0)
                )
            elif "mul" in op:
                v = xx * yy
            elif "div" in op:
                v = quotient(xx << (n // 2), yy)
            elif "add" in op:
                v = xx + yy
            else:
                v = xx - yy
            if ".fix" in op and "mul" in op:
                v >>= n // 2
            if op.endswith(".overflow"):
                flag = int(v < lower or v > upper)
            if op.endswith(".sat"):
                v = max(lower, min(upper, v))
        output = buf(0, n)
        gotflag = fn(buf(x, n), buf(y, n), buf(z, n), output)
        actual = int.from_bytes(
            output.raw[: (1 if op in ["scmp", "ucmp"] else (n + 7) // 8)], "little"
        )
        want = v & (255 if op in ["scmp", "ucmp"] else mask)
        assert (actual, gotflag) == (want, flag), (
            n,
            op,
            x,
            y,
            actual,
            want,
            gotflag,
            flag,
        )
        expected.append((x, y, z, want, flag))
    if (n, op) in vector_cases:
        vfn = getattr(lib, "v" + name)
        vfn.argtypes = [ctypes.c_void_p] * 5
        vfn.restype = None
        for start in range(0, len(expected), 4):
            lanes = [expected[(start + k) % len(expected)] for k in range(4)]
            inputs = [
                ctypes.create_string_buffer(
                    b"".join(row[j].to_bytes(n // 8, "little") for row in lanes)
                )
                for j in range(3)
            ]
            width = 1 if op in ["scmp", "ucmp"] else n // 8
            output = ctypes.create_string_buffer(4 * width)
            flags = ctypes.create_string_buffer(4)
            vfn(*inputs, output, flags)
            actual = [
                int.from_bytes(output.raw[k * width : (k + 1) * width], "little")
                for k in range(4)
            ]
            assert actual == [row[3] for row in lanes], (n, op, actual, lanes)
            if op.endswith(".overflow"):
                assert list(flags.raw[:4]) == [row[4] for row in lanes], (
                    n,
                    op,
                    flags.raw,
                    lanes,
                )
        rows.append(f"vector4/{n}/{op}")
    rows.append(f"{n}/{op}")
for case, shift in [("shift", 8), ("join", 24)]:
    fn = getattr(lib, "vector_funnel_" + case)
    fn.argtypes = [ctypes.c_void_p] * 3
    fn.restype = None
    for _ in range(8):
        left = [rng.getrandbits(32) for _ in range(4)]
        right = [rng.getrandbits(32) for _ in range(4)]
        joined = [left[0], *right[:3]] if case == "shift" else [left[3], *right[:3]]
        output = ctypes.create_string_buffer(16)
        fn(
            *(
                ctypes.create_string_buffer(
                    b"".join(v.to_bytes(4, "little") for v in values)
                )
                for values in [left, right]
            ),
            output,
        )
        actual = [
            int.from_bytes(output.raw[4 * k : 4 * k + 4], "little") for k in range(4)
        ]
        assert actual == [
            ((x << shift) | (y >> (32 - shift))) & 0xFFFFFFFF
            for x, y in zip(right, joined)
        ], (case, actual, left, right)
    rows.append("memcpy-funnel-" + case)
# Defined-zero count, modular funnel, partial limbs, scalar flags and division faults
# above all use real plugin definitions. Fault rows execute in isolated children.
for n in [7, 65, 129, 192, 257, 512]:
    for op in ["sdiv.fix", "udiv.fix", "sdiv.fix.sat", "udiv.fix.sat"]:
        pid = os.fork()
        if pid == 0:
            getattr(lib, f"f{n}_" + op.replace(".", "_"))(
                buf(1, n), buf(0, n), buf(0, n), buf(0, n)
            )
            os._exit(0)
        assert os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1]) == 5, (n, op)
    rows.append(f"{n}/fault5")
# Production must contain and execute the count-slot body, overflow and saturation.
prod = d / "production.ll"
prod.write_text("""declare i192 @llvm.ctlz.i192(i192,i1)
declare i192 @llvm.uadd.sat.i192(i192,i192)
declare {i192,i1} @llvm.uadd.with.overflow.i192(i192,i192)
define internal i1 @n27prod(ptr %p) { %a = load i192,ptr %p,align 1
 %n = call i192 @llvm.ctlz.i192(i192 %a,i1 false)
 %s = call i192 @llvm.uadd.sat.i192(i192 %a,i192 1)
 %pair = call {i192,i1} @llvm.uadd.with.overflow.i192(i192 %a,i192 1)
 %flag = extractvalue {i192,i1} %pair,1
 %c = icmp eq i192 %n,191
 %v = icmp eq i192 %s,2
 %both = and i1 %c,%v
 %no = xor i1 %flag,true
 %r = and i1 %both,%no
 ret i1 %r }
!llvm.module.flags = !{!0}
!0 = !{i32 1, !"bennett.sstack", i64 256}""")
obj = d / "production"
run(
    [
        *plugin_command(a.major),
        "-bennett-oracle=n27prod",
        "-bennett-scalar-shape=MEM_IN(32);tgt=1",
        "-bennett-scalar-stack=4096",
        "-bennett-scalar-heap=4096",
        "-bennett-out=" + str(obj),
        "-disable-output",
        prod,
    ]
)
run([REF, "check", obj / "ref.bennett"])
for x in [0, 1, (1 << 192) - 1]:
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
                "m0=" + x.to_bytes(32, "little").hex(),
                "--budget",
                "1000000,4096,4096,256",
            ]
        ).stdout
    )
    assert data["code"] == 0 and data["payload"] == int(x == 1), data
rows.append("production-count-slot-overflow-saturation")
result = dict(major=a.major, cases=len(rows), passed=len(rows), results=rows)
(R / f".tmp/integer-intrinsics-{a.major}.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))
