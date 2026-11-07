"""Test comparison link: ordinary host launcher and actual materialised module.

The host launcher binds the real public launch API before entering the source
main. Its CRT and API implementation are infrastructure; program definitions
come from the materialised module and pinned runtime/arithmetic libraries.
This does not stand in for the driver's full native-startup acceptance.
"""

import json
import os
from pathlib import Path
import struct
import subprocess
import tomllib

from contracts import ROOT as R, sibling, arith_path
from native_comparison import sha, vm_library

CAPACITY = 8 * 1024 * 1024


from functools import partial
from contracts import run_checked

run = partial(run_checked, timeout=600)


def support(major):
    root = sibling("bennett-native-runtimes") / "dist"
    path = root / f"llvm{major}/musl-sysroot/lib/native-support.bc"
    pin = tomllib.loads((R / "SPEC_VERSIONS.toml").read_text())["native_comparison"]
    assert sha(path) == pin[f"llvm{major}_support_sha256"], (
        "native support pin changed",
        path,
    )
    return path


def build(
    major, directory, native, metadata, obj, harness, runtime=None, heap_limit=4096
):
    """Keep the ISA object in a fixed-size, replaceable, native-only section."""
    os.environ["BENNETT_VM_ENGINE"] = "interpreter"
    t = f"/usr/lib/llvm-{major}/bin/"
    library = vm_library()
    target = json.loads(
        (sibling("bennett-targets") / "targets/ideal-all-to-all.json").read_text()
    )
    encoded = json.dumps(target, sort_keys=True, separators=(",", ":")).encode()
    target_literal = ",".join(map(str, encoded))
    wrapper = directory / "launcher.c"
    flush = (
        "__bennett_comparison_flush_" + metadata["materialised_sha256"][:20]
        if runtime
        else None
    )
    declarations = f"extern int {flush}(void *);" if flush else ""
    flush_call = f"if ({flush}(0)) return 125;" if flush else ""
    wrapper.write_text(f"""#include <stddef.h>
#include <stdint.h>
#include "bennett_launch.h"
extern const unsigned char __bennett_comparison_object[{CAPACITY}];
extern int __real_main(int,char **,char **);
extern void {metadata['binding_symbol']}(bennett_program_t *);
{declarations}
static const unsigned char target[] = {{{target_literal}}};
int __wrap_main(int argc,char **argv,char **envp) {{
 uint64_t length=0;
 for (unsigned i=0;i<8;++i) length |= (uint64_t)__bennett_comparison_object[i] << (8*i);
 if (length>{CAPACITY}-8) return 125;
 bennett_program_t *program=0;
 if (bennett_load(__bennett_comparison_object+8,length,target,sizeof target,&program)) return 125;
 {metadata['binding_symbol']}(program);
 int result=__real_main(argc,argv,envp);
 {flush_call}
 if (bennett_unload(program)) return 125;
 return result;
}}
""")
    blob = directory / "object.s"
    blob.write_text(f""".section .bennett.object,"a",@progbits
.balign 8
.global __bennett_comparison_object
__bennett_comparison_object:
.zero {CAPACITY}
.section .note.GNU-stack,"",@progbits
""")
    layout = directory / "native-layout.ll"
    layout.write_text(
        f"""@__bennett_rt_native_layout = externally_initialized constant {{i64,i64,i64}} {{i64 1, i64 0, i64 {heap_limit}}}, section ".bennett.layout", align 8
"""
    )
    # Exclude native-only startup: the host test launcher owns process startup.
    # The primitive and transport bodies are the published comparison support.
    trimmed = directory / "support.bc"
    run(
        [
            t + "llvm-extract",
            "--delete",
            "--func=_start",
            "--func=__bennett_rt_start",
            support(major),
            "-o",
            trimmed,
        ]
    )
    seed = directory / "seed.bc"
    inputs = [native]
    if flush:
        postlude = directory / "postlude.ll"
        postlude.write_text(f"""declare i32 @fflush(ptr)
define i32 @{flush}(ptr %stream) {{
 %result = call i32 @fflush(ptr %stream)
 ret i32 %result
}}
""")
        inputs.append(postlude)
    if harness:
        harness_bc = directory / "harness.bc"
        includes = (
            ["-nostdinc", "-isystem", runtime.parent / "musl-sysroot/include"]
            if runtime
            else []
        )
        run(
            [
                t + "clang",
                "-O2",
                "-emit-llvm",
                "-c",
                *includes,
                harness,
                "-o",
                harness_bc,
            ]
        )
        inputs.append(harness_bc)
    run([t + "llvm-link", *inputs, "-o", seed])
    base = directory / "base.bc"
    if runtime:
        run(
            [
                t + "llvm-link",
                seed,
                runtime,
                arith_path(major),
                "--only-needed",
                "-o",
                base,
            ]
        )
        adapted = directory / "adapted.bc"
        run(
            [t + "llvm-link", base, layout, "--override=" + str(trimmed), "-o", adapted]
        )
        run(
            [
                t + "llvm-link",
                adapted,
                runtime,
                arith_path(major),
                "--only-needed",
                "-o",
                base,
            ]
        )
    else:
        run([t + "llvm-link", seed, layout, "-o", base])
        run([t + "llvm-link", base, trimmed, "--only-needed", "-o", base])
    # Keep source symbol aliases and the explicit boundary. Ordinary runtime
    # names become local so they cannot interpose on the API DSO's host libc.
    public = [
        "main",
        "__bennett_rt_native_layout",
        metadata["binding_symbol"],
        *[r["native_symbol"] for r in metadata["symbols"]],
    ]
    if flush:
        public.append(flush)
    imports = directory / "imports.bc"
    run(
        [
            t + "opt",
            "-load-pass-plugin=" + str(R / f"build/libbennett-plugin-{major}.so"),
            "-passes=bennett-native-host-imports",
            base,
            "-o",
            imports,
        ]
    )
    # Host console adaptation may introduce this dependency after the earlier
    # --only-needed closure. Pull only its real published implementation.
    run([t + "llvm-link", imports, trimmed, "--only-needed", "-o", imports])
    ready = directory / "ready.bc"
    run(
        [
            t + "opt",
            "-passes=internalize,strip-dead-prototypes,verify",
            "-internalize-public-api-list=" + ",".join(public),
            imports,
            "-o",
            ready,
        ]
    )
    executable = directory / "comparison"
    program_object = directory / "program.o"
    # §17.7: optimise machine code without rerunning an IR optimisation
    # pipeline over the fixed materialised instruction stream.
    run(
        [
            t + "llc",
            "-O2",
            "-filetype=obj",
            "-relocation-model=static",
            ready,
            "-o",
            program_object,
        ]
    )
    run(
        [
            t + "clang",
            "-O2",
            "-no-pie",
            "-fno-merge-all-constants",
            program_object,
            wrapper,
            blob,
            "-I" + str(sibling("bennett-isa-spec") / "include"),
            "-Wl,--wrap=main",
            "-L" + str(library.parent),
            "-lbennett_vm",
            "-Wl,-rpath," + str(library.parent),
            "-o",
            executable,
        ]
    )
    names = elf_symbols(major, executable)
    heap_base = (names["_end"] + 4095) & -4096
    table = directory / "native-layout.bin"
    table.write_bytes(struct.pack("<QQQ", 1, heap_base, heap_limit))
    run(
        [
            t + "llvm-objcopy",
            "--update-section=.bennett.layout=" + str(table),
            executable,
        ]
    )
    assert (
        elf_symbols(major, executable) == names
    ), "native-only layout fixup changed source addresses"
    update_object(major, executable, obj)
    return executable, dict(
        launch_library_sha256=sha(library),
        support_sha256=sha(support(major)),
        program_uses_materialised_module=True,
        program_codegen="llc -O2",
        source_ir_reoptimised=False,
        native_process_startup_acceptance=False,
    )


def update_object(major, executable, obj):
    payload = obj.read_bytes()
    assert (
        len(payload) + 8 <= CAPACITY
    ), "increase the reserve before resolving the native link"
    section = executable.with_suffix(".object")
    section.write_bytes(
        (struct.pack("<Q", len(payload)) + payload).ljust(CAPACITY, b"\0")
    )
    run(
        [
            f"/usr/lib/llvm-{major}/bin/llvm-objcopy",
            "--update-section=.bennett.object=" + str(section),
            executable,
        ]
    )


def elf_symbols(major, executable):
    names = {}
    for line in run(
        [
            f"/usr/lib/llvm-{major}/bin/llvm-nm",
            "--defined-only",
            "--format=posix",
            executable,
        ]
    ).stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            names[fields[0]] = int(fields[2], 16)
    return names


def resolved_layout(major, executable, metadata):
    names = elf_symbols(major, executable)
    table = executable.with_suffix(".layout")
    run(
        [
            f"/usr/lib/llvm-{major}/bin/llvm-objcopy",
            "--dump-section=.bennett.layout=" + str(table),
            executable,
        ]
    )
    abi, heap_base, heap_limit = struct.unpack("<QQQ", table.read_bytes())
    assert abi == 1 and heap_base == (names["_end"] + 4095) & -4096
    globals_, functions = {}, {}
    for row in metadata["symbols"]:
        assert row["native_symbol"] in names, row
        entry = dict(
            address=names[row["native_symbol"]], native_symbol=row["native_symbol"]
        )
        if row["kind"] == "global":
            entry.update(size=row["size"], alignment=row["alignment"])
            globals_[row["source_key"]] = entry
        else:
            functions[row["source_key"]] = entry
    return dict(
        schema="bennett-comparison-layout-1",
        ptr_width=64,
        materialised_structure_sha256=metadata["materialised_structure_sha256"],
        data_end=names["_end"],
        heap_base=heap_base,
        globals=globals_,
        functions=functions,
    )
