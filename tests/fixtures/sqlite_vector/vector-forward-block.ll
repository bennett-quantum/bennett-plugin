target datalayout = "e-p:64:64"
define i32 @top() {
entry:
  br label %producer
consumer:
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
producer:
  %v = add <2 x i32> <i32 1, i32 3>, <i32 4, i32 4>
  br label %consumer
}
