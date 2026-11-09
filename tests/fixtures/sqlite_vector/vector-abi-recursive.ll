target datalayout = "e-p:64:64"
define internal <2 x i32> @identity(<2 x i32> %v, i1 %recurse) {
entry:
  br i1 %recurse, label %rec, label %base
rec:
  %r = call <2 x i32> @identity(<2 x i32> %v, i1 false)
  ret <2 x i32> %r
base:
  ret <2 x i32> %v
}
define i32 @top() {
  %v = call <2 x i32> @identity(<2 x i32> <i32 1, i32 3>, i1 true)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
}
