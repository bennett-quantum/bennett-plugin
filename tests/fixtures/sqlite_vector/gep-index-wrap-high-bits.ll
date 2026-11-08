; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/gep-index-wrap-high-bits.ll (design reproducer).
target datalayout = "e-p:64:64:64:32"
define i64 @top() {
  %base = inttoptr i64 4294967296 to ptr
  %p = getelementptr i8, ptr %base, <2 x i64> <i64 4294967296, i64 -1>
  %p1 = extractelement <2 x ptr> %p, i32 1
  %r = ptrtoint ptr %p1 to i64
  ret i64 %r
}
