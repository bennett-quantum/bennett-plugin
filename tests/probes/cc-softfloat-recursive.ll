; Transport-only library fixture, never a numerical implementation.
; §13.1 calls enter a mutually recursive §14.1 closure; §17.4 carries tuples.
define internal { i32, { i64, i1 } } @eval(i64 %n) {
entry:
 %zero = icmp eq i64 %n, 0
 br i1 %zero, label %base, label %recurse
base:
 br label %done
recurse:
 %next = sub i64 %n, 1
 %v = call { i32, { i64, i1 } } @step(i64 %next)
 %sum = extractvalue { i32, { i64, i1 } } %v, 1, 0
 %r = add i64 %sum, %n
 %out = insertvalue { i32, { i64, i1 } } %v, i64 %r, 1, 0
 br label %done
done:
 %vout = phi { i32, { i64, i1 } } [ { i32 7, { i64, i1 } { i64 0, i1 true } }, %base ], [ %out, %recurse ]
 %chosen = select i1 %zero, { i32, { i64, i1 } } %vout, { i32, { i64, i1 } } %vout
 %transport = call { i32, { i64, i1 } } @tuple({ i32, { i64, i1 } } %chosen)
 ret { i32, { i64, i1 } } %transport
}
define internal { i32, { i64, i1 } } @tuple({ i32, { i64, i1 } } %a) {
 ret { i32, { i64, i1 } } %a
}
define internal { i32, { i64, i1 } } @step(i64 %n) {
 %r = call { i32, { i64, i1 } } @eval(i64 %n)
 ret { i32, { i64, i1 } } %r
}
define i1 @__bennett_sf_cmp_f64(i64 %a, i64 %b, i32 %p) {
 %v = call { i32, { i64, i1 } } @eval(i64 %a)
 %sum = extractvalue { i32, { i64, i1 } } %v, 1, 0
 %r = icmp ne i64 %sum, 0
 ret i1 %r
}
define i1 @top(i64 %x) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 %a = bitcast i64 %x to double
 %r = fcmp une double %a, 0.0
 call void @__bennett_qfree(ptr %q)
 ret i1 %r
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
