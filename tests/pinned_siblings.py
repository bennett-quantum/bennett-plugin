"""Resolve this repository's gate pins; never use a live sibling as a fallback."""

import os
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def head(path):
    if not (path / ".git").exists():
        return "unavailable"
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    return result.stdout.strip() if result.returncode == 0 else "unavailable"


def sibling(name):
    config = tomllib.loads((ROOT / "gate.toml").read_text())
    pin = config["siblings"].get(name, {})
    sha = pin.get("sha", "<undeclared>")
    layout = os.environ.get("BENNETT_GATE_LAYOUT")
    path = (
        Path(layout) / name
        if layout
        else ROOT / ".tmp/gate/cache" / f"{name}@{sha[:12]}" / name
    )
    actual = head(path)
    if not re.fullmatch("[0-9a-f]{40}", sha) or actual != sha:
        live = pin.get("repo", name)
        raise SystemExit(
            f"pin: {name} pinned {sha}; {path} HEAD={actual}; "
            f"live ../{live} HEAD={head(ROOT.parent / live)}; "
            f'materialise with gate_run.py verify --repo {config["repo"]} --sha HEAD'
        )
    return path
