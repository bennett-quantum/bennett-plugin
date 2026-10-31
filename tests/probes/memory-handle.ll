define void @top() {
 %x = call ptr @__bennett_qalloc(i64 0, i64 1)
 %slot = alloca ptr
 store ptr %x, ptr %slot
 %q = load ptr, ptr %slot
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_gate(i32 1, ptr %q, i64 0)
 call void @__bennett_qfree(ptr %q)
 ret void
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_gate(i32, ptr, i64)
