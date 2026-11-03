#!/usr/bin/env python3
"""The actual R hello materialisation can enter native comparison transport.

ISA0.8 must continue to report BD-B-ISA7; successful native output is not R
budget, tape, reversal or native-process-startup acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from allocator_closure import RUNTIME_SHA
from contracts import ROOT as R, SIBLINGS, arith_path
from native_comparison import sha
from native_link import build, resolved_layout, run, update_object


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--major', type=int, required=True)
    a = p.parse_args()
    t = f'/usr/lib/llvm-{a.major}/bin/'
    plugin = R / f'build/libbennett-plugin-{a.major}.so'
    runtime = Path(os.environ.get('BENNETT_ALLOCATOR_PINNED_ROOT',
                                  SIBLINGS / 'bennett-runtimes/dist')) / f'llvm{a.major}/bennett-runtimes.bc'
    assert sha(runtime) == RUNTIME_SHA[a.major]
    source = R / 'tests/probes/r-hello.c'
    source_identity = sha(source)
    d = R / f'.tmp/native-hello/{a.major}'
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    run([t + 'clang', '-O2', '-nostdinc', '-isystem', runtime.parent / 'musl-sysroot/include',
         '-emit-llvm', '-c', source, '-o', d / 'input.bc'])
    run([t + 'llvm-link', d / 'input.bc', runtime, arith_path(a.major),
         '--only-needed', '-o', d / 'linked.bc'])
    run([t + 'opt', '-passes=lto<O3>', d / 'linked.bc', '-o', d / 'postlink.bc'])
    producer = [t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett',
                '-bennett-dialect=0.2.13', '-bennett-tier=reversible', '-bennett-entry=main',
                '-bennett-budget-default=1048576,1048576,65536,256,65536']

    def emit(out, extra=()):
        z = subprocess.run([*producer, *extra, '-bennett-out=' + str(out),
                            str(d / 'postlink.bc'), '-disable-output'],
                           capture_output=True, text=True, timeout=600)
        assert z.returncode == 3 and 'BD-B-ISA7' in z.stderr, (z.returncode, z.stderr)
        assert json.loads((out / 'main/blockers.json').read_text())[0]['code'] == 'BD-B-ISA7'

    out = d / 'out'
    emit(out)
    native, report = d / 'native.bc', d / 'native.json'
    run([t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett-native-comparison',
         '-bennett-native-record=' + str(out / 'main/launch-record.json'),
         '-bennett-native-entry=main', '-bennett-native-report=' + str(report),
         out / 'device.bc', '-o', native])
    undefined = run([t + 'llvm-nm', '--undefined-only', native]).stdout
    assert '__bennett_effect_console_write' not in undefined, undefined
    meta = json.loads(report.read_text())
    exe, state = build(a.major, d, native, meta, out / 'main/launch.bennett',
                       None, runtime, 1048576)
    layout = resolved_layout(a.major, exe, meta)
    layout_file = d / 'resolved-layout.json'
    layout_file.write_text(json.dumps(layout, indent=2) + '\n')
    mapped = d / 'mapped'
    emit(mapped, ['-bennett-comparison-layout=' + str(layout_file)])
    update_object(a.major, exe, mapped / 'main/launch.bennett')
    actual = run([exe])
    assert actual.stdout == 'hello, world\n' and actual.stderr == '', (actual.stdout, actual.stderr)
    assert sha(source) == source_identity
    result = dict(major=a.major, passed=1, cases=1, native_stdout=actual.stdout,
                  source_sha256=source_identity, runtime_sha256=sha(runtime),
                  materialised_sha256=sha(out / 'device.bc'), native_sha256=sha(native),
                  executable_sha256=sha(exe), layout_sha256=sha(layout_file),
                  native_link=state, expected_isa_blocker='BD-B-ISA7',
                  r_execution_acceptance=False, full_comparison_acceptance=False)
    (R / f'.tmp/native-hello-{a.major}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(major=a.major, passed=1, cases=1)))


if __name__ == '__main__':
    main()
