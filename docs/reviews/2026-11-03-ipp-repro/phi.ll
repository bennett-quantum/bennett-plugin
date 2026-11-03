target datalayout = "e-p:64:64"
@g = internal global [8 x i64] zeroinitializer
define ptr @top(i64 %n) {
entry:
 br label %loop
loop:
 %p = phi ptr [ @g, %entry ], [ %q, %loop ]
 %q = getelementptr i8, ptr %p, i64 8
 %c = icmp ult ptr %q, null
 br i1 %c, label %loop, label %exit
exit:
 ret ptr %q
}
