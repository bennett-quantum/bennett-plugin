#!/usr/bin/env python3
"""Built plugins must load pinned arithmetic independently of the caller's cwd."""

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def main():
    pins = tomllib.loads((ROOT / "SPEC_VERSIONS.toml").read_text())
    environment = {k: v for k, v in os.environ.items() if not k.startswith("BENNETT_")}
    with tempfile.TemporaryDirectory() as directory:
        work = Path(directory)
        source = work / "add.ll"
        source.write_text(
            "define double @add(double %x, double %y) {\n"
            "  %z = fadd double %x, %y\n  ret double %z\n}\n"
        )
        for major in (18, 23):
            tool = Path(f"/usr/lib/llvm-{major}/bin")
            output = work / f"add-{major}.ll"
            plugin = ROOT / f"build/libbennett-plugin-{major}.so"
            result = subprocess.run(
                [
                    tool / "opt",
                    "-load-pass-plugin=" + str(plugin),
                    "-passes=bennett",
                    "-bennett-dialect=" + pins["dialect"],
                    "-bennett-comparison",
                    source,
                    "-S",
                    "-o",
                    output,
                ],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, (major, result.stdout, result.stderr)
            assert pins["arith"][f"llvm{major}_sha256"] in output.read_text(), major
            library = work / f"add-{major}.so"
            subprocess.run(
                [tool / "clang", "-shared", "-fPIC", output, "-o", library],
                cwd=work,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
            add = ctypes.CDLL(str(library)).add
            add.argtypes = [ctypes.c_double, ctypes.c_double]
            add.restype = ctypes.c_double
            for x, y, expected in (
                (1.5, 2.25, 3.75),
                (-4.0, 1.0, -3.0),
                (0.0, 0.0, 0.0),
            ):
                actual = add(x, y)
                assert actual == expected, (major, x, y, actual, expected)
            print(
                f"LLVM {major}: pinned arithmetic loaded from unrelated cwd; 3/3 sums passed"
            )


if __name__ == "__main__":
    main()
