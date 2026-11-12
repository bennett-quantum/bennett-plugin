#!/usr/bin/env python3
"""Production address relocation scans bodies once, independent of symbol count."""
import argparse
import json
from pathlib import Path

from contracts import ROOT, run_checked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for count in (8, 64):
        source = directory / f'functions-{count}.ll'
        functions = '\n'.join(f'@g{i} = global i32 {i}\n'
                              f'define i32 @f{i}() {{ %v = load i32, ptr @g{i}\n ret i32 %v }}'
                              for i in range(count))
        pointers = ', '.join(f'ptr @f{i}' for i in range(count))
        source.write_text('target datalayout = "e-p:64:64"\n'
                          f'@table = global [{count} x ptr] [{pointers}]\n' + functions + '''
define i32 @main(i32 %argc, ptr %argv) {
 %which = and i32 %argc, 7
 %p = getelementptr ptr, ptr @table, i32 %which
 %f = load ptr, ptr %p
 %r = call i32 %f()
 ret i32 %r
}
''')
        output = directory / f'out-{count}'
        result = run_checked([f'/usr/lib/llvm-{args.major}/bin/opt',
                              f'-load-pass-plugin={args.plugin.absolute()}',
                              '-passes=bennett', '-bennett-dialect=0.3-r1',
                              '-bennett-isa=0.9', '-bennett-tier=reversible',
                              '-bennett-entry=main', '-bennett-link-work',
                              '-bennett-budget-default=100000,131072,4096,32,65536',
                              f'-bennett-out={output}', '-disable-output', source])
        source.with_suffix('.stderr').write_text(result.stderr)
        work = [json.loads(line.split(':', 1)[1]) for line in result.stderr.splitlines()
                if line.startswith('bennett-link-work:')]
        assert work, result.stderr
        assert {stage['stage'] for stage in work} == {'function-addresses', 'global-addresses'}
        receipts.append(dict(count=count, work=work))
        (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
        obj = (output / 'main/launch.bennett').read_text()
        for stage in work:
            assert stage['input_bytes'] > 0, stage
            assert stage['scanned_bytes'] <= len(obj), stage
        coverage = [json.loads(line.split(':', 1)[1]) for line in result.stderr.splitlines()
                    if line.startswith('bennett-coverage-work:')]
        assert coverage and all(row['entries'] > 0 and row['relocated_entries'] == 0
                                for row in coverage), coverage
        assert 'CCFUNCTION' not in obj and 'CCADDRESS' not in obj
        assert json.loads((output / 'main/blockers.json').read_text()) == []
        run_checked([f'/usr/lib/llvm-{args.major}/bin/opt', '-passes=verify',
                     '-disable-output', output / 'host.bc'])
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
