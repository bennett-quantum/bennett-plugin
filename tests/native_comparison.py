#!/usr/bin/env python3
"""Native arithmetic and real register operations from emitted materialisation.

This compact bridge regression precedes the full comparison/layout fixtures.
It does not certify native memory fault instrumentation or a complete launch.
"""
import argparse
import ctypes as c
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from contracts import ROOT as R, SIBLINGS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vm_library():
    return Path(os.environ.get('BENNETT_VM_NATIVE_LIBRARY',
                                SIBLINGS / 'bennett-vm/target/release/libbennett_vm.so'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True)
    args = parser.parse_args()
    major = args.major
    tool = f'/usr/lib/llvm-{major}/bin/'
    plugin = R / f'build/libbennett-plugin-{major}.so'
    directory = R / f'.tmp/native-comparison/{major}'
    shutil.rmtree(directory, ignore_errors=True)
    directory.mkdir(parents=True)

    def run(command):
        result = subprocess.run(list(map(str, command)), capture_output=True,
                                text=True, timeout=600)
        assert result.returncode == 0, (command, result.stdout, result.stderr)
        return result

    output = directory / 'out'
    run([tool + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett',
         '-bennett-dialect=0.2.10', '-bennett-budget-default=1000,128,128,8,0',
         '-bennett-out=' + str(output), '-disable-output',
         R / 'tests/probes/native-comparison.ll'])
    materialised = output / 'device.bc'
    identity = sha(materialised)
    record = output / 'native_probe/launch-record.json'
    native = directory / 'native.bc'
    report = directory / 'native.json'
    run([tool + 'opt', '-load-pass-plugin=' + str(plugin),
         '-passes=bennett-native-comparison',
         '-bennett-native-record=' + str(record),
         '-bennett-native-entry=native_probe',
         '-bennett-native-report=' + str(report), materialised, '-o', native])
    adapter = [tool + 'opt', '-load-pass-plugin=' + str(plugin),
               '-passes=bennett-native-comparison',
               '-bennett-native-record=' + str(record),
               '-bennett-native-entry=native_probe',
               '-bennett-native-report=' + str(directory / 'rejected.json')]
    # A launch record cannot authorise adaptation of another input or a module
    # changed by an earlier pass. These are identity checks, not marker stubs.
    for label, command in (
        ('entry', [*adapter, '-bennett-native-entry=absent', materialised, '-disable-output']),
        ('identity', [*adapter, native, '-disable-output']),
        ('transformation', [*(x for x in adapter if not x.startswith('-passes=')),
                            '-passes=function(instnamer),bennett-native-comparison',
                            materialised, '-disable-output'])):
        rejected = subprocess.run(list(map(str, command)), capture_output=True,
                                  text=True, timeout=600)
        assert rejected.returncode != 0 and 'BD-E-NATIVE-INPUT' in rejected.stderr, (label, rejected)
        assert not (directory / 'rejected.json').exists(), label
    assert sha(materialised) == identity, 'native lowering changed original identity'
    run([tool + 'opt', '-passes=verify', native, '-disable-output'])
    text = run([tool + 'llvm-dis', native, '-o', '-']).stdout
    assert 'call i32 @bennett_qreg_new(' in text, text
    assert 'call i32 @bennett_qreg_free(' in text, text
    undefined = run([tool + 'llvm-nm', '--undefined-only', native]).stdout
    assert '__bennett_qalloc' not in undefined and '__bennett_qfree' not in undefined
    assert 'define ptr @__bennett_qalloc' not in text
    assert 'define void @__bennett_qfree' not in text
    metadata = json.loads(report.read_text())
    assert metadata['materialised_sha256'] == identity
    assert metadata['entries'] == ['native_probe']

    # A real published launch implementation supplies the register state.
    # The probe arithmetic is compiled directly to native machine code.
    library = vm_library()
    assert library.is_file(), library
    native_library = directory / 'native.so'
    native_object = directory / 'native.o'
    run([tool + 'llc', '-O2', '-relocation-model=pic', '-filetype=obj', native, '-o', native_object])
    run([tool + 'clang', '-shared', '-fPIC', native_object, '-L' + str(library.parent),
         '-lbennett_vm', '-Wl,-rpath,' + str(library.parent), '-o', native_library])
    os.environ['BENNETT_VM_ENGINE'] = 'interpreter'
    backend = c.CDLL(str(library), mode=os.RTLD_GLOBAL)
    backend.bennett_load.argtypes = [c.c_void_p, c.c_size_t, c.c_void_p,
                                    c.c_size_t, c.POINTER(c.c_void_p)]
    backend.bennett_load.restype = c.c_int
    backend.bennett_unload.argtypes = [c.c_void_p]
    backend.bennett_unload.restype = c.c_int
    backend.bennett_last_error.restype = c.c_char_p
    obj = output / 'native_probe/launch.bennett'
    data = obj.read_bytes()
    target = json.loads((SIBLINGS / 'bennett-targets/targets/ideal-all-to-all.json').read_text())
    encoded = json.dumps(target, sort_keys=True, separators=(',', ':')).encode()
    object_buffer, target_buffer = c.create_string_buffer(data), c.create_string_buffer(encoded)
    program = c.c_void_p()
    status = backend.bennett_load(object_buffer, len(data), target_buffer,
                                  len(encoded), c.byref(program))
    assert status == 0, (status, backend.bennett_last_error())
    # Unused error/transport imports are resolved by the complete comparison
    # support in the full fixture test; this unit exercises successful qreg calls.
    compiled = c.CDLL(str(native_library), mode=os.RTLD_LAZY | os.RTLD_LOCAL)
    bind = getattr(compiled, metadata['binding_symbol'])
    bind.argtypes = [c.c_void_p]
    bind.restype = None
    bind(program)
    probe = compiled.native_probe
    probe.argtypes, probe.restype = [c.c_uint64], c.c_uint64
    rows = []
    for value in (0, 9, (1 << 64) - 1, 1 << 63, 0x123456789abcdef0):
        actual = probe(value)
        expected = (value + 5) & ((1 << 64) - 1)
        assert actual == expected, (value, actual, expected)
        rows.append(dict(input=value, result=actual, expected=expected))
    assert backend.bennett_unload(program) == 0
    result = dict(major=major, cases=len(rows), passed=len(rows), runs=rows,
                  materialised_sha256=identity, native_sha256=sha(native),
                  launch_library_sha256=sha(library),
                  source_memory_faults_checked=False,
                  full_comparison_acceptance=False)
    (R / f'.tmp/native-comparison-{major}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
