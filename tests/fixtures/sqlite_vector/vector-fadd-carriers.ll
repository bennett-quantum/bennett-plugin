; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-fadd-carriers.ll (design reproducer).
target datalayout = "e-p:64:64"
define i64 @top() {
  %v = fadd <2 x float> <float 1.0, float 2.0>, <float 2.0, float 4.0>
  %r = bitcast <2 x float> %v to i64
  ret i64 %r
}
