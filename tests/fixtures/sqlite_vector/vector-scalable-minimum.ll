target datalayout = "e-p:64:64"
declare i32 @llvm.vscale.i32()
define i32 @top() vscale_range(2, 4) {
  %v = insertelement <vscale x 2 x i32> zeroinitializer, i32 7, i32 3
  %lane = extractelement <vscale x 2 x i32> %v, i32 3
  %scale = call i32 @llvm.vscale.i32()
  %r = add i32 %lane, %scale
  ret i32 %r
}
