; Independent source for the fixed one-live-entry runtime contract microvector
; (§16, entry-stack); this is not the general replay loop or N24 map.
@ss_state = internal global [3 x i64] zeroinitializer, align 8

define void @__bennett_rt_entry_replay(ptr %s) #0 {
 %t0 = getelementptr i8, ptr %s, i64 8
 %n = load i64, ptr %t0
 %p = call ptr @__bennett_nz_alloc(i64 %n)
 %t1 = getelementptr i8, ptr %s, i64 24
 %v0 = load i128, ptr %t1
 store i128 %v0, ptr @ss_state
 %t2 = getelementptr i8, ptr %t1, i64 16
 %v1 = load i64, ptr %t2
 %t3 = getelementptr i8, ptr @ss_state, i64 16
 store i64 %v1, ptr %t3
 %t4 = getelementptr i8, ptr %s, i64 48
 %v2 = load i128, ptr %t4
 store i128 %v2, ptr %p
 ret void
}
define void @__bennett_rt_ss_init(i64 %size) #1 {
 %b = load ptr, ptr @ss_state
 %c = icmp eq ptr %b, null
 br i1 %c, label %init, label %done
init:
 %p = call ptr @__bennett_nz_alloc(i64 %size)
 store ptr %p, ptr @ss_state
 br label %done
done:
 ret void
}
define ptr @f() {
 %p = call ptr @__bennett_nz_alloc(i64 16)
 ret ptr %p
}
declare ptr @__bennett_nz_alloc(i64)
attributes #0 = { "bennett.runtime.locations" }
attributes #1 = { "bennett.runtime.locations" "bennett.runtime.constants"="z" }
!llvm.module.flags = !{!0,!1,!2,!3,!4,!5}
!0 = !{i32 1, !"bennett.entry.snapshot", i64 6}
!1 = !{i32 1, !"bennett.ss.init", i64 1}
!2 = !{i32 1, !"bennett.null_size", i64 256}
!3 = !{i32 1, !"bennett.heap_base", i64 4096}

!4 = !{i32 1, !"bennett.sstack", i64 16}

!5 = !{i32 1, !"bennett.region_base", i64 8192}
