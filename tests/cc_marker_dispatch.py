#!/usr/bin/env python3
"""Replay unchanged driver inputs through reversible call/marker dispatch."""

import argparse,hashlib,json
from pathlib import Path
from contracts import ROOT,run,sibling


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
    report={'major':args.major,'module_sha256':manifest['sha256'][str(args.major)],
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
