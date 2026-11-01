; §13.1 real, SHA-pinned numerical helper closure; §14.1 recursion.
define i1 @top(i64 %x) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 %a = bitcast i64 %x to double
 %r = fcmp une double %a, 0.0
 call void @__bennett_qfree(ptr %q)
 ret i1 %r
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
