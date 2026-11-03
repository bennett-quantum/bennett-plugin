target datalayout = "e-p:64:64"
define i8 @oracle() {
 %vec = shufflevector <2 x i8> <i8 7, i8 9>, <2 x i8> zeroinitializer, <2 x i32> <i32 undef, i32 1>
 %v = extractelement <2 x i8> %vec, i32 0
 ret i8 %v
}
