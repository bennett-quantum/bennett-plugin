#!/usr/bin/env python3
"""Qprep is XOR, validates memory before mutation, and has compact large output."""

import argparse
import json
from pathlib import Path
from contracts import ROOT, dialect_blob, plugin_command, run, sibling


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--major',type=int,required=True)
    parser.add_argument('--large',action='store_true')
    args=parser.parse_args()
    root=ROOT/f'.tmp/production-qprep/{args.major}'
    root.mkdir(parents=True,exist_ok=True)
    (root/'bennett_markers.h').write_text(dialect_blob('spec/bennett_markers.h'))
    ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
    report=[]
    for size in ((16,32,2**25) if args.large else (1,2,16,32)):
        directory=root/str(size);directory.mkdir(exist_ok=True)
        width=size*8
        src=directory/'input.c';ll=directory/'input.ll'
        src.write_text('''#include "../bennett_markers.h"
static unsigned char bytes[SIZE] = { INITIAL };
unsigned top(unsigned long long n, unsigned long long bad) {
 void *q=__bennett_qalloc(0,WIDTH);
 __bennett_gate(1,q,0);
 const void *p=bad ? (const void *)(uintptr_t)bad : bytes;
 __bennett_qprep(q,p,n);
 unsigned r=0;
 MEASURE
 __bennett_qprep(q,p,n);
 __bennett_gate(1,q,0);
 __bennett_qfree(q);
 return r;
}
'''.replace('SIZE',str(size)).replace('WIDTH',str(width)).replace('INITIAL','173' if size==1 else f'[0]=173, [{size-1}]=91').replace('MEASURE','\n'.join(f'r|=(unsigned)__bennett_measure(q,{j})<<{j};'for j in range(8)) + ('' if size==1 else '\n'+'\n'.join(f'r|=(unsigned)__bennett_measure(q,{width-8+j})<<{8+j};'for j in range(8)))))
        z=run([f'/usr/lib/llvm-{args.major}/bin/clang','-O1','-S','-emit-llvm',src,'-o',ll])
        assert z.returncode==0,z.stderr
        z=run([*plugin_command(args.major),'-bennett-out='+str(directory/'out'),'-disable-output',ll],timeout=600)
        row={'bytes':size,'lower_exit':z.returncode,'diagnostic':z.stderr,'runs':[]};report.append(row)
        if z.returncode:continue
        obj=directory/'out/top/launch.bennett';check=run([ref,'check',obj],timeout=600)
        row['object_bytes']=obj.stat().st_size;row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
        # Data image costs two hex digits/byte; executable code stays bounded.
        text=obj.read_text();functions=text.split('\n\nsection functions\n')[1].split('\n\nsection ')[0]
        row['function_bytes']=len(functions);row['compact']=len(functions)<40000
        if not row['check']:continue
        if size<=32:
            build=json.loads((directory/'out/top/build.json').read_text());tokens=len(build['budgets'])
            for n,bad,want,code in [(0,0,1,None),(1,0,172,None),(size,0,172 if size==1 else 172|(91<<8),None),
                                    (size+1,0,None,4),(1,1,None,7),(0,1,1,None)]+([]if size==1 else[(2,2**64-1,None,7)]):
                values=[n,bad]+[4]*tokens
                z=run([ref,'run-program',obj,'top','--args',','.join(map(str,values)),'--budget','1000000,0,0,0'])
                value=json.loads(z.stdout)if z.returncode==0 else {}
                ok=(value.get('status')=='COMPLETED' and value.get('results')==[{'type':'i32','value':str(want)}])if code is None else value.get('status')=='FAILED' and any(int(f['code'])==code for f in value.get('faults',[]))
                row['runs'].append({'n':n,'bad':bad,'exit':z.returncode,'result':value,'diagnostic':z.stderr,'ok':ok})
        row['ok']=row['check'] and row['compact'] and all(r['ok']for r in row['runs'])
    result={'major':args.major,'cases':report,'passed':sum(c.get('ok',False)for c in report)}
    (root/('large-report.json'if args.large else'report.json')).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return result['passed']!=len(report)


if __name__=='__main__':
    raise SystemExit(main())
