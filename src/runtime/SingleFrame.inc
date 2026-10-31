// Fixed linked input of dialect 0.2.10 @023f5a7 §9.2. Used only as a
// structural proof template, never substituted for supplied runtime code.
R"IR(
@ss_base = internal global ptr null, align 8
@ss_size = internal global i64 0, align 8
@ss_sp = internal global i64 0, align 8
declare ptr @__bennett_nz_alloc(i64)
declare void @__bennett_nz_fault(i64)
define void @__bennett_rt_ss_init(i64 %size) {
entry:
  %base = load ptr, ptr @ss_base, align 8
  %unset = icmp eq ptr %base, null
  br i1 %unset, label %init, label %done
init:
  %p = call ptr @__bennett_nz_alloc(i64 %size)
  store ptr %p, ptr @ss_base, align 8
  store i64 %size, ptr @ss_size, align 8
  store i64 0, ptr @ss_sp, align 8
  br label %done
done:
  ret void
}
define ptr @__bennett_rt_ss_push(i64 %n, i64 %a) {
entry:
  %sp = load i64, ptr @ss_sp, align 8
  %meta = add i64 %sp, 8
  %am1 = sub i64 %a, 1
  %pad = add i64 %meta, %am1
  %neg = sub i64 0, %a
  %start = and i64 %pad, %neg
  %end = add i64 %start, %n
  %size = load i64, ptr @ss_size, align 8
  %too_big = icmp ugt i64 %end, %size
  br i1 %too_big, label %bad, label %ok
bad:
  call void @__bennett_nz_fault(i64 2)
  unreachable
ok:
  %base = load ptr, ptr @ss_base, align 8
  %prev = sub i64 %start, 8
  %slot = getelementptr i8, ptr %base, i64 %prev
  store i64 %sp, ptr %slot, align 8
  store i64 %end, ptr @ss_sp, align 8
  %p = getelementptr i8, ptr %base, i64 %start
  br label %zero
zero:
  %i = phi i64 [ 0, %ok ], [ %next, %byte ]
  %done = icmp eq i64 %i, %n
  br i1 %done, label %ret, label %byte
byte:
  %b = getelementptr i8, ptr %p, i64 %i
  store i8 0, ptr %b, align 1
  %next = add i64 %i, 1
  br label %zero
ret:
  ret ptr %p
}
define void @__bennett_rt_ss_pop(ptr %p) {
entry:
  %slot = getelementptr i8, ptr %p, i64 -8
  %prev = load i64, ptr %slot, align 8
  store i64 %prev, ptr @ss_sp, align 8
  ret void
}
)IR"
