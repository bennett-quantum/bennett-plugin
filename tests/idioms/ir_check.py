#!/usr/bin/env python3
"""Check generated idiom survival and save concise post-LTO IR evidence."""
import json
from pathlib import Path
import re
import sys


def check(d):
    r = json.loads((d/'result.json').read_text())
    s = (d/'postlink.ll').read_text()
    i, v, n = r['idiom'], r['variant'], r['n']
    checks = {}
    def need(name, pattern, count=1):
        checks[name] = len(re.findall(pattern, s, re.M)) >= count
    note = ''
    if i == '01_scalar':
        need('direct_callees', r'^define internal .*@f\d+\(', n)
    elif i == '02_objects':
        need('stack_objects', r'\balloca\b', n)
        need('globals', r'^@g\d+ =', n)
    elif i == '03_walk':
        if n == 1:
            note = 'O3 simplifies the one-element loop; baseline only.'
        else:
            need('loop', r'\bphi\b')
            need('pointer_recurrence' if v.startswith('inbounds') else 'integer_recurrence',
                 r'getelementptr inbounds i32, ptr %' if v.startswith('inbounds') else r'\binttoptr i64 %')
        if v.endswith('global'):
            need('global_bound', r'load volatile i64, ptr @bound')
    elif i == '04_heap':
        need('malloc_sites', r'call .*@malloc\(', n)
        need('node_access', r'getelementptr inbounds %struct.Node')
    elif i == '05_allocator':
        need('wrapper_calls', r'call .*@my_alloc\(', n)
        need('malloc', r'call .*@malloc\(')
    elif i == '06_table':
        need('callbacks', r'^define internal .*@cb\d+\(', n)
        if n == 1:
            note = 'O3 devirtualizes the one-entry function table; baseline only.'
        else:
            need('indirect_call', r'\bcall\b[^@\n]*%[\w.]+\(')
            need('table_index', r'getelementptr inbounds .*@table')
    elif i == '07_callback':
        need('callback_fields', r'load volatile ptr, ptr %', 2)
        need('indirect_call', r'\bcall\b[^@\n]*%[\w.]+\(')
        if v == 'sentinel':
            need('sentinel_guard', r'icmp (?:eq|ne) ptr .*inttoptr \(i64 -1')
    elif i == '08_variadic':
        need('variadic_wrappers', r'call .*@llvm.va_start', n if v == 'printf' else 1)
        if v == 'config':
            need('methods_copy', r'call .*@llvm.memcpy')
            need('indirect_call', r'\bcall\b[^@\n]*%[\w.]+\(')
        else:
            need('byte_traversal', r'getelementptr inbounds i8, ptr %')
    elif i == '09_copy':
        op = v.split('_')[0]
        need('copy_operation', rf'call .*@llvm\.{op}.*', n)
        calls = re.findall(r'call .*@llvm\.'+op+r'.*', s)
        checks['length_kind'] = all(bool(re.search(r', i64 \d+, i1 false', x)) == v.endswith('const') for x in calls)
    elif i == '10_casts':
        need('pointer_to_integer', r'\bptrtoint\b')
        need('integer_to_pointer' if v == 'cast' else 'pointer_difference',
             r'\binttoptr\b' if v == 'cast' else r'\bsub i64\b')
    elif i == '11_linkage':
        need('pointer_parameters', r'^define (?:internal|dso_local) .*@access\d+\(ptr ', n)
        checks['linkage'] = len(re.findall(r'^define internal .*@access\d+', s, re.M)) == (n if v == 'static' else 0)
    elif i == '12_strings':
        if n > 1:
            need('string_table', r'^@names =')
        need('byte_load', r'load i8, ptr ')
    evidence = [line for line in s.splitlines() if re.search(
        r'^define |^@(?:names|table|g\d+) =|\balloca\b|\bphi\b|load volatile ptr|'
        r'\binttoptr\b|\bptrtoint\b|\bsub i64\b|icmp.*inttoptr|'
        r'call .*@(?:llvm\.mem|llvm\.va_start|malloc|my_alloc)|\bcall\b[^@]*%[\w.]+\(', line)]
    (d/'ir-evidence.txt').write_text('\n'.join(evidence)+'\n')
    result = {'checks': checks, 'survives': all(checks.values()), 'note': note}
    (d/'ir-check.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    failed = []
    for p in sorted(Path(sys.argv[1]).glob('*/*/result.json')):
        result = check(p.parent)
        if not result['survives']:
            failed.append((str(p.parent), result))
    print(json.dumps({'failures': failed}, indent=2))
    sys.exit(bool(failed))
