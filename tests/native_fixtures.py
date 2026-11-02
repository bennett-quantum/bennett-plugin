#!/usr/bin/env python3
"""Unchanged public C fixtures through the emitted comparison artifact."""
import argparse
import json
import os
from pathlib import Path
import shutil

from contracts import ROOT as R, SIBLINGS, arith_path
from allocator_closure import RUNTIME_SHA
from native_comparison import sha
from native_link import build, resolved_layout, run, update_object


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--major', required=True, type=int)
    p.add_argument('--host-link', choices=('before', 'after'), default='after')
    a = p.parse_args()
    t = f'/usr/lib/llvm-{a.major}/bin/'
    plugin = R / f'build/libbennett-plugin-{a.major}.so'
    runtime_root = Path(os.environ.get('BENNETT_ALLOCATOR_PINNED_ROOT',
                                       SIBLINGS / 'bennett-runtimes/dist'))
    runtime = runtime_root / f'llvm{a.major}/bennett-runtimes.bc'
    assert sha(runtime) == RUNTIME_SHA[a.major], 'production runtime pin changed'
    fixture = SIBLINGS / 'bennett-conformance/ladder/rung-2/fixtures'
    source, harness, baseline_source = [fixture / name for name in
        ('hashtable_marked.c', 'main_golden.c', 'hashtable.c')]
    source_hashes = {str(path): sha(path) for path in (source, harness, baseline_source)}
    published_hashes = json.loads((fixture / 'sha256.json').read_text())
    for path in (source, harness, baseline_source):
        assert source_hashes[str(path)] == published_hashes[path.name], path
    d = R / f'.tmp/native-fixtures/{a.major}/hashtable-{a.host_link}'
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    baseline = d / 'original-baseline'
    run([t + 'clang', '-O2', baseline_source, harness, '-o', baseline])
    expected = run([baseline]).stdout
    assert len(expected.splitlines()) == 10
    for name, path in (('marked', source), ('harness', harness)):
        run([t + 'clang', '-O2', '-nostdinc', '-isystem',
             runtime.parent / 'musl-sysroot/include', '-emit-llvm', '-c', path,
             '-o', d / f'{name}.bc'])
    source_inputs = [d / 'marked.bc']
    if a.host_link == 'before': source_inputs.append(d / 'harness.bc')
    run([t + 'llvm-link', *source_inputs, '-o', d / 'source.bc'])
    run([t + 'llvm-link', d / 'source.bc', runtime, arith_path(a.major),
         '--only-needed', '-o', d / 'linked.bc'])
    run([t + 'opt', '-passes=lto<O3>', d / 'linked.bc', '-o', d / 'postlink.bc'])
    out = d / 'out'
    producer = [t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett',
                '-bennett-dialect=0.2.10', '-bennett-analysis-budget-ms=300000',
                '-bennett-budget-default=10000000,1048576,4096,256,65536']
    run([*producer, '-bennett-out=' + str(out), d / 'postlink.bc', '-disable-output'])
    assert (out / 'ht_demo_basic/launch.bennett').is_file()
    assert (out / 'ht_demo_grow/launch.bennett').is_file()
    native, report = d / 'native.bc', d / 'native.json'
    run([t + 'opt', '-load-pass-plugin=' + str(plugin), '-passes=bennett-native-comparison',
         '-bennett-native-record=' + str(out / 'ht_demo_basic/launch-record.json'),
         '-bennett-native-entry=ht_demo_basic', '-bennett-native-report=' + str(report),
         out / 'device.bc', '-o', native])
    undefined = run([t + 'llvm-nm', '--undefined-only', native]).stdout
    for marker in ('__bennett_qalloc', '__bennett_qfree', '__bennett_effect_console_write'):
        assert marker not in undefined, undefined
    meta = json.loads(report.read_text())
    obj = out / 'ht_demo_basic/launch.bennett'
    exe, state = build(a.major, d, native, meta, obj,
                       harness if a.host_link == 'after' else None, runtime, 1048576)
    layout = resolved_layout(a.major, exe, meta)
    layout_file = d / 'resolved-layout.json'
    layout_file.write_text(json.dumps(layout, indent=2) + '\n')
    mapped = d / 'mapped'
    run([*producer, '-bennett-out=' + str(mapped),
         '-bennett-comparison-layout=' + str(layout_file), d / 'postlink.bc', '-disable-output'])
    update_object(a.major, exe, mapped / 'ht_demo_basic/launch.bennett')
    assert resolved_layout(a.major, exe, meta) == layout, 'native addresses moved after embedding'
    actual = run([exe]).stdout
    assert actual == expected, (expected, actual)
    for path, identity in source_hashes.items():
        assert sha(Path(path)) == identity, path
    result = dict(major=a.major, passed=10, cases=10, native_stdout=actual,
                  original_baseline_stdout=expected, source_sha256=source_hashes,
                  runtime_sha256=sha(runtime), arith_sha256=sha(arith_path(a.major)),
                  materialised_sha256=sha(out / 'device.bc'), native_sha256=sha(native),
                  executable_sha256=sha(exe), layout_sha256=sha(layout_file),
                  native_link=state, full_comparison_acceptance=False)
    suffix = '-before' if a.host_link == 'before' else ''
    (R / f'.tmp/native-fixtures{suffix}-{a.major}.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(dict(major=a.major, passed=10, cases=10)))


if __name__ == '__main__':
    main()
