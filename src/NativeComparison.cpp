#include "Bennett.h"
#include "NativeComparison.h"
#include "ComparisonLayout.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Bitcode/BitcodeReader.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Transforms/Utils/Cloning.h"

using namespace llvm;
namespace bennett {
namespace {
cl::opt<std::string> NativeRecord("bennett-native-record");
cl::opt<std::string> NativeEntry("bennett-native-entry");
cl::opt<std::string> NativeReport("bennett-native-report");
cl::opt<bool> NativePrepareOnly("bennett-native-prepare-only",
    cl::desc("Publish source symbols before external native memory instrumentation"));
cl::opt<std::string> LayoutFile("bennett-comparison-layout",
    cl::desc("Resolved comparison ELF addresses, outside source normalisation"));
cl::opt<std::string> StructureReport("bennett-comparison-structure-report",
    cl::desc("Optional canonical materialisation IR for address-map audits"));
std::optional<json::Value> layout;
std::string layoutHash;

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
std::string structure(Module &m) {
  auto copy = CloneModule(m);
  auto encoded=bits(m);
  LLVMContext decodeContext;
  auto decoded=parseBitcodeFile(MemoryBufferRef(encoded,"comparison-structure"),decodeContext);
  if(!decoded)fail("BD-E-NATIVE-INPUT",toString(decoded.takeError()));
  // LLVM's reader records target ABI defaults explicitly (for example i128
  // alignment on x86). Compare the actual bitcode consumer's DataLayout.
  copy->setDataLayout((*decoded)->getDataLayout());
  for (auto &f : *copy)
    f.setMetadata("bennett.address", nullptr);
  // Bitcode use-list/attribute encoding can differ across a read/write cycle.
  // Canonical printed IR has no input-path ModuleID and omits use-list order.
  copy->setModuleIdentifier("");
  std::string text;
  raw_string_ostream out(text);
  copy->print(out, nullptr);
  if (!StructureReport.empty()) {
    std::error_code ec;
    raw_fd_ostream file(StructureReport, ec);
    if (ec) fail("BD-E-NATIVE-OUTPUT", ec.message());
    file << text;
    file.flush();
    if (file.has_error()) fail("BD-E-NATIVE-OUTPUT", "cannot write structure audit");
  }
  return digest(text);
}
uint64_t integer(const json::Object &o, StringRef field) {
  auto n = o.getInteger(field);
  if (!n || *n < 0)
    fail("BD-E-COMPARISON-LAYOUT", ("missing/nonnegative integer: " + field).str());
  return uint64_t(*n);
}
const json::Object *layoutEntry(StringRef table, StringRef key) {
  if (!layout)
    return nullptr;
  auto *entries = layout->getAsObject()->getObject(table);
  auto *entry = entries ? entries->getObject(key) : nullptr;
  return entry;
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
      // §10 launch statuses: not-clean=7, arg=11. An invalid program/run
      // state is an infrastructure/context error, not a dead source handle.
      auto *semantic = b.CreateOr(b.CreateICmpEQ(s, b.getInt32(7)),
                                 b.CreateICmpEQ(s, b.getInt32(11)));
      b.CreateCondBr(semantic, error(f, true, ""), infra);
    } else
      b.CreateCondBr(b.CreateICmpEQ(s, b.getInt32(0)), ok, infra);
    b.SetInsertPoint(ok);
  }
public:
  std::string binding;
  Bridge(Module &module, StringRef identity, std::optional<uint64_t> shadowStack,
         std::optional<uint64_t> sourceSteps)
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
    if (shadowStack) {
      auto *init=m.getFunction("__bennett_rt_ss_init");
      if (!init || init->isDeclaration() ||
          init->getFunctionType()!=FunctionType::get(voidTy,{i64},false))
        fail("BD-E-NATIVE-INPUT","R entry shadow-stack initialiser missing");
      b.CreateCall(init,{b.getInt64(*shadowStack)});
    }
    if (sourceSteps) {
      auto *steps=m.getGlobalVariable("__bennett_rt_rsteps",true);
      if(!steps || steps->getValueType()!=i64)
        fail("BD-E-NATIVE-INPUT","R source-step state missing");
      b.CreateStore(b.getInt64(*sourceSteps),steps);
    }
    b.CreateRetVoid();
  }
  Function *allocate(FunctionType *type) {
    auto *f = Function::Create(type, GlobalValue::InternalLinkage, prefix + "_new", m);
    IRBuilder<> b(BasicBlock::Create(c, "entry", f));
    auto *out = b.CreateAlloca(i64);
    auto *p = context(b, f);
    auto *valid = b.CreateICmpNE(f->getArg(1), b.getInt64(0));
    auto *width = BasicBlock::Create(c, "backend.width", f);
    auto *choose = BasicBlock::Create(c, "class", f);
    auto *invalid = error(f, true, "");
    b.CreateCondBr(valid, width, invalid);
    b.SetInsertPoint(width);
    b.CreateCondBr(b.CreateICmpULE(f->getArg(1), b.getInt64(UINT32_MAX)), choose,
                   error(f,false,"launch C ABI cannot represent register width; native backend extension required"));
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

std::string lowerNativeMarkers(Module &m, StringRef identity,
                              std::optional<uint64_t> shadowStack,
                              std::optional<uint64_t> sourceSteps) {
  SmallVector<std::pair<CallBase *, Function *>> calls;
  for (auto &f : m)for(auto &i:instructions(f))if(auto *call=dyn_cast<CallBase>(&i))
    if(auto *g=resolve(call->getCalledOperand());g && markers().count(g->getName().str()))
      calls.push_back({call,g});
  Bridge bridge(m, identity,shadowStack,sourceSteps);
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
  for (auto [old, replacement] : replacements)if(old->use_empty())old->eraseFromParent();
  return bridge.binding;
}
void writeReport(StringRef text) {
  if(NativeReport.empty())fail("BD-E-NATIVE-OUTPUT","native report path is required");
  std::error_code ec;
  raw_fd_ostream out(NativeReport,ec);
  if(ec)fail("BD-E-NATIVE-OUTPUT",ec.message());
  out << text;
  out.flush();
  if(out.has_error())fail("BD-E-NATIVE-OUTPUT","cannot write comparison report");
}

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
    // A separate context preserves identified type names. Parsing a second
    // copy into m's context can rename %struct.T to %struct.T.0 and falsely
    // report a transformation in unchanged C materialisation.
    LLVMContext originalContext;
    auto original = parseBitcodeFile(input->getMemBufferRef(), originalContext);
    if (!original)
      fail("BD-E-NATIVE-INPUT", toString(original.takeError()));
    if (bits(**original) != bits(m))
      fail("BD-E-NATIVE-INPUT", "run comparison adaptation before further IR transformations");
    auto buildBytes=read((sys::path::parent_path(NativeRecord)+"/build.json").str());
    auto *buildArtifact=artifacts->getObject(NativeEntry+"/build.json");
    if(!buildArtifact || buildArtifact->getString("sha256")!=digest(buildBytes->getBuffer()))
      fail("BD-E-NATIVE-INPUT","build metadata does not match launch record");
    auto build=json::parse(buildBytes->getBuffer());
    if(!build)fail("BD-E-NATIVE-INPUT",toString(build.takeError()));
    auto *buildObject=build->getAsObject();
    if(!buildObject)fail("BD-E-NATIVE-INPUT","invalid build metadata");
    bool reversible=buildObject->getString("mode")=="reversible";
    std::optional<uint64_t> shadowStack,sourceSteps;
    if(reversible) {
      auto *initialisation=buildObject->getObject("entry_initialisation");
      auto stack=initialisation?initialisation->getString("shadow_stack_bytes"):std::nullopt;
      auto steps=buildObject->getString("source_step_limit");
      uint64_t stackBytes,stepLimit;
      if(!stack || !steps || stack->getAsInteger(10,stackBytes) || steps->getAsInteger(10,stepLimit))
        fail("BD-E-NATIVE-INPUT","R entry initialisation metadata missing; regenerate launch artifacts");
      shadowStack=stackBytes;sourceSteps=stepLimit;
    }

    auto fingerprint = structure(m);
    // Stable, collision-resistant aliases expose private/unnamed source
    // definitions to the comparison linker without changing their bodies or
    // making a second copy of any source global.
    json::Array symbols;
    SmallVector<GlobalValue *> values;
    for (auto &g : m.globals()) if (!g.isDeclaration()) values.push_back(&g);
    for (auto &f : m) if (!f.isDeclaration()) values.push_back(&f);
    for (unsigned i = 0; i < values.size(); ++i) {
      auto *v = values[i];
      auto name = "__bennett_comparison_" + identity.substr(0, 20) + "_" + std::to_string(i);
      if (m.getNamedValue(name))
        fail("BD-E-NATIVE-INPUT", "comparison symbol collision", v);
      v->setUnnamedAddr(GlobalValue::UnnamedAddr::None);
      GlobalAlias::create(GlobalValue::ExternalLinkage, name, v);
      json::Object row{{"llvm_name", v->getName()}, {"native_symbol", name}};
      if (auto *g = dyn_cast<GlobalVariable>(v)) {
        row["kind"] = "global";
        row["source_key"] = scalarGlobalKey(*g);
        row["size"] = int64_t(m.getDataLayout().getTypeAllocSize(g->getValueType()).getFixedValue());
        row["alignment"] = int64_t(m.getDataLayout().getPreferredAlign(g).value());
      } else {
        row["kind"] = "function";
        row["source_key"] = v->getName();
        cast<Function>(v)->addFnAttr("bennett.native.materialised.sha256", identity);
      }
      symbols.push_back(std::move(row));
    }
    auto binding="__bennett_native_"+identity.substr(0,20)+"_bind";
    if(!NativePrepareOnly)binding=lowerNativeMarkers(m,identity,shadowStack,sourceSteps);
    json::Object report{{"schema", "bennett-native-comparison-1"},
                        {"materialised_sha256", identity},
                        {"materialised_structure_sha256", fingerprint},
                        {"record_sha256", digest(recordBytes->getBuffer())},
                        {"entries", json::Array{NativeEntry.getValue()}},
                        {"binding_symbol", binding},
                        {"phase", NativePrepareOnly?"prepared":"finalised"},
                        {"source_mode", reversible?"reversible":"marked"},
                        {"r_source_step_checks", false},
                        {"symbols", std::move(symbols)},
                        {"source_memory_faults_checked", false},
                        {"resolved_link_layout", false},
                        {"full_comparison_acceptance", false}};
    if(shadowStack)report["shadow_stack_bytes"]=std::to_string(*shadowStack);
    if(sourceSteps)report["source_step_limit"]=std::to_string(*sourceSteps);
    auto reportText=formatv("{0:2}\n",json::Value(std::move(report))).str();
    if(NativePrepareOnly)
      m.addModuleFlag(Module::Error,"bennett.native.prepared",MDString::get(m.getContext(),reportText));
    writeReport(reportText);
    return PreservedAnalyses::none();
  }
  static bool isRequired() { return true; }
};
struct NativeFinalisePass : PassInfoMixin<NativeFinalisePass> {
  PreservedAnalyses run(Module &m,ModuleAnalysisManager &) {
    auto *record=dyn_cast_or_null<MDString>(m.getModuleFlag("bennett.native.prepared"));
    if(!record || m.getModuleFlag("bennett.native.finalised"))
      fail("BD-E-NATIVE-INPUT","finalisation requires an unfinalised prepared component");
    auto value=json::parse(record->getString());
    if(!value)fail("BD-E-NATIVE-INPUT",toString(value.takeError()));
    auto *report=value->getAsObject();
    if(!report || report->getString("schema")!="bennett-native-comparison-1" ||
        report->getString("phase")!="prepared" || !report->getString("materialised_sha256") ||
        !report->getArray("symbols"))
      fail("BD-E-NATIVE-INPUT","invalid prepared component metadata");
    auto identity=*report->getString("materialised_sha256");
    for(auto &item:*report->getArray("symbols")) {
      auto *row=item.getAsObject();
      auto name=row?row->getString("native_symbol"):std::nullopt;
      auto *alias=name?dyn_cast_or_null<GlobalAlias>(m.getNamedValue(*name)):nullptr;
      if(!alias)fail("BD-E-NATIVE-INPUT","prepared source symbol correspondence was lost");
      if(row->getString("kind")=="function") {
        auto *f=dyn_cast_or_null<Function>(alias->getAliaseeObject());
        if(!f || f->isDeclaration() || !f->hasFnAttribute("bennett.native.materialised.sha256") ||
            f->getFnAttribute("bennett.native.materialised.sha256").getValueAsString()!=identity)
          fail("BD-E-NATIVE-INPUT","prepared source function provenance was lost",alias);
      }
    }
    auto limit=[&](StringRef field)->std::optional<uint64_t> {
      auto text=report->getString(field);
      if(!text)return std::nullopt;
      uint64_t n;if(text->getAsInteger(10,n))fail("BD-E-NATIVE-INPUT","invalid prepared initialisation limit");
      return n;
    };
    auto binding=lowerNativeMarkers(m,identity,limit("shadow_stack_bytes"),limit("source_step_limit"));
    (*report)["binding_symbol"]=binding;
    (*report)["phase"]="finalised";
    // The external instrumenter owns its own receipt. This pass does not
    // certify instrumentation merely because a prepared module was supplied.
    (*report)["source_memory_faults_checked"]=false;
    writeReport(formatv("{0:2}\n",*value).str());
    m.addModuleFlag(Module::Error,"bennett.native.finalised",1);
    return PreservedAnalyses::none();
  }
  static bool isRequired() { return true; }
};
// H modules can be linked after marked-module materialisation. Their runtime
// console transport must be adapted without normalising them as device code or
// replacing any protected materialised body with another runtime publication.
struct NativeHostImportsPass : PassInfoMixin<NativeHostImportsPass> {
  PreservedAnalyses run(Module &m, ModuleAnalysisManager &) {
    bool component=false;
    for(auto &f:m)component |= f.hasFnAttribute("bennett.native.materialised.sha256");
    if(!component)fail("BD-E-NATIVE-INPUT","host import adaptation requires a materialised native component");
    SmallVector<CallBase *> calls;
    for(auto &f:m)for(auto &i:instructions(f))if(auto *call=dyn_cast<CallBase>(&i))
      if(auto *g=resolve(call->getCalledOperand());g && markers().count(g->getName().str())) {
        if(f.hasFnAttribute("bennett.native.materialised.sha256"))
          fail("BD-E-NATIVE-INPUT","host linking introduced markers into a protected materialised body",call);
        if(g->getName()!="__bennett_effect_console_write")
          fail("BD-E-NATIVE-MARKERS","native host import needs backend lowering",call);
        calls.push_back(call);
      }
    for(auto *call:calls) {
      auto *old=resolve(call->getCalledOperand());
      auto replacement=m.getOrInsertFunction("__bennett_rt_native_console_write",old->getFunctionType());
      call->setCalledFunction(cast<Function>(replacement.getCallee()));
      if(old->use_empty())old->eraseFromParent();
    }
    return PreservedAnalyses::none();
  }
  static bool isRequired() { return true; }
};
} // namespace
void addNativeComparisonPass(ModulePassManager &pm) {
  pm.addPass(NativeComparisonPass());
}
void addNativeHostImportsPass(ModulePassManager &pm) { pm.addPass(NativeHostImportsPass()); }
void addNativeFinalisePass(ModulePassManager &pm) { pm.addPass(NativeFinalisePass()); }
void initialiseComparisonLayout(Module &m) {
  layout.reset();
  layoutHash.clear();
  if (LayoutFile.empty()) return;
  auto bytes = read(LayoutFile);
  auto value = json::parse(bytes->getBuffer());
  if (!value) fail("BD-E-COMPARISON-LAYOUT", toString(value.takeError()));
  auto *o = value->getAsObject();
  if (!o || o->getString("schema") != "bennett-comparison-layout-1" ||
      integer(*o, "ptr_width") != m.getDataLayout().getPointerSizeInBits() ||
      !o->getString("materialised_structure_sha256") ||
      !o->getObject("globals") || !o->getObject("functions"))
    fail("BD-E-COMPARISON-LAYOUT", "schema, pointer width or source correspondence missing");
  auto end = integer(*o, "data_end"), heap = integer(*o, "heap_base");
  if (end < 4096 || end > uint64_t(INT64_MAX) - 4095 || heap != alignTo(end, uint64_t(4096)))
    fail("BD-E-COMPARISON-LAYOUT", "heap must be the first page boundary after linked data");
  std::vector<std::pair<uint64_t,uint64_t>> ranges;
  for (auto &item : *o->getObject("globals")) {
    auto *entry = item.second.getAsObject();
    if (!entry) fail("BD-E-COMPARISON-LAYOUT", "invalid global entry");
    auto address = integer(*entry, "address"), size = integer(*entry, "size"), alignment = integer(*entry, "alignment");
    if (address < 4096 || address > end || size > end - address ||
        !isPowerOf2_64(alignment) || address % alignment)
      fail("BD-E-COMPARISON-LAYOUT", "misaligned/out-of-data global range");
    if (size) ranges.push_back({address, address+size});
  }
  llvm::sort(ranges);
  for (unsigned i=1; i<ranges.size(); ++i)
    if (ranges[i].first < ranges[i-1].second)
      fail("BD-E-COMPARISON-LAYOUT", "overlapping source globals");
  std::set<uint64_t> addresses;
  for (auto &item : *o->getObject("functions")) {
    auto *entry = item.second.getAsObject();
    if (!entry) fail("BD-E-COMPARISON-LAYOUT", "invalid function entry");
    auto address = integer(*entry, "address");
    if (address < 4096 || !addresses.insert(address).second)
      fail("BD-E-COMPARISON-LAYOUT", "null or merged source function address");
    for (auto range : ranges) if (address >= range.first && address < range.second)
      fail("BD-E-COMPARISON-LAYOUT", "function address overlaps source data");
  }
  layoutHash = digest(bytes->getBuffer());
  layout = std::move(*value);
}
bool hasComparisonLayout() { return layout.has_value(); }
std::string comparisonLayoutDigest() { return layoutHash; }
std::optional<uint64_t> comparisonGlobalAddress(const GlobalVariable &g) {
  if (!layout) return std::nullopt;
  auto *e = layoutEntry("globals", scalarGlobalKey(g));
  if (!e || integer(*e,"size") != g.getParent()->getDataLayout().getTypeAllocSize(g.getValueType()).getFixedValue() ||
      integer(*e,"alignment") < g.getParent()->getDataLayout().getPreferredAlign(&g).value())
    fail("BD-E-COMPARISON-LAYOUT", "missing or incompatible source global", &g);
  return integer(*e, "address");
}
std::optional<uint64_t> comparisonFunctionAddress(const Function &f) {
  if (auto *e = layoutEntry("functions", f.getName())) return integer(*e,"address");
  return std::nullopt;
}
std::optional<uint64_t> comparisonHeapBase() {
  if (!layout) return std::nullopt;
  return integer(*layout->getAsObject(), "heap_base");
}
void checkComparisonMaterialisation(Module &m) {
  if (layout) {
    auto actual=structure(m);
    auto expected=*layout->getAsObject()->getString("materialised_structure_sha256");
    if (actual != expected)
      fail("BD-E-COMPARISON-LAYOUT", ("resolved map belongs to a different materialised module: expected " + expected + ", got " + actual).str());
  }
}
} // namespace bennett
