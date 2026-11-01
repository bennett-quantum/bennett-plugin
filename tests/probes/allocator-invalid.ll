declare ptr @malloc(i64)
declare void @free(ptr)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_qalloc(i64, i64)
define i64 @top(i64 %mode) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %p = call ptr @malloc(i64 4)
  %double = icmp eq i64 %mode, 0
  %retire = select i1 %double, ptr %p, ptr null
  call void @free(ptr %retire)
  %interior = getelementptr i8, ptr %p, i64 1
  %bad = select i1 %double, ptr %p, ptr %interior
  call void @free(ptr %bad)
  ret i64 99
}
