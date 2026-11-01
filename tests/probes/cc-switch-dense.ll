; Dialect 0.2.10 §§14.8/16.4/17.4: switch compare trees and block parameters.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define i64 @top(i64 %x) {
entry:
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  switch i64 %x, label %done [
    i64 7, label %c0
    i64 0, label %c1
    i64 6, label %c2
    i64 1, label %c0
    i64 5, label %c1
    i64 2, label %c2
    i64 4, label %c0
    i64 3, label %c1
  ]
c0:
  br label %done
c1:
  br label %done
c2:
  br label %done
done:
  %r = phi i64 [ 99, %entry ], [ 10, %c0 ], [ 20, %c1 ], [ 30, %c2 ]
  ret i64 %r
}
