#!/usr/bin/env python3
"""Independent plugin validator against accepted §12.4 boundary fixtures."""
import argparse, json, re, subprocess
from contracts import ROOT as R, dialect_text
p=argparse.ArgumentParser(); p.add_argument('--major', type=int, required=True); a=p.parse_args()
cases=[(n,v,b) for n,v,b in re.findall(r'```llvm example=(validator-\S+) verdict=(\S+) mode=validate[^\n]*\n(.*?)```',dialect_text(),re.S)]
cases += [('validator-v1-clean','accept','define i8 @f(i8 %x) { %r = add i8 %x, 1\n ret i8 %r }'),
          ('validator-v1-residue','reject:BD-E-RESIDUAL','define i8 @f(i8 %x) { %r = add nsw i8 %x, 1\n ret i8 %r }')]
# Adversarial boundaries beyond the published pairs: inspect nested constants,
# shared data, call-site attributes, guards and carrier-only signatures.
cases += [
 ('validator-v1-exact','reject:BD-E-RESIDUAL','define i8 @f(i8 %x) { %r = lshr exact i8 %x, 1\n ret i8 %r }'),
 ('validator-v1-fast','reject:BD-E-RESIDUAL','define float @f(float %x) { %r = fneg nnan float %x\n ret float %r }'),
 ('validator-v3-call','reject:BD-E-RESIDUAL','define ptr @g(ptr %p) { ret ptr %p }\ndefine ptr @f(ptr %p) { %r = call ptr @g(ptr nonnull %p)\n ret ptr %r }'),
 ('validator-v5-global','reject:BD-E-RESIDUAL','@g = internal global {i8, i8} {i8 0, i8 poison}\ndefine ptr @f() { ret ptr @g }'),
 ('validator-v5-unreferenced-clean','accept','@g = internal global i8 poison\ndefine i8 @f() { ret i8 0 }'),
 ('validator-v7-wrong-width','reject:BD-E-RESIDUAL','define i8 @f(i8 %x, i8 %s) { %c = icmp uge i8 %s, 7\n %v = shl i8 %x, %s\n %r = select i1 %c, i8 0, i8 %v\n ret i8 %r }'),
 ('validator-v7-extra-use','reject:BD-E-RESIDUAL','define i8 @f(i8 %x, i8 %s) { %c = icmp uge i8 %s, 8\n %v = shl i8 %x, %s\n %r = select i1 %c, i8 0, i8 %v\n %z = add i8 %v, %r\n ret i8 %z }'),
 ('validator-v12-primitive-clean','accept','declare ptr @__bennett_nz_alloc(i64)\ndeclare void @__bennett_nz_free(ptr)\ndefine void @f() { %p = call ptr @__bennett_nz_alloc(i64 1)\n call void @__bennett_nz_free(ptr %p)\n ret void }'),
 ('validator-v12-runtime-name','reject:BD-E-RESIDUAL','declare i8 @__bennett_rt_missing()\ndefine i8 @f() { %r = call i8 @__bennett_rt_missing()\n ret i8 %r }'),
 ('validator-v13-signature','reject:BD-E-RESIDUAL','define <2 x i8> @f(<2 x i8> %x) { ret <2 x i8> %x }'),
 ('validator-v14-nested','reject:BD-E-RESIDUAL','define {i129} @f({i129} %x) { ret {i129} %x }'),
 ('validator-v16-target','reject:BD-E-RESIDUAL','declare i64 @llvm.x86.rdtsc()\ndefine i64 @f() { %r = call i64 @llvm.x86.rdtsc()\n ret i64 %r }'),
]
rows=[]
for name,verdict,body in cases:
 d=R/f'.tmp/validation/{a.major}/{name}';d.mkdir(parents=True,exist_ok=True);src=d/'in.ll';src.write_text(body)
 x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.13','-bennett-validate-only','-disable-output',str(src)],capture_output=True,text=True)
 rule=re.search(r'validator-(v[0-9]+)',name)[1].upper()
 ok=(x.returncode==0) if verdict=='accept' else x.returncode!=0 and 'BD-E-RESIDUAL' in x.stderr and rule in x.stderr
 rows.append(dict(case=name,rule=rule,ok=ok,diagnostic=x.stderr if not ok else ''))
# Exercise the production L path, including an unrelated H alloca. The reader
# must run after materialisation and inspect the emitted closure only.
d=R/f'.tmp/validation/{a.major}/automatic-l';d.mkdir(parents=True,exist_ok=True)
src=d/'in.ll';src.write_text('define internal i8 @entry(i8 %x) { %r = add nsw i8 %x, 1\n ret i8 %r }\ndefine i8 @host(i8 %x) { %p = alloca i8\n store i8 %x, ptr %p\n %r = load i8, ptr %p\n ret i8 %r }\n')
x=subprocess.run([f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.13','-bennett-oracle=entry','-bennett-scalar-shape=IN(8,zext);tgt=8','-bennett-out='+str(d),'-disable-output',str(src)],capture_output=True,text=True)
rows.append(dict(case='automatic-L-materialised-closure',rule='S7',ok=x.returncode==0 and 'residual validator accepted L closure' in x.stderr,diagnostic=x.stderr if x.returncode else ''))
# CC may retain a host call; L/R may not. This is the actual reader mode,
# independently of the normaliser and without runtime-name exemptions.
for classical in (False,True):
 src=d/'external.ll';src.write_text('declare i8 @external()\ndefine i8 @f() { %r = call i8 @external()\n ret i8 %r }')
 cmd=[f'/usr/lib/llvm-{a.major}/bin/opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.13','-bennett-validate-only','-disable-output',str(src)]
 if classical:cmd.append('-bennett-validate-classical')
 x=subprocess.run(cmd,capture_output=True,text=True)
 rows.append(dict(case='V12-'+('CC' if classical else 'LR')+'-hostcall',rule='V12',ok=x.returncode==0 if classical else x.returncode!=0 and 'V12' in x.stderr,diagnostic=x.stderr if classical and x.returncode else ''))
j=dict(major=a.major,cases=len(rows),passed=sum(r['ok'] for r in rows),results=rows)
(R/f'.tmp/validation-{a.major}.json').write_text(json.dumps(j,indent=2)+'\n');print(json.dumps(j,indent=2));raise SystemExit(j['passed']!=j['cases'])
