// Inspect the exact module compiled by the numerical drivers, including helpers.
#include "llvm/ADT/STLExtras.h"
#include "llvm/ADT/StringSwitch.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/raw_ostream.h"
#include <optional>
using namespace llvm;

// Dialect §12.4 V14 caps scalar values; N25 makes memory accesses byte-sized.
constexpr unsigned MaxScalarBits = 128;
constexpr unsigned ByteBits = 8;

bool residueType(Type *type, bool memory) {
  if (type->isVectorTy()) return true;
  if (auto *integer = dyn_cast<IntegerType>(type))
    return integer->getBitWidth() > MaxScalarBits || (memory && integer->getBitWidth() % ByteBits);
  if (auto *structure = dyn_cast<StructType>(type))
    return any_of(structure->elements(), [&](Type *element) { return residueType(element, memory); });
  if (auto *array = dyn_cast<ArrayType>(type)) return residueType(array->getElementType(), memory);
  return false;
}

bool checkFunction(Function &function, bool byteMemory) {
  if (residueType(function.getReturnType(), false)) return false;
  for (auto &argument : function.args())
    if (residueType(argument.getType(), false)) return false;
  for (auto &instruction : instructions(function)) {
    if (auto *call = dyn_cast<CallBase>(&instruction))
      if (auto *callee = call->getCalledFunction(); callee && callee->isIntrinsic()) return false;
    if (residueType(instruction.getType(), byteMemory && isa<LoadInst>(instruction))) return false;
    for (auto &operand : instruction.operands())
      if (residueType(operand->getType(), byteMemory && isa<StoreInst>(instruction))) return false;
  }
  return true;
}

int main(int argc, char **argv) {
  if (argc != 3) {
    errs() << "usage: normalisation_check <module.ll> <values|byte-memory>\n";
    return 2;
  }
  auto byteMemory = StringSwitch<std::optional<bool>>(argv[2])
      .Case("values", false).Case("byte-memory", true).Default(std::nullopt);
  if (!byteMemory) {
    errs() << "unknown memory representation: " << argv[2] << "\n";
    return 2;
  }
  LLVMContext context;
  SMDiagnostic diagnostic;
  auto module = parseIRFile(argv[1], diagnostic, context);
  if (!module) {
    diagnostic.print(argv[0], errs());
    return 2;
  }
  for (auto &function : *module)
    if (!function.isDeclaration() && !checkFunction(function, *byteMemory)) {
      errs() << "normalisation residue: " << function.getName()
             << " in " << argv[1] << " (intrinsic, vector, wide value or non-byte memory)\n";
      return 1;
    }
  return 0;
}
