; The consumer's {i64,i64} result and the single-field identity case.
target datalayout = "e-p:64:64"
@fp = internal constant ptr @single
define internal {i64, i64} @pair(i64 %x) {
  %next = add i64 %x, 3
  %a = insertvalue {i64, i64} zeroinitializer, i64 %x, 0
  %b = insertvalue {i64, i64} %a, i64 %next, 1
  ret {i64, i64} %b
}
define internal {i64} @single(i64 %x) !bennett.address !900 {
  %r = insertvalue {i64} zeroinitializer, i64 %x, 0
  ret {i64} %r
}
define i64 @top(i64 %x) {
  %pair = call {i64, i64} @pair(i64 %x)
  %field = extractvalue {i64, i64} %pair, 1
  %fn = load ptr, ptr @fp
  %r = call {i64} %fn(i64 %field)
  %result = extractvalue {i64} %r, 0
  ret i64 %result
}

!900 = !{i64 8192}
