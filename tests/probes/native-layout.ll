target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-pc-linux-gnu"
@native_data = global i64 41, align 8
@native_table = constant [2 x ptr] [ptr @native_data, ptr @native_callback], align 8
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define internal i64 @native_callback(i64 %x) {
 %r = add i64 %x, 17
 ret i64 %r
}
define i64 @native_addresses(i64 %mode) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %q)
 switch i64 %mode, label %invoke [i64 0, label %data i64 1, label %function]
data:
 %d = ptrtoint ptr @native_data to i64
 ret i64 %d
function:
 %f = ptrtoint ptr @native_callback to i64
 ret i64 %f
invoke:
 %slot = getelementptr [2 x ptr], ptr @native_table, i64 0, i64 1
 %callee = load ptr, ptr %slot, align 8
 %result = call i64 %callee(i64 25)
 ret i64 %result
}
