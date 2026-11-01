#!/usr/bin/env python3
"""Published allocator closure in CC: exact byte operations, history and faults."""
import argparse, hashlib, json, shutil, subprocess, tomllib
from pathlib import Path
from contracts import ROOT as R, SIBLINGS
from production import REF as DEBUG_REF
REF = DEBUG_REF.parent.parent / 'release/bennett-isa-ref'
RUNTIME_SHA = {18:'5eff8d60621e2f999ab32508845ef8585ed6298e048466e2025f4b6f390d1e88',23:'5c630b9b0e60e9d7aba6777885809c7e5194d4226c4bb5e8bee9df26b1f0bf8b'}
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--major',type=int,required=True);a=ap.parse_args()
    tool=f'/usr/lib/llvm-{a.major}/bin/';plugin=R/f'build/libbennett-plugin-{a.major}.so'
    runtime=SIBLINGS/f'bennett-runtimes/dist/llvm{a.major}/bennett-runtimes.bc'
    assert sha(runtime)==RUNTIME_SHA[a.major]
    # Use the same SHA-pinned arith publication as the rest of the gate.
    pin=tomllib.loads((R/'SPEC_VERSIONS.toml').read_text())['arith']
    arith=Path(pin[f'llvm{a.major}_path'])
    assert sha(arith)==pin[f'llvm{a.major}_sha256']
    rows=[]
    def run(args):
        z=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=120)
        assert z.returncode==0,(args,z.stdout,z.stderr)
        return z
    for name,vectors in [('allocator-closure',[(1,175),(3,175),(7,175),(32,175),(64,'heapfault')]),('allocator-overflow',[(3,7),((1<<64)-1,'hostfault')]),('allocator-invalid',[(0,'fault'),(1,'fault')]),('allocator-bounds',[(0,'fault'),(1,'fault')])]:
        d=R/f'.tmp/allocator-closure/{a.major}/{name}';shutil.rmtree(d,ignore_errors=True);d.mkdir(parents=True)
        run([tool+'llvm-link',R/f'tests/probes/{name}.ll',runtime,arith,'--only-needed','-o',d/'linked.bc'])
        run([tool+'opt','-passes=lto<O3>',d/'linked.bc','-o',d/'postlink.bc'])
        base=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett','-bennett-dialect=0.2.10',d/'postlink.bc']
        run([*base,'-bennett-analysis-only','-bennett-report='+str(d/'recognised.json'),'-disable-output'])
        run([*base,'-bennett-normalise-only','-o',d/'normalised.bc'])
        run([tool+'opt','-passes=verify',d/'normalised.bc','-disable-output'])
        run([*base,'-bennett-budget-default=100000,128,4096,32,0','-bennett-scalar-stack=4096','-bennett-out='+str(d/'out'),'-disable-output'])
        for file in ['device.bc','host.bc']:run([tool+'opt','-passes=verify',d/'out'/file,'-disable-output'])
        obj=d/'out/top/launch.bennett';run([DEBUG_REF,'check',obj]);run([DEBUG_REF,'hash',obj])
        body=obj.read_text();assert ' = alloc ' in body and 'free ' in body
        executions=[]
        for n,expected in vectors:
            args=[REF,'run-program',obj,'top','--args',str(n),'--budget','100000,128,4096,32']
            if isinstance(expected,int):
                data=json.loads(run([*args,'--reverse']).stdout)
                assert data['status']=='REVERSED' and data['results']==[dict(type='i64',value=str(expected))],data
                assert data['equals_entry'] and data['memory_equals_entry'] and data['first_difference'] is None,data
                assert data['memory_digest']==data['entry_memory_digest'],data
            elif expected in ('fault','heapfault'):
                data=json.loads(run(args).stdout)
                assert data['status']=='FAILED' and data['faults'][0]['code']==(2 if expected=='heapfault' else 7),data
            else:
                # §11.5 requires the code-2 request before the terminal trap.
                replies=d/'replies.json';replies.write_text(json.dumps([dict(service='bennett.fault',payload='0200000000000000',reply='')]))
                data=json.loads(run([*args,'--replies',replies]).stdout)
                assert data['status']=='FAILED' and data['host_requests'][0]['service']=='bennett.fault',data
                assert data['host_requests'][0]['payload']=='0200000000000000',data
            executions.append(dict(input=n,expected=expected,result=data))
        rows.append(dict(case=name,ok=True,runtime_sha256=sha(runtime),arith_sha256=sha(arith),recognised_sha256=sha(d/'recognised.json'),normalised_sha256=sha(d/'normalised.bc'),materialised_sha256=sha(d/'out/device.bc'),materialised_verified=True,object_sha256=sha(obj),runs=executions))
    result=dict(major=a.major,cases=len(rows),passed=len(rows),results=rows)
    (R/f'.tmp/allocator-closure-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
