#!/usr/bin/env python3
"""Resolved native ELF addresses must also drive ISA pointers and images."""
import argparse
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess

from contracts import ROOT as R
from native_comparison import sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--major', type=int, required=True)
    a = p.parse_args()
    tool = f'/usr/lib/llvm-{a.major}/bin/'
    plugin = R / f'build/libbennett-plugin-{a.major}.so'
    d = R / f'.tmp/native-layout/{a.major}'
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)

    def run(cmd):
        z = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=600)
        assert z.returncode == 0, (cmd, z.stdout, z.stderr)
        return z

    source = R / 'tests/probes/native-layout.ll'
    out = d / 'out'
    producer = [tool + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett',
                '-bennett-dialect=0.2.10', '-bennett-budget-default=1000,4096,128,8,0']
    run([*producer, '-bennett-out=' + str(out), source, '-disable-output'])
    native, report = d / 'native.bc', d / 'native.json'
    run([tool + 'opt', '-load-pass-plugin=' + str(plugin),
         '-passes=bennett-native-comparison',
         '-bennett-native-record=' + str(out / 'native_addresses/launch-record.json'),
         '-bennett-native-entry=native_addresses',
         '-bennett-comparison-structure-report=' + str(d / 'expected-structure.ll'),
         '-bennett-native-report=' + str(report), out / 'device.bc', '-o', native])
    meta = json.loads(report.read_text())
    assert meta['symbols'], 'native symbol correspondence is required'
    # The rest of this test consumes those symbols from a real non-PIE ELF,
    # then repeats the producer with the resolved map, never invented offsets.
    from native_link import build, update_object, resolved_layout
    harness = d / 'main.c'
    harness.write_text('''#include <stdint.h>
#include <stdio.h>
extern uint64_t native_addresses(uint64_t);
int main(void) {
 for (uint64_t i=0; i<3; ++i) printf("%llu\\n", (unsigned long long)native_addresses(i));
 return 0;
}
''')
    exe, state = build(a.major, d, native, meta,
                       out / 'native_addresses/launch.bennett', harness)
    layout = resolved_layout(a.major, exe, meta)
    layout_file = d / 'resolved-layout.json'
    layout_file.write_text(json.dumps(layout, indent=2) + '\n')
    mapped = d / 'mapped'
    run([*producer, '-bennett-comparison-layout=' + str(layout_file),
         '-bennett-comparison-structure-report=' + str(d / 'actual-structure.ll'),
         '-bennett-out=' + str(mapped), source, '-disable-output'])
    obj = mapped / 'native_addresses/launch.bennett'
    update_object(a.major, exe, obj)
    native_values = [int(x) for x in run([exe]).stdout.splitlines()]
    from production import REF
    run([REF, 'check', obj])
    runs = []
    for mode, expected in enumerate(native_values):
        v = json.loads(run([REF, 'run-program', obj, 'native_addresses', '--args', str(mode),
                            '--budget', '1000,0,128,8']).stdout)
        assert v['status'] == 'COMPLETED' and not v['faults'], v
        assert v['results'] == [dict(type='i64', value=str(expected))], (mode, expected, v)
        runs.append(dict(mode=mode, expected=expected, result=v))
    sections = obj.read_text().split('section layout\n', 1)[1].split('\n\n', 1)[0]
    isa_layout = json.loads(sections)
    assert isa_layout['heap_base'] == layout['heap_base']
    actual_globals = {v['base'] for v in isa_layout['globals'].values()}
    assert layout['globals']['name:native_data']['address'] in actual_globals
    assert layout['globals']['name:native_table']['address'] in actual_globals
    for label in ('heap', 'missing', 'alignment', 'functions', 'materialisation'):
        bad = copy.deepcopy(layout)
        if label == 'heap':
            bad['heap_base'] += 4096
        elif label == 'missing':
            del bad['globals']['name:native_table']
        elif label == 'alignment':
            bad['globals']['name:native_data']['address'] += 1
        elif label == 'functions':
            bad['functions']['native_callback']['address'] = bad['functions']['native_addresses']['address']
        else:
            bad['materialised_structure_sha256'] = '0' * 64
        path = d / f'invalid-{label}.json'
        path.write_text(json.dumps(bad) + '\n')
        z = subprocess.run([*producer, '-bennett-comparison-layout=' + str(path),
                            '-bennett-out=' + str(d / f'rejected-{label}'), str(source),
                            '-disable-output'], capture_output=True, text=True, timeout=600)
        assert z.returncode != 0 and 'BD-E-COMPARISON-LAYOUT' in z.stderr, (label, z)
    plain = d / 'plain-again'
    run([*producer, '-bennett-out=' + str(plain), source, '-disable-output'])
    for artifact in ('device.bc', 'native_addresses/launch.bennett'):
        assert (out / artifact).read_bytes() == (plain / artifact).read_bytes(), artifact
    result = dict(major=a.major, passed=3, cases=3, runs=runs,
                  native_sha256=sha(native), executable_sha256=sha(exe),
                  materialised_sha256=sha(out / 'device.bc'),
                  layout_sha256=sha(layout_file), object_sha256=sha(obj),
                  resolved_layout=layout, native_link=state,
                  rejection_checks=5, default_output_unchanged=True,
                  full_comparison_acceptance=False)
    (R / f'.tmp/native-layout-{a.major}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(major=a.major, passed=3, cases=3)))


if __name__ == '__main__':
    main()
