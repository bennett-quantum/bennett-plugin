#!/usr/bin/env python3
"""§14.8/§16.4 CC switch: native differential and complete retained-history reversal."""
import argparse, hashlib, json, re, shutil, subprocess
from contracts import ROOT as R
from production import REF

CASES = {
    'dense': list(range(10)) + [-1, -(1<<63)],
    'sparse': [-1,1000,-(1<<63),0,123456789,5,-(1<<63)+1,1,999,1001,(1<<63)-1],
    'default': [0,7,-1,-(1<<63)],
    'loop': list(range(9)),
    'loaded': [0,42,-1,-(1<<63),-(1<<63)+1],
}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def check(major,case,inputs):
    tool=f'/usr/lib/llvm-{major}/bin/';plugin=R/f'build/libbennett-plugin-{major}.so'
    d=R/f'.tmp/cc-switch/{major}/{case}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
    def run(args):
        z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        assert z.returncode==0,(args,z.stdout,z.stderr)
        return z.stdout
    source=R/f'tests/probes/cc-switch-{case}.ll'
    # Independent native execution of the original IR. The clean, unused marker
    # pair has no classical effect; only this native driver supplies its stubs.
    driver=d/'driver.c'
    driver.write_text('#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n'
        'void *__bennett_qalloc(uint64_t c,uint64_t w){return 0;}\nvoid __bennett_qfree(void *p){}\n'
        'extern int64_t top(int64_t);\nint main(int c,char **v){printf("%lld\\n",(long long)top(strtoll(v[1],0,10)));}\n')
    run([tool+'clang','-O0',source,driver,'-o',d/'native'])
    base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10',source]
    run([*base,'-bennett-analysis-only','-bennett-report='+str(d/'recognised.json'),'-disable-output'])
    run([*base,'-bennett-budget-default=100000,128,4096,32,0','-bennett-out='+str(d/'out'),'-disable-output'])
    for f in ['device.bc','host.bc']:run([tool+'opt','-passes=verify',d/'out'/f,'-disable-output'])
    obj=d/'out/top/launch.bennett';run([REF,'check',obj]);run([REF,'hash',obj])
    body=obj.read_text()
    if case in ('dense','sparse'):
        # First split is the unsigned median, even for negative signed keys.
        median=3 if case=='dense' else 123456789
        assert re.search(r'= const.i64 '+str(median)+r'\n\w+ = icmp.ult a0 ',body),body
        assert body.count(' = icmp.eq ')==len(inputs)-(4 if case=='dense' else 4),body
    if case=='default':assert 'icmp.' not in body
    if case=='loaded':assert body.count(' = load.i64 ')==1
    executions=[]
    for n in inputs:
        expected=int(run([d/'native',n])) % (1<<64)
        data=json.loads(run([REF,'run-program',obj,'top','--args',str(n%(1<<64)),'--budget',('100000,0,4096,32' if case=='loaded' else '100000,0,0,0'),'--reverse']))
        assert data['status']=='REVERSED' and not data['faults'] and not data['host_requests'],data
        assert int(data['results'][0]['value'],0)==expected,data
        assert data['equals_entry'] and data['memory_equals_entry'] and data['first_difference'] is None,data
        assert data['memory_digest']==data['entry_memory_digest'],data
        executions.append(dict(input=n,expected=expected,result=data))
    return dict(case=case,ok=True,recognised_sha256=sha(d/'recognised.json'),materialised_sha256=sha(d/'out/device.bc'),materialised_verified=True,object_sha256=sha(obj),runs=executions)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--major',type=int,required=True);a=ap.parse_args()
    rows=[check(a.major,k,v) for k,v in CASES.items()]
    result=dict(major=a.major,cases=len(rows),passed=len(rows),results=rows)
    (R/f'.tmp/cc-switch-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
