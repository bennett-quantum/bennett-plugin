; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/fneg-nan-payload.ll (design reproducer).
target datalayout = "e-p:64:64"
define i64 @top() {
  %bits = bitcast <2 x i32> <i32 2141266757, i32 -4119739> to <2 x float>
  %neg = fneg <2 x float> %bits
  %r = bitcast <2 x float> %neg to i64
  ret i64 %r
}
