; PT6: equal [4,12) contributes PTR(@hc,0), even with partial neighbors.
; All pointer accesses at byte offset 4 use align 1.
target datalayout = "e-p:64:64-i64:64-n8:16:32:64"
@g = internal global [64 x i8] zeroinitializer
@hc = internal global ptr null
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_gate(i32, ptr, i64)
declare void @__bennett_qfree(ptr)
define void @top() {
entry:
 %h = call ptr @__bennett_qalloc(i64 0, i64 1)
 store ptr %h, ptr @hc, align 8
 ; Store set {0,4,8}; write 4 last so the concrete pointer stays intact.
 %at0 = getelementptr i8, ptr @g, i64 0
 %at8 = getelementptr i8, ptr @g, i64 8
 %at4store = getelementptr i8, ptr @g, i64 4
 store ptr @hc, ptr %at0, align 1
 store ptr @hc, ptr %at8, align 1
 store ptr @hc, ptr %at4store, align 1
 %at4 = getelementptr i8, ptr @g, i64 4
 %x = load ptr, ptr %at4, align 1
 %hh = load ptr, ptr %x, align 1
 call void @__bennett_gate(i32 1, ptr %hh, i64 0)
 call void @__bennett_gate(i32 1, ptr %hh, i64 0)
 call void @__bennett_qfree(ptr %h)
 ret void
}
