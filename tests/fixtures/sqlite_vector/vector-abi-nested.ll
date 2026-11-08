target datalayout = "e-p:64:64"
define internal { i8, [1 x <2 x i32>] } @identity({ i8, [1 x <2 x i32>] } %v) {
  ret { i8, [1 x <2 x i32>] } %v
}
define i32 @top() {
  %v = call { i8, [1 x <2 x i32>] } @identity({ i8, [1 x <2 x i32>] } { i8 4, [1 x <2 x i32>] [<2 x i32> <i32 1, i32 3>] })
  %lane = extractvalue { i8, [1 x <2 x i32>] } %v, 1, 0
  %r = extractelement <2 x i32> %lane, i32 1
  ret i32 %r
}
