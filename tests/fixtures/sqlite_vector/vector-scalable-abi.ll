target datalayout = "e-p:64:64"
define internal <vscale x 2 x i32> @identity(<vscale x 2 x i32> %v) vscale_range(2, 2) {
  ret <vscale x 2 x i32> %v
}
define i32 @top() vscale_range(2, 2) {
  %input = insertelement <vscale x 2 x i32> zeroinitializer, i32 7, i32 3
  %v = call <vscale x 2 x i32> @identity(<vscale x 2 x i32> %input)
  %r = extractelement <vscale x 2 x i32> %v, i32 3
  ret i32 %r
}
