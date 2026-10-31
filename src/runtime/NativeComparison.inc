R"ir(
define void @__bennett_rt_memmove(ptr %d, ptr %s, i64 %n) {
entry:
 %zero = icmp eq i64 %n, 0
 br i1 %zero, label %done, label %direction
direction:
 %back = icmp ugt ptr %d, %s
 br i1 %back, label %reverse, label %forward
forward:
 %i = phi i64 [0, %direction], [%next, %forward]
 %sp = getelementptr i8, ptr %s, i64 %i
 %v = load i8, ptr %sp, align 1
 %dp = getelementptr i8, ptr %d, i64 %i
 store i8 %v, ptr %dp, align 1
 %next = add i64 %i, 1
 %more = icmp ult i64 %next, %n
 br i1 %more, label %forward, label %done
reverse:
 %end = phi i64 [%n, %direction], [%j, %reverse]
 %j = sub i64 %end, 1
 %rsp = getelementptr i8, ptr %s, i64 %j
 %rv = load i8, ptr %rsp, align 1
 %rdp = getelementptr i8, ptr %d, i64 %j
 store i8 %rv, ptr %rdp, align 1
 %again = icmp ne i64 %j, 0
 br i1 %again, label %reverse, label %done
done:
 ret void
}
define void @__bennett_rt_memset(ptr %d, i8 %v, i64 %n) {
entry:
 %zero = icmp eq i64 %n, 0
 br i1 %zero, label %done, label %loop
loop:
 %i = phi i64 [0, %entry], [%next, %loop]
 %p = getelementptr i8, ptr %d, i64 %i
 store i8 %v, ptr %p, align 1
 %next = add i64 %i, 1
 %more = icmp ult i64 %next, %n
 br i1 %more, label %loop, label %done
done:
 ret void
}
define void @__bennett_nz_fault(i64 %code) {
 call void @llvm.trap()
 unreachable
}
declare void @llvm.trap()
)ir"
