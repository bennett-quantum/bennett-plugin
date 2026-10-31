R"ir(
@__bennett_ss_base = internal global ptr null, align 8
@__bennett_ss_size = internal global i64 0, align 8
@__bennett_ss_sp = internal global i64 0, align 8
@__bennett_ss_count = internal global i64 0, align 8
@__bennett_ss_nsaves = internal global i64 0, align 8
@__bennett_ss_saves = internal global [CAP x i64] zeroinitializer, align 8
@__bennett_ss_entries = internal global [CAP x [3 x i64]] zeroinitializer, align 8

declare ptr @__bennett_nz_alloc(i64)
declare void @__bennett_nz_fault(i64)
define void @__bennett_ss_size_check(i1 %bad) {
 br i1 %bad, label %fail, label %ok
fail:
 call void @__bennett_nz_fault(i64 2)
 unreachable
ok:
 ret void
}
define void @__bennett_rt_ss_init(i64 %size) {
 %base = load ptr, ptr @__bennett_ss_base
 %unset = icmp eq ptr %base, null
 br i1 %unset, label %init, label %done
init:
 %p = call ptr @__bennett_nz_alloc(i64 %size)
 store ptr %p, ptr @__bennett_ss_base
 store i64 %size, ptr @__bennett_ss_size
 store i64 0, ptr @__bennett_ss_sp
 store i64 0, ptr @__bennett_ss_count
 br label %done
done:
 ret void
}
define ptr @__bennett_ss_extend(i64 %n, i64 %a, i64 %kind) {
 %sp = load i64, ptr @__bennett_ss_sp
 %base = load ptr, ptr @__bennett_ss_base
 %bi = ptrtoint ptr %base to i64
 %frame = icmp eq i64 %kind, 1
 %header = select i1 %frame, i64 16, i64 0
 %s = add i64 %sp, %header
 %sabs = add i64 %bi, %s
 %am1 = sub i64 %a, 1
 %pad = add i64 %sabs, %am1
 %neg = sub i64 0, %a
 %startabs = and i64 %pad, %neg
 %start = sub i64 %startabs, %bi
 %iszero = icmp eq i64 %n, 0
 %extent = select i1 %iszero, i64 1, i64 %n
 %end = add i64 %start, %extent
 %size = load i64, ptr @__bennett_ss_size
 %big = icmp ult i64 %size, %end
 %wrap0 = icmp ult i64 %s, %sp
 %wrap1 = icmp ult i64 %sabs, %bi
 %wrap2 = icmp ult i64 %pad, %sabs
 %wrap3 = icmp ult i64 %end, %start
 %w0 = or i1 %wrap0, %wrap1
 %w1 = or i1 %wrap2, %wrap3
 %w2 = or i1 %w0, %w1
 %bad = or i1 %big, %w2
 br i1 %bad, label %fault, label %ok
fault:
 call void @__bennett_nz_fault(i64 2)
 unreachable
ok:
 %p = inttoptr i64 %startabs to ptr
 %count = load i64, ptr @__bennett_ss_count
 %slot = getelementptr [CAP x [3 x i64]], ptr @__bennett_ss_entries, i64 0, i64 %count, i64 0
 store i64 %startabs, ptr %slot
 %sz = getelementptr i8, ptr %slot, i64 8
 store i64 %n, ptr %sz
 %kd = getelementptr i8, ptr %slot, i64 16
 store i64 %kind, ptr %kd
 %nextcount = add i64 %count, 1
 store i64 %nextcount, ptr @__bennett_ss_count
 store i64 %end, ptr @__bennett_ss_sp
 br i1 %frame, label %save, label %zero
save:
 %prev = getelementptr i8, ptr %p, i64 -16
 store i64 %sp, ptr %prev
 %ci = getelementptr i8, ptr %p, i64 -8
 store i64 %count, ptr %ci
 br label %zero
zero:
 %i = phi i64 [ 0, %ok ], [ 0, %save ], [ %next, %byte ]
 %done = icmp eq i64 %i, %n
 br i1 %done, label %ret, label %byte
byte:
 %bp = getelementptr i8, ptr %p, i64 %i
 store i8 0, ptr %bp
 %next = add i64 %i, 1
 br label %zero
ret:
 ret ptr %p
}
define ptr @__bennett_rt_ss_push(i64 %n, i64 %a) {
 %p = call ptr @__bennett_ss_extend(i64 %n, i64 %a, i64 1)
 ret ptr %p
}
define ptr @__bennett_rt_ss_alloca(i64 %n, i64 %a) {
 %p = call ptr @__bennett_ss_extend(i64 %n, i64 %a, i64 0)
 ret ptr %p
}
define void @__bennett_rt_ss_pop(ptr %p) {
entry:
 %pi = ptrtoint ptr %p to i64
 %count = load i64, ptr @__bennett_ss_count
 br label %loop
loop:
 %i = phi i64 [ 0, %entry ], [ %next, %skip ]
 %done = icmp eq i64 %i, %count
 br i1 %done, label %bad, label %test
test:
 %slot = getelementptr [CAP x [3 x i64]], ptr @__bennett_ss_entries, i64 0, i64 %i, i64 0
 %base = load i64, ptr %slot
 %kp = getelementptr i8, ptr %slot, i64 16
 %kind = load i64, ptr %kp
 %eq = icmp eq i64 %base, %pi
 %frame = icmp eq i64 %kind, 1
 %match = and i1 %eq, %frame
 br i1 %match, label %found, label %skip
skip:
 %next = add i64 %i, 1
 br label %loop
bad:
 call void @__bennett_nz_fault(i64 7)
 unreachable
found:
 %prev = getelementptr i8, ptr %p, i64 -16
 %sp = load i64, ptr %prev
 store i64 %sp, ptr @__bennett_ss_sp
 store i64 %i, ptr @__bennett_ss_count
 %sc = load i64, ptr @__bennett_ss_nsaves
 br label %saves
saves:
 %j = phi i64 [0, %found], [%jn, %keepsave]
 %se = icmp eq i64 %j, %sc
 br i1 %se, label %finish, label %testsave
testsave:
 %sv = getelementptr [CAP x i64], ptr @__bennett_ss_saves, i64 0, i64 %j
 %so = load i64, ptr %sv
 %released = icmp ult i64 %sp, %so
 br i1 %released, label %finish, label %keepsave
keepsave:
 %jn = add i64 %j, 1
 br label %saves
finish:
 store i64 %j, ptr @__bennett_ss_nsaves
 ret void
}
define void @__bennett_rt_ss_check(ptr %p, i64 %n) {
 %pi = ptrtoint ptr %p to i64
 %end = add i64 %pi, %n
 %wrap = icmp ult i64 %end, %pi
 br i1 %wrap, label %bad, label %range
range:
 %base = load ptr, ptr @__bennett_ss_base
 %bi = ptrtoint ptr %base to i64
 %size = load i64, ptr @__bennett_ss_size
 %be = add i64 %bi, %size
 %lo = icmp ule i64 %bi, %pi
 %hi = icmp ult i64 %pi, %be
 %inside = and i1 %lo, %hi
 br i1 %inside, label %setup, label %ok
setup:
 %count = load i64, ptr @__bennett_ss_count
 br label %loop
loop:
 %i = phi i64 [ 0, %setup ], [ %next, %skip ]
 %done = icmp eq i64 %i, %count
 br i1 %done, label %bad, label %test
test:
 %slot = getelementptr [CAP x [3 x i64]], ptr @__bennett_ss_entries, i64 0, i64 %i, i64 0
 %b = load i64, ptr %slot
 %sz = getelementptr i8, ptr %slot, i64 8
 %s = load i64, ptr %sz
 %e = add i64 %b, %s
 %l = icmp ule i64 %b, %pi
 %h = icmp ule i64 %end, %e
 %live = and i1 %l, %h
 br i1 %live, label %ok, label %skip
skip:
 %next = add i64 %i, 1
 br label %loop
bad:
 call void @__bennett_nz_fault(i64 7)
 unreachable
ok:
 ret void
}
define ptr @__bennett_rt_ss_save() {
entry:
 %base = load ptr, ptr @__bennett_ss_base
 %sp = load i64, ptr @__bennett_ss_sp
 %p = getelementptr i8, ptr %base, i64 %sp
 %count = load i64, ptr @__bennett_ss_nsaves
 br label %loop
loop:
 %i = phi i64 [0, %entry], [%next, %skip]
 %end = icmp eq i64 %i, %count
 br i1 %end, label %append, label %test
test:
 %slot = getelementptr [CAP x i64], ptr @__bennett_ss_saves, i64 0, i64 %i
 %value = load i64, ptr %slot
 %eq = icmp eq i64 %value, %sp
 br i1 %eq, label %done, label %skip
skip:
 %next = add i64 %i, 1
 br label %loop
append:
 %new = getelementptr [CAP x i64], ptr @__bennett_ss_saves, i64 0, i64 %count
 store i64 %sp, ptr %new
 %n = add i64 %count, 1
 store i64 %n, ptr @__bennett_ss_nsaves
 br label %done
done:
 ret ptr %p
}
define void @__bennett_rt_ss_restore(ptr %saved) {
entry:
 %base = load ptr, ptr @__bennett_ss_base
 %bi = ptrtoint ptr %base to i64
 %si = ptrtoint ptr %saved to i64
 %offset = sub i64 %si, %bi
 %sp = load i64, ptr @__bennett_ss_sp
 %bad = icmp ult i64 %sp, %offset
 br i1 %bad, label %fault, label %setup
setup:
 %count = load i64, ptr @__bennett_ss_nsaves
 br label %search
search:
 %i = phi i64 [0, %setup], [%next, %skip]
 %end = icmp eq i64 %i, %count
 br i1 %end, label %fault, label %test
test:
 %slot = getelementptr [CAP x i64], ptr @__bennett_ss_saves, i64 0, i64 %i
 %value = load i64, ptr %slot
 %eq = icmp eq i64 %value, %offset
 br i1 %eq, label %found, label %skip
skip:
 %next = add i64 %i, 1
 br label %search
fault:
 call void @__bennett_nz_fault(i64 7)
 unreachable
found:
 %entries = load i64, ptr @__bennett_ss_count
 br label %logical
logical:
 %j = phi i64 [0, %found], [%jn, %keep]
 %all = icmp eq i64 %j, %entries
 br i1 %all, label %done, label %check
check:
 %ep = getelementptr [CAP x [3 x i64]], ptr @__bennett_ss_entries, i64 0, i64 %j, i64 0
 %eb = load i64, ptr %ep
 %released = icmp ule i64 %si, %eb
 br i1 %released, label %done, label %keep
keep:
 %jn = add i64 %j, 1
 br label %logical
done:
 store i64 %j, ptr @__bennett_ss_count
 store i64 %offset, ptr @__bennett_ss_sp
 ; Saved points after this restore are invalid. Creation order is monotone
 ; between restores, so retaining the found prefix implements that rule.
 %n = add i64 %i, 1
 store i64 %n, ptr @__bennett_ss_nsaves
 ret void
}
)ir"
