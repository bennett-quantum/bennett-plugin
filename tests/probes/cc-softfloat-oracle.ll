define internal i1 @region(i64 %x) { %a = bitcast i64 %x to double
 %r = fcmp une double %a, 0.0
 ret i1 %r }
define void @top() {
 %d = alloca [64 x i8], align 8
 %q = call ptr @__bennett_qalloc(i64 0,i64 64)
 %t = call ptr @__bennett_qalloc(i64 0,i64 1)
 %f = call ptr @__bennett_qalloc(i64 0,i64 4)
 %p0 = getelementptr i8, ptr %d, i64 0
 store i32 2, ptr %p0
%p1 = getelementptr i8, ptr %d, i64 4
 store i32 1, ptr %p1
%p2 = getelementptr i8, ptr %d, i64 8
 store i32 0, ptr %p2
%p3 = getelementptr i8, ptr %d, i64 12
 store i32 0, ptr %p3
%p4 = getelementptr i8, ptr %d, i64 16
 store ptr %t, ptr %p4
%p5 = getelementptr i8, ptr %d, i64 24
 store ptr %f, ptr %p5
%p6 = getelementptr i8, ptr %d, i64 32
 store i32 1, ptr %p6
%p7 = getelementptr i8, ptr %d, i64 36
 store i32 0, ptr %p7
%p8 = getelementptr i8, ptr %d, i64 40
 store ptr %q, ptr %p8
%p9 = getelementptr i8, ptr %d, i64 48
 store i64 0, ptr %p9
%p10 = getelementptr i8, ptr %d, i64 56
 store i64 0, ptr %p10
 call void @__bennett_oracle(ptr @region,ptr null,ptr %d)
 call void @__bennett_oracle(ptr @region,ptr null,ptr %d)
 call void @__bennett_qfree(ptr %f)
 call void @__bennett_qfree(ptr %t)
 call void @__bennett_qfree(ptr %q)
 ret void }
declare ptr @__bennett_qalloc(i64,i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_oracle(ptr,ptr,ptr)
