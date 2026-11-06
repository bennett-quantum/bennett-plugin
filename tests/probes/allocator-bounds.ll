declare ptr @malloc(i64)
declare void @free(ptr)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_qalloc(i64, i64)
define i64 @top(i64 %mode) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %p = call ptr @malloc(i64 4)
  %dead = icmp eq i64 %mode, 0
  %retire = select i1 %dead, ptr %p, ptr null
  call void @free(ptr %retire)
  ; malloc(4) owns a 16-byte ABI-rounded primitive allocation. Its padding
  ; is live and zero-filled. The published allocator then creates a separate
  ; live 32-byte bookkeeping record. Byte 48 lies past both live intervals.
  %padding = icmp eq i64 %mode, 1
  %offset = select i1 %padding, i64 4, i64 48
  %past = getelementptr i8, ptr %p, i64 %offset
  %address = select i1 %dead, ptr %p, ptr %past
  %v = load volatile i8, ptr %address
  %result = zext i8 %v to i64
  ret i64 %result
}
