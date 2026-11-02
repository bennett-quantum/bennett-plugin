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

from contracts import ROOT as R, SIBLINGS, arith_path
from native_comparison import sha

CAPACITY = 2 * 1024 * 1024
# Published native-only support, observed at runtime commit be6e641bd7123d748e17b85851b0a227d6de6907.
# This is separate from the production runtime pin. Relocation still checks bytes.
SUPPORT_SHA = {
    18: 'c7a1306784e7f487c040b724e2074294ff687f149bf6403a9e403973a833e596',
    23: 'f7fee923e2b06d1c4106439e46ed03936a9ee7721d3498d008e298cb5265cade',
}


def run(cmd):
    z = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=600)
    assert z.returncode == 0, (cmd, z.stdout, z.stderr)
    return z


def support(major):
    root = Path(os.environ.get('BENNETT_NATIVE_SUPPORT_PINNED_ROOT',
                               SIBLINGS / 'bennett-runtimes/dist'))
    path = root / f'llvm{major}/musl-sysroot/lib/native-support.bc'
    assert sha(path) == SUPPORT_SHA[major], ('native support pin changed', path)
    return path


def build(major, directory, native, metadata, obj, harness, runtime=None, heap_limit=4096):
    """Keep the ISA object in a fixed-size, replaceable, native-only section."""
    t = f'/usr/lib/llvm-{major}/bin/'
    library = SIBLINGS / 'bennett-vm/target/release/libbennett_vm.so'
    target = json.loads((SIBLINGS / 'bennett-targets/targets/ideal-all-to-all.json').read_text())
    encoded = json.dumps(target, sort_keys=True, separators=(',', ':')).encode()
    target_literal = ','.join(map(str, encoded))
    wrapper = directory / 'launcher.c'
    flush = next((r['native_symbol'] for r in metadata['symbols']
                  if r['kind'] == 'function' and r['llvm_name'] == 'fflush'), None)
    declarations = f'extern int {flush}(void *);' if flush else ''
    flush_call = f'if ({flush}(0)) return 125;' if flush else ''
    wrapper.write_text(f'''#include <stddef.h>
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
''')
    blob = directory / 'object.s'
    blob.write_text(f'''.section .bennett.object,"a",@progbits
.balign 8
.global __bennett_comparison_object
__bennett_comparison_object:
.zero {CAPACITY}
.section .note.GNU-stack,"",@progbits
''')
    layout = directory / 'native-layout.ll'
    layout.write_text(f'''@__bennett_comparison_heap_base = external global i8
@__bennett_rt_native_layout = constant {{i64,i64,i64}} {{i64 1, i64 ptrtoint (ptr @__bennett_comparison_heap_base to i64), i64 {heap_limit}}}, align 8
''')
    # Exclude native-only startup: the host test launcher owns process startup.
    # The primitive and transport bodies are the published comparison support.
    trimmed = directory / 'support.bc'
    run([t + 'llvm-extract', '--delete', '--func=_start', '--func=__bennett_rt_start',
         support(major), '-o', trimmed])
    harness_bc = directory / 'harness.bc'
    includes = ['-nostdinc', '-isystem', runtime.parent / 'musl-sysroot/include'] if runtime else []
    run([t + 'clang', '-O0', '-emit-llvm', '-c', *includes, harness, '-o', harness_bc])
    seed = directory / 'seed.bc'
    run([t + 'llvm-link', native, harness_bc, '-o', seed])
    base = directory / 'base.bc'
    if runtime:
        run([t + 'llvm-link', seed, runtime, arith_path(major),
             '--only-needed', '-o', base])
        adapted = directory / 'adapted.bc'
        run([t + 'llvm-link', base, layout, '--override=' + str(trimmed), '-o', adapted])
        run([t + 'llvm-link', adapted, runtime, arith_path(major), '--only-needed', '-o', base])
    else:
        run([t + 'llvm-link', seed, layout, '-o', base])
        run([t + 'llvm-link', base, trimmed, '--only-needed', '-o', base])
    # Keep source symbol aliases and the explicit boundary. Ordinary runtime
    # names become local so they cannot interpose on the API DSO's host libc.
    public = ['main', metadata['binding_symbol'], *[r['native_symbol'] for r in metadata['symbols']]]
    ready = directory / 'ready.bc'
    run([t + 'opt', '-passes=internalize,strip-dead-prototypes,verify',
         '-internalize-public-api-list=' + ','.join(public), base, '-o', ready])
    executable = directory / 'comparison'
    run([t + 'clang', '-O0', '-no-pie', '-fno-merge-all-constants', ready, wrapper, blob,
         '-I' + str(SIBLINGS / 'bennett-isa-spec/include'),
         '-Wl,--wrap=main', '-Wl,--defsym=__bennett_comparison_heap_base=(_end+4095)&-4096',
         '-L' + str(library.parent), '-lbennett_vm', '-Wl,-rpath,' + str(library.parent),
         '-o', executable])
    update_object(major, executable, obj)
    return executable, dict(launch_library_sha256=sha(library),
                            support_sha256=sha(support(major)),
                            program_uses_materialised_module=True,
                            native_process_startup_acceptance=False)


def update_object(major, executable, obj):
    payload = obj.read_bytes()
    assert len(payload) + 8 <= CAPACITY, 'increase the reserve before resolving the native link'
    section = executable.with_suffix('.object')
    section.write_bytes((struct.pack('<Q', len(payload)) + payload).ljust(CAPACITY, b'\0'))
    run([f'/usr/lib/llvm-{major}/bin/llvm-objcopy',
         '--update-section=.bennett.object=' + str(section), executable])


def resolved_layout(major, executable, metadata):
    names = {}
    for line in run([f'/usr/lib/llvm-{major}/bin/llvm-nm', '--defined-only',
                     '--format=posix', executable]).stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3:
            names[fields[0]] = int(fields[2], 16)
    globals_, functions = {}, {}
    for row in metadata['symbols']:
        assert row['native_symbol'] in names, row
        entry = dict(address=names[row['native_symbol']], native_symbol=row['native_symbol'])
        if row['kind'] == 'global':
            entry.update(size=row['size'], alignment=row['alignment'])
            globals_[row['source_key']] = entry
        else:
            functions[row['source_key']] = entry
    return dict(schema='bennett-comparison-layout-1', ptr_width=64,
                materialised_structure_sha256=metadata['materialised_structure_sha256'],
                data_end=names['_end'], heap_base=names['__bennett_comparison_heap_base'],
                globals=globals_, functions=functions)
