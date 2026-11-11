#!/usr/bin/env python3
"""ISA0.9 CC launches bind quantum references, data, budgets and records."""

import argparse,json,re,hashlib
from contracts import ROOT,run,sibling,plugin_command,dialect_blob


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--major',type=int,required=True);args=parser.parse_args()
    root=ROOT/f'.tmp/quantum-r-production/{args.major}';root.mkdir(parents=True,exist_ok=True)
    (root/'bennett_markers.h').write_text(dialect_blob('spec/bennett_markers.h'))
    (root/'input.c').write_text('''#include "bennett_markers.h"
unsigned char inc8(unsigned char x) {return (unsigned char)(x+1);}
unsigned top(unsigned char value) {
 void*x=__bennett_qalloc(0,8),*t=__bennett_qalloc(0,8),*f=__bennett_qalloc(0,4);
 struct D {struct {unsigned version,nparam,ndev,flags;void*tgt,*fault;}h;
 struct {unsigned kind,mode;void*q;unsigned long long value,size;}p[1];}d={{2,1,0,0,t,f},{{1,0,x,0,0}}};
 __bennett_qprep(x,&value,1);
 __bennett_oracle((void*)inc8,0,(const bennett_oracle_desc*)&d);
 unsigned r=0; MEASURE
 __bennett_oracle((void*)inc8,0,(const bennett_oracle_desc*)&d);
 __bennett_qprep(x,&value,1);
 __bennett_qfree(f);__bennett_qfree(t);__bennett_qfree(x);return r;
}
'''.replace('MEASURE','\n'.join(f'r|=(unsigned)__bennett_measure(t,{j})<<{j};'for j in range(8))))
    ll=root/'input.ll';z=run([f'/usr/lib/llvm-{args.major}/bin/clang','-O1','-S','-emit-llvm',root/'input.c','-o',ll]);assert z.returncode==0,z.stderr
    command=[v for v in plugin_command(args.major)if not v.startswith('-bennett-dialect=')]+['-bennett-dialect=0.3-r1','-bennett-isa=0.9']
    z=run([*command,'-bennett-scalar-stack=7','-bennett-budget-default=5,0,7,1,0','-bennett-out='+str(root/'out'),'-disable-output',ll])
    report={'major':args.major,'lower_exit':z.returncode,'diagnostic':z.stderr,'runs':[]}
    if z.returncode==0:
        obj=root/'out/top/launch.bennett';ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
        check=run([ref,'check',obj]);report['check']=check.returncode==0;report['check_output']=check.stdout+check.stderr
        if report['check']:
            hashes=json.loads(check.stdout);build=json.loads((root/'out/top/build.json').read_text());cert=json.loads((root/'out/top/certificate.json').read_text())
            report['bindings']=(build['object_hash']==hashes['object_hash']==cert['bindings']['object_hash'] and cert['bindings']['dialect_mapping_version']=='0.3' and build['dialect_version']=='0.3-r1' and build['isa_version']=='0.9' and cert['producer']['version'].endswith(hashlib.sha256((root/'out/top/build.json').read_bytes().rstrip(b'\n')).hexdigest()))
            layout=json.loads(obj.read_text().split('\n\nsection layout\n')[1].splitlines()[0]);budgets=build['budgets']
            for value in (0,7,255):
                command=[ref,'run-program',obj,'top','--arg',str(value),'--budget',f'1000000,{layout["heap_limit_max"]},{1<<layout["S_cells"]},16','--token-aliases',json.dumps(list(range(len(budgets))))]
                for b in budgets:command+=['--arg','token:'+','.join(str(b[k])for k in ('steps','heap','stack','depth'))]
                z=run(command);result=json.loads(z.stdout)if z.returncode==0 else {}
                report['runs'].append({'input':value,'exit':z.returncode,'result':result,'diagnostic':z.stderr,'ok':result.get('status')=='COMPLETED' and result.get('run_state')=='CLOSED' and result.get('results')==[{'type':'i32','value':str((value+1)&255)}]})
        report['ok']=report.get('check') and report.get('bindings') and all(r['ok']for r in report['runs'])
    (root/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));return not report.get('ok')


if __name__=='__main__':
    raise SystemExit(main())
