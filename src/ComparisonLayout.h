#pragma once
#include "llvm/IR/Module.h"
#include <optional>

namespace bennett {
void initialiseComparisonLayout(llvm::Module &);
bool hasComparisonLayout();
void checkComparisonMaterialisation(llvm::Module &);
std::optional<uint64_t> comparisonGlobalAddress(const llvm::GlobalVariable &);
std::optional<uint64_t> comparisonFunctionAddress(const llvm::Function &);
std::optional<uint64_t> comparisonHeapBase();
std::string comparisonLayoutDigest();
}
