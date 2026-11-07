#!/usr/bin/env python3
"""Independent ISA 0.9 §9.2 envelopes, including K47 paths and cyclic SCCs."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from contracts import ROOT, run_checked, sibling


def jcs(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def components(graph):
    """Tarjan's algorithm yields dependency components before their callers."""
    indices, low, stack, active, result = {}, {}, [], set(), []

    def visit(name):
        indices[name] = low[name] = len(indices)
        stack.append(name)
        active.add(name)
        for target in graph[name]:
            if target not in indices:
                visit(target)
                low[name] = min(low[name], low[target])
            elif target in active:
                low[name] = min(low[name], indices[target])
        if low[name] == indices[name]:
            group = []
            while True:
                member = stack.pop()
                active.remove(member)
                group.append(member)
                if member == name:
                    break
            result.append(sorted(group, key=lambda item: item.encode()))

    for name in graph:
        if name not in indices:
            visit(name)
    return result


def identities(text, structured=True):
    """Derive claims from signatures, bodies and original JSON keys, not claims."""
    sections = dict(re.findall(r"\n\nsection ([^\n]+)\n(.*?)(?=\n\nsection |\Z)", text, re.S))
    symbols = {item["name"]: item for item in json.loads(sections["symbols"]).values()}
    version, width = re.search(r"isa=(\S+).*ptr_width=(\d+)", text.splitlines()[0]).groups()
    prefix = f"isa={version}\nptr_width={width}\n"
    data = dict(line.split(" ", 1) for line in sections.get("data", "").splitlines())
    layout = json.loads(sections.get("layout", "{}"))
    devices = json.loads(sections.get("devices", "{}"))
    leaves = []
    for key, value in layout.items():
        if key == "globals":
            leaves.extend(([key, name], item) for name, item in value.items())
        elif key == "interface_regions":
            leaves.extend(([key, owner, name], item) for owner, regions in value.items() for name, item in regions.items())
        else:
            leaves.append(([key], value))
    paths = [(jcs(path) if structured else ".".join(path), value) for path, value in leaves]
    memory = "".join(f"data {name} {data[name]}\n" for name in sorted(data))
    memory += "".join(f"layout {key} {jcs(value)}\n" for key, value in sorted(paths, key=lambda item: item[0].encode()))
    functions = {}
    for body in re.split(r"(?=^fn (?:cc|r) @)", sections["functions"], flags=re.M):
        if body.strip():
            name = re.match(r"fn (?:cc|r) @([^ ]+)", body)[1]
            functions[name] = body.rstrip("\n")
    token = re.compile(r"@([A-Za-z_][A-Za-z_0-9]*)")
    graph = {name: {ref for ref in token.findall(body.split("\n", 1)[1]) if ref in functions}
             for name, body in functions.items()}
    hashes = {name: sha(prefix + jcs(item["signature"]) + "\n" + name + " " + data[name] + "\n")
              for name, item in symbols.items() if item["kind"] == "data"}
    for group in components(graph):
        cyclic = len(group) > 1 or group[0] in graph[group[0]]
        envelopes = []
        for name in group:
            header, body = functions[name].split("\n", 1)
            refs = []

            def replace(match):
                target = match[1]
                if cyclic and target in group:
                    return "@$" + str(group.index(target))
                if target not in refs:
                    refs.append(target)
                return "@" + hashes[target]

            canonical = header + "\n" + token.sub(replace, body)
            used = set(re.findall(r"effect ([a-z]+)\.", body) + re.findall(r"hostcall ([A-Za-z_0-9./]+) ", body))
            binding = "".join(f"device {device} {jcs(devices[category][device])}\n"
                              for device in sorted(used) for category in ("models", "services")
                              if device in devices.get(category, {}))
            envelopes.append(prefix + jcs(symbols[name]["signature"]) + "\n" + canonical + "\n"
                             + memory + binding + "".join(hashes[target] + "\n" for target in refs))
        digest = sha("".join(envelopes))
        hashes.update({name: sha(digest + ":" + str(index)) if cyclic else digest
                       for index, name in enumerate(group)})
    return hashes


def rewrite_claims(text, expected):
    match = re.search(r"(?<=section symbols\n)[^\n]+", text)
    records = json.loads(match[0])
    for record in records.values():
        record["interface_hash"] = expected[record["name"]]
    return text[:match.start()] + jcs(records) + text[match.end():]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", required=True, type=int, choices=(18, 23))
    args = parser.parse_args()
    work = ROOT / f".tmp/r3-typed-faults/envelopes/{args.major}"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    source = work / "input.c"
    source.write_text('extern void __bennett_effect_console_write(const void *, unsigned long);\n'
                      'static const char bytes[] = "x";\n'
                      'int main(void) { __bennett_effect_console_write(bytes,1); return 0; }\n')
    tool = Path(f"/usr/lib/llvm-{args.major}/bin")
    run_checked([tool / "clang", "-O1", "-emit-llvm", "-c", source, "-o", work / "input.bc"])
    run_checked([tool / "opt", f"-load-pass-plugin={ROOT}/build/libbennett-plugin-{args.major}.so",
                 "-passes=bennett", "-bennett-dialect=0.3-r1", "-bennett-isa=0.9",
                 "--bennett-tier=reversible", "--bennett-entry=main", "-bennett-budget-default=100,131072,4096,32,65536",
                 f"-bennett-out={work}/out", "-disable-output", work / "input.bc"])
    obj = work / "out/main/launch.bennett"
    text = obj.read_text()
    arrays, dotted = identities(text), identities(text, structured=False)
    assert arrays["main"] != dotted["main"], "fixture must distinguish the two hash recipes"
    reader = sibling("bennett-isa-spec") / "reference-interpreter/target/release/bennett-isa-ref"
    for recipe, hashes, code in [("arrays", arrays, 0), ("dotted", dotted, 1)]:
        candidate = work / f"{recipe}.bennett"
        candidate.write_text(rewrite_claims(text, hashes))
        result = run_checked([reader, "check", candidate], code=code)
        if code:
            assert "§9.2" in result.stderr and "interface_hash mismatch" in result.stderr
    assert text == rewrite_claims(text, arrays), "producer must emit ISA 0.9 K47 array-path identities"
    run_checked([reader, "check", obj])
    print(f"LLVM {args.major}: independently derived array envelopes accepted; dotted recipe rejected")


if __name__ == "__main__":
    main()
