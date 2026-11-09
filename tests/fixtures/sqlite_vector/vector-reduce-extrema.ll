; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-reduce-extrema.ll (design reproducer).
target datalayout = "e-p:64:64"
declare i32 @llvm.vector.reduce.smax.v2i32(<2 x i32>)
define i32 @top() {
  %r = call i32 @llvm.vector.reduce.smax.v2i32(<2 x i32> <i32 1, i32 9>)
  ret i32 %r
}
