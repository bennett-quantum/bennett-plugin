#!/usr/bin/env python3
"""Exact 0.2.13 negotiation/reporting with unchanged ISA 0.8 semantic bytes."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.13"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--major", required=True, type=int, choices=(18, 23))
    args = parser.parse_args()
    tool = f"/usr/lib/llvm-{args.major}/bin/"
    plugin = ROOT / f"build/libbennett-plugin-{args.major}.so"
    libraries = subprocess.check_output(
        [tool + "llvm-config", "--link-shared", "--libfiles"], text=True
    ).split()
    # One LLVM per child process avoids mixing its global symbol/option tables.
    loader = """import ctypes,json,sys
for lib in json.loads(sys.argv[1]): ctypes.CDLL(lib,mode=ctypes.RTLD_GLOBAL)
class Info(ctypes.Structure):
 _fields_=[('api',ctypes.c_uint32),('name',ctypes.c_char_p),('version',ctypes.c_char_p),('callback',ctypes.c_void_p)]
plugin=ctypes.CDLL(sys.argv[2]);plugin.llvmGetPassPluginInfo.restype=Info
info=plugin.llvmGetPassPluginInfo()
print(json.dumps(dict(api=info.api,name=info.name.decode(),version=info.version.decode())))
"""
    info = json.loads(
        subprocess.check_output(
            [sys.executable, "-c", loader, json.dumps(libraries), str(plugin)],
            text=True,
        )
    )
    assert (
        info["name"] == "bennett" and info["version"] == f"dialect-{VERSION};isa-0.8"
    ), info
    work = ROOT / f".tmp/dialect-version/{args.major}"
    work.mkdir(parents=True, exist_ok=True)
    source, report = work / "input.ll", work / "report.json"
    base = "define i8 @unit(i8 %x) { ret i8 %x }\n"
    command = [
        tool + "opt",
        "-load-pass-plugin=" + str(plugin),
        "-passes=bennett",
        "-disable-output",
    ]

    def run(flags, body=base):
        source.write_text(body)
        return subprocess.run(
            [*command, *flags, source], capture_output=True, text=True, timeout=120
        )

    valid = (
        base
        + '!llvm.module.flags = !{!0}\n!0 = !{i32 1, !"bennett.dialect", !"0.2.13"}\n'
    )
    result = run(
        [
            "-bennett-dialect=" + VERSION,
            "-bennett-analysis-only",
            "-bennett-report=" + str(report),
        ],
        valid,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["dialect"] == VERSION
    for flags, body in [
        (["-bennett-dialect=0.2.10", "-bennett-analysis-only"], base),
        (["-bennett-dialect=0.2.14", "-bennett-analysis-only"], base),
        (["-bennett-analysis-only"], base),
        (
            [
                "-bennett-dialect=" + VERSION,
                "-bennett-isa=0.9",
                "-bennett-analysis-only",
            ],
            valid,
        ),
        (
            ["-bennett-dialect=" + VERSION, "-bennett-analysis-only"],
            valid.replace('!"0.2.13"', '!"0.2.10"'),
        ),
    ]:
        result = run(flags, body)
        assert result.returncode != 0 and "BD-E-VERSION" in result.stderr, (
            flags,
            result.stderr,
        )
    result = run(["-bennett-pre-link", "-bennett-dialect=wrong"], valid)
    assert result.returncode == 0, result.stderr
    original = (ROOT / "tests/probes/review-mixed-native.ll").read_text()
    result = run(["-bennett-dialect=" + VERSION, "-bennett-out=" + str(work)], original)
    assert result.returncode == 0, result.stderr
    directory = work / "top"
    build = json.loads((directory / "build.json").read_text())
    certificate = json.loads((directory / "certificate.json").read_text())
    assert build["dialect"] == VERSION and build["isa"] == "0.8", build
    assert certificate["producer"]["version"].startswith(
        VERSION + "+build."
    ), certificate
    assert certificate["bindings"]["dialect_mapping_version"] == "0.2.9", certificate
    assert (
        certificate["producer"]["materialisation"]["normaliser_version"] == "0.2.8"
    ), certificate
    for filename in ("coverage.json", "all-coverage.json"):
        coverage = json.loads((directory / filename).read_text())
        assert coverage["entries"] and all(
            row["source"].startswith("dialect-0.2.13:") for row in coverage["entries"]
        ), coverage
    # Captured from the accepted 0.2.10 compiler before adoption: this source
    # has no changed helper body or ISA mapping and must keep its semantic bytes.
    digest = hashlib.sha256((directory / "launch.bennett").read_bytes()).hexdigest()
    assert (
        digest == "201b40a382bdcfd04b9d307f0d69d9f8a748f31b2c8d1b0f2f1b4b4a389f3ccb"
    ), digest
    result = dict(
        major=args.major,
        identity=info,
        checks=10,
        passed=10,
        unchanged_object_sha256=digest,
    )
    (ROOT / f".tmp/dialect-version-{args.major}.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
