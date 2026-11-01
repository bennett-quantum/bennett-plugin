#!/usr/bin/env python3
"""N21 lanes of the forms SLP/loop vectorisers emit (bp-1bb): every vector value of a device
function is scalarised, and the result computes what an independent Python model says.

The expected numbers are computed here, not by LLVM. The original module also runs under lli
where the program has no N7/N14 totalisation in it, so its output is a second witness."""
import argparse,re,subprocess
from contracts import ROOT as R
M=(1<<64)-1
TABLE=[(i*1000+7)&M for i in range(16)]
GLOBAL='@t = internal global [16 x i64] ['+', '.join(f'i64 {v}' for v in TABLE)+']\n'
def gep(x):
 # Lane 0 of %p is t[2x+1], lane 1 is t[2·3+1]. %q steps both back one element; %c is the constant vector form.
 a=TABLE[2*x+1];b=TABLE[7];c=TABLE[2*x];d=TABLE[6];e=TABLE[0];f=TABLE[1]
 return (a+2*b+3*c+5*d+7*e+11*f)&M
def loop(x):
 # Two-lane accumulator through a phi cycle: (a,b) -> (b+x, a+1), four rounds, then sum.
 a,b=x,1
 for _ in range(4):a,b=(b+x)&M,(a+1)&M
 return (a+b)&M
def sgn(v,w):return v-(1<<w) if v>>(w-1) else v
def extrema(x):
 x&=0xffffffff;m=(1<<32)-1;l=[x,5,(-3)&m,9];r=[2,x,7,(-1)&m]
 hi=[max(a,b,key=lambda v:sgn(v,32)) for a,b in zip(l,r)];un=[max(a,b) for a,b in zip(l,r)];lo=[min(a,b) for a,b in zip(l,r)]
 return (max(hi,key=lambda v:sgn(v,32))+max(un)+min(lo)+sum(hi))&m
def shifts(x):
 x&=63;m=(1<<32)-1;s=[x,x+32,1,40] # N14: a lane shift by >=W is 0, as a scalar one is.
 v=[(0x80000001<<a)&m if a<32 else 0 for a in s[:2]]+[(0x80000001>>s[2])&m,0]
 return sum(v)&m
def shuffle(x):
 a=[x&0xffff,1,2,3];b=[10,20,30,40]
 r=[b[0],a[0],a[3],b[3],a[0]] # The last mask element is undefined: N7 makes it 0, source lane 0.
 return (r[0]+2*r[1]+3*r[2]+5*r[3]+7*r[4])&0xffff
def select(x):
 c=[x&1==0,x&1==1];return (([x,1][0] if c[0] else 100)+(1 if c[1] else 200))&M
CASES={
'gep':(GLOBAL+'''define i64 @top(i64 %x) {
  %a = insertelement <2 x i64> poison, i64 %x, i32 0
  %b = insertelement <2 x i64> %a, i64 3, i32 1
  %p = getelementptr inbounds { i64, i64 }, ptr @t, <2 x i64> %b, i32 1
  %q = getelementptr i8, <2 x ptr> %p, i64 -8
  %c = getelementptr i8, ptr @t, <2 x i64> <i64 0, i64 8>
  %p0 = extractelement <2 x ptr> %p, i32 0
  %p1 = extractelement <2 x ptr> %p, i32 1
  %q0 = extractelement <2 x ptr> %q, i32 0
  %q1 = extractelement <2 x ptr> %q, i32 1
  %c0 = extractelement <2 x ptr> %c, i32 0
  %c1 = extractelement <2 x ptr> %c, i32 1
  %v0 = load i64, ptr %p0
  %v1 = load i64, ptr %p1
  %v2 = load i64, ptr %q0
  %v3 = load i64, ptr %q1
  %v4 = load i64, ptr %c0
  %v5 = load i64, ptr %c1
  %m1 = mul i64 %v1, 2
  %m2 = mul i64 %v2, 3
  %m3 = mul i64 %v3, 5
  %m4 = mul i64 %v4, 7
  %m5 = mul i64 %v5, 11
  %s1 = add i64 %v0, %m1
  %s2 = add i64 %s1, %m2
  %s3 = add i64 %s2, %m3
  %s4 = add i64 %s3, %m4
  %r = add i64 %s4, %m5
  ret i64 %r
}''',gep,range(8)),
'loop':('''define i64 @top(i64 %x) {
entry:
  %i0 = insertelement <2 x i64> poison, i64 %x, i32 0
  %i1 = insertelement <2 x i64> %i0, i64 1, i32 1
  %inc = insertelement <2 x i64> <i64 0, i64 1>, i64 %x, i32 0
  br label %loop
loop:
  %v = phi <2 x i64> [ %i1, %entry ], [ %next, %loop ]
  %n = phi i32 [ 0, %entry ], [ %n1, %loop ]
  %swap = shufflevector <2 x i64> %v, <2 x i64> poison, <2 x i32> <i32 1, i32 0>
  %next = add <2 x i64> %swap, %inc
  %n1 = add i32 %n, 1
  %again = icmp ult i32 %n1, 4
  br i1 %again, label %loop, label %done
done:
  %r = call i64 @llvm.vector.reduce.add.v2i64(<2 x i64> %next)
  ret i64 %r
}
declare i64 @llvm.vector.reduce.add.v2i64(<2 x i64>)''',loop,[0,1,2,5,1<<40]),
'extrema':('''define i64 @top(i64 %x) {
  %t = trunc i64 %x to i32
  %l0 = insertelement <4 x i32> <i32 0, i32 5, i32 -3, i32 9>, i32 %t, i32 0
  %r0 = insertelement <4 x i32> <i32 2, i32 0, i32 7, i32 -1>, i32 %t, i32 1
  %hi = call <4 x i32> @llvm.smax.v4i32(<4 x i32> %l0, <4 x i32> %r0)
  %un = call <4 x i32> @llvm.umax.v4i32(<4 x i32> %l0, <4 x i32> %r0)
  %lo = call <4 x i32> @llvm.umin.v4i32(<4 x i32> %l0, <4 x i32> %r0)
  %a = call i32 @llvm.vector.reduce.smax.v4i32(<4 x i32> %hi)
  %b = call i32 @llvm.vector.reduce.umax.v4i32(<4 x i32> %un)
  %c = call i32 @llvm.vector.reduce.umin.v4i32(<4 x i32> %lo)
  %d = call i32 @llvm.vector.reduce.add.v4i32(<4 x i32> %hi)
  %s1 = add i32 %a, %b
  %s2 = add i32 %s1, %c
  %s3 = add i32 %s2, %d
  %r = zext i32 %s3 to i64
  ret i64 %r
}
declare <4 x i32> @llvm.smax.v4i32(<4 x i32>, <4 x i32>)
declare <4 x i32> @llvm.umax.v4i32(<4 x i32>, <4 x i32>)
declare <4 x i32> @llvm.umin.v4i32(<4 x i32>, <4 x i32>)
declare i32 @llvm.vector.reduce.smax.v4i32(<4 x i32>)
declare i32 @llvm.vector.reduce.umax.v4i32(<4 x i32>)
declare i32 @llvm.vector.reduce.umin.v4i32(<4 x i32>)
declare i32 @llvm.vector.reduce.add.v4i32(<4 x i32>)''',extrema,[0,1,2,7,0xffffffff,1<<31]),
'shifts':('''define i64 @top(i64 %x) {
  %t0 = trunc i64 %x to i32
  %t = and i32 %t0, 63
  %big = add i32 %t, 32
  %a0 = insertelement <2 x i32> poison, i32 %t, i32 0
  %a1 = insertelement <2 x i32> %a0, i32 %big, i32 1
  %l = shl <2 x i32> <i32 -2147483647, i32 -2147483647>, %a1
  %h = lshr <2 x i32> <i32 -2147483647, i32 -2147483647>, <i32 1, i32 40>
  %j = shufflevector <2 x i32> %l, <2 x i32> %h, <4 x i32> <i32 0, i32 1, i32 2, i32 3>
  %s = call i32 @llvm.vector.reduce.add.v4i32(<4 x i32> %j)
  %r = zext i32 %s to i64
  ret i64 %r
}
declare i32 @llvm.vector.reduce.add.v4i32(<4 x i32>)''',shifts,[0,1,3,31,32,63]),
'shuffle':('''define i64 @top(i64 %x) {
  %t = trunc i64 %x to i16
  %a = insertelement <4 x i16> <i16 0, i16 1, i16 2, i16 3>, i16 %t, i32 0
  %s = shufflevector <4 x i16> %a, <4 x i16> <i16 10, i16 20, i16 30, i16 40>, <5 x i32> <i32 4, i32 0, i32 3, i32 7, i32 poison>
  %e0 = extractelement <5 x i16> %s, i32 0
  %e1 = extractelement <5 x i16> %s, i32 1
  %e2 = extractelement <5 x i16> %s, i32 2
  %e3 = extractelement <5 x i16> %s, i32 3
  %e4 = extractelement <5 x i16> %s, i32 4
  %m1 = mul i16 %e1, 2
  %m2 = mul i16 %e2, 3
  %m3 = mul i16 %e3, 5
  %m4 = mul i16 %e4, 7
  %s1 = add i16 %e0, %m1
  %s2 = add i16 %s1, %m2
  %s3 = add i16 %s2, %m3
  %s4 = add i16 %s3, %m4
  %r = zext i16 %s4 to i64
  ret i64 %r
}''',shuffle,[0,1,9,65535]),
'select':('''define i64 @top(i64 %x) {
  %bit = and i64 %x, 1
  %c0 = icmp eq i64 %bit, 0
  %c1 = icmp eq i64 %bit, 1
  %m0 = insertelement <2 x i1> poison, i1 %c0, i32 0
  %m1 = insertelement <2 x i1> %m0, i1 %c1, i32 1
  %v0 = insertelement <2 x i64> <i64 0, i64 1>, i64 %x, i32 0
  %s = select <2 x i1> %m1, <2 x i64> %v0, <2 x i64> <i64 100, i64 200>
  %r = call i64 @llvm.vector.reduce.add.v2i64(<2 x i64> %s)
  ret i64 %r
}
declare i64 @llvm.vector.reduce.add.v2i64(<2 x i64>)''',select,[0,1,2,3]),
}
def harness(body,xs):
 calls=''.join(f'  %r{n} = call i64 @top(i64 {x})\n  call i32 (ptr, ...) @printf(ptr @fmt, i64 %r{n})\n' for n,x in enumerate(xs))
 return ('target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"\n'
  'target triple = "x86_64-unknown-linux-gnu"\n@fmt = private constant [6 x i8] c"%llu\\0A\\00"\ndeclare i32 @printf(ptr, ...)\n'+body+
  '\ndefine i32 @main() {\n'+calls+'  ret i32 0\n}\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--major',type=int,required=True);a=p.parse_args();tool=f'/usr/lib/llvm-{a.major}/bin/';passed=0
 for name,(body,model,xs) in CASES.items():
  d=R/f'.tmp/vector-lanes/{a.major}/{name}';d.mkdir(parents=True,exist_ok=True);src=d/'in.ll';out=d/'out.ll';src.write_text(harness(body,xs))
  z=subprocess.run([tool+'opt','-load-pass-plugin='+str(R/f'build/libbennett-plugin-{a.major}.so'),'-passes=bennett','-bennett-dialect=0.2.10','-bennett-normalise-only','-S',str(src),'-o',str(out)],capture_output=True,text=True,timeout=120)
  assert z.returncode==0,(name,z.stderr)
  text=out.read_text();top=re.search(r'define [^\n]*@top\(.*?^}',text,re.S|re.M)[0]
  assert not re.search(r'<\d+ x ',top),(name,'a vector value survived N21',re.findall(r'.*<\d+ x .*',top)[:5])
  verified=subprocess.run([tool+'opt','-passes=verify','-disable-output',str(out)],capture_output=True,text=True);assert verified.returncode==0,(name,verified.stderr)
  run=subprocess.run([tool+'lli',str(out)],capture_output=True,text=True,timeout=120);assert run.returncode==0,(name,run.stderr)
  want=[str(model(x)) for x in xs];assert run.stdout.split()==want,(name,'materialised',xs,run.stdout.split(),want)
  if name not in('shifts','shuffle'): # Those two carry LLVM poison that only N7/N14 define.
   native=subprocess.run([tool+'lli',str(src)],capture_output=True,text=True,timeout=120);assert native.returncode==0 and native.stdout.split()==want,(name,'source',native.stdout.split(),want)
  passed+=1
 print(f'vector lanes LLVM {a.major}: {passed}/{len(CASES)}')
if __name__=='__main__':raise SystemExit(main())
