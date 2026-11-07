#!/usr/bin/env python3
"""Probe real vfprintf from the gate-pinned, digest-checked musl source archive."""

import argparse
import hashlib
import importlib.util
import json

from contracts import ROOT, plugin_command, run, run_checked, sibling
from varargs import no_va_ops


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, choices=(18, 23), required=True)
    args = parser.parse_args()
    root = sibling("bennett-runtimes")
    directory = ROOT / f".tmp/varargs-musl/{args.major}"
    directory.mkdir(parents=True, exist_ok=True)
    # Invoke the publication's own source preparation, which checks the archive
    # hash and applies its recorded patches. All outputs stay in this checkout.
    spec = importlib.util.spec_from_file_location("pinned_musl", root / "scripts/musl.py")
    musl = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(musl)
    scratch = directory / "source"
    scratch.mkdir(exist_ok=True)
    # prepare() applies patches in place; use a fresh tree on repeated probes.
    import shutil
    shutil.rmtree(scratch / "musl-1.2.5", ignore_errors=True)
    files, flags = musl.prepare(root, directory, scratch)
    source = next(path for path in files if path.name == "vfprintf.c")
    tool = f"/usr/lib/llvm-{args.major}/bin/"
    raw = directory / "vfprintf.bc"
    run_checked([tool + "clang", *flags, "-c", source, "-o", raw])
    output = directory / "vfprintf-out.ll"
    result = run([
        *plugin_command(args.major), "-bennett-normalise-only", "-S", raw, "-o", output,
    ], timeout=180)
    report = dict(
        major=args.major, runtime_pin=root.parent.name,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        normalise_exit=result.returncode, diagnostic=result.stderr,
    )
    if result.returncode == 0:
        run_checked([tool + "opt", "-passes=verify", output, "-disable-output"])
        no_va_ops(output.read_text())
        report["no_va_operations"] = True
        residual = run([
            *plugin_command(args.major), "-bennett-validate-only",
            "-bennett-validate-classical", output, "-disable-output",
        ])
        report.update(residual_exit=residual.returncode, residual_diagnostic=residual.stderr)
    (directory / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    assert result.returncode == 0, report


if __name__ == "__main__":
    main()
