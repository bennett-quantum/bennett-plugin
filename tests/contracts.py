"""Read published contracts and artefacts from this repository's gate pins."""

import hashlib
import json
import os
import subprocess
import tomllib

from pinned_siblings import ROOT, sibling

for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "BROWSER"):
    os.environ.pop(key, None)
(ROOT / ".tmp").mkdir(exist_ok=True)
os.environ.setdefault("TMPDIR", str(ROOT / ".tmp"))
PIN = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"][
    "bennett-dialect-spec"
]["sha"]
DIALECT = tomllib.loads((ROOT / "SPEC_VERSIONS.toml").read_text())["dialect"]
# The plugin's implicit arithmetic input must follow the same pin as explicit links.
os.environ["BENNETT_ARITH_PINNED_ROOT"] = str(sibling("bennett-arith") / "dist")


def run(command, env=None, timeout=120, **kwargs):
    """Run a bounded headless command; retain failures for diagnostic tests."""
    environment = dict(os.environ if env is None else env)
    for key in ("DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "BROWSER"):
        environment.pop(key, None)
    return subprocess.run(
        list(map(str, command)),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=environment,
        **kwargs,
    )


def run_checked(command, *, code=0, **kwargs):
    result = run(command, **kwargs)
    assert result.returncode == code, (
        command,
        result.returncode,
        result.stdout,
        result.stderr,
    )
    return result


def run_stdout(command, **kwargs):
    return run_checked(command, **kwargs).stdout


def plugin_command(major, pipeline="bennett"):
    return [
        f"/usr/lib/llvm-{major}/bin/opt",
        "-load-pass-plugin=" + str(ROOT / f"build/libbennett-plugin-{major}.so"),
        "-passes=" + pipeline,
        "-bennett-dialect=" + DIALECT,
    ]


def dialect_blob(path):
    return subprocess.check_output(
        ["git", "-C", str(sibling("bennett-dialect-spec")), "show", f"{PIN}:{path}"],
        text=True,
    )


def dialect_text():
    return dialect_blob("spec/Bennett-Dialect-Spec.md")


def drift():
    registry = tomllib.loads(dialect_blob("SPEC_VERSIONS.toml"))
    pin = tomllib.loads((ROOT / "SPEC_VERSIONS.toml").read_text())
    return (
        registry["dialect"] != pin["dialect"]
        or registry["isa"] != pin["isa"]
        or pin["specs"]["bennett-dialect-spec"] != pin["dialect"]
        or pin["specs"]["bennett-isa-spec"] != pin["isa"]
        or hashlib.sha256(dialect_text().encode()).hexdigest() != pin["dialect_sha256"]
        or pin["commits"]["bennett-dialect-spec"] != PIN
    )


def arith_path(major):
    pin = tomllib.loads((ROOT / "SPEC_VERSIONS.toml").read_text())["arith"]
    root = sibling("bennett-arith")
    gate_sha = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"][
        "bennett-arith"
    ]["sha"]
    assert (
        pin["commit"] == gate_sha
    ), "arith commit differs between gate.toml and SPEC_VERSIONS.toml"
    path = root / f"dist/llvm{major}/bennett-arith.bc"
    assert (
        hashlib.sha256(path.read_bytes()).hexdigest() == pin[f"llvm{major}_sha256"]
    ), f"LLVM {major}: arith pin mismatch: {path}"
    return path


def arith_manifest(major):
    arith_path(major)
    pin = tomllib.loads((ROOT / "gate.toml").read_text())["siblings"]["bennett-arith"][
        "sha"
    ]
    return json.loads(
        subprocess.check_output(
            [
                "git",
                "-C",
                str(sibling("bennett-arith")),
                "show",
                f"{pin}:dist/llvm{major}/manifest.json",
            ],
            text=True,
        )
    )
