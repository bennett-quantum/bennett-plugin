; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-fadd-layout-23.ll (design reproducer).
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-i128:128-f80:128-n8:16:32:64-S128"
define i64 @top() {
  %v = fadd <2 x float> <float 1.0, float 2.0>, <float 2.0, float 4.0>
  %r = bitcast <2 x float> %v to i64
  ret i64 %r
}
