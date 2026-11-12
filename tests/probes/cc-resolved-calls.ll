; Reduced musl init/fini call shapes: the called operand resolves to a
; function, but getCalledFunction() is null for a differing call type or alias.
; Both calls must execute: dropping either changes the returned value.
target datalayout = "e-m:e-p270:32:32-p271:32:32-p272:64:64-i64:64-f80:128-n8:16:32:64-S128"
target triple = "x86_64-unknown-linux-gnu"

@state = internal global i32 0, align 4
@fini = internal alias void (...), ptr @finish

define internal void @init() {
  store i32 20, ptr @state, align 4
  ret void
}

define internal void @finish() {
  %before = load i32, ptr @state, align 4
  %after = add i32 %before, 22
  store i32 %after, ptr @state, align 4
  ret void
}

define i32 @main() {
  call void (...) @init()
  call void (...) @fini()
  %result = load i32, ptr @state, align 4
  ret i32 %result
}
