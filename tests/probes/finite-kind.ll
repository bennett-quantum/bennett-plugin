define internal i8 @f(i8 %x) { %v = add i8 %x, 1
 ret i8 %v }
define internal i8 @g(i8 %x) { %v = add i8 %x, 2
 ret i8 %v }
define void @top(i1 %choose) {
 %x = call ptr @__bennett_qalloc(i64 0, i64 8)
 %t = call ptr @__bennett_qalloc(i64 0, i64 8)
 %fault = call ptr @__bennett_qalloc(i64 0, i64 4)
 %desc = alloca [64 x i8]
 %p0 = getelementptr i8, ptr %desc, i64 0
 store i32 2, ptr %p0
%p1 = getelementptr i8, ptr %desc, i64 4
 store i32 1, ptr %p1
%p2 = getelementptr i8, ptr %desc, i64 8
 store i32 0, ptr %p2
%p3 = getelementptr i8, ptr %desc, i64 12
 store i32 0, ptr %p3
%p4 = getelementptr i8, ptr %desc, i64 16
 store ptr %t, ptr %p4
%p5 = getelementptr i8, ptr %desc, i64 24
 store ptr %fault, ptr %p5
%p6 = getelementptr i8, ptr %desc, i64 32
 %kind = select i1 %choose, i32 1, i32 2
 store i32 %kind, ptr %p6
%p7 = getelementptr i8, ptr %desc, i64 36
 store i32 0, ptr %p7
%p8 = getelementptr i8, ptr %desc, i64 40
 store ptr %x, ptr %p8
%p9 = getelementptr i8, ptr %desc, i64 48
 store i64 0, ptr %p9
%p10 = getelementptr i8, ptr %desc, i64 56
 store i64 0, ptr %p10
 call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)
call void @__bennett_oracle(ptr @g, ptr null, ptr %desc)
call void @__bennett_oracle(ptr @g, ptr null, ptr %desc)
call void @__bennett_oracle(ptr @f, ptr null, ptr %desc)
 call void @__bennett_qfree(ptr %fault)
 call void @__bennett_qfree(ptr %t)
 call void @__bennett_qfree(ptr %x)
 ret void
}
declare ptr @__bennett_qalloc(i64, i64)
declare void @__bennett_qfree(ptr)
declare void @__bennett_oracle(ptr, ptr, ptr)
