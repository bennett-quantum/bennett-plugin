#!/usr/bin/env python3
"""Exercise the actual no-CMake flags, then build/load both majors from scratch."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe-only", action="store_true")
    args = parser.parse_args()
    work = ROOT / ".tmp/sol-plugin-queue/tmp/build-fallback"
    shutil.rmtree(work, ignore_errors=True)
    fixture, shim, capture = work / "source", work / "bin", work / "captured"
    fixture.mkdir(parents=True)
    shim.mkdir()
    capture.mkdir()
    shutil.copytree(ROOT / "src", fixture / "src")
    (fixture / "scripts").mkdir()
    shutil.copy2(ROOT / "scripts/build", fixture / "scripts/build")
    shutil.copy2(ROOT / "SPEC_VERSIONS.toml", fixture / "SPEC_VERSIONS.toml")
    shutil.copy2(ROOT / "gate.toml", fixture / "gate.toml")
    (fixture / "tests").mkdir()
    for name in ("contracts.py", "pinned_siblings.py"):
        shutil.copy2(ROOT / "tests" / name, fixture / "tests" / name)
    (fixture / ".tmp/gate").mkdir(parents=True)
    (fixture / ".tmp/gate/cache").symlink_to(
        ROOT / ".tmp/gate/cache", target_is_directory=True
    )
    compiler = shutil.which("g++")
    assert compiler
    for name in ("python3", "git", "as", "ld"):
        target = shutil.which(name)
        assert target, name
        (shim / name).symlink_to(target)
    wrapper = shim / "g++"
    # Stop at the first compiler call per major; no object is fabricated.
    wrapper.write_text("#!" + sys.executable + """
import json, os, sys
from pathlib import Path
major = next(m for m in (18,23) if any('/llvm-'+str(m)+'/' in arg for arg in sys.argv))
(Path(os.environ['BENNETT_FALLBACK_CAPTURE']) / (str(major)+'.json')).write_text(json.dumps(sys.argv[1:]))
sys.exit(99)
""")
    wrapper.chmod(0o755)
    environment = dict(
        os.environ, PATH=str(shim), BENNETT_FALLBACK_CAPTURE=str(capture)
    )
    assert shutil.which("cmake", path=environment["PATH"]) is None
    probe = subprocess.run(
        [sys.executable, fixture / "scripts/build"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert probe.returncode != 0, "compiler capture must stop the build"
    (work / "capture.log").write_text(probe.stdout + probe.stderr)
    pins = tomllib.loads((ROOT / "SPEC_VERSIONS.toml").read_text())
    rows = []
    for major in (18, 23):
        flags = json.loads((capture / f"{major}.json").read_text())
        flags = flags[: flags.index("-c")]
        syntax = subprocess.run(
            [compiler, *flags, "-fsyntax-only", fixture / "src/SoftFloat.cpp"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        arith_sha = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"][
            "bennett-arith"
        ]["sha"]
        arith_root = (
            Path(os.environ["BENNETT_GATE_LAYOUT"]) / "bennett-arith"
            if os.environ.get("BENNETT_GATE_LAYOUT")
            else fixture
            / f".tmp/gate/cache/bennett-arith@{arith_sha[:12]}/bennett-arith"
        )
        expected = [
            f'-DBENNETT_ARITH_DEFAULT_PATH="{arith_root}/dist/llvm{major}/bennett-arith.bc"',
            f'-DBENNETT_ARITH_DEFAULT_SHA256="{pins["arith"][f"llvm{major}_sha256"]}"',
        ]
        ok = syntax.returncode == 0 and all(flag in flags for flag in expected)
        rows.append(dict(major=major, ok=ok, flags=flags, error=syntax.stderr))
    report = ROOT / ".tmp/build-fallback.json"
    report.write_text(
        json.dumps(dict(probe_only=args.probe_only, results=rows), indent=2) + "\n"
    )
    assert all(row["ok"] for row in rows), rows
    if not args.probe_only:
        wrapper.unlink()
        wrapper.symlink_to(compiler)
        with (work / "build.log").open("w") as log:
            subprocess.run(
                [sys.executable, fixture / "scripts/build"],
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=1200,
                check=True,
            )
        source = work / "smoke.ll"
        source.write_text("define void @unit() { ret void }\n")
        for row in rows:
            major = row["major"]
            plugin = fixture / f"build/libbennett-plugin-{major}.so"
            subprocess.run(
                [
                    f"/usr/lib/llvm-{major}/bin/opt",
                    "-load-pass-plugin=" + str(plugin),
                    "-passes=bennett",
                    "-bennett-normalise-only",
                    "-bennett-dialect=" + pins["dialect"],
                    "-disable-output",
                    source,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                check=True,
            )
            row["built_and_loaded"] = True
            row["library_bytes"] = plugin.stat().st_size
        report.write_text(
            json.dumps(dict(probe_only=False, results=rows), indent=2) + "\n"
        )
    print(json.dumps(dict(majors=2, probes_passed=2, fresh_build=not args.probe_only)))


if __name__ == "__main__":
    main()
