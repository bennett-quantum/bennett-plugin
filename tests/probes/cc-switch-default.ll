; Dialect 0.2.10 §§14.8/16.4/17.4: switch compare trees and block parameters.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define i64 @top(i64 %x) {
entry:
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  switch i64 %x, label %done []
done:
  %r = phi i64 [ %x, %entry ]
  ret i64 %r
}
