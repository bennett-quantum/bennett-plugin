; N22 true top limb widths and N25 hidden first return pointer (>128 bits).
target datalayout = "e-p:64:64"
%wide = type { i64, i129, [2 x i7] }
define internal %wide @make(i64 %x) {
  %lo = zext i64 %x to i129
  %hi = or i129 %lo, 340282366920938463463374607431768211456
  %a = insertvalue %wide zeroinitializer, i64 %x, 0
  %b = insertvalue %wide %a, i129 %hi, 1
  %c = insertvalue %wide %b, i7 3, 2, 0
  %d = insertvalue %wide %c, i7 5, 2, 1
  %check = icmp eq i64 %x, 0
  %alternate = insertvalue %wide %d, i7 6, 2, 1
  %chosen = select i1 %check, %wide %d, %wide %alternate
  br i1 %check, label %yes, label %no
yes: br label %end
no: br label %end
end:
  %merge = phi %wide [ %chosen, %yes ], [ %chosen, %no ], [ %stable, %end ]
  %iteration = phi i8 [ 0, %yes ], [ 0, %no ], [ %next, %end ]
  %stable = freeze %wide %merge
  %next = add i8 %iteration, 1
  %again = icmp ult i8 %next, 2
  br i1 %again, label %end, label %done
done:
  ret %wide %stable
}
define i64 @top(i64 %x) {
  %r = call %wide @make(i64 %x)
  %a = extractvalue %wide %r, 0
  %b = extractvalue %wide %r, 1
  %c = extractvalue %wide %r, 2, 0
  %d = extractvalue %wide %r, 2, 1
  %hi = lshr i129 %b, 128
  %flag = trunc i129 %hi to i64
  %cw = zext i7 %c to i64
  %dw = zext i7 %d to i64
  %s0 = add i64 %a, %flag
  %s1 = add i64 %s0, %cw
  %out = add i64 %s1, %dw
  ret i64 %out
}
!llvm.module.flags = !{!0}
!0 = !{i32 1, !"bennett.sstack", i64 4096}
