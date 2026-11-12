@msg = private constant [2 x i8] c"x\0A"
@__bennett_rt_eh = global {i32, i32, ptr} zeroinitializer
declare void @__bennett_effect_console_write(ptr, i64)

define void @__bennett_rt_exit(i32 %status) {
  store i32 4, ptr @__bennett_rt_eh
  store i32 %status, ptr getelementptr ({i32, i32, ptr}, ptr @__bennett_rt_eh, i64 0, i32 1)
  ret void
}

define internal void @maybe_exit(i1 %exit) {
  br i1 %exit, label %stop, label %done
stop:
  call void @__bennett_effect_console_write(ptr @msg, i64 2)
  call void @__bennett_rt_exit(i32 3)
  unreachable
done:
  ret void
}

; The musl long-double path carries x86_fp80 bits in an i80 result.
define internal i80 @bits80(i1 %exit) {
  call void @maybe_exit(i1 %exit)
  %bits = bitcast x86_fp80 0xK3FFF8000000000000000 to i80
  ret i80 %bits
}

define internal i128 @bits128(i1 %exit) {
  call void @maybe_exit(i1 %exit)
  ret i128 -1
}

; Cover the first integer width above the i64 zero carrier as well.
define internal i65 @bits65(i1 %exit) {
  call void @maybe_exit(i1 %exit)
  ret i65 -1
}

define i32 @main(i32 %argc, ptr %argv, ptr %envp) {
  %a = call i80 @bits80(i1 false)
  %b = call i128 @bits128(i1 false)
  %wide = call i65 @bits65(i1 false)
  %ok80 = icmp eq i80 %a, 302222231531620438900736
  %ok128 = icmp eq i128 %b, -1
  %ok65 = icmp eq i65 %wide, -1
  %ab = and i1 %ok80, %ok128
  %ok = and i1 %ab, %ok65
  br i1 %ok, label %stop, label %bad
stop:
  %unused = call i80 @bits80(i1 true)
  call void @__bennett_effect_console_write(ptr @msg, i64 2)
  ret i32 99
bad:
  ret i32 98
}
