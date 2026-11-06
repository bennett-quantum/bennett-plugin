#!/usr/bin/env python3
"""Missing entry runtime definitions produce contextual diagnostics, never aborts."""
import argparse
from pathlib import Path
import re

from contracts import ROOT, plugin_command, run


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--major', type=int, required=True, choices=(18, 23))
    parser.add_argument('--plugin', type=Path)
    args = parser.parse_args()
    work = ROOT / f'.tmp/entry-runtime/{args.major}'
    work.mkdir(parents=True, exist_ok=True)
    original = (ROOT / 'tests/probes/entry-stack.ll').read_text()
    command = plugin_command(args.major)
    if args.plugin:
        command[1] = '-load-pass-plugin=' + str(args.plugin)
    command += ['-bennett-oracle=f', '-bennett-scalar-shape=;tgt=64',
                '-bennett-scalar-stack=64', '-bennett-scalar-heap=64', '-disable-output']
    for helper in ('__bennett_rt_entry_replay', '__bennett_rt_ss_init'):
        source = work / f'{helper}.ll'
        source.write_text(re.sub(r'define void @' + helper + r'\(.*?^}\n', '', original,
                                 flags=re.M | re.S))
        result = run([*command, '-bennett-out=' + str(work), source])
        assert result.returncode == 1, result
        assert 'BD-E-ENTRY-RUNTIME' in result.stderr and helper in result.stderr, result.stderr
        assert 'stack dump' not in result.stderr.lower(), result.stderr
    disabled = re.sub(r'define void @__bennett_rt_(?:entry_replay|ss_init)\(.*?^}\n', '',
                      original, flags=re.M | re.S)
    disabled = disabled.replace('!"bennett.entry.snapshot", i64 6', '!"bennett.entry.snapshot", i64 0')
    disabled = disabled.replace('!"bennett.ss.init", i64 1', '!"bennett.ss.init", i64 0')
    source = work / 'disabled.ll'
    source.write_text(disabled)
    result = run([*command, '-bennett-out=' + str(work / 'disabled'), source])
    assert result.returncode == 0, result.stderr
    print(f'LLVM {args.major}: two missing helpers diagnosed; disabled flags accepted')


if __name__ == '__main__':
    main()
