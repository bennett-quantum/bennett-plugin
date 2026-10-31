; §16.4: depth-first fields, packed calls/returns, and unchanged insert fields.
target datalayout = "e-p:64:64"
%pair = type { i24, [2 x i8], i1 }
define internal %pair @relay(%pair %p, i1 %c) {
entry:
  %old = extractvalue %pair %p, 1
  %a = extractvalue [2 x i8] %old, 0
  %b = add i8 %a, 1
  %edit = insertvalue [2 x i8] %old, i8 %b, 1
  %updated = insertvalue %pair %p, [2 x i8] %edit, 1
  %chosen = select i1 %c, %pair %updated, %pair %p
  br i1 %c, label %yes, label %no
yes: br label %end
no: br label %end
end:
  %merged = phi %pair [ %chosen, %yes ], [ %p, %no ]
  %stable = freeze %pair %merged
  ret %pair %stable
}
define i64 @top(i64 %x) {
  %n = trunc i64 %x to i24
  %a = insertvalue %pair { i24 0, [2 x i8] [i8 7, i8 11], i1 true }, i24 %n, 0
  %r = call %pair @relay(%pair %a, i1 true)
  %v = extractvalue %pair %r, 0
  %b = extractvalue %pair %r, 1, 1
  %flag = extractvalue %pair %r, 2
  %w = zext i24 %v to i64
  %bw = zext i8 %b to i64
  %fw = zext i1 %flag to i64
  %sum = add i64 %w, %bw
  %out = add i64 %sum, %fw
  ret i64 %out
}
