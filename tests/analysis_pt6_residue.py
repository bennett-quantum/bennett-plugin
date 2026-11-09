#!/usr/bin/env python3
"""PT6 must retain an identical member interval inside a residue slot.

Oracle: dialect 0.2.13 section 5.2 PT6, section 6.2; archived review P0-A
(docs/reviews/2026-11-03-factored-points-to-design.md, commit 33ff4be;
original witness/review by Claude Opus 5.5).
Reconstructed from review 33ff4be P0-A, Opus, 2026-11-03.
The pointer-width load [4,12) equals the residue member starting at 4.
Its whole PTR(@hc,0) survives alongside top from partial neighbors, so
loading @hc must preserve ROOT(%h). Top never stands for a ROOT atom.

Run under the repository's process hang guard. Only --artifacts (or TMPDIR)
is written; fixtures and the selected plugin remain read-only.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


CASES = ("explicit", "residue")
EXPECTED = {"%x": "PTR(@hc,0,0)", "%hh": "ROOT(%h,0,0)"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, choices=(18, 23), required=True)
    parser.add_argument("--plugin", type=Path)
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "BROWSER"):
        os.environ.pop(key, None)
    plugin = (args.plugin or Path(__file__).absolute().parents[1]
              / f"build/libbennett-plugin-{args.major}.so").absolute()
    assert plugin.is_file(), f"missing plugin: {plugin}"
    directory = args.artifacts or Path(tempfile.mkdtemp(prefix="analysis-pt6-"))
    directory.mkdir(parents=True, exist_ok=True)
    probes = Path(__file__).parent / "probes"
    results = []
    for case in CASES:
        report = directory / f"{case}.json"
        report.unlink(missing_ok=True)
        command = [
            f"/usr/lib/llvm-{args.major}/bin/opt",
            f"-load-pass-plugin={plugin}", "-passes=bennett",
            "-bennett-dialect=0.2.13", "-bennett-tier=reversible",
            "-bennett-entry=top", "-bennett-analysis-only",
            f"-bennett-report={report}", "-disable-output",
            str(probes / f"pt6-{case}-handle.ll"),
        ]
        run = subprocess.run(command, capture_output=True, text=True)
        (directory / f"{case}.stdout").write_text(run.stdout)
        (directory / f"{case}.stderr").write_text(run.stderr)
        failures = []
        if run.returncode:
            failures.append(f"expected acceptance; opt exited {run.returncode}")
        else:
            assert report.is_file(), f"missing analysis report: {report}"
            data = json.loads(report.read_text())
            for value, atom in EXPECTED.items():
                rows = [row for row in data["values"]
                        if row["function"] == "top" and row["value"] == value]
                assert len(rows) == 1, (case, value, rows)
                row = rows[0]
                if atom not in row["atoms"]:
                    failures.append(f"{value} lost required {atom}: {row}")
                if not row["top"]:
                    failures.append(f"{value} lost the partial/unknown alternative: {row}")
        results.append({"case": case, "ok": not failures,
                        "opt_exit": run.returncode, "command": command,
                        "failures": failures, "diagnostic": run.stderr.strip()})
    summary = {"major": args.major, "plugin": str(plugin),
               "cases": len(results), "passed": sum(r["ok"] for r in results),
               "results": results}
    (directory / "result.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    return int(any(not result["ok"] for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
