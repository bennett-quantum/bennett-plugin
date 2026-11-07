#!/usr/bin/env python3
"""Mutations of real source files must trip each quality-ratchet dimension."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("quality", ROOT / "scripts/quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)


class Ratchet(unittest.TestCase):
    def test_cpp_mutations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src/sample.cpp"
            source.parent.mkdir()
            original = "int f(int x) {\n  return x + 1;\n}\n"
            source.write_text(original)
            baseline = quality.measure(root, ["src/sample.cpp"])
            self.assertEqual(quality.regressions(baseline, baseline), [])
            for label, change in {
                "length": original.replace("  return", "\n" * 350 + "  return"),
                "complexity": original.replace(
                    "  return", "  if (x) { if (x > 1) return 2; }\n  return"
                ),
                "trivial_wrappers": original + "int wrapper(int x) { return f(x); }\n",
                "process_identifiers": original + "// bp-abc\n",
            }.items():
                with self.subTest(label=label):
                    source.write_text(change)
                    failures = quality.regressions(
                        quality.measure(root, ["src/sample.cpp"]), baseline
                    )
                    self.assertTrue(any(label in item for item in failures), failures)
            source.write_text(original)
            self.assertTrue(
                any(
                    "litter" in item
                    for item in quality.regressions(
                        quality.measure(
                            root, ["src/sample.cpp", "tests/__pycache__/probe.pyc"]
                        ),
                        baseline,
                    )
                )
            )

    def test_python_branch_and_wrapper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "source.py"
            path.write_text("def f(x):\n    return x + 1\n")
            baseline = quality.measure(root, ["source.py"])
            path.write_text(
                "def f(x):\n    if x:\n        return x + 1\n    return 1\n"
                "def wrapper(x):\n    return f(x)\n"
            )
            failures = quality.regressions(
                quality.measure(root, ["source.py"]), baseline
            )
            self.assertTrue(any("complexity" in item for item in failures), failures)
            self.assertTrue(
                any("trivial_wrappers" in item for item in failures), failures
            )


if __name__ == "__main__":
    unittest.main()
