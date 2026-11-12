#!/usr/bin/env python3
"""Build/run geometric idiom series; paths are supplied, never embedded."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess as sp
import sys
import time

HERE = Path(__file__).resolve().parent
MATRIX = {
    '01_scalar': ['default'], '02_objects': ['independent', 'chain'],
    '03_walk': ['inbounds_const', 'inbounds_global', 'integer_const', 'integer_global'],
    '04_heap': ['list', 'tree'], '05_allocator': ['default'], '06_table': ['default'],
    '07_callback': ['plain', 'sentinel'], '08_variadic': ['config', 'printf'],
    '09_copy': ['memcpy_const', 'memcpy_global', 'memmove_const', 'memmove_global'],
    '10_casts': ['cast', 'subtract'], '11_linkage': ['exported', 'static'],
    '12_strings': ['default'],
}
SWITCHES = ('VA CFSKIP VANOREG WS TYPEFILTER NOTOP SENTINEL SEED DUMP HEAPCLONE '
            'VACLAMP TOPOBJ SLOTS W1 W2 W4').split()


def parse_run(d):
    probe = (d/'probe.log').read_text() if (d/'probe.log').exists() else ''
    rounds = re.findall(r'^ROUND .*', probe, re.M)
    finals = re.findall(r'^FINAL .*', probe, re.M)
    def fields(line):
        return dict(re.findall(r'(\w+)=([^\s]+)', line))
    result = {'rounds': len(rounds), 'fixpoint': bool(finals),
              'last': fields(rounds[-1]) if rounds else {},
              'final': fields(finals[-1]) if finals else {},
              'wide': re.findall(r'^WIDE .*', probe, re.M)}
    err = (d/'stderr').read_text() if (d/'stderr').exists() else ''
    result['budget_exhausted'] = 'budget exhausted' in err
    reason = re.search(r'compiler resource allowance: (.*?) at ', err)
    result['resource_reason'] = reason[1] if reason else None
    result['cpu_budget_exhausted'] = result['budget_exhausted'] and result['resource_reason'] == 'thread CPU milliseconds'
    result['status'] = (d/'status').read_text() if (d/'status').exists() else ''
    for label, key in [('User time (seconds)', 'total_user'),
                       ('System time (seconds)', 'total_system'),
                       ('Maximum resident set size (kbytes)', 'max_rss_kb')]:
        m = re.search(re.escape(label)+r':\s*([\d.]+)', err)
        result[key] = float(m[1]) if m else None
    if result['total_user'] is not None:
        result['total_cpu'] = result['total_user'] + result['total_system']
    return result


def audit(ir):
    patterns = {'alloca': r'\balloca\b', 'gep_inbounds': r'getelementptr inbounds',
                'gep_other': r'getelementptr (?!inbounds)', 'phi': r'\bphi\b',
                'ptrtoint': r'\bptrtoint\b', 'inttoptr': r'\binttoptr\b',
                'memcpy': r'call .*@llvm.memcpy', 'memmove': r'call .*@llvm.memmove|call .*@__bennett_rt_memmove',
                'malloc': r'call .*@malloc', 'va_start': r'call .*@llvm.va_start',
                'indirect': r'\bcall\b[^@\n]*%[\w.]+\(',
                'volatile_load': r'load volatile', 'sub_i64': r'\bsub i64'}
    counts = {k: len(re.findall(p, ir)) for k, p in patterns.items()}
    counts['definitions'] = len(re.findall(r'^define ', ir, re.M))
    return counts


def one(args, idiom, variant, n):
    d = args.out/f'{idiom}--{variant}'/str(n)
    d.mkdir(parents=True, exist_ok=True)
    if args.resume and (d/'result.json').exists():
        return json.loads((d/'result.json').read_text())
    # Do not allow stale FINAL/ROUND lines after a deliberate rerun.
    for name in ['probe.log', 'status', 'stderr', 'stdout']:
        (d/name).unlink(missing_ok=True)
    c = sp.check_output([sys.executable, str(HERE/(idiom+'.py')), str(n), '--variant', variant])
    (d/'gen.c').write_bytes(c)
    env = os.environ.copy()
    for k in list(env):
        if k in SWITCHES or k.startswith('BENNETT_PROBE_') or k in (
                'DISPLAY', 'WAYLAND_DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'BROWSER'):
            env.pop(k, None)
    env.update(LC_ALL='C', TMPDIR=str(args.out/'tmp'), VA='1', CFSKIP='1', VANOREG='1', WS='1')
    # The supplied runner overrides TMPDIR. A readonly Bash variable preserves
    # this job's directory without changing that runner (one harmless warning).
    env['BASH_ENV'] = str(args.out/'bash-env')
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    tools = args.llvm
    r = args.runtime
    commands = [
        [str(tools/'clang'), '--target=x86_64-unknown-linux-musl', f'--sysroot={r}/musl-sysroot',
         '-nostdinc', '-isystem', str(r/'musl-sysroot/include'), '-emit-llvm', '-O2', '-flto',
         '-g0', '-fno-stack-protector', '-c', 'gen.c', '-o', 'p.bc'],
        [str(tools/'llvm-link'), 'p.bc', str(r/'bennett-runtimes.bc'), str(args.arith),
         '--only-needed', '-o', 'linked.bc'],
        [str(tools/'opt'), '-passes=lto<O3>', '-S', 'linked.bc', '-o', 'postlink.ll'],
    ]
    start = time.monotonic()
    result = {'idiom': idiom, 'variant': variant, 'n': n, 'slice': 'bennett.slice'}
    try:
        with (d/'build.log').open('w') as log:
            for cmd in commands:
                # Builds are serial, nice, and use the same capped slice.
                sp.run(['systemd-run', '--user', '--slice=bennett.slice', '--scope', '-p', 'MemoryMax=2G',
                        '-p', 'MemorySwapMax=0', 'nice', '-n', '10', *cmd],
                       cwd=d, env=env, stdout=log, stderr=sp.STDOUT, check=True, timeout=180)
        ir = (d/'postlink.ll').read_text()
        result['ir'] = audit(ir)
        (d/'ir-audit.json').write_text(json.dumps(result['ir'], indent=2)+'\n')
        cmd = ['systemd-run', '--user', '--slice=bennett.slice', '--scope', '-p', 'MemoryMax=2G', '-p', 'MemorySwapMax=0',
               'nice', '-n', '10', 'timeout', '--kill-after=10s', '180s',
               'bash', str(args.runner), str(args.plugin), str(d/'postlink.ll'), str(d), '60000']
        with (d/'runner.log').open('w') as log:
            completed = sp.run(cmd, cwd=d, env=env, stdout=log, stderr=sp.STDOUT, timeout=200)
        result.update(parse_run(d))
        result['scope_exit'] = completed.returncode
    except (sp.SubprocessError, OSError) as e:
        result['error'] = str(e)
        result.update(parse_run(d))
    result['wall'] = time.monotonic()-start
    (d/'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k: result.get(k) for k in ['idiom', 'variant', 'n', 'fixpoint', 'rounds', 'total_cpu', 'error']}), flush=True)
    return result


def series(args, idiom, variant):
    rows = []
    for n in args.sizes:
        row = one(args, idiom, variant, n)
        rows.append(row)
        if row.get('error') or not row.get('fixpoint'):
            break
    return rows


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ['plugin', 'runner', 'runtime', 'arith']:
        p.add_argument('--'+key, type=Path, default=os.environ.get('IDIOMS_'+key.upper()), required=not os.environ.get('IDIOMS_'+key.upper()))
    p.add_argument('--llvm', type=Path, default=os.environ.get('LLVM18_BIN') or
                   (str(Path(shutil.which('clang-18')).resolve().parent) if shutil.which('clang-18') else None))
    p.add_argument('--out', type=Path, default=HERE.parents[1]/'.tmp/idioms')
    p.add_argument('--sizes', type=int, nargs='+', default=[1, 4, 16, 64, 256])
    p.add_argument('--jobs', type=int, choices=[1], default=1)
    p.add_argument('--only', nargs='+', help='idiom or idiom:variant selectors')
    p.add_argument('--resume', action='store_true')
    args = p.parse_args()
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    if args.llvm is None:
        p.error('set LLVM18_BIN or pass --llvm')
    for key in ['plugin', 'runner', 'runtime', 'arith', 'llvm', 'out']:
        setattr(args, key, getattr(args, key).resolve())
    (args.out/'tmp').mkdir(parents=True, exist_ok=True)
    (args.out/'bash-env').write_text('readonly TMPDIR\n')
    manifest = {'sizes': args.sizes, 'jobs': args.jobs, 'budget_ms': 60000,
                'plugin_sha256': hashlib.sha256(args.plugin.read_bytes()).hexdigest(),
                'slice': 'bennett.slice', 'switches': {'VA': 1, 'CFSKIP': 1, 'VANOREG': 1, 'WS': 1}}
    (args.out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    selected = [(i, v) for i, vs in MATRIX.items() for v in vs
                if not args.only or i in args.only or f'{i}:{v}' in args.only]
    rows = [row for i, v in selected for row in series(args, i, v)]
    rows.sort(key=lambda x: (x['idiom'], x['variant'], x['n']))
    (args.out/'results.json').write_text(json.dumps(rows, indent=2)+'\n')


if __name__ == '__main__':
    main()
