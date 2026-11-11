// §12.1 N4 follows N28: retain the personality while any EH representation
// still needs it, including native EH intrinsics without an unwind edge.
static bool unloweredPersonalityUse(const Instruction &instruction) {
  if(instruction.isEHPad() || isa<InvokeInst>(instruction) || isa<ResumeInst>(instruction) || isa<CatchReturnInst>(instruction) || isa<CleanupReturnInst>(instruction))return true;
  auto *intrinsic=dyn_cast<IntrinsicInst>(&instruction);
  return intrinsic && intrinsic->getCalledFunction()->getName().starts_with("llvm.eh.");
}
static void normaliseUnusedPersonality(Function &function) {
  if(!function.hasPersonalityFn())return;
  for(auto &instruction:instructions(function))if(unloweredPersonalityUse(instruction))return;
  function.setPersonalityFn(nullptr);
}
