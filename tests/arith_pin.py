#!/usr/bin/env python3
"""Check both plugin pin records against an immutable arithmetic publication.

With no arguments, inspect the gate-materialised pin. During an upgrade, pass
the publication repository and the full commit observed on its pushed main.
"""

import argparse
import hashlib
from pathlib import Path
import subprocess
import tomllib

from pinned_siblings import ROOT, sibling


def check_pin(root, publication, commit):
    spec = tomllib.loads((root / "SPEC_VERSIONS.toml").read_text())["arith"]
    gate = tomllib.loads((root / "gate.toml").read_text())["siblings"]["bennett-arith"]
    for major in (18, 23):
        relative = f"dist/llvm{major}/bennett-arith.bc"
        bitcode = subprocess.check_output(
            ["git", "-C", str(publication), "show", f"{commit}:{relative}"]
        )
        digest = hashlib.sha256(bitcode).hexdigest()
        sums = subprocess.check_output(
            ["git", "-C", str(publication), "show", f"{commit}:dist/llvm{major}/SHA256SUMS"],
            text=True,
        )
        published = dict(line.split()[::-1] for line in sums.splitlines())
        assert digest == published["bennett-arith.bc"], f"LLVM {major}: invalid publication SHA256SUMS"
        assert spec[f"llvm{major}_sha256"] == digest, (
            f"LLVM {major}: arith publication differs from plugin pin: "
            f'{spec[f"llvm{major}_sha256"]} != {digest}'
        )
        assert gate["files"][relative] == digest, f"LLVM {major}: gate file hash differs from publication"
        expected = f'.tmp/gate/cache/bennett-arith@{commit[:12]}/bennett-arith/{relative}'
        assert spec[f"llvm{major}_path"] == expected, f"LLVM {major}: stale arithmetic cache path"
    assert spec["commit"] == gate["sha"] == commit, "arithmetic publication commits differ"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publication-repo", type=Path)
    parser.add_argument("--publication-commit")
    args = parser.parse_args()
    if (args.publication_repo is None) != (args.publication_commit is None):
        parser.error("--publication-repo and --publication-commit must be supplied together")
    publication = args.publication_repo
    commit = args.publication_commit
    if publication is None:
        publication = sibling("bennett-arith")
        commit = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"]["bennett-arith"]["sha"]
    check_pin(ROOT, publication, commit)
    print(f"Arithmetic publication {commit}: LLVM 18/23 hashes, paths and commits agree")


if __name__ == "__main__":
    main()
