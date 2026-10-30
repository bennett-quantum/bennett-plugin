#!/usr/bin/env python3
"""Reference PT9/PT10/PT12 and tier regressions, derived from §4–§6."""
import argparse,json,subprocess
from contracts import ROOT as R
CASES={
'byval':('''@seed = internal global i8 7
define internal i8 @copy(ptr byval(i8) %p) {
 store i8 9, ptr %p
 %v = load i8, ptr %p
 ret i8 %v
}
define i8 @top() {
 %r = call i8 @copy(ptr byval(i8) @seed)
 %v = load i8, ptr @seed
 ret i8 %v
}''', [('top','%v',{'INT(7)'}),('copy','%v',{'INT(7)','INT(9)'})]),
'packed':('''define i64 @top() {
 %v = bitcast <2 x i32> <i32 1, i32 2> to i64
 ret i64 %v
}''',[('top','%v',{'INT(8589934593)'})]),
'atomic':('''@cell = internal global i8 -16
define i8 @top() {
 %old = atomicrmw nand ptr @cell, i8 -52 seq_cst
 %new = load i8, ptr @cell
 ret i8 %new
}''',[('top','%old',{'INT(240)','INT(63)','INT(243)'}),('top','%new',{'INT(240)','INT(63)','INT(243)'})]),
'host-tiers':('''define internal i8 @leaf(i8 %n) { ret i8 %n }
define i8 @top(i8 %n) { %r = call i8 @leaf(i8 %n)
 ret i8 %r }''',[]),
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();results=[]
 for name,(body,wants) in CASES.items():
  dest=R/f'.tmp/analysis-edges/{a.major}/{name}';dest.mkdir(parents=True,exist_ok=True);src=dest/'in.ll';src.write_text('target datalayout = "e-p:64:64"\n'+body+'\n');report=dest/'report.json'
  x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.7','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(src)],capture_output=True,text=True)
  ok=x.returncode==0;data=json.loads(report.read_text()) if ok else {}
  for fn,val,atoms in wants:ok=ok and any(v['function']==fn and v['value']==val and set(v['atoms'])==atoms and not v['top'] for v in data.get('values',[]))
  if name=='host-tiers':ok=ok and all(f['tiers']==['H'] for f in data.get('functions',[]))
  results.append({'case':name,'ok':ok,'diagnostic':x.stderr.strip() if x.returncode else ''})
 result={'major':a.major,'cases':len(results),'passed':sum(r['ok'] for r in results),'results':results};(R/f'.tmp/analysis-edges-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return any(not r['ok'] for r in results)
if __name__=='__main__':raise SystemExit(main())
