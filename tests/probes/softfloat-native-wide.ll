; §13.1 M>128 slot ABI in the native comparison build, with real pinned arith.
define i192 @roundtrip(i192 %x) {
 %f = sitofp i192 %x to double
 %r = fptosi double %f to i192
 ret i192 %r
}
declare ptr @__bennett_rt_ss_push(i64, i64)
declare void @__bennett_rt_ss_pop(ptr)
define i32 @main() {
 %frame = call ptr @__bennett_rt_ss_push(i64 8, i64 8)
 store i64 123, ptr %frame
 %a = call i192 @roundtrip(i192 1569275433846670190958947355801916604025588861116008628224)
 %b = call i192 @roundtrip(i192 -1569275433846670190958947355801916604025588861116008628224)
 %c = call i192 @roundtrip(i192 0)
 %d = call i192 @roundtrip(i192 -1)
 %ok0 = icmp eq i192 %a, 1569275433846670190958947355801916604025588861116008628224
 %ok1 = icmp eq i192 %b, -1569275433846670190958947355801916604025588861116008628224
 %ok2 = icmp eq i192 %c, 0
 %ok3 = icmp eq i192 %d, -1
 %ok01 = and i1 %ok0, %ok1
 %ok23 = and i1 %ok2, %ok3
 %numbers = and i1 %ok01, %ok23
 %saved = load i64, ptr %frame
 %preserved = icmp eq i64 %saved, 123
 call void @__bennett_rt_ss_pop(ptr %frame)
 %ok = and i1 %numbers, %preserved
 %bad = xor i1 %ok, true
 %r = zext i1 %bad to i32
 ret i32 %r
}
