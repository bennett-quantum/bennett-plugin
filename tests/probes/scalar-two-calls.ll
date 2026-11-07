target datalayout = "e-p:64:64"
define i8 @one(i8 %x) !bennett.address !0 {
 %r = add i8 %x, 1
 ret i8 %r
}
define i8 @two(i8 %x) !bennett.address !1 {
 %r = add i8 %x, 2
 ret i8 %r
}
define i8 @f(i1 %which, i8 %x) {
 %p = select i1 %which, ptr @one, ptr @two
 %a = call i8 %p(i8 %x)
 %b = call i8 %p(i8 %a)
 ret i8 %b
}
!0 = !{i64 4096}
!1 = !{i64 4112}
