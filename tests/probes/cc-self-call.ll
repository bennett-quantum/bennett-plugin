; §14.1 unrestricted recursion, including a recursive launch entry.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
@bias = internal global i64 17
define i64 @top(i64 %n) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %z = icmp eq i64 %n, 0
  br i1 %z, label %done, label %more
more:
  %next = sub i64 %n, 1
  %r = call i64 @top(i64 %next)
  %sum = add i64 %r, %n
  store volatile i64 %sum, ptr @bias
  ret i64 %sum
done:
  %initial = load volatile i64, ptr @bias
  ret i64 %initial
}
