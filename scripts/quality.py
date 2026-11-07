#!/usr/bin/env python3
"""Repository-local quality proxies and a ratchet against docs/quality.md."""

import argparse
import ast
import json
import math
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASELINE = re.compile(r"<!-- quality-baseline -->\s*```json\n(.*?)\n```", re.S)
IDENTIFIER = re.compile(
    r"\b(?:bp|bd|b-dialect-spec)-[a-z0-9]+\b|\b(?:sol|quality)-plugin\b"
)
LITTER = re.compile(
    r"(^|/)(__pycache__|PROGRESS[^/]*|LAST-RUN[^/]*)(/|$)|\.(pyc|log|lock|darc)$|(^|/)LOCK$"
)
CONTROL = {"if", "for", "while", "switch", "catch", "sizeof", "alignas"}
TOKENS = re.compile(
    r'//[^\n]*|/\*.*?\*/|R"([^ ()\\\t\r\n]*)\(.*?\)\1"|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27',
    re.S,
)


def cpp_functions(source):
    masked = TOKENS.sub(lambda match: re.sub(r"[^\n]", " ", match.group()), source)
    stack, functions = [], []
    for match in re.finditer(r"[{}]", masked):
        position = match.start()
        if match.group() == "{":
            boundary = max(masked.rfind(char, 0, position) for char in ";{}") + 1
            header = masked[boundary:position]
            signature = re.search(
                r"([A-Za-z_~]\w*)\s*\([^{};]*\)\s*(?:const|override|noexcept)?\s*$",
                header,
            )
            name = signature.group(1) if signature else None
            stack.append((position, name if name not in CONTROL else None, boundary))
        else:
            if not stack:
                raise ValueError("unbalanced closing brace in C++ source")
            start, name, boundary = stack.pop()
            if name:
                first = (
                    boundary
                    + len(masked[boundary:start])
                    - len(masked[boundary:start].lstrip())
                )
                line = masked.count("\n", 0, first) + 1
                length = masked.count("\n", first, position) + 1
                body = masked[start + 1 : position].strip()
                trivial = bool(re.fullmatch(r"(?:return\s+)?[\w:.]+\([^;{}]*\);", body))
                functions.append(
                    {"name": name, "line": line, "length": length, "trivial": trivial}
                )
    if stack:
        raise ValueError("unbalanced opening brace in C++ source")
    depth, complexity = 0, 0
    for match in re.finditer(
        r"\b(?:if|for|while|switch|catch|else)\b|&&|\|\||\?|[{}]", masked
    ):
        token = match.group()
        if token == "{":
            depth += 1
        elif token == "}":
            depth -= 1
        else:
            complexity += 1 + depth
    return functions, complexity


def python_functions(source):
    tree = ast.parse(source)
    functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                body = body[1:]
            trivial = (
                len(body) == 1
                and isinstance(body[0], (ast.Return, ast.Expr))
                and isinstance(body[0].value, ast.Call)
            )
            functions.append(
                {
                    "name": node.name,
                    "line": node.lineno,
                    "length": node.end_lineno - node.lineno + 1,
                    "trivial": trivial,
                }
            )
    branches = (
        ast.If,
        ast.For,
        ast.AsyncFor,
        ast.While,
        ast.ExceptHandler,
        ast.IfExp,
        ast.Match,
    )

    def mass(node, depth=0):
        branch = isinstance(node, branches)
        own = 1 + depth if branch else 0
        if isinstance(node, ast.BoolOp):
            own += len(node.values) - 1
        return own + sum(
            mass(child, depth + branch) for child in ast.iter_child_nodes(node)
        )

    return functions, mass(tree)


def measure(root, paths):
    files, long_functions = {}, []
    process_identifiers = 0
    for name in sorted(paths):
        path = root / name
        if not path.is_file():
            continue
        is_python = path.suffix == ".py" or (
            name.startswith("scripts/")
            and not path.suffix
            and "python" in path.read_text().partition("\n")[0]
        )
        if not is_python and path.suffix not in (".cpp", ".c", ".h", ".inc"):
            continue
        source = path.read_text()
        if name.startswith(("src/", "include/")):
            process_identifiers += len(IDENTIFIER.findall(source))
        if is_python:
            functions, complexity = python_functions(source)
        else:
            functions, complexity = cpp_functions(source)
        lengths = sorted(function["length"] for function in functions)
        percentile = lambda fraction: (
            lengths[math.ceil(fraction * len(lengths)) - 1] if lengths else 0
        )
        files[name] = {
            "functions": len(lengths),
            "length_p50": percentile(0.5),
            "length_p90": percentile(0.9),
            "length_max": max(lengths, default=0),
            "over_300": sum(length > 300 for length in lengths),
            "complexity": complexity,
            "trivial_wrappers": sum(function["trivial"] for function in functions),
        }
        long_functions.extend(
            {"file": name, **function}
            for function in functions
            if function["length"] > 300
        )
    return {
        "files": files,
        "process_identifiers": process_identifiers,
        "litter": sorted(name for name in paths if LITTER.search(name)),
        "long_functions": long_functions,
    }


def regressions(current, baseline):
    failures = []
    for key in ("process_identifiers", "litter"):
        count = lambda value: len(value) if isinstance(value, list) else value
        if count(current[key]) > count(baseline[key]):
            failures.append(f"{key}: {count(baseline[key])} -> {count(current[key])}")
    for name, values in current["files"].items():
        previous = baseline["files"].get(name, {})
        for key, value in values.items():
            if key != "functions" and value > previous.get(key, 0):
                failures.append(f"{name} {key}: {previous.get(key, 0)} -> {value}")
    return failures


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    paths = result.stdout.rstrip("\0").split("\0")
    current = measure(ROOT, paths)
    if args.check:
        match = BASELINE.search((ROOT / "docs/quality.md").read_text())
        if not match:
            raise SystemExit("docs/quality.md has no quality-baseline JSON block")
        failures = regressions(current, json.loads(match.group(1)))
        if failures:
            raise SystemExit("quality baseline worsened:\n" + "\n".join(failures))
        print("quality baseline: no regressions")
    else:
        print(json.dumps(current, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
