#include "Bennett.h"
#include "NativeComparison.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Bitcode/BitcodeReader.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/SHA256.h"

using namespace llvm;
namespace bennett {
namespace {
cl::opt<std::string> NativeRecord("bennett-native-record");
cl::opt<std::string> NativeEntry("bennett-native-entry");
cl::opt<std::string> NativeReport("bennett-native-report");

std::string digest(StringRef s) {
  return toHex(SHA256::hash(arrayRefFromStringRef(s)), true);
}
std::unique_ptr<MemoryBuffer> read(StringRef path) {
  auto b = MemoryBuffer::getFile(path);
  if (!b)
    fail("BD-E-NATIVE-INPUT", (path + ": " + b.getError().message()).str());
  return std::move(*b);
}
std::string bits(Module &m) {
  std::string s;
  raw_string_ostream out(s);
  WriteBitcodeToFile(m, out);
  return s;
}

// Backend state belongs to this marked component. The caller loads its actual
// ISA object, binds that program, then calls the native entry. No main/startup
// replacement and no assumption that this module is the whole native binary.
class Bridge {
  Module &m;
  LLVMContext &c;
  Type *ptr, *i32, *i64, *voidTy;
  GlobalVariable *program;
  FunctionCallee fault, infrastructure;
  std::string prefix;

  BasicBlock *error(Function *f, bool semantic, StringRef message) {
    auto *bb = BasicBlock::Create(c, semantic ? "handle.fault" : "infrastructure", f);
    IRBuilder<> b(bb);
    if (semantic)
      b.CreateCall(fault, b.getInt64(4));
    else
      b.CreateCall(infrastructure, b.CreateGlobalString(message));
    b.CreateUnreachable();
    return bb;
  }
  Value *context(IRBuilder<> &b, Function *f) {
    auto *p = b.CreateLoad(ptr, program);
    auto *bound = BasicBlock::Create(c, "bound", f);
    b.CreateCondBr(b.CreateICmpNE(p, ConstantPointerNull::get(cast<PointerType>(ptr))),
                   bound, error(f, false, "native comparison component is not bound"));
    b.SetInsertPoint(bound);
    return p;
  }
  void status(IRBuilder<> &b, Function *f, Value *s, bool handleErrors) {
    auto *ok = BasicBlock::Create(c, "ok", f);
    auto *infra = error(f, false, "native comparison register backend failed");
    if (handleErrors) {
      auto *bad = BasicBlock::Create(c, "backend.error", f);
      b.CreateCondBr(b.CreateICmpEQ(s, b.getInt32(0)), ok, bad);
      b.SetInsertPoint(bad);
      // §10 launch statuses: not-clean=7, invalid-state=8, arg=11.
      auto *semantic = b.CreateOr(b.CreateICmpEQ(s, b.getInt32(7)),
                                 b.CreateOr(b.CreateICmpEQ(s, b.getInt32(8)),
                                            b.CreateICmpEQ(s, b.getInt32(11))));
      b.CreateCondBr(semantic, error(f, true, ""), infra);
    } else
      b.CreateCondBr(b.CreateICmpEQ(s, b.getInt32(0)), ok, infra);
    b.SetInsertPoint(ok);
  }
public:
  std::string binding;
  Bridge(Module &module, StringRef identity)
      : m(module), c(m.getContext()), ptr(PointerType::get(c, 0)),
        i32(Type::getInt32Ty(c)), i64(Type::getInt64Ty(c)),
        voidTy(Type::getVoidTy(c)), prefix("__bennett_native_" + identity.take_front(20).str()) {
    program = new GlobalVariable(m, ptr, false, GlobalValue::InternalLinkage,
                                ConstantPointerNull::get(cast<PointerType>(ptr)), prefix + "_program");
    fault = m.getOrInsertFunction("__bennett_nz_fault", voidTy, i64);
    infrastructure = m.getOrInsertFunction("__bennett_rt_native_infrastructure", voidTy, ptr);
    binding = prefix + "_bind";
    if (m.getNamedValue(binding))
      fail("BD-E-NATIVE-INPUT", "comparison adapter already present");
    auto *bind = Function::Create(FunctionType::get(voidTy, {ptr}, false),
                                  GlobalValue::ExternalLinkage, binding, m);
    IRBuilder<> b(BasicBlock::Create(c, "entry", bind));
    b.CreateStore(bind->getArg(0), program);
    b.CreateRetVoid();
  }
  Function *allocate(FunctionType *type) {
    auto *f = Function::Create(type, GlobalValue::InternalLinkage, prefix + "_new", m);
    IRBuilder<> b(BasicBlock::Create(c, "entry", f));
    auto *out = b.CreateAlloca(i64);
    auto *p = context(b, f);
    auto *valid = b.CreateAnd(b.CreateICmpNE(f->getArg(1), b.getInt64(0)),
                              b.CreateICmpULE(f->getArg(1), b.getInt64(UINT32_MAX)));
    auto *choose = BasicBlock::Create(c, "class", f);
    auto *invalid = error(f, true, "");
    b.CreateCondBr(valid, choose, invalid);
    b.SetInsertPoint(choose);
    auto *invoke = BasicBlock::Create(c, "allocate", f);
    auto *dispatch = b.CreateSwitch(f->getArg(0), invalid);
    IRBuilder<> at(invoke);
    auto *cls = at.CreatePHI(ptr, 1, "class.name");
    SmallVector<std::string> classes = {"any"};
    if (auto *table = dyn_cast_or_null<MDNode>(m.getModuleFlag("bennett.classes")))
      for (auto &item : table->operands()) {
        auto *name = dyn_cast<MDString>(item.get());
        if (!name)
          fail("BD-E-NATIVE-INPUT", "malformed bennett.classes table");
        classes.push_back(name->getString().str());
      }
    for (unsigned i = 0; i < classes.size(); ++i) {
      auto *bb = BasicBlock::Create(c, "class.name", f);
      IRBuilder<> cb(bb);
      auto *name = cb.CreateGlobalString(classes[i]);
      cb.CreateBr(invoke);
      cls->addIncoming(name, bb);
      dispatch->addCase(b.getInt64(i), bb);
    }
    b.SetInsertPoint(invoke);
    auto api = m.getOrInsertFunction("bennett_qreg_new", i32, ptr, ptr, i32, ptr);
    auto *s = b.CreateCall(api, {p, cls, b.CreateTrunc(f->getArg(1), i32), out});
    status(b, f, s, false);
    auto *id = b.CreateLoad(i64, out);
    auto *nonzero = BasicBlock::Create(c, "nonzero", f);
    b.CreateCondBr(b.CreateICmpNE(id, b.getInt64(0)), nonzero,
                   error(f, false, "native comparison backend returned a null register"));
    b.SetInsertPoint(nonzero);
    b.CreateRet(b.CreateIntToPtr(id, ptr));
    return f;
  }
  Function *release(FunctionType *type) {
    auto *f = Function::Create(type, GlobalValue::InternalLinkage, prefix + "_free", m);
    IRBuilder<> b(BasicBlock::Create(c, "entry", f));
    auto *p = context(b, f);
    auto api = m.getOrInsertFunction("bennett_qreg_free", i32, ptr, i64);
    auto *s = b.CreateCall(api, {p, b.CreatePtrToInt(f->getArg(0), i64)});
    status(b, f, s, true);
    b.CreateRetVoid();
    return f;
  }
};

struct NativeComparisonPass : PassInfoMixin<NativeComparisonPass> {
  PreservedAnalyses run(Module &m, ModuleAnalysisManager &) {
    if (NativeRecord.empty() || NativeEntry.empty() || NativeReport.empty())
      fail("BD-E-NATIVE-INPUT", "record, entry and report are required");
    auto recordBytes = read(NativeRecord);
    auto parsed = json::parse(recordBytes->getBuffer());
    if (!parsed)
      fail("BD-E-NATIVE-INPUT", toString(parsed.takeError()));
    auto *record = parsed->getAsObject();
    if (!record || record->getString("schema") != "bennett-plugin-launch-record-1" ||
        record->getString("entry") != NativeEntry)
      fail("BD-E-NATIVE-INPUT", "launch record schema or entry mismatch");
    auto *entry = m.getFunction(NativeEntry);
    if (!entry || entry->isDeclaration())
      fail("BD-E-NATIVE-INPUT", "selected entry is not a materialised definition");
    auto input = read(m.getModuleIdentifier());
    auto identity = digest(input->getBuffer());
    auto *artifacts = record->getObject("artifacts");
    auto *device = artifacts ? artifacts->getObject("device.bc") : nullptr;
    if (!device || device->getString("sha256") != identity ||
        device->getInteger("bytes") != int64_t(input->getBufferSize()))
      fail("BD-E-NATIVE-INPUT", "materialised bitcode does not match launch record");
    auto original = parseBitcodeFile(input->getMemBufferRef(), m.getContext());
    if (!original)
      fail("BD-E-NATIVE-INPUT", toString(original.takeError()));
    if (bits(**original) != bits(m))
      fail("BD-E-NATIVE-INPUT", "run comparison adaptation before further IR transformations");

    SmallVector<std::pair<CallBase *, Function *>> calls;
    for (auto &f : m)
      for (auto &i : instructions(f))
        if (auto *call = dyn_cast<CallBase>(&i))
          if (auto *g = dyn_cast<Function>(call->getCalledOperand()->stripPointerCasts()))
            if (markers().count(g->getName().str()))
              calls.push_back({call, g});
    Bridge bridge(m, identity);
    DenseMap<Function *, Function *> replacements;
    for (auto [call, g] : calls) {
      auto *replacement = replacements.lookup(g);
      if (!replacement) {
        if (g->getName() == "__bennett_qalloc" || g->getName() == "__bennett_qborrow")
          replacement = bridge.allocate(g->getFunctionType());
        else if (g->getName() == "__bennett_qfree")
          replacement = bridge.release(g->getFunctionType());
        else if (g->getName() == "__bennett_effect_console_write")
          replacement = cast<Function>(m.getOrInsertFunction("__bennett_rt_native_console_write",
                                                            g->getFunctionType()).getCallee());
        else
          fail("BD-E-NATIVE-MARKERS", "native comparison lowering required", call);
        replacements[g] = replacement;
      }
      call->setCalledFunction(replacement);
    }
    for (auto [old, replacement] : replacements)
      if (old->use_empty())
        old->eraseFromParent();
    json::Object report{{"schema", "bennett-native-comparison-1"},
                        {"materialised_sha256", identity},
                        {"record_sha256", digest(recordBytes->getBuffer())},
                        {"entries", json::Array{NativeEntry.getValue()}},
                        {"binding_symbol", bridge.binding},
                        {"source_memory_faults_checked", false},
                        {"resolved_link_layout", false},
                        {"full_comparison_acceptance", false}};
    std::error_code ec;
    raw_fd_ostream out(NativeReport, ec);
    if (ec)
      fail("BD-E-NATIVE-OUTPUT", ec.message());
    out << formatv("{0:2}\n", json::Value(std::move(report)));
    out.flush();
    if (out.has_error())
      fail("BD-E-NATIVE-OUTPUT", "cannot write comparison report");
    return PreservedAnalyses::none();
  }
  static bool isRequired() { return true; }
};
} // namespace
void addNativeComparisonPass(ModulePassManager &pm) {
  pm.addPass(NativeComparisonPass());
}
} // namespace bennett
