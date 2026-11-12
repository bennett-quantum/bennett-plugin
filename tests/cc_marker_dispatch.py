#!/usr/bin/env python3
"""Execute resolved classical calls and replay unchanged driver inputs."""

import argparse,hashlib,json
from pathlib import Path
from contracts import ROOT,run,sibling


def reduced_calls(major,plugin,directory):
    source=ROOT/'tests/probes/cc-resolved-calls.ll'
    tool=f'/usr/lib/llvm-{major}/bin/opt'
    verified=run([tool,'-passes=verify','-disable-output',source])
    assert verified.returncode==0,verified.stderr
    lowered=run([tool,'-load-pass-plugin='+str(plugin),'-passes=bennett',
                 '-bennett-dialect=0.3-r1','-bennett-isa=0.9',
                 '--bennett-tier=reversible','--bennett-entry=main',
                 '-bennett-out='+str(directory/'reduced'),'-disable-output',source])
    assert lowered.returncode==0,(lowered.returncode,lowered.stderr)
    obj=directory/'reduced/main/launch.bennett'
    ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
    checked=run([ref,'check',obj])
    assert checked.returncode==0,checked.stdout+checked.stderr
    replies=directory/'replies.json'
    replies.write_text(json.dumps([{'service':'bennett.argv','payload':'00'*20,'reply':'00'*20}]))
    executions=[]
    for reverse in (False,True):
        result=run([ref,'run-program',obj,'main','--budget','100000,131072,4096,32',
                    '--replies',replies,*(['--reverse'] if reverse else [])])
        assert result.returncode==0,result.stdout+result.stderr
        value=json.loads(result.stdout)
        assert value['results']==[{'type':'i32','value':'42'}] and not value['faults'],value
        assert value['status']==('REVERSED' if reverse else 'COMPLETED'),value
        if reverse:
            assert value['equals_entry'] and value['memory_equals_entry'],value
        executions.append(value)
    return executions


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--major',type=int,required=True)
    parser.add_argument('--plugin',type=Path)
    args=parser.parse_args()
    fixtures=ROOT/'tests/fixtures/driver-marker-probe'
    manifest=json.loads((fixtures/'provenance.json').read_text())
    source=fixtures/f'probe-{args.major}.bc'
    assert hashlib.sha256(source.read_bytes()).hexdigest()==manifest['sha256'][str(args.major)]
    directory=ROOT/f'.tmp/cc-marker-dispatch/{args.major}';directory.mkdir(parents=True,exist_ok=True)
    tool=f'/usr/lib/llvm-{args.major}/bin/'
    verified=run([tool+'opt','-passes=verify','-disable-output',source])
    assert verified.returncode==0,verified.stderr
    plugin=args.plugin or ROOT/f'build/libbennett-plugin-{args.major}.so'
    command=[tool+'opt','-load-pass-plugin='+str(plugin),'-passes=bennett',
             '-bennett-dialect=0.3-r1','-bennett-isa=0.9',
             '-bennett-out='+str(directory/'out'),'--bennett-tier=reversible',
             '--bennett-entry=main','-disable-output',str(source)]
    lowered=run(command,timeout=600)
    report={'major':args.major,'reduced_calls':reduced_calls(args.major,plugin,directory),
            'module_sha256':manifest['sha256'][str(args.major)],
            'module_verified':True,'lower_exit':lowered.returncode,'diagnostic':lowered.stderr}
    if lowered.returncode==0:
        obj=directory/'out/main/launch.bennett'
        assert obj.exists(),directory
        ref=sibling('bennett-isa-spec')/'reference-interpreter/target/release/bennett-isa-ref'
        checked=run([ref,'check',obj],timeout=600)
        report['reference_admission']=checked.returncode==0
        report['reference_output']=checked.stdout+checked.stderr
        # Read the actual publication: callbacks and cleanup remain in its
        # selected source closure; successful lowering cannot erase them.
        objects=json.loads((directory/'out/launches.json').read_text())
        report['published']=any(row.get('entry')=='main' and row.get('verdict')=='accept' for row in objects)
        report['ok']=report['reference_admission']and report['published']
    (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));return not report.get('ok')


if __name__=='__main__':raise SystemExit(main())
