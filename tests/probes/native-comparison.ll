; Native code must perform the arithmetic and use the actual register backend.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)

define i64 @native_probe(i64 %x) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  %null = icmp eq ptr %q, null
  %sum = add i64 %x, 5
  %result = select i1 %null, i64 123456, i64 %sum
  call void @__bennett_qfree(ptr %q)
  ret i64 %result
}
