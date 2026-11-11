#!/usr/bin/env python3
"""ISA0.9 quantum reference migration; independent admission and execution."""

import argparse,json,re,hashlib,shutil
from contracts import ROOT,run,sibling,plugin_command,dialect_text,PIN


def mini_case(spec):
    source=re.search(r"```llvm lift=rung4-mini[^\n]*\n(.*?)```",spec,re.S)[1]
    if "declare void @__bennett_nz_fault" not in source:
        source+="\ndeclare void @__bennett_nz_fault(i64)\n"
    linkmap=re.search(r"```text linkmap=rung4-mini\n(.*?)```",spec,re.S)[1]
    for index,(name,address) in enumerate(re.findall(r"function @([^ ]+) A=0x([a-fA-F0-9]+)",linkmap)):
        source=re.sub(r"(define [^\n]*@"+re.escape(name)+r"\([^\n]*?\)) \{",r"\1 !bennett.address !"+str(900+index)+" {",source)
        source+="\n!"+str(900+index)+" = !{i64 "+str(int(address,16))+"}\n"
    runs=re.search(r"```text run=rung4-mini\n(.*?)```",spec,re.S)[1]
    vectors=[]
    for line in runs.splitlines():
        match=re.search(r"budget=([^ ]+) -> code=(\d+) payload=(\d+) steps=(\d+)",line)
        if not match:continue
        budget,code,payload,steps=match.groups();options=['--budget',budget]
        for value in re.findall(r"arg=([^ ]+)",line):options+=['--arg',value]
        for value in re.findall(r"mem=([^ ]+)",line):options+=['--mem',value.replace(':','=',1)]
        vectors.append((re.search(r"input=([^ ]*)",line)[1],options,int(payload),int(code),int(steps)))
    return ('rung4-mini',source,'MEM_IN(16),ARG(64),IN(3,zext);tgt=1',vectors)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--major',type=int,required=True);parser.add_argument('--publish-mini',action='store_true');args=parser.parse_args()
    root=ROOT/f'.tmp/quantum-r-references/{args.major}';root.mkdir(parents=True,exist_ok=True)
    ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
    command=[v for v in plugin_command(args.major)if not v.startswith('-bennett-dialect=')]+['-bennett-dialect=0.3-r1','-bennett-isa=0.9']
    cases=[('inc8','''define i8 @f(i8 %x) {
 %v=add i8 %x,1
 ret i8 %v
}
''','IN(8,zext);tgt=8',[(str(x),[],(x+1)&255)for x in range(256)]),
('recursive','''define i8 @f(i8 %n) {
 %zero=icmp eq i8 %n,0
 br i1 %zero,label %done,label %step
step:
 %p=sub i8 %n,1
 %v=call i8 @f(i8 %p)
 %r=add i8 %v,%n
 ret i8 %r
done:
 ret i8 0
}
''','IN(8,zext);tgt=8',[(str(x),[],x*(x+1)//2)for x in range(8)]),
('memory','''@bytes=global [4 x i8] c"\\01\\02\\03\\04"
define i8 @f(ptr %p,i8 %x) {
 %i=and i8 %x,15
 %j=zext i8 %i to i64
 %q=getelementptr i8,ptr %p,i64 %j
 %v=load i8,ptr %q
 %g=load i8,ptr @bytes
 %r=add i8 %v,%g
 ret i8 %r
}
''','MEM_IN(16),IN(8,zext);tgt=8',[(str(x),['--mem','m0='+bytes(range(16)).hex()],(x&15)+1)for x in range(32)])]
    spec=dialect_text();cases.append(mini_case(spec))
    report=[]
    for name,source,shape,vectors in cases:
        directory=root/name;directory.mkdir(exist_ok=True);ll=directory/'input.ll';ll.write_text(source)
        z=run([*command,'-bennett-oracle='+('q'if name=='rung4-mini'else'f'),'-bennett-scalar-shape='+shape,'-bennett-scalar-stack='+('1024'if name=='rung4-mini'else'256'),'-bennett-out='+str(directory/'out'),'-disable-output',ll])
        row={'case':name,'lower_exit':z.returncode,'diagnostic':z.stderr,'runs':[]};report.append(row)
        if z.returncode:continue
        obj=directory/'out/ref.bennett';check=run([ref,'check',obj]);row['check']=check.returncode==0;row['check_output']=check.stdout+check.stderr
        if not row['check']:continue
        for vector in vectors:
            value,options,want,*outcome=vector
            expected_code=outcome[0]if outcome else 0
            expected_steps=outcome[1]if outcome else None
            budget=[]if '--budget'in options else ['--budget','1000,0,256,16']
            z=run([ref,'run-oracle',obj,'ref','--input',value,*budget,*options])
            result=json.loads(z.stdout)if z.returncode==0 else {}
            row['runs'].append({'input':value,'exit':z.returncode,'result':result,'diagnostic':z.stderr,'ok':result.get('code')==expected_code and int(result.get('payload',-1))==want and (expected_steps is None or result.get('steps')==expected_steps)})
        row['ok']=row['check'] and all(r['ok']for r in row['runs'])
        if name=='rung4-mini' and row['ok']:
            artifacts=ROOT/'tests/fixtures/rung4-mini'
            old=re.search(r'```isa object=rung4-mini\n(.*?)```',spec,re.S)[1].encode()
            assert hashlib.sha256(old).hexdigest()=='742ccbaf23ca1b89c93e8fa6e3e6953df99748d45d6ef01cfc9f91f1a89726a8'
            if args.publish_mini:
                artifacts.mkdir(parents=True,exist_ok=True)
                (artifacts/'rung4-mini-0.8.bennett').write_bytes(old)
                (artifacts/'rung4-mini-0.9.bennett').write_bytes(obj.read_bytes())
                manifest={'scope':'Reduced-control diagnostic; does not satisfy full SQLite acceptance or clause (c).','source':{'repo':'bennett-dialect-spec','commit':PIN,'lift':'rung4-mini','linkmap':'rung4-mini'},'producer':{'name':'bennett-plugin','llvm_major':args.major,'binary_sha256':hashlib.sha256((ROOT/f'build/libbennett-plugin-{args.major}.so').read_bytes()).hexdigest()},'objects':{'0.8':{'sha256':hashlib.sha256(old).hexdigest()},'0.9':{'sha256':hashlib.sha256(obj.read_bytes()).hexdigest(),'hashes':json.loads(check.stdout)}},'vectors_checked':len(vectors)}
                (artifacts/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
            row['published_bytes']=(artifacts/'rung4-mini-0.8.bennett').read_bytes()==old and (artifacts/'rung4-mini-0.9.bennett').read_bytes()==obj.read_bytes()
            row['ok']&=row['published_bytes']
    result={'major':args.major,'cases':report,'passed':sum(r.get('ok',False)for r in report)}
    (root/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return result['passed']!=len(report)


if __name__=='__main__':
    raise SystemExit(main())
