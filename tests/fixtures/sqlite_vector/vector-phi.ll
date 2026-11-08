; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/vector-phi.ll (design reproducer).
target datalayout = "e-p:64:64"
define i32 @top(i1 %c) {
entry:
  br i1 %c, label %left, label %right
left:
  br label %join
right:
  br label %join
join:
  %v = phi <2 x i32> [ <i32 1, i32 3>, %left ], [ <i32 5, i32 7>, %right ]
  %r = extractelement <2 x i32> %v, i32 0
  ret i32 %r
}
