; Ordinary memcpy alignment joins: poison mask lanes are replaced before use.
declare <4 x i32> @llvm.fshl.v4i32(<4 x i32>, <4 x i32>, <4 x i32>)

define void @vector_funnel_shift(ptr %p, ptr %q, ptr %out) {
  %seed = load i32, ptr %p, align 1
  %tail = load <4 x i32>, ptr %q, align 1
  %shift = shufflevector <4 x i32> %tail, <4 x i32> poison, <4 x i32> <i32 poison, i32 0, i32 1, i32 2>
  %joined = insertelement <4 x i32> %shift, i32 %seed, i64 0
  %r = call <4 x i32> @llvm.fshl.v4i32(<4 x i32> %tail, <4 x i32> %joined, <4 x i32> <i32 8, i32 8, i32 8, i32 8>)
  store <4 x i32> %r, ptr %out, align 1
  ret void
}

define void @vector_funnel_join(ptr %p, ptr %q, ptr %out) {
  %a = load <4 x i32>, ptr %p, align 1
  %b = load <4 x i32>, ptr %q, align 1
  %joined = shufflevector <4 x i32> %a, <4 x i32> %b, <4 x i32> <i32 3, i32 4, i32 5, i32 6>
  %r = call <4 x i32> @llvm.fshl.v4i32(<4 x i32> %b, <4 x i32> %joined, <4 x i32> <i32 24, i32 24, i32 24, i32 24>)
  store <4 x i32> %r, ptr %out, align 1
  ret void
}
