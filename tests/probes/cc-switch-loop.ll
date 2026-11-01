; Dialect 0.2.10 §§14.8/16.4/17.4: switch compare trees and block parameters.
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
define i64 @top(i64 %x) {
entry:
  %q = call ptr @__bennett_qalloc(i64 0, i64 1)
  call void @__bennett_qfree(ptr %q)
  br label %loop
loop:
  %i = phi i64 [ 0, %entry ], [ %next, %back ], [ %next, %step ]
  %a = phi i64 [ 3, %entry ], [ %v, %back ], [ %plus, %step ]
  %b = phi i64 [ 7, %entry ], [ %u, %back ], [ %a, %step ]
  %stop = icmp eq i64 %i, %x
  %next = add i64 %i, 1
  %plus = add i64 %a, %b
  switch i1 %stop, label %step [ i1 true, label %done ]
step:
  %key = urem i64 %i, 3
  switch i64 %key, label %loop [ i64 0, label %swap ]
swap:
  ; A separate switch self-edge below exercises parallel phi swaps.
  br label %again
again:
  %j = phi i64 [ 0, %swap ], [ %jnext, %again ], [ %jnext, %again ]
  %u = phi i64 [ %a, %swap ], [ %v, %again ], [ %v, %again ]
  %v = phi i64 [ %b, %swap ], [ %u, %again ], [ %u, %again ]
  %jnext = add i64 %j, 1
  switch i64 %j, label %back [ i64 0, label %again
                                      i64 1, label %again ]
back:
  br label %loop
done:
  %r = add i64 %a, %b
  ret i64 %r
}
