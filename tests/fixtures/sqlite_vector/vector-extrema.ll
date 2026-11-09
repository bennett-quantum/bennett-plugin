; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-extrema.ll (design reproducer).
target datalayout = "e-p:64:64"
declare <2 x i32> @llvm.smax.v2i32(<2 x i32>, <2 x i32>)
define i32 @top() {
  %v = call <2 x i32> @llvm.smax.v2i32(<2 x i32> <i32 1, i32 9>, <2 x i32> <i32 3, i32 7>)
  %r = extractelement <2 x i32> %v, i32 0
  ret i32 %r
}
