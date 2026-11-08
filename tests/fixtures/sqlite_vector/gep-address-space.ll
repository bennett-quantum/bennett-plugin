target datalayout = "e-p:64:64-p270:64:64:64:32"
define i64 @top() {
  %base = inttoptr i64 4294967296 to ptr addrspace(270)
  %p = getelementptr i8, ptr addrspace(270) %base, <2 x i16> <i16 0, i16 -1>
  %p0 = extractelement <2 x ptr addrspace(270)> %p, i32 0
  %p1 = extractelement <2 x ptr addrspace(270)> %p, i32 1
  %i0 = ptrtoint ptr addrspace(270) %p0 to i64
  %i1 = ptrtoint ptr addrspace(270) %p1 to i64
  %r = sub i64 %i1, %i0
  ret i64 %r
}
