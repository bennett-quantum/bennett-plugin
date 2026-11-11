#pragma once
#include "llvm/IR/Constants.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include <map>
namespace bennett {
// Recover constant-only casts/GEPs for the established L operand recipe before
// its analysis and residual validation. CC/R keeps their instruction form.
class ScalarConstantOperands {
  std::map<llvm::Instruction *,llvm::Constant *> values;
  llvm::Constant *constant(llvm::Value *value) {
    using namespace llvm;
    if(auto *literal=dyn_cast<Constant>(value))return literal;
    auto *instruction=dyn_cast<Instruction>(value);
    if(!instruction)return nullptr;
    auto *metadata=instruction->getMetadata("bennett.constant.operand");
    if(!metadata)return nullptr;
    auto found=values.find(instruction);if(found!=values.end())return found->second;
    values[instruction]=nullptr;
    auto *expression=metadata && metadata->getNumOperands()==1?
      mdconst::dyn_extract<ConstantExpr>(metadata->getOperand(0)):nullptr;
    if(!expression || expression->getOpcode()!=instruction->getOpcode() ||
        expression->getType()!=instruction->getType())return nullptr;
    SmallVector<Constant *> operands;
    for(auto &operand:instruction->operands()) {
      auto *literal=constant(operand);if(!literal)return nullptr;
      operands.push_back(literal);
    }
    auto *result=expression->getWithOperands(operands,expression->getType());
    values[instruction]=result;return result;
  }
public:
  void run(llvm::Module &module) {
    llvm::SmallVector<llvm::Instruction *> erase;
    for(auto &function:module)for(auto &instruction:llvm::instructions(function))
      if(auto *value=constant(&instruction)) {
        instruction.replaceAllUsesWith(value);erase.push_back(&instruction);
      }
    for(auto *instruction:erase)instruction->eraseFromParent();
  }
};
}
