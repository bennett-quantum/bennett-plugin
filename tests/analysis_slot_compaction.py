#!/usr/bin/env python3
"""Residue stores compact their own object without copying unrelated memory.

Each table starts with two zero pointer slots. A stride-16 store of {null,
@target} covers exactly its first slot, retaining its second slot. Compacting
N disjoint tables visits their 3N old/new facts plus the shared EXT family
for an out-of-object GEP. Visiting the whole module after each store is
quadratic. Counts, never host time, gate this rule.
"""

import argparse
import json
from pathlib import Path

from contracts import ROOT, run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--major", type=int, required=True, choices=(18, 23))
    parser.add_argument("--plugin", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    directory = args.artifacts / str(args.major)
    directory.mkdir(parents=True, exist_ok=True)
    receipts = []
    for count in (16, 32, 64):
        globals_ = ['@target = global i8 7'] + [
            f'@table{i} = internal global [2 x ptr] zeroinitializer' for i in range(count)]
        body = ['%v = select i1 true, ptr null, ptr @target']
        for i in range(count):
            body += [f'%p{i} = getelementptr [2 x ptr], ptr @table{i}, i64 %index, i64 0',
                     f'store ptr %v, ptr %p{i}',
                     f'%read{i} = load ptr, ptr @table{i}',
                     f'%tail{i} = load ptr, ptr getelementptr ([2 x ptr], ptr @table{i}, i64 0, i64 1)']
        blocks = {'entry': 'br label %body', 'body': '\n '.join(body) + '\n br label %exit',
                  'exit': 'ret void'}
        helper = 'define internal i8 @helper() { ret i8 9 }\n'
        domains = []
        for order in ('original', 'functions', 'blocks'):
            source = directory / f'{count}-{order}.ll'
            report = source.with_suffix('.json')
            block_order = ('entry', 'exit', 'body') if order == 'blocks' else ('entry', 'body', 'exit')
            top = 'define void @top(i64 %index) {\n' + '\n'.join(
                b + ':\n ' + blocks[b] for b in block_order) + '\n}\n'
            source.write_text('target datalayout = "e-p:64:64"\n' + '\n'.join(globals_) + '\n'
                              + (top + helper if order == 'functions' else helper + top))
            command = [f'/usr/lib/llvm-{args.major}/bin/opt',
                       f'-load-pass-plugin={args.plugin.absolute()}', '-passes=bennett',
                       '-bennett-dialect=0.2.13', '-bennett-analysis-only',
                       f'-bennett-report={report}', '-disable-output', source]
            result = run(command)
            source.with_suffix('.stderr').write_text(result.stderr)
            assert result.returncode == 0, result.stderr
            data = json.loads(report.read_text())
            values = {(v['function'], v['value']): (v['top'], sorted(v['atoms']))
                      for v in data['values']}
            for i in range(count):
                assert values['top', f'%read{i}'] == (False, ['INT(0)', 'PTR(@target,0,0)']), values
                assert values['top', f'%tail{i}'] == (False, ['INT(0)']), values
            domains.append(values)
            work = data['analysis_work']
            receipts.append(dict(count=count, order=order, argv=list(map(str, command)), work=work))
            (directory / 'work.json').write_text(json.dumps(receipts, indent=2) + '\n')
            memory = work['memory']
            assert memory['compact_slots'] <= 3 * count + 1, (count, order, memory)
            assert memory['compact_copies'] == 0, (count, order, memory)
            assert memory['reindexed_slots'] <= count, (count, order, memory)
        assert domains[0] == domains[1] == domains[2], (count, 'evaluation order')
    print(json.dumps(dict(major=args.major, cases=len(receipts), passed=True)))


if __name__ == '__main__':
    main()
