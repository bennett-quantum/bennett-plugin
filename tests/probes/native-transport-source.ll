; Minimal runtime wrappers for the public native adapter, independent of any
; runtime publication. Native support owns transports; source helpers stay fixed.
declare void @__bennett_effect_clock_read(ptr)
declare void @__bennett_effect_entropy_read(ptr, i64)
declare void @__bennett_effect_console_write(ptr, i64)
declare void @__bennett_effect_block_read(i64, ptr)
declare void @__bennett_effect_block_write(i64, ptr)

define void @__bennett_rt_transport_clock_read(ptr %p) {
  call void @__bennett_effect_clock_read(ptr %p)
  ret void
}
define void @__bennett_rt_transport_entropy_read(ptr %p, i64 %n) {
  call void @__bennett_effect_entropy_read(ptr %p, i64 %n)
  ret void
}
define i64 @__bennett_rt_transport_console_write(i64 %fd, ptr %p, i64 %n) {
  call void @__bennett_effect_console_write(ptr %p, i64 %n)
  ret i64 %n
}
define void @__bennett_rt_transport_block_read(i64 %sector, ptr %p) {
  call void @__bennett_effect_block_read(i64 %sector, ptr %p)
  ret void
}
define void @__bennett_rt_transport_block_write(i64 %sector, ptr %p) {
  call void @__bennett_effect_block_write(i64 %sector, ptr %p)
  ret void
}
define void @__bennett_rt_transport_exit(i32 %status) {
  ret void
}
define void @__bennett_rt_source_helper() {
  ret void
}
define void @entry(ptr %p) {
  ; Optimisation may inline transport wrappers into ordinary source functions.
  call void @__bennett_effect_clock_read(ptr %p)
  call void @__bennett_effect_entropy_read(ptr %p, i64 8)
  call void @__bennett_effect_console_write(ptr %p, i64 8)
  call void @__bennett_effect_block_read(i64 0, ptr %p)
  call void @__bennett_effect_block_write(i64 0, ptr %p)
  call void @__bennett_rt_source_helper()
  call void @__bennett_rt_transport_clock_read(ptr %p)
  call void @__bennett_rt_transport_entropy_read(ptr %p, i64 8)
  %n = call i64 @__bennett_rt_transport_console_write(i64 1, ptr %p, i64 8)
  call void @__bennett_rt_transport_block_read(i64 0, ptr %p)
  call void @__bennett_rt_transport_block_write(i64 0, ptr %p)
  call void @__bennett_rt_transport_exit(i32 0)
  ret void
}
