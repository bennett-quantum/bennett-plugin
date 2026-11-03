target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_ctrl(ptr, i64, ptr, ptr, ptr)
define internal void @act(ptr %env) { ret void }
define void @top() {
%q = call ptr @__bennett_qalloc(i64 0, i64 1)
call void @__bennett_ctrl(ptr %q, i64 0, ptr @act, ptr null, ptr null)
call void @__bennett_qfree(ptr %q)
ret void
}
