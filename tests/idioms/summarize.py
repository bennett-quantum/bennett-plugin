#!/usr/bin/env python3
"""Export raw measurements and reproducible finite-size growth fits."""
import argparse
import csv
import json
import math
from pathlib import Path

FIELDS = ['rounds', 'valueAtoms', 'slotAtoms', 'uniqueSets', 'wideSites', 'topValues',
          'cpu', 'total_user', 'total_system', 'total_cpu', 'candMean', 'candMax']


def load(root):
    rows = []
    for p in root.glob('*/*/result.json'):
        r = json.loads(p.read_text())
        r['directory'] = str(p.parent.relative_to(root))
        rows.append(r)
    return sorted(rows, key=lambda r: (r['idiom'], r['variant'], r['n']))


def flat(r):
    out = {k: r.get(k) for k in ['idiom', 'variant', 'n', 'fixpoint', 'rounds',
                                'total_user', 'total_system', 'total_cpu', 'budget_exhausted',
                                'cpu_budget_exhausted', 'resource_reason', 'error']}
    out.update(r.get('last', {}))
    out.update(r.get('final', {}))
    out['atoms'] = (int(out['valueAtoms'])+int(out['slotAtoms'])
                    if 'valueAtoms' in out and 'slotAtoms' in out else None)
    return out


def fit(xs, ys, fn):
    z = [fn(x) for x in xs]
    zm, ym = sum(z)/len(z), sum(ys)/len(ys)
    den = sum((x-zm)**2 for x in z)
    b = max(0, sum((x-zm)*(y-ym) for x, y in zip(z, ys))/den) if den else 0
    a = ym-b*zm
    errors = [y-(a+b*x) for x, y in zip(z, ys)]
    sse = sum(e*e for e in errors)
    sst = sum((y-ym)**2 for y in ys)
    return {'intercept': a, 'slope': b, 'r_squared': 1-sse/sst if sst else 1,
            'normalized_rmse': math.sqrt(sse/len(ys))/max(max(ys)-min(ys), 1e-12)}


def fits(rows):
    out = []
    groups = sorted(set((r['idiom'], r['variant']) for r in rows))
    for i, v in groups:
        # Exclude N=1/4 baselines and incomplete fixpoints from growth fits.
        rs = [flat(r) for r in rows if r['idiom'] == i and r['variant'] == v
              and r.get('fixpoint') and r['n'] >= 16]
        if len(rs) < 3:
            continue
        for metric in ['rounds', 'atoms', 'total_user', 'total_cpu']:
            xs, ys = [r['n'] for r in rs], [float(r.get(metric) or 0) for r in rs]
            candidates = {name: fit(xs, ys, fn) for name, fn in [
                ('constant', lambda x: 1), ('logarithmic', math.log2),
                ('linear', lambda x: x), ('quadratic', lambda x: x*x)]}
            best = min(candidates, key=lambda k: candidates[k]['normalized_rmse'])
            # Prefer the simpler fit if its error is within 3% of the range.
            if max(ys) == min(ys):
                best = 'constant'
            elif candidates['linear']['normalized_rmse'] < 0.03:
                best = 'linear'
            p = math.log(ys[-1]/ys[-2])/math.log(xs[-1]/xs[-2]) if min(ys[-2:]) > 0 else None
            out.append({'idiom': i, 'variant': v, 'metric': metric, 'n': xs,
                        'values': ys, 'best_descriptive_fit': best,
                        'last_interval_power': p, 'models': candidates})
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rows = load(a.root)
    (a.out/'all-results.json').write_text(json.dumps(rows, indent=2)+'\n')
    (a.out/'fits.json').write_text(json.dumps(fits(rows), indent=2)+'\n')
    fs = [flat(r) for r in rows]
    keys = ['idiom', 'variant', 'n', 'fixpoint', *FIELDS, 'atoms', 'budget_exhausted',
            'ptrResidue', 'ptrAny', 'ptrExtUnknown', 'oobExact', 'fn', 'int', 'root',
            'ptrValues', 'avgObjsPerPtrValue', 'slots', 'values', 'rssMB',
            'indirectSites', 'calleeTop', 'calleeDataPtr', 'typeWide',
            'cpu_budget_exhausted', 'resource_reason', 'error']
    with (a.out/'raw.csv').open('w') as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction='ignore')
        w.writeheader()
        w.writerows(fs)
    print(f'{len(rows)} runs exported')
