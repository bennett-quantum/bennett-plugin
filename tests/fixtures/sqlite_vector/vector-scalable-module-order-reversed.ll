; Link V=min(2,4)=2 for both nonfixed ranges; 10*2+2=22.
target datalayout = "e-p:64:64"
declare i32 @llvm.vscale.i32()
define internal i32 @second() #1 {
  %s = call i32 @llvm.vscale.i32()
  %v = insertelement <vscale x 2 x i32> zeroinitializer, i32 %s, i32 0
  %r = extractelement <vscale x 2 x i32> %v, i32 0
  ret i32 %r
}
define internal i32 @first() #0 {
  %s = call i32 @llvm.vscale.i32()
  %v = insertelement <vscale x 2 x i32> zeroinitializer, i32 %s, i32 0
  %r = extractelement <vscale x 2 x i32> %v, i32 0
  ret i32 %r
}
define i32 @top() {
  %a = call i32 @first()
  %b = call i32 @second()
  %tens = mul i32 %a, 10
  %r = add i32 %tens, %b
  ret i32 %r
}
attributes #0 = { vscale_range(2,8) }
attributes #1 = { vscale_range(4,8) }
