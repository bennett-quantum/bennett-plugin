target datalayout = "e-p:64:64"
@fp = internal global ptr @identity
define internal <2 x i32> @identity(<2 x i32> %v) !bennett.address !0 {
  ret <2 x i32> %v
}
define i32 @top() {
  %f = load ptr, ptr @fp
  %v = call <2 x i32> %f(<2 x i32> <i32 1, i32 3>)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
}
!0 = !{i64 4096}
