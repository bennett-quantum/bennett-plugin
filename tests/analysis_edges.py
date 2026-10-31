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
# Geometry and Cartesian products: independent hand-derived PT3/N21 domains.
'subbyte':('''define i6 @top() {
 %v = bitcast <2 x i3> <i3 1, i3 3> to i6
 ret i6 %v
}''',[('top','%v',{'INT(25)'})]),
'subbyte-big':('''define i6 @top() {
 %v = bitcast <2 x i3> <i3 1, i3 3> to i6
 ret i6 %v
}''',[('top','%v',{'INT(11)'})]),
'constant-pack':('''define i16 @top() {
 %v = add i16 bitcast (<2 x i8> <i8 1, i8 1> to i16), 1
 ret i16 %v
}''',[('top','%v',{'INT(258)'})]),
'cartesian':('''define i16 @top(i1 %c) {
 %a = select i1 %c, i8 1, i8 2
 %v0 = insertelement <2 x i8> zeroinitializer, i8 %a, i32 0
 %v1 = insertelement <2 x i8> %v0, i8 %a, i32 1
 %v = bitcast <2 x i8> %v1 to i16
 ret i16 %v
}''',[('top','%v',{'INT(257)','INT(258)','INT(513)','INT(514)'})]),
# Accepted 0.2.10 N9: PT3 unions BOTH select value operands, even with a
# constant-false condition. Do not import 0.2.11's refined cmpxchg domains.
'cmpxchg-success':('''@cell = internal global i8 1
define i8 @top() {
 %pair = cmpxchg ptr @cell, i8 1, i8 3 seq_cst seq_cst
 %old = extractvalue {i8,i1} %pair, 0
 %flag = extractvalue {i8,i1} %pair, 1
 %new = load i8, ptr @cell
 ret i8 %new
}''',[('top','%old',{'INT(1)','INT(3)'}),('top','%flag',{'INT(0)','INT(1)'}),('top','%new',{'INT(1)','INT(3)'})]),
'cmpxchg-failure':('''@cell = internal global i8 1
define i8 @top() {
 %pair = cmpxchg ptr @cell, i8 9, i8 3 seq_cst seq_cst
 %old = extractvalue {i8,i1} %pair, 0
 %flag = extractvalue {i8,i1} %pair, 1
 %new = load i8, ptr @cell
 ret i8 %new
}''',[('top','%old',{'INT(1)','INT(3)'}),('top','%flag',{'INT(0)'}),('top','%new',{'INT(1)','INT(3)'})]),
# A symbolic zero initial image has no arbitrary numerical cut-off.
'zero-symbolic-large':('''declare ptr @malloc(i64)
define i8 @top(i64 %n) {
 %p = call ptr @malloc(i64 %n)
 %q = getelementptr i8, ptr %p, i64 1152921504606846976
 %v = load i8, ptr %q
 ret i8 %v
}''',[('top','%v',{'INT(0)'})]),
'fixed-vscale-pack':('''define i16 @top() {
 %a = insertelement <vscale x 2 x i8> zeroinitializer, i8 1, i32 1
 %v = bitcast <vscale x 2 x i8> %a to <vscale x 1 x i16>
 %n = extractelement <vscale x 1 x i16> %v, i32 0
 ret i16 %n
}''',[('top','%n',{'INT(256)'})]),
'host-tiers':('''define internal i8 @leaf(i8 %n) { ret i8 %n }
define i8 @top(i8 %n) { %r = call i8 @leaf(i8 %n)
 ret i8 %r }''',[]),
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();results=[]
 for name,(body,wants) in CASES.items():
  dest=R/f'.tmp/analysis-edges/{a.major}/{name}';dest.mkdir(parents=True,exist_ok=True);src=dest/'in.ll';src.write_text(('target datalayout = "E-p:64:64"\n' if name=='subbyte-big' else 'target datalayout = "e-p:64:64"\n')+body+'\n');report=dest/'report.json'
  x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-analysis-only','-bennett-report='+str(report),'-disable-output',str(src)],capture_output=True,text=True)
  ok=x.returncode==0;data=json.loads(report.read_text()) if ok else {}
  for fn,val,atoms in wants:ok=ok and any(v['function']==fn and v['value']==val and set(v['atoms'])==atoms and not v['top'] for v in data.get('values',[]))
  if name=='host-tiers':ok=ok and all(f['tiers']==['H'] for f in data.get('functions',[]))
  results.append({'case':name,'ok':ok,'diagnostic':x.stderr.strip() if x.returncode else ''})
 result={'major':a.major,'cases':len(results),'passed':sum(r['ok'] for r in results),'results':results};(R/f'.tmp/analysis-edges-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return any(not r['ok'] for r in results)
if __name__=='__main__':raise SystemExit(main())
