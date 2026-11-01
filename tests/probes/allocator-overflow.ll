declare ptr @calloc(i64, i64)
declare void @free(ptr)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_qalloc(i64, i64)
@after = global i8 0
define i64 @top(i64 %n) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %p = call ptr @calloc(i64 %n, i64 2)
  store i8 99, ptr @after
  call void @free(ptr %p)
  ret i64 7
}
