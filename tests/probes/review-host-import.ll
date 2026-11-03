target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare i32 @host_fn(i32)
define i32 @top(i32 %x) {
 %q = call ptr @__bennett_qalloc(i64 0, i64 1)
 call void @__bennett_qfree(ptr %q)
 %safe = icmp eq i32 %x, 0
 br i1 %safe, label %done, label %external
external:
 %z = call i32 @host_fn(i32 %x)
 ret i32 %z
done:
 ret i32 7
}
