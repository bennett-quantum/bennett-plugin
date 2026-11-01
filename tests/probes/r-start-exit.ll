@msg = private constant [2 x i8] c"x\0A"
@__bennett_rt_eh = global {i32, i32, ptr} zeroinitializer
declare void @__bennett_effect_console_write(ptr, i64)
define void @__bennett_rt_exit(i32 %status) {
  store i32 4, ptr @__bennett_rt_eh
  store i32 %status, ptr getelementptr ({i32, i32, ptr}, ptr @__bennett_rt_eh, i64 0, i32 1)
  ret void
}
define internal void @nested() {
  call void @__bennett_effect_console_write(ptr @msg, i64 2)
  call void @__bennett_rt_exit(i32 3)
  unreachable
}
define i32 @main(i32 %argc, ptr %argv, ptr %envp) {
  call void @nested()
  call void @__bennett_effect_console_write(ptr @msg, i64 2)
  ret i32 99
}
