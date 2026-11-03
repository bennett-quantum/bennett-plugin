target datalayout = "e-p:64:64"
@g = internal global [8 x i64] zeroinitializer
define internal ptr @rec(ptr %p, i64 %n) {
 %q = getelementptr i8, ptr %p, i64 8
 %c = icmp eq i64 %n, 0
 br i1 %c, label %done, label %more
more:
 %m = sub i64 %n, 1
 %r = call ptr @rec(ptr %q, i64 %m)
 ret ptr %r
done:
 ret ptr %p
}
define ptr @top(i64 %n) {
 %r = call ptr @rec(ptr @g, i64 %n)
 ret ptr %r
}
