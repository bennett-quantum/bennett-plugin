#!/usr/bin/env python3
"""Record the latest gate pass into docs/verification.json.

The file keeps only the latest pass in full. When a new pass name is recorded, the
previous latest pass is reduced to a short summary under `previous_passes`
(pass name, date, gate counts, object pairs, commits; at most ten lines each).
Full history: `git log -p docs/verification.json`.

Evidence comes from a completed gate run: <root>/.tmp/*.json written by tests/*.py and
<root>/build/*.so. Run the gate first (scripts/gate in the tree), then for example:

  scripts/record-verification.py --pass ninth --date 2026-11-01 --commits abc1234,def5678 --gate-exit 0
"""
import argparse, datetime, hashlib, json, os, re, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'tests'))
from contracts import PIN, SIBLINGS, dialect_text, drift

MAJORS = (18, 23)
ISA_REF = SIBLINGS / 'bennett-isa-spec/reference-interpreter/target/debug/bennett-isa-ref'
SUMMARY_KEYS = ('cases_run', 'cases_agree', 'cases_deferred', 'cases_blocked', 'cases_diverge')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate_counts(summary):
    """run/agree/deferred/blocked/diverge plus cells, per major."""
    return {str(m): '/'.join(str(summary[str(m)][k]) for k in SUMMARY_KEYS) +
            f" cells {summary[str(m)]['cells_agree']}/{summary[str(m)]['cells_run']}" for m in MAJORS}


def check_rows(rows):
    """Count rows whose own recorded verdicts all hold (checks, runs, rejections)."""
    ok = 0
    for r in rows:
        good = r.get('ok', True) and r.get('check', True) and r.get('run', True)
        good = good and all(x.get('ok', True) for x in r.get('runs', []))
        good = good and r.get('common_failure', True)
        ok += bool(good)
    return {'cases': len(rows), 'ok': ok, 'expected_rejections': sum(bool(r.get('expected_rejection')) for r in rows)}


def object_paths(tmp, major, scalars):
    """(name, path) of every emitted object whose cross-major equality is recorded."""
    out = []
    for o in scalars['objects']:
        if o.get('lowered'):
            out.append((f"scalar/{o['name']}", tmp / f"scalars/{major}/{o['name']}/ref.bennett"))
    out.append(('scalar/c-O3-inc8', tmp / f'scalars/{major}/c-inc8/ref.bennett'))
    out.append(('descriptor-reference/inc8', tmp / f'descriptors/{major}/oracle-0/ref.bennett'))
    for rel in ('top/launch.bennett', 'top/oracle-0/ref.bennett'):
        out.append((f'descriptor-production/{rel}', tmp / f'descriptors/{major}/production/{rel}'))
    for case in ('0', '7', '255', 'published'):
        for rel in ('launch.bennett', 'oracle-0/ref.bennett'):
            out.append((f'production/{case}/{rel}', tmp / f'production/{major}/{case}/out/top/{rel}'))
    out.append(('production/abi/launch.bennett', tmp / f'production/{major}/abi/out/abi/launch.bennett'))
    for family in ('production-shapes', 'production-budgets', 'production-dispatch', 'production-environments'):
        base = tmp / f'{family}/{major}'
        for p in sorted(base.rglob('*.bennett')):
            out.append((f'{family}/{p.relative_to(base)}', p))
    return out


def summarise(latest):
    """Reduce a full latest pass to the <= 10 line previous_passes entry."""
    pairs = latest['object_pairs']
    return {'pass': latest['name'], 'date': latest['date'],
            'gate_run_agree_deferred_blocked_diverge': latest['gate']['corpus']['18'].split(' ')[0],
            'object_pairs': f"{pairs['count']} cross-major byte-identical, {pairs['published_matches']} equal published fixtures",
            'commits': ','.join(latest['commits']), 'code_head': latest['code_head'][:7]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pass', dest='name', required=True, help='pass name, e.g. ninth')
    ap.add_argument('--date', required=True)
    ap.add_argument('--commits', required=True, help='comma-separated landed commits')
    ap.add_argument('--gate-exit', type=int, required=True)
    ap.add_argument('--root', type=Path, default=R, help='tree whose .tmp/ and build/ the gate used')
    ap.add_argument('--seed-previous', type=Path, help='JSON list of previous_passes when the file has none')
    a = ap.parse_args()
    assert a.gate_exit == 0, 'refusing to record a failed gate'
    tmp, build = a.root / '.tmp', a.root / 'build'
    read = lambda name: json.loads((tmp / name).read_text())
    assert not drift(), 'accepted contract drift'
    gate = read('corpus-gate.json')
    assert gate['dialect_commit'] == PIN and not gate['accepted_contract_drift']
    for major, h in gate['plugin_sha256'].items():
        assert digest(build / f'libbennett-plugin-{major}.so') == h, f'plugin {major} changed after the gate'
    for m in MAJORS:
        s = gate['summary'][str(m)]
        assert [s[k] for k in SUMMARY_KEYS] == [66, 65, 1, 0, 0], (m, s)

    checks, scalars = {}, {}
    for m in MAJORS:
        c = {}
        for name in ('recognition', 'analysis-edges', 'reference-images', 'materialisation', 'region-keys'):
            j = read(f'{name}-{m}.json')
            assert j['passed'] == j['cases'], (name, m)
            c[name] = {'cases': j['cases'], 'passed': j['passed']}
        d = read(f'descriptors-{m}.json')
        assert d['descriptor_inc8_equal'] and d['production_complete'] and d['production_exit'] == 0
        c['descriptors'] = {'descriptor_inc8_equal': True, 'production_complete': True}
        p = read(f'production-{m}.json')
        assert p['passed'] == 3 and p['published_oracle_inc8']['ok'] and p['native_abi']['ok']
        c['production'] = check_rows(p['cases'])
        for fam in ('dispatch', 'environments', 'shapes', 'budgets', 'records'):
            c[f'production-{fam}'] = check_rows(read(f'production-{fam}-{m}.json')['cases'])
            assert c[f'production-{fam}']['cases'] == c[f'production-{fam}']['ok'], (fam, m)
        checks[str(m)] = c
        sc = read(f'scalars-{m}.json')
        assert sc['c_inc8_equal'] and sc['passed'] == 16
        lowered = [o for o in sc['objects'] if o.get('lowered')]
        assert all(o['check'] and o['fixture_equal'] and o['hash_fixture_equal'] and all(r['ok'] for r in o['runs']) for o in lowered)
        scalars[str(m)] = {'objects_byte_exact': len(lowered), 'run_vectors': sum(len(o['runs']) for o in lowered),
                           'deferred': sc['deferred'], 'c_inc8_equal': True}
    assert scalars['18'] == scalars['23']

    fixtures = {n: b.encode() for n, b in re.findall(r'```isa object=([^\n ]+)\n(.*?)```', dialect_text(), re.S)}
    sc18 = read('scalars-18.json')
    by_major = {m: dict(object_paths(tmp, m, sc18)) for m in MAJORS}
    assert by_major[18].keys() == by_major[23].keys()
    rows = []
    for name, p18 in by_major[18].items():
        data = p18.read_bytes()
        assert data == by_major[23][name].read_bytes(), f'{name}: LLVM 18/23 bytes differ'
        golden = next((g for g, b in fixtures.items() if b == data), None)
        rows.append({'object': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(), 'published_golden': golden})
    cross = read('production-cross-major.json')
    assert cross['byte_identical']
    # Independent check of every launch object (CC lowering is plugin-defined, 17.4: no published golden).
    for name, p18 in by_major[18].items():
        if name.endswith('launch.bennett'):
            r = subprocess.run([str(ISA_REF), 'check', str(p18)], capture_output=True, text=True, timeout=60)
            assert r.returncode == 0, (name, r.stderr)

    path = R / 'docs/verification.json'
    previous = []
    if path.exists():
        old = json.loads(path.read_text())
        previous = old.get('previous_passes', [])
        if 'latest_pass' in old and old['latest_pass']['name'] != a.name:
            previous.append(summarise(old['latest_pass']))
    if not previous and a.seed_previous:
        previous = json.loads(a.seed_previous.read_text())
    head = subprocess.check_output(['git', '-C', str(a.root), 'rev-parse', 'HEAD'], text=True).strip()
    latest = {
        'name': a.name, 'date': a.date, 'commits': a.commits.split(','), 'code_head': head,
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'dialect': '0.2.10', 'dialect_commit': PIN, 'isa': '0.8',
        'plugin_sha256': gate['plugin_sha256'],
        'gate': {'command': 'scripts/pre-push', 'exit': a.gate_exit, 'accepted_contract_drift': False,
                 'contract_head_drift': gate['contract_head_drift'], 'contract_worktree_drift': gate['contract_worktree_drift'],
                 'corpus': gate_counts(gate['summary']),
                 'non_agreeing': [{k: r[k] for k in ('case', 'major', 'pipeline', 'classification')}
                                  for r in gate['cells'] if r['classification'] != 'agree']},
        'checks': checks, 'scalars': scalars,
        'object_pairs': {'count': len(rows), 'byte_identical': True,
                         'published_matches': sum(bool(r['published_golden']) for r in rows),
                         'production_cross_major_pairs': cross['pairs'], 'rows': rows},
    }
    path.write_text(json.dumps({'schema': 2, 'latest_pass': latest, 'previous_passes': previous}, indent=2) + '\n')
    print(f"recorded pass {a.name}: {len(rows)} object pairs, {latest['object_pairs']['published_matches']} published matches, "
          f"{len(previous)} previous passes")


if __name__ == '__main__':
    main()
