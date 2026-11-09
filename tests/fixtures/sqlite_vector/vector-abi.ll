; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-abi.ll (design reproducer).
target datalayout = "e-p:64:64"
define internal <2 x i32> @identity(<2 x i32> %v) {
  ret <2 x i32> %v
}
define i32 @top() {
  %v = call <2 x i32> @identity(<2 x i32> <i32 1, i32 3>)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
}
