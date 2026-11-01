@msg = private constant [1 x i8] c"x"
declare void @__bennett_effect_console_write(ptr, i64)
define i32 @main(i32 %argc, ptr %argv, ptr %envp) {
  %bad = icmp ne i32 %argc, 0
  br i1 %bad, label %trapped, label %console
trapped:
  call void asm sideeffect "unlisted-op", "~{memory}"()
  br label %console
console:
  call void asm sideeffect "", "~{memory}"()
  call void @__bennett_effect_console_write(ptr @msg, i64 1)
  ret i32 0
}
