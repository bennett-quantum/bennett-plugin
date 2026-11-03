target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define i8 @top(i8 %x) {
entry:
%q = call ptr @__bennett_qalloc(i64 0, i64 1)
call void @__bennett_qfree(ptr %q)
br label %def
use:
%z = add i8 %y, 1
ret i8 %z
def:
%y = add i8 %x, 2
br label %use
}
