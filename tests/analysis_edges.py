#!/usr/bin/env python3
"""Reference PT9/PT10/PT12 and tier regressions, derived from §4–§6."""
import argparse,json,subprocess
from contracts import ROOT as R
CASES={
# An additive cycle whose step is a finite set is the same orbit: past K it is top at once (bp-fj1).
'additive-set-step':('''define internal i32 @cycle(i1 %c) {
entry: br label %loop
loop:
 %n = phi i32 [ 0, %entry ], [ %copy, %loop ]
 %step = zext i1 %c to i32
 %sum = add i32 %n, %step
 %copy = select i1 %c, i32 %sum, i32 %n
 br label %loop
}
define i32 @top() {
 %r = call i32 @cycle(i1 true)
 ret i32 %r
}''',[]),
'additive-vector-lane':('''define internal <2 x i64> @cycle() {
entry: br label %loop
loop:
 %v = phi <2 x i64> [ zeroinitializer, %entry ], [ %next, %loop ]
 %next = add <2 x i64> %v, <i64 1, i64 2>
 br label %loop
}
define <2 x i64> @top() {
 %r = call <2 x i64> @cycle()
 ret <2 x i64> %r
}''',[]),
'additive-pointer-integer':('''@g = internal global [8 x i64] zeroinitializer
define internal i64 @cycle() {
entry:
 %base = ptrtoint ptr @g to i64
 br label %loop
loop:
 %n = phi i64 [ %base, %entry ], [ %sum, %loop ]
 %sum = add i64 %n, 1
 br label %loop
}
define i64 @top() {
 %r = call i64 @cycle()
 ret i64 %r
}''',[]),
# A set-valued step of zero is no cycle: the set stays exact.
'additive-zero-set-step':('''define internal i32 @cycle(i1 %c) {
entry: br label %loop
loop:
 %n = phi i32 [ 7, %entry ], [ %sum, %loop ]
 %step = select i1 %c, i32 0, i32 0
 %sum = add i32 %n, %step
 br label %loop
}
define i32 @top() {
 %r = call i32 @cycle(i1 true)
 ret i32 %r
}''',[('cycle','%n',{'INT(7)'})]),
# N23's value effect (§14.3): va_start points overflow_arg_area at the va block, whose slots hold
# the call's variadic arguments, so an inline va_arg's memory path reads them.
'vararg-values':('''%va = type { i32, i32, ptr, ptr }
declare void @llvm.va_start(ptr)
define internal i32 @sum(i32 %n, ...) {
 %ap = alloca %va
 call void @llvm.va_start(ptr %ap)
 %gp = load i32, ptr %ap
 %fpp = getelementptr i8, ptr %ap, i64 4
 %fp = load i32, ptr %fpp
 %ovp = getelementptr i8, ptr %ap, i64 8
 %ov = load ptr, ptr %ovp
 %v0 = load i32, ptr %ov
 %ov1 = getelementptr i8, ptr %ov, i64 8
 %v1 = load i64, ptr %ov1
 ret i32 %v0
}
define i32 @top() {
 %r = call i32 (i32, ...) @sum(i32 2, i32 20, i64 300)
 ret i32 %r
}''',[('sum','%gp',{'INT(0)','INT(48)'}),('sum','%fp',{'INT(0)','INT(176)'}),('sum','%v0',{'INT(20)'}),('sum','%v1',{'INT(300)'})]),
# PT2 lane by lane (bp-1bb): a vector GEP computes each lane as the scalar GEP of that lane's base and indices.
'vector-gep-scalar-base':('''@g = internal global [4 x i64] zeroinitializer
define void @top() {
 %v = getelementptr inbounds i64, ptr @g, <2 x i64> <i64 1, i64 3>
 %a = extractelement <2 x ptr> %v, i32 0
 %b = extractelement <2 x ptr> %v, i32 1
 ret void
}''',[('top','%a',{'PTR(@g,8,0)'}),('top','%b',{'PTR(@g,24,0)'})]),
'vector-gep-vector-base':('''@g = internal global [4 x i64] zeroinitializer
define void @top() {
 %v = getelementptr i8, ptr @g, <2 x i64> <i64 0, i64 8>
 %w = getelementptr i8, <2 x ptr> %v, i64 16
 %a = extractelement <2 x ptr> %w, i32 0
 %b = extractelement <2 x ptr> %w, i32 1
 ret void
}''',[('top','%a',{'PTR(@g,16,0)'}),('top','%b',{'PTR(@g,24,0)'})]),
'vector-gep-struct-field':('''%s = type { i64, i64 }
@g = internal global [4 x %s] zeroinitializer
define void @top() {
 %i0 = insertelement <2 x i64> <i64 1, i64 2>, i64 3, i32 1
 %v = getelementptr %s, ptr @g, <2 x i64> %i0, i32 1
 %w = getelementptr %s, ptr @g, <2 x i64> <i64 0, i64 1>, <2 x i32> <i32 1, i32 1>
 %a = extractelement <2 x ptr> %v, i32 0
 %b = extractelement <2 x ptr> %v, i32 1
 %c = extractelement <2 x ptr> %w, i32 0
 %d = extractelement <2 x ptr> %w, i32 1
 ret void
}''',[('top','%a',{'PTR(@g,24,0)'}),('top','%b',{'PTR(@g,56,0)'}),('top','%c',{'PTR(@g,8,0)'}),('top','%d',{'PTR(@g,24,0)'})]),
# The lane's memory is reached through the GEP: the load sees the slot, never an empty set.
'vector-gep-load':('''@g = internal global [2 x i64] [i64 5, i64 6]
define void @top() {
 %v = getelementptr i64, ptr @g, <2 x i64> <i64 0, i64 1>
 %b = extractelement <2 x ptr> %v, i32 1
 %x = load i64, ptr %b
 ret void
}''',[('top','%x',{'INT(6)'})]),
# N21 folds through the integer min/max rules; S2 keeps every value that fold can produce.
'vector-extrema-lanes':('''declare <2 x i32> @llvm.smax.v2i32(<2 x i32>, <2 x i32>)
declare i32 @llvm.vector.reduce.umax.v2i32(<2 x i32>)
define void @top() {
 %m = call <2 x i32> @llvm.smax.v2i32(<2 x i32> <i32 1, i32 2>, <2 x i32> <i32 3, i32 4>)
 %a = extractelement <2 x i32> %m, i32 0
 %b = extractelement <2 x i32> %m, i32 1
 %u = call i32 @llvm.vector.reduce.umax.v2i32(<2 x i32> <i32 7, i32 9>)
 ret void
}''',[('top','%a',{'INT(1)','INT(3)'}),('top','%b',{'INT(2)','INT(4)'}),('top','%u',{'INT(7)','INT(9)'})]),
# An intrinsic result S2 does not expand may not be an empty set: PT5 evaluates finite inputs.
'scalar-intrinsic-finite':('''declare i32 @llvm.bswap.i32(i32)
declare i32 @llvm.abs.i32(i32, i1)
declare i32 @llvm.fshl.i32(i32, i32, i32)
define void @top(i1 %c) {
 %x = select i1 %c, i32 1, i32 2
 %s = call i32 @llvm.bswap.i32(i32 %x)
 %a = call i32 @llvm.abs.i32(i32 -5, i1 false)
 %f = call i32 @llvm.fshl.i32(i32 1, i32 0, i32 %x)
 ret void
}''',[('top','%s',{'INT(16777216)','INT(33554432)'}),('top','%a',{'INT(5)'}),('top','%f',{'INT(2)','INT(4)'})]),
# An additive PT5 cycle remains additive through PT3's unconditional copies.
'additive-copy-cycle':('''define internal i64 @cycle(i1 %c) {
entry: br label %loop
loop:
 %n = phi i64 [ 0, %entry ], [ %copy, %loop ]
 %plus = add i64 %n, 1
 %copy = select i1 %c, i64 %plus, i64 %n
 br label %loop
}''',[]),
'cancelled-copy-cycle':('''define internal i64 @cycle() {
entry: br label %loop
loop:
 %n = phi i64 [ 7, %entry ], [ %copy, %loop ]
 %plus = add i64 %n, 1
 %minus = sub i64 %plus, 1
 %copy = freeze i64 %minus
 br label %loop
}''',[('cycle','%n',{'INT(7)'})]),
'small-copy-cycle':('''define internal i4 @cycle() {
entry: br label %loop
loop:
 %n = phi i4 [ 0, %entry ], [ %copy, %loop ]
 %plus = add i4 %n, 4
 %copy = freeze i4 %plus
 br label %loop
}''',[('cycle','%n',{'INT(0)','INT(4)','INT(8)','INT(12)'})]),
'runtime-memmove':('''@src = internal global i8 7
@dst = internal global i8 9
declare void @__bennett_rt_memmove(ptr,ptr,i64)
define i8 @top() {
 call void @__bennett_rt_memmove(ptr @dst,ptr @src,i64 1)
 %v = load i8, ptr @dst
 ret i8 %v
}''',[('top','%v',{'INT(7)','INT(9)'})]),
'runtime-memset':('''@dst = internal global i16 0
declare void @__bennett_rt_memset(ptr,i8,i64)
define i16 @top() {
 call void @__bennett_rt_memset(ptr @dst,i8 7,i64 2)
 %v = load i16, ptr @dst
 ret i16 %v
}''',[('top','%v',{'INT(0)','INT(1799)'})]),
'atomic-xchg-pointer':('''@cell = internal global ptr @old
define internal void @old() { ret void }
define internal void @new() { ret void }
define ptr @top() {
 %before = atomicrmw xchg ptr @cell, ptr @new seq_cst
 %after = load ptr, ptr @cell
 ret ptr %after
}''',[('top','%before',{'FN(@old,0,0)','FN(@new,0,0)'}),('top','%after',{'FN(@old,0,0)','FN(@new,0,0)'})]),
# N9's min/max uses an icmp plus PT3 select: both value operands union,
# even when the comparison is a singleton. Do not import a refined analysis.
'atomic-min-select':('''@cell = internal global i8 1
define i8 @top() {
 %before = atomicrmw min ptr @cell, i8 3 seq_cst
 %after = load i8, ptr @cell
 ret i8 %after
}''',[('top','%before',{'INT(1)','INT(3)'}),('top','%after',{'INT(1)','INT(3)'})]),
# N7 replaces an undefined shuffle MASK by lane index zero, not a zero lane.
'shuffle-undef-mask':('''define i8 @top() {
 %vec = shufflevector <2 x i8> <i8 7, i8 9>, <2 x i8> zeroinitializer, <2 x i32> <i32 undef, i32 1>
 %v = extractelement <2 x i8> %vec, i32 0
 ret i8 %v
}''',[('top','%v',{'INT(7)'})]),
'byval':('''@seed = internal global i8 7
define internal i8 @copy(ptr byval(i8) %p) {
 store i8 9, ptr %p
 %v = load i8, ptr %p
 ret i8 %v
}
define internal i8 @top() {
 %r = call i8 @copy(ptr byval(i8) @seed)
 %v = load i8, ptr @seed
 ret i8 %v
}
declare void @__bennett_oracle(ptr,ptr,ptr)
define void @host() {
 call void @__bennett_oracle(ptr @top,ptr null,ptr null)
 ret void
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
  if name=='additive-copy-cycle':ok=ok and data.get('analysis_rounds',100)<10 and any(v['value']=='%n' and v['top'] for v in data.get('values',[]))
  if name in ('additive-set-step','additive-vector-lane','additive-pointer-integer'):
   # Solved directly, not by one element per round up to K.
   ok=ok and data.get('analysis_rounds',100)<20 and any(v['value'] in ('%n','%v') and v['top'] for v in data.get('values',[]))
  if name=='host-tiers':ok=ok and all(f['tiers']==['H'] for f in data.get('functions',[]))
  results.append({'case':name,'ok':ok,'diagnostic':x.stderr.strip() if x.returncode else ''})
 result={'major':a.major,'cases':len(results),'passed':sum(r['ok'] for r in results),'results':results};(R/f'.tmp/analysis-edges-{a.major}.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2));return any(not r['ok'] for r in results)
if __name__=='__main__':raise SystemExit(main())
