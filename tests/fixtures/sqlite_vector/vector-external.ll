target datalayout = "e-p:64:64"
declare <2 x i32> @external(<2 x i32>)
define i32 @top() {
  %v = call <2 x i32> @external(<2 x i32> <i32 1, i32 3>)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
}
