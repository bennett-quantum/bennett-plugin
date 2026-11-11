#pragma once
#include "llvm/IR/LLVMContext.h"
namespace bennett {
inline bool retainedNormalisationMetadata(llvm::LLVMContext &context, unsigned kind) {
  for(auto name:{"bennett.rstep","bennett.n22.pack","bennett.varargs.fixed"})
    if(kind==context.getMDKindID(name))return true;
  return false;
}
}
