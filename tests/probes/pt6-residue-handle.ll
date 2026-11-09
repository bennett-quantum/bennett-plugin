; PT6: equal [4,12) contributes PTR(@hc,0), even with partial neighbors.
; This two-iteration loop writes offsets 0 and 4; align 1 makes offset 4 legal.
; The index form retains stride 4 on both majors; PT9 copies the index exactly.
; A defined identity call prevents SCEV from enumerating just the concrete loop.
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
 br label %loop
loop:
 %i = phi i64 [ 0, %entry ], [ %next, %loop ]
 %index = call i64 @copy_index(i64 %i)
 %p = getelementptr i32, ptr @g, i64 %index
 store ptr @hc, ptr %p, align 1
 %next = add i64 %i, 1
 %again = icmp ult i64 %next, 2
 br i1 %again, label %loop, label %exit
exit:
 %at4 = getelementptr i8, ptr @g, i64 4
 %x = load ptr, ptr %at4, align 1
 %hh = load ptr, ptr %x, align 1
 call void @__bennett_gate(i32 1, ptr %hh, i64 0)
 call void @__bennett_gate(i32 1, ptr %hh, i64 0)
 call void @__bennett_qfree(ptr %h)
 ret void
}

define internal i64 @copy_index(i64 %value) {
 ret i64 %value
}
