target datalayout = "e-p:64:64"
define <2 x i32> @identity(<2 x i32> %v) !bennett.address !0 {
  ret <2 x i32> %v
}
define i32 @top() {
  %v = call <2 x i32> @identity(<2 x i32> <i32 1, i32 3>)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
}
!0 = !{i64 4096}
