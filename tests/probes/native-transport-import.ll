; Transient prepared IR from a native importer: the source alias still names a
; runtime import. Finalisation must remove that alias before LLVM verification.
@source = alias void (), ptr @entry
@transport = alias void (ptr), ptr @__bennett_rt_transport_clock_read

declare void @__bennett_rt_transport_clock_read(ptr)

define void @entry() #0 {
  call void @transport(ptr null)
  ret void
}

attributes #0 = { "bennett.native.materialised.sha256"="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" }

!llvm.module.flags = !{!0}
!0 = !{i32 1, !"bennett.native.prepared", !"{\22schema\22:\22bennett-native-comparison-1\22,\22phase\22:\22prepared\22,\22materialised_sha256\22:\22aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\22,\22symbols\22:[{\22kind\22:\22function\22,\22llvm_name\22:\22entry\22,\22native_symbol\22:\22source\22},{\22kind\22:\22function\22,\22llvm_name\22:\22__bennett_rt_transport_clock_read\22,\22native_symbol\22:\22transport\22}]}"}
