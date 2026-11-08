target datalayout = "e-p:64:64"
declare i32 @llvm.vector.reduce.smin.v4i32(<4 x i32>)
define i32 @top() {
  %r = call i32 @llvm.vector.reduce.smin.v4i32(<4 x i32> <i32 -1, i32 1, i32 9, i32 -2147483648>)
  ret i32 %r
}
