// N23 can call a nonvariadic implementation through a variadic alias (_fini).
// Such an implementation receives its fixed parameters and ignores the va block.
static bool ignoresVarargsBlock(const CallBase &call, const Function &callee) {
  auto *metadata=call.getMetadata("bennett.varargs.fixed");
  auto *fixed=metadata?mdconst::dyn_extract<ConstantInt>(metadata->getOperand(0)):nullptr;
  if(!fixed || callee.isVarArg() || callee.arg_size()!=fixed->getZExtValue() ||
      callee.getReturnType()!=call.getType())return false;
  for(unsigned k=0;k<callee.arg_size();++k)
    if(callee.getArg(k)->getType()!=call.getArgOperand(k)->getType())return false;
  return true;
}

static bool compatibleProcessCall(const CallBase &call, const Function &callee) {
  return callee.getFunctionType()==call.getFunctionType() || ignoresVarargsBlock(call,callee);
}

static std::vector<std::string> processCallOperands(const CallBase &call,
    const Function &callee, std::vector<std::string> operands) {
  if(ignoresVarargsBlock(call,callee))operands.pop_back();
  return operands;
}

// §14.7: an exit-group runtime body can end in a noreturn loop after setting
// the complete EH record. Propagate at that control transfer, after its stores.
static bool shouldPropagateProcessExit(bool reversible, const GlobalVariable *state,
                                       const Instruction *control) {
  if(!reversible || !state)return false;
  if(!control)return true;
  if(!control->isTerminator() || isa<ReturnInst>(control))return false;
  for(auto &instruction:*control->getParent())
    if(auto *store=dyn_cast<StoreInst>(&instruction);
        store && getUnderlyingObject(store->getPointerOperand())==state)return true;
  return false;
}
