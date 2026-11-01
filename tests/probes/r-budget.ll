@msg = private constant [1 x i8] c"x"
declare void @__bennett_effect_console_write(ptr, i64)
define i32 @main() {
  call void @__bennett_effect_console_write(ptr @msg, i64 1)
  ret i32 0
}
