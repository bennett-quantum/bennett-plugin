target datalayout = "e-p:64:64"
define <2 x i32> @identity(<2 x i32> %v) {
  ret <2 x i32> %v
}
declare i32 @check(ptr)
define i32 @top() {
  %r = call i32 @check(ptr @identity)
  ret i32 %r
}
