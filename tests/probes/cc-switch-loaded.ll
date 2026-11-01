; Dialect 0.2.10 §§14.8/16.4/17.4: switch compare trees and block parameters.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
@cell = internal global i64 42
define i64 @top(i64 %x) {
entry:
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  store volatile i64 %x, ptr @cell
  %value = load volatile i64, ptr @cell
  switch i64 %value, label %done [ i64 -9223372036854775808, label %done
                                 i64 -9223372036854775807, label %case ]
case:
  store volatile i64 123, ptr @cell
  br label %done
done:
  %r = phi i64 [ %value, %entry ], [ %value, %entry ], [ 123, %case ]
  ret i64 %r
}
