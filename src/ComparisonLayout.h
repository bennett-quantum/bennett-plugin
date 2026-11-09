#pragma once
#include "llvm/IR/Module.h"
#include <optional>

namespace bennett {
// Dialect §§19.5/24: bases shared by the device image and comparison link.
uint64_t comparisonDataBase(uint64_t defaultBase = 4096);
bool hasComparisonDataBaseOverride();
uint64_t comparisonTextBase(uint64_t regionsEnd);
void initialiseComparisonLayout(llvm::Module &);
bool hasComparisonLayout();
void checkComparisonMaterialisation(llvm::Module &);
std::optional<uint64_t> comparisonGlobalAddress(const llvm::GlobalVariable &);
std::optional<uint64_t> comparisonFunctionAddress(const llvm::Function &);
std::optional<uint64_t> comparisonHeapBase();
std::string comparisonLayoutDigest();
}
