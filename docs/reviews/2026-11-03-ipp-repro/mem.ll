target datalayout = "e-p:64:64"
@g = internal global [8 x i64] zeroinitializer
@cell = internal global ptr @g
define ptr @top(i64 %n) {
entry:
 br label %loop
loop:
 %p = load ptr, ptr @cell
 %q = getelementptr i8, ptr %p, i64 8
 store ptr %q, ptr @cell
 %c = icmp ult i64 %n, 5
 br i1 %c, label %loop, label %exit
exit:
 %r = load ptr, ptr @cell
 ret ptr %r
}
