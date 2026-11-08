target datalayout = "e-p:64:64"
define i32 @top() {
  %v = add <vscale x 2 x i32> zeroinitializer, splat (i32 3)
  %r = extractelement <vscale x 2 x i32> %v, i32 1
  ret i32 %r
}
