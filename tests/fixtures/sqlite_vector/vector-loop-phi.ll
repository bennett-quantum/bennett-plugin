target datalayout = "e-p:64:64"
define i32 @top() {
entry:
  br label %loop
exit:
  %r = extractelement <2 x i32> %v, i32 0
  ret i32 %r
loop:
  %v = phi <2 x i32> [ <i32 1, i32 3>, %entry ], [ %next, %loop ]
  %n = phi i2 [ 0, %entry ], [ %inc, %loop ]
  %next = shufflevector <2 x i32> %v, <2 x i32> zeroinitializer, <2 x i32> <i32 1, i32 0>
  %inc = add i2 %n, 1
  %done = icmp eq i2 %inc, 2
  br i1 %done, label %exit, label %loop
}
