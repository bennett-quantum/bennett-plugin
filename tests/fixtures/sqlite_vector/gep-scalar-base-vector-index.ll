; Source: bennett/.tmp/orchestrator/s2-1bb/work/fixtures/gep-scalar-base-vector-index.ll (design reproducer).
target datalayout = "e-p:64:64"
@buf = internal global [8 x i32] zeroinitializer
define i64 @top() {
  %p = getelementptr i32, ptr @buf, <2 x i64> <i64 1, i64 3>
  %p0 = extractelement <2 x ptr> %p, i32 0
  %p1 = extractelement <2 x ptr> %p, i32 1
  %i0 = ptrtoint ptr %p0 to i64
  %i1 = ptrtoint ptr %p1 to i64
  %r = sub i64 %i1, %i0
  ret i64 %r
}
