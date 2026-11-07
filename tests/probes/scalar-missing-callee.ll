target datalayout = "e-p:64:64"
declare !bennett.address !0 i8 @missing(i8)
define i8 @one(i8 %x) !bennett.address !1 {
 %r = add i8 %x, 1
 ret i8 %r
}
define i8 @f(i1 %which, i8 %x) {
 %p = select i1 %which, ptr @one, ptr @missing
 %r = call i8 %p(i8 %x)
 ret i8 %r
}
!0 = !{i64 4096}
!1 = !{i64 4112}
