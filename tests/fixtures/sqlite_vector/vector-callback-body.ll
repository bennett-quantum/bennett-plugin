declare <2 x i32> @identity(<2 x i32>)
define i32 @check(ptr %fn) {
  %same = icmp eq ptr %fn, @identity
  br i1 %same, label %invoke, label %wrong
invoke:
  %v = call <2 x i32> %fn(<2 x i32> <i32 1, i32 3>)
  %r = extractelement <2 x i32> %v, i32 1
  ret i32 %r
wrong:
  ret i32 99
}
