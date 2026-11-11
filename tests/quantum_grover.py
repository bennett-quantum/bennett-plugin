#!/usr/bin/env python3
"""The unchanged published library + Grover TU produce on both ISA profiles."""

import argparse,json,re
from contracts import ROOT,run,sibling,plugin_command,dialect_blob,dialect_text


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--major',type=int,required=True);args=parser.parse_args()
    root=ROOT/f'.tmp/quantum-grover/{args.major}';root.mkdir(parents=True,exist_ok=True)
    spec=dialect_text();tool=f'/usr/lib/llvm-{args.major}/bin/'
    (root/'bennett_markers.h').write_text(dialect_blob('spec/bennett_markers.h'))
    for name,fixture in [('db','rung4-minidb'),('tu','rung4-grover-tu')]:
        source=re.search(r'```c example='+fixture+r'[^\n]*\n(.*?)```',spec,re.S)[1]
        (root/(name+'.c')).write_text(source)
        z=run([tool+'clang','-O2','-flto','-emit-llvm','-c',root/(name+'.c'),'-o',root/(name+'.bc')]);assert z.returncode==0,z.stderr
    z=run([tool+'llvm-link',root/'db.bc',root/'tu.bc','-o',root/'linked.bc']);assert z.returncode==0,z.stderr
    z=run([tool+'opt','-passes=lto<O3>','-S',root/'linked.bc','-o',root/'post.ll']);assert z.returncode==0,z.stderr
    ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref';rows=[]
    for profile in ('legacy','r'):
        command=plugin_command(args.major)
        if profile=='r':command=[v for v in command if not v.startswith('-bennett-dialect=')]+['-bennett-dialect=0.3-r1','-bennett-isa=0.9']
        output=root/profile
        z=run([*command,'-bennett-budget-default=400,0,512,8,0','-bennett-out='+str(output),'-disable-output',root/'post.ll'],timeout=600)
        row={'profile':profile,'lower_exit':z.returncode,'diagnostic':z.stderr};rows.append(row)
        if z.returncode:continue
        obj=output/'grover_once/launch.bennett';check=run([ref,'check',obj],timeout=600)
        row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
        materialised=run([tool+'opt','-passes=verify','-disable-output',output/'host.bc'])
        row['host_verified']=materialised.returncode==0;row['host_output']=materialised.stderr
        row['ok']=row['check']and row['host_verified']
    result={'major':args.major,'cases':rows,'passed':sum(r.get('ok',False)for r in rows)}
    (root/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result['passed']!=len(rows)


if __name__=='__main__':raise SystemExit(main())
