declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define i64 @native_divide(i64 %x, i64 %y) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %q)
 %r = sdiv i64 %x, %y
 ret i64 %r
}
