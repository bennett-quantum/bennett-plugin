target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
define void @top(i32 %op) {
%q = call ptr @__bennett_qalloc(i64 0, i64 1)
call void @__bennett_gate(i32 %op, ptr %q, i64 0)
call void @__bennett_qfree(ptr %q)
ret void
}
