#!/usr/bin/env python3
"""Record the latest gate pass into docs/verification.json.

The file keeps only the latest pass.
Full history: `git log -p docs/verification.json`.

Evidence comes from a completed gate run: <root>/.tmp/*.json written by tests/*.py and
<root>/build/*.so. Run the gate first (scripts/gate in the tree), then for example:

  scripts/record-verification.py --pass ninth --date 2026-11-01 --commits abc1234,def5678 --gate-exit 0
"""
import argparse, datetime, hashlib, json, os, re, subprocess, sys
from pathlib import Path
R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / 'tests'))
from contracts import PIN, sibling, dialect_text, drift

MAJORS = (18, 23)
ISA_REF = sibling('bennett-isa-spec') / 'reference-interpreter/target/debug/bennett-isa-ref'
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
    for family in ('production-shapes', 'production-budgets', 'production-dispatch', 'production-environments', 'production-lifts', 'shadow-stack', 'budget-stage', 'entry-snapshot', 'softfloat', 'wide', 'integer-intrinsics', 'memory-runtime', 'aggregate-rows', 'cc-calls', 'cc-switch', 'reversible'):
        base = tmp / f'{family}/{major}'
        for p in sorted(base.rglob('*.bennett')):
            if family=='reversible' and 'r-hello' in p.relative_to(base).parts: continue
            out.append((f'{family}/{p.relative_to(base)}', p))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pass', dest='name', required=True, help='pass name, e.g. ninth')
    ap.add_argument('--date', required=True)
    ap.add_argument('--commits', required=True, help='comma-separated landed commits')
    ap.add_argument('--gate-exit', type=int, required=True)
    ap.add_argument('--root', type=Path, default=R, help='tree whose .tmp/ and build/ the gate used')
    ap.add_argument('--rung3-report', type=Path, help='consumer report, including failed prerequisite rows')
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
        assert [s[k] for k in SUMMARY_KEYS]==[66,66,0,0,0], (m,s)

    checks, scalars = {}, {}
    for m in MAJORS:
        c = {}
        for name in ('recognition', 'analysis-edges', 'analysis-performance', 'reference-images', 'materialisation', 'aggregate-rows', 'allocator-closure', 'cc-calls', 'cc-switch', 'reversible', 'softfloat', 'wide', 'integer-intrinsics', 'memory-runtime', 'region-keys', 'validation'):
            j = read(f'{name}-{m}.json')
            assert j['passed'] == j['cases'], (name, m)
            c[name] = {'cases': j['cases'], 'passed': j['passed']}
            if name in ('aggregate-rows','allocator-closure','cc-calls', 'cc-switch', 'reversible'):c[name]['evidence']=j['results']
            if name=='analysis-performance':
                c[name].update(seconds=j['seconds'],rounds=j['rounds'],budget_diagnostic=j['budget_diagnostic'])
            if name=='softfloat':
                c[name]['known_remainders']=[r for r in j['results'] if r.get('expected_unimplemented')]
                c[name]['native_wide']=[r for r in j['results'] if r['name'].startswith('published-native-wide-')]
                c[name]['recursive_closure']=[r for r in j['results'] if r['name'].startswith('CC-recursive-')]
                c[name]['closure_contract'] = {
                    'rewrite': '§13.1: The entry points are defined by bennett-arith and are part of its bitcode the driver links.',
                    'recursion': '§14.1: Direct calls lower to CC/R call; Recursion is unrestricted.',
                    'transport': '§17.4: LLVM integer and memory instructions map to ISA instructions; phis to block parameters; multi-result calls carry aggregates.',
                    'original_stop': '§13.1 recursive CC soft-float closure: active-set inlining guard at bennett_sf_eval',
                    'llvm23_recursive_instruction': 'call void @bennett_sf_eval(ptr %19, i32 %1, i32 3, ptr %18, i32 0, i32 %5)',
                    'cc_steps_note': 'run-program reports CC steps separately from the nested oracle; successful unchanged 64-wire launch uses two 1000000-step oracle tokens. L numerical rows record nested materialised steps.'}

                c[name]['published_production']=[r for r in j['results'] if r['name'].startswith('published-production')]
        audit = read(f'key-audit-{m}.json')
        assert not audit['unaccounted'] and audit['accounted'] == audit['unmatched']
        c['full-key-audit'] = {k: audit[k] for k in ('cases', 'matched', 'unmatched', 'accounted', 'unaccounted')}
        d = read(f'descriptors-{m}.json')
        assert d['descriptor_inc8_equal'] and d['production_complete'] and d['production_exit'] == 0
        c['descriptors'] = {'descriptor_inc8_equal': True, 'production_complete': True}
        p = read(f'production-{m}.json')
        assert p['passed'] == 3 and p['published_oracle_inc8']['ok'] and p['native_abi']['ok']
        c['production'] = check_rows(p['cases'])
        for fam in ('dispatch', 'environments', 'shapes', 'budgets', 'records', 'lifts'):
            c[f'production-{fam}'] = check_rows(read(f'production-{fam}-{m}.json')['cases'])
            assert c[f'production-{fam}']['cases'] == c[f'production-{fam}']['ok'], (fam, m)
        snapshot = read(f'entry-snapshot-{m}.json')
        assert snapshot['cases'] and all(r.get('ok') and r.get('check') for r in snapshot['cases'])
        c['entry-snapshot'] = check_rows(snapshot['cases'])
        c['entry-snapshot']['isa_ref'] = snapshot['isa_ref']
        c['entry-snapshot']['isa_ref_sha256'] = snapshot['isa_ref_sha256']
        ss = read(f'shadow-stack-{m}.json')
        assert all(r.get('check') and r.get('ok') for r in ss['cases'])
        c['shadow-stack'] = check_rows(ss['cases'])
        stage = read(f'budget-stage-{m}.json')
        assert all(r.get('ok') and r.get('check') for r in stage['cases'])
        assert all(r['ok'] for r in stage['proof_cases'])
        final = next(r for r in stage['cases'] if r['name'] == 'identity-once')
        assert final['reference_exact'] and final['prefix_vectors'] == 316 and final['prefixes_ok'] and final['tokens_final']
        shape = final['build']['budget_table']['shapes'][0]
        c['budget-stage'] = dict(check_rows(stage['cases']), proof_cases=len(stage['proof_cases']),
                                prefix_vectors=316, reference_exact=True, tokens_final=True,
                                selection_identity=shape['selection_identity'], identity=shape['identity'])
        checks[str(m)] = c
        sc = read(f'scalars-{m}.json')
        assert sc['c_inc8_equal'] and sc['passed'] == 21
        lowered = [o for o in sc['objects'] if o.get('lowered')]
        assert all(o['check'] and o['fixture_equal'] and o['hash_fixture_equal'] and all(r['ok'] for r in o['runs']) for o in lowered)
        scalars[str(m)] = {'objects_byte_exact': len(lowered), 'run_vectors': sum(len(o['runs']) for o in lowered),
                           'deferred': sc['deferred'], 'c_inc8_equal': True}
    assert scalars['18'] == scalars['23']

    fixtures = {n: b.encode() for n, b in re.findall(r'```isa object=([^\n ]+)\n(.*?)```', dialect_text(), re.S)}
    for size in (16, 32):
        fixtures[f'budget-stage-{size}'] = (R / f'tests/fixtures/budget-stage-{size}.bennett').read_bytes()
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
    baseline = json.loads(path.read_text()).get('latest_pass', {}).get('object_pairs', {}).get('rows', []) if path.exists() else []
    current = {r['object']: r for r in rows}
    for old in baseline:
        assert old['object'] in current and old['sha256'] == current[old['object']]['sha256'], f"previously recorded object changed: {old['object']}"
    head = subprocess.check_output(['git', '-C', str(a.root), 'rev-parse', 'HEAD'], text=True).strip()
    latest = {
        'name': a.name, 'date': a.date, 'commits': a.commits.split(','), 'code_head': head,
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'),
        'dialect': '0.2.13', 'dialect_commit': PIN, 'isa': '0.8',
        'arith': __import__('tomllib').loads((R/'SPEC_VERSIONS.toml').read_text())['arith'],
        'arith_gate_paths': {str(m):str(__import__('contracts').arith_path(m)) for m in MAJORS},
        'allocator_gate_root': str(sibling('bennett-runtimes') / 'dist'),
        'plugin_sha256': gate['plugin_sha256'],
        'gate': {'command': 'scripts/gate', 'exit': a.gate_exit, 'accepted_contract_drift': False,
                 'contract_head_drift': gate['contract_head_drift'], 'contract_worktree_drift': gate['contract_worktree_drift'],
                 'corpus': gate_counts(gate['summary']),
                 'non_agreeing': [{k: r[k] for k in ('case', 'major', 'pipeline', 'classification')}
                                  for r in gate['cells'] if r['classification'] != 'agree']},
        'checks': checks, 'scalars': scalars,
        'rung2_analysis': json.loads((R/'docs/rung2-analysis.json').read_text()),
        'object_pairs': {'count': len(rows), 'byte_identical': True,
                         'published_matches': sum(bool(r['published_golden']) for r in rows),
                         'production_cross_major_pairs': cross['pairs'], 'preserved_previous_objects': len(baseline), 'rows': rows},
    }
    if a.rung3_report:
        report = json.loads(a.rung3_report.read_text())
        latest['rung3'] = {'source_report': str(a.rung3_report.resolve()),
                          'source_report_sha256': digest(a.rung3_report),
                          'exit': int(any(row['status'] != 'PASS' for stages in report['stages'].values() for row in stages.values())),
                          'report': report}
    if a.name == 'bp-ivy' and (tmp/'r-hello23-execution.json').is_file():
        obj = tmp/'reversible/23/r-hello/out/main/launch.bennett'
        checked = read('r-hello23-check.log')
        assert checked['object_hash'] == digest(obj), 'exploratory object changed after execution'
        latest['whole_program_r_exploratory'] = {
            'major': 23, 'classification': 'measured failure, not corpus agreement',
            'object_sha256': digest(obj), 'admission': checked['status'],
            'command': ['bennett-isa-spec/reference-interpreter/target/release/bennett-isa-ref',
                        'run-program', str(obj), 'main', '--budget', '10000000,1048576,65536,256',
                        '--replies', str(tmp/'reversible/23/r-console/argv.json')],
            'result': read('r-hello23-execution.json'),
            'execution_log_sha256': digest(tmp/'r-hello23-execution.json')}
    failed_logs = sorted(tmp.glob('bp-ivy-gate-*-red.log'))
    latest['prior_failed_attempts'] = [{'log': str(p.relative_to(a.root)), 'sha256': digest(p)} for p in failed_logs]
    path.write_text(json.dumps({'schema': 2, 'latest_pass': latest}, indent=2) + '\n')
    print(f"recorded pass {a.name}: {len(rows)} object pairs, {latest['object_pairs']['published_matches']} published matches, "
          "latest pass only")


if __name__ == '__main__':
    main()
