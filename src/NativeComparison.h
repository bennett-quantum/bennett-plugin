#pragma once
#include "llvm/IR/PassManager.h"

namespace bennett {
void addNativeComparisonPass(llvm::ModulePassManager &);
}
