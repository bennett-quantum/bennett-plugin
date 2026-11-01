@msg = private constant [1 x i8] c"x"
@callback = global ptr @write_one
declare void @__bennett_effect_console_write(ptr, i64)
define internal void @write_one() {
  call void @__bennett_effect_console_write(ptr @msg, i64 1)
  ret void
}
define i32 @main() {
  %f = load ptr, ptr @callback
  call void %f()
  ret i32 0
}
