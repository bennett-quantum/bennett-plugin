; §19.1: link the published runtime and arith before lto<O3>.
; §17.1/17.4: dead and zero-sized allocations still advance history.
declare ptr @malloc(i64)
declare ptr @calloc(i64, i64)
declare void @free(ptr)
declare ptr @memset(ptr, i32, i64)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_qalloc(i64, i64)
define i64 @top(i64 %n) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %dead = call ptr @malloc(i64 3)
  call void @free(ptr %dead)
  %zero = call ptr @malloc(i64 0)
  %p = call ptr @calloc(i64 %n, i64 2)
  %initial = load volatile i8, ptr %p
  %filled = call ptr @memset(ptr %p, i32 171, i64 %n)
  %value = load volatile i8, ptr %p
  %d = ptrtoint ptr %dead to i64
  %z = ptrtoint ptr %zero to i64
  %a = ptrtoint ptr %p to i64
  %dz = sub i64 %z, %d
  %dp = sub i64 %a, %z
  %history = add i64 %dz, %dp
  %v = zext i8 %value to i64
  %i = zext i8 %initial to i64
  %result = add i64 %history, %v
  %all = add i64 %result, %i
  call void @free(ptr %zero)
  call void @free(ptr %p)
  call void @free(ptr null)
  ret i64 %all
}
