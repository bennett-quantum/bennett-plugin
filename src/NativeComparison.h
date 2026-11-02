#pragma once
#include "llvm/IR/PassManager.h"

namespace bennett {
void addNativeComparisonPass(llvm::ModulePassManager &);
void addNativeHostImportsPass(llvm::ModulePassManager &);
void addNativeFinalisePass(llvm::ModulePassManager &);
}
