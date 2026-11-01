; §14.1/§17.4: keep real calls, typed pointers, nested/recursive frames.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare ptr @__bennett_nz_alloc(i64)
declare void @__bennett_nz_free(ptr)
define internal fastcc ptr @write(ptr %p, i64 %v) noinline {
  store i64 %v, ptr %p
  ret ptr %p
}
define internal fastcc i64 @nested(ptr %p, i64 %n) noinline {
  %q = tail call fastcc ptr @write(ptr %p, i64 %n)
  %v = load i64, ptr %q
  %r = add i64 %v, 1
  ret i64 %r
}
define internal fastcc i64 @odd(ptr %p, i64 %n) noinline {
  %z = icmp eq i64 %n, 0
  br i1 %z, label %done, label %more
more:
  %k = sub i64 %n, 1
  %r = call fastcc i64 @even(ptr %p, i64 %k)
  %v = add i64 %r, %n
  ret i64 %v
done:
  %x = load i64, ptr %p
  ret i64 %x
}
define internal fastcc i64 @even(ptr %p, i64 %n) noinline {
  %z = icmp eq i64 %n, 0
  br i1 %z, label %done, label %more
more:
  %k = sub i64 %n, 1
  %r = call fastcc i64 @odd(ptr %p, i64 %k)
  %v = add i64 %r, %n
  ret i64 %v
done:
  %x = load i64, ptr %p
  ret i64 %x
}
define internal fastcc void @touch(ptr %p, i64 %n) noinline {
  %r = call fastcc i64 @nested(ptr %p, i64 %n)
  store i64 %r, ptr %p
  ret void
}
define i64 @top(i64 %n) {
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  %p = call ptr @__bennett_nz_alloc(i64 8)
  store i64 0, ptr %p
  br label %loop
loop:
  %i = phi i64 [0, %0], [%next, %body]
  %test = icmp ult i64 %i, %n
  br i1 %test, label %body, label %done
body:
  call fastcc void @touch(ptr %p, i64 %i)
  %next = add i64 %i, 1
  br label %loop
done:
  %result = call fastcc i64 @even(ptr %p, i64 %n)
  call void @__bennett_nz_free(ptr %p)
  ret i64 %result
}
