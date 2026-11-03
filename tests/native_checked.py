#!/usr/bin/env python3
"""Instrument fixed source materialisation before adding the native backend."""
import argparse
import json
import os
import resource
from pathlib import Path
import shutil
import subprocess
import tomllib

from allocator_closure import RUNTIME_SHA
from contracts import ROOT as R, SIBLINGS, arith_path
from native_comparison import sha
from native_link import build, resolved_layout, run, update_object

def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))
    p = argparse.ArgumentParser()
    p.add_argument('--major', type=int, required=True)
    a = p.parse_args()
    t = f'/usr/lib/llvm-{a.major}/bin/'
    plugin = R / f'build/libbennett-plugin-{a.major}.so'
    root = Path(os.environ.get('BENNETT_ALLOCATOR_PINNED_ROOT', SIBLINGS / 'bennett-runtimes/dist'))
    runtime = root / f'llvm{a.major}/bennett-runtimes.bc'
    assert sha(runtime) == RUNTIME_SHA[a.major]
    tools = Path(os.environ.get('BENNETT_NATIVE_TOOL_ROOT', SIBLINGS / 'bennett-runtimes'))
    checker = tools / 'scripts/native-check'
    pin = tomllib.loads((R / 'SPEC_VERSIONS.toml').read_text())['native_comparison']
    assert sha(checker) == pin['checker_script_sha256'], 'published checker CLI changed'
    assert sha(tools / 'scripts/native-check.cpp') == pin['checker_source_sha256'], 'published checker tool source changed'
    d = R / f'.tmp/native-checked/{a.major}'
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    run([t + 'llvm-link', R / 'tests/probes/allocator-bounds.ll', R / 'tests/probes/native-division.ll',
         '-o', d / 'source.bc'])
    run([t + 'llvm-link', d / 'source.bc', runtime, arith_path(a.major),
         '--only-needed', '-o', d / 'linked.bc'])
    run([t + 'opt', '-passes=lto<O3>', d / 'linked.bc', '-o', d / 'postlink.bc'])
    producer = [t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett',
                '-bennett-dialect=0.2.13', '-bennett-budget-default=100000,128,4096,32,0']
    out = d / 'out'
    run([*producer, '-bennett-out=' + str(out), d / 'postlink.bc', '-disable-output'])
    prepared, checked, native = [d / f'{name}.bc' for name in ('prepared', 'checked', 'native')]
    report = d / 'native.json'
    run([t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett-native-comparison',
         '-bennett-native-prepare-only',
         '-bennett-native-record=' + str(out / 'top/launch-record.json'),
         '-bennett-native-entry=top', '-bennett-native-report=' + str(report),
         out / 'device.bc', '-o', prepared])
    before = run([t + 'llvm-nm', '--defined-only', prepared]).stdout
    assert '__bennett_native_' not in before, 'backend state must be introduced after source checks'
    run([checker, str(a.major), prepared, checked])
    run([t + 'opt', '-load-pass-plugin=' + str(plugin),
         '-passes=bennett-native-comparison-finalise',
         '-bennett-native-report=' + str(report), checked, '-o', native])
    meta = json.loads(report.read_text())
    assert meta['phase'] == 'finalised'
    for label, artifact in (('unprepared', out / 'device.bc'), ('already-finalised', native)):
        z = subprocess.run([t + 'opt', '-load-pass-plugin=' + str(plugin),
                            '-passes=bennett-native-comparison-finalise',
                            '-bennett-native-report=' + str(d / 'rejected.json'),
                            str(artifact), '-disable-output'], capture_output=True, text=True, timeout=60)
        assert z.returncode != 0 and 'BD-E-NATIVE-INPUT' in z.stderr, (label, z)
        assert not (d / 'rejected.json').exists(), label
    disassembly = run([t + 'llvm-dis', native, '-o', '-']).stdout
    import re
    for f in re.finditer(r'^define [^\n]*@(__bennett_native_[^(]+)\([^\n]*\{.*?^}', disassembly, re.M | re.S):
        assert '__bennett_rt_native_check' not in f.group(), 'source checks instrumented backend bookkeeping'
    harness = d / 'main.c'
    harness.write_text('''#include <stdint.h>
extern int64_t top(int64_t);
extern int64_t native_divide(int64_t,int64_t);
int main(int argc,char **argv) {
 int mode=argc-1;
 if(mode==3) return (int)native_divide(10,0);
 if(mode==4) return (int)native_divide(INT64_MIN,-1);
 if(mode==5) return native_divide(10,2)!=5;
 return (int)top(mode);
}
''')
    exe, state = build(a.major, d, native, meta, out / 'top/launch.bennett', harness, runtime, 128)
    layout = resolved_layout(a.major, exe, meta)
    layout_file = d / 'resolved-layout.json'
    layout_file.write_text(json.dumps(layout, indent=2) + '\n')
    mapped = d / 'mapped'
    run([*producer, '-bennett-comparison-layout=' + str(layout_file),
         '-bennett-out=' + str(mapped), d / 'postlink.bc', '-disable-output'])
    update_object(a.major, exe, mapped / 'top/launch.bennett')
    from production import REF
    runs = []
    for mode in range(6):
        z = subprocess.run([str(exe), *['mode'] * mode], capture_output=True, text=True, timeout=60)
        entry = 'top' if mode < 3 else 'native_divide'
        arguments = str(mode) if mode < 3 else {3:'10,0',4:'-9223372036854775808,-1',5:'10,2'}[mode]
        budget = '100000,128,4096,32' if mode < 3 else '100000,0,0,0'
        isa = json.loads(run([REF, 'run-program', mapped / f'{entry}/launch.bennett', entry,
                              '--args', arguments, '--budget', budget]).stdout)
        if mode in (1,5):
            assert z.returncode == 0 and z.stdout == z.stderr == '', z
            assert isa['status'] == 'COMPLETED' and isa['results'] == [dict(type='i64', value=str(0 if mode==1 else 5))], isa
        else:
            fault = {0:7,2:7,3:5,4:6}[mode]
            assert z.returncode != 0 and z.stderr == f'bennett runtime fault {fault}\n', z
            assert isa['status'] == 'FAILED' and isa['faults'][0]['code'] == fault, isa
        runs.append(dict(mode=mode, native_exit=z.returncode, native_stderr=z.stderr, isa=isa))
    result = dict(major=a.major, passed=6, cases=6, runs=runs, checker_sha256=sha(checker),
                  materialised_sha256=sha(out / 'device.bc'), prepared_sha256=sha(prepared),
                  checked_sha256=sha(checked), native_sha256=sha(native),
                  native_link=state, source_memory_faults_checked=True,
                  original_source_definedness_not_asserted=True,
                  full_comparison_acceptance=False)
    (R / f'.tmp/native-checked-{a.major}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(major=a.major, passed=6, cases=6)))


if __name__ == '__main__':
    main()
