#include "Bennett.h"
#include "AnalysisBudgetClock.h"
#include "llvm/ADT/Hashing.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Analysis/AssumptionCache.h"
#include "llvm/Analysis/ConstantFolding.h"
#include "llvm/Analysis/LoopInfo.h"
#include "llvm/Analysis/ScalarEvolution.h"
#include "llvm/Analysis/TargetLibraryInfo.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/ConstantRange.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DebugInfo.h"
#include "llvm/IR/Dominators.h"
#include "llvm/IR/GlobalAlias.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Operator.h"
#include "llvm/IR/PatternMatch.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include "llvm/Transforms/Utils/PromoteMemToReg.h"
#include <numeric>
#include <cstdlib>
#include <memory>
#include "llvm/Support/CommandLine.h"
#include <tuple>
using namespace llvm;
namespace bennett {
static std::string label(const Value *v);
namespace {
cl::opt<unsigned> MaxAnalysisRounds("bennett-analysis-max-rounds",cl::init(16384));
cl::opt<unsigned> AnalysisMilliseconds("bennett-analysis-budget-ms",cl::init(30000),
    cl::desc("S2 thread CPU allowance in milliseconds; source/ISA budgets are independent"));
static bool sameAV(const AV &a, const AV &b) {
  return a.top == b.top && a.atoms.size() == b.atoms.size() &&
         std::equal(a.atoms.begin(), a.atoms.end(), b.atoms.begin(),
                    [](const Atom &x, const Atom &y) { return !(x < y) && !(y < x); });
}
struct AnalysisWork {
  static constexpr size_t TopFunctionLimit = 10;
  uint64_t transferApplications = 0;
  // S2 scans an implicit instruction worklist each round. Count dispatches,
  // including cached transfers and private normalisation instructions.
  uint64_t worklistPops = 0;
  uint64_t roundsCompleted = 0;
  uint64_t avMerges = 0, fieldJoins = 0, slotJoins = 0;
  uint64_t functionVisits = 0;
  struct MemoryWork {
    uint64_t loadAddresses = 0, loadSlotTests = 0, loadImageHits = 0, loadImageMisses = 0;
    uint64_t loadImageComputations = 0, loadSignatureHits = 0, loadImageUnionSkips = 0;
    uint64_t loadByteSlotTests = 0;
    uint64_t loadImageInternHits = 0;
    uint64_t pointerContainmentTests = 0;
    uint64_t compactions = 0, compactSlots = 0, compactCopies = 0, reindexedSlots = 0;
    uint64_t mergeFamilyVisits = 0, mergeTopVisits = 0;
    json::Object report() const {
      return json::Object{{"load_addresses", loadAddresses}, {"load_slot_tests", loadSlotTests},
              {"load_image_hits", loadImageHits}, {"load_image_misses", loadImageMisses},
              {"load_image_computations", loadImageComputations},
              {"load_signature_hits", loadSignatureHits}, {"load_image_union_skips", loadImageUnionSkips},
              {"load_byte_slot_tests", loadByteSlotTests},
              {"load_image_intern_hits", loadImageInternHits},
              {"pointer_containment_tests", pointerContainmentTests},
              {"compactions", compactions}, {"compact_slots", compactSlots},
              {"compact_copies", compactCopies}, {"reindexed_slots", reindexedSlots},
              {"merge_family_visits", mergeFamilyVisits}, {"merge_top_visits", mergeTopVisits}};
    }
  } memory;
  struct FunctionVisits {
    std::string name;
    uint64_t visits = 0;
    uint64_t rounds = 0, dispatches = 0, transfers = 0;
    uint64_t avMerges = 0, fieldJoins = 0, slotJoins = 0;
    MemoryWork memory;
  };
  std::vector<FunctionVisits> functions;
  FunctionVisits *currentFunction = nullptr;

  explicit AnalysisWork(const Module &module) {
    functions.reserve(module.size());
    for (const Function &function : module)
      if (!function.isDeclaration())
        functions.push_back({function.hasName() ? function.getName().str()
                                                 : label(&function), 0});
  }
  json::Object report(std::optional<uint64_t> cpuNanoseconds) const {
    std::vector<const FunctionVisits *> ranked;
    for (const auto &function : functions)
      if (function.visits) ranked.push_back(&function);
    llvm::sort(ranked, [](const auto *a, const auto *b) {
      if (a->visits != b->visits) return a->visits > b->visits;
      return a->name < b->name;
    });
    json::Object perFunction;
    for (const auto &f : functions)
      perFunction[f.name] = json::Object{{"rounds_completed", f.rounds},
          {"worklist_pops", f.dispatches}, {"transfer_applications", f.transfers},
          {"join_count", f.avMerges + f.fieldJoins + f.slotJoins},
          {"memory", f.memory.report()}};
    json::Object top;
    for (size_t n = 0; n < std::min(TopFunctionLimit, ranked.size()); ++n)
      top[ranked[n]->name] = ranked[n]->visits;
    json::Object cpu{{"deterministic", false}};
    if (cpuNanoseconds) cpu["value"] = double(*cpuNanoseconds) / 1000000.0;
    else {
      cpu["value"] = nullptr;
      cpu["error"] = "S2 thread CPU clock unavailable";
    }
    return json::Object{{"transfer_applications", transferApplications},
            {"worklist_pops", worklistPops},
            {"rounds_completed", roundsCompleted},
            {"join_count", avMerges + fieldJoins + slotJoins},
            {"av_merges", avMerges}, {"field_joins", fieldJoins},
            {"slot_joins", slotJoins},
            {"memory", memory.report()},
            {"function_visits", json::Object{{"total", functionVisits},
                {"top_limit", TopFunctionLimit}, {"top", std::move(top)}}},
            {"per_function", std::move(perFunction)}, {"cpu_ms", std::move(cpu)}};
  }
};
// The existing pass calls report() immediately after run(). Retain just that
// invocation's frozen receipt, without attaching bookkeeping to the source IR.
struct AnalysisReceipt {
  const Analysis *owner = nullptr;
  const Module *module = nullptr;
  std::string json;
  json::Value document{nullptr};
};
thread_local AnalysisReceipt completedReceipt;
struct AnalysisBudget {
  AnalysisBudgetClock clock{AnalysisMilliseconds};
  AnalysisWork work;
  // PT6 images depend on one object's slots and the accessed representation.
  // Every growing PT7 fact invalidates that object's cached images.
  using LoadPartKey = std::tuple<int64_t, int64_t, uint64_t, bool, bool, unsigned>;
  using LoadSignature = std::tuple<Type *, std::vector<LoadPartKey>, std::optional<int64_t>>;
  using LoadImage = std::shared_ptr<const AV>;
  std::map<const Value *, std::map<std::pair<Atom, Type *>, LoadImage>> loadImages;
  std::map<const Value *, std::map<LoadSignature, LoadImage>> loadSignatures;
  std::map<size_t, SmallVector<std::weak_ptr<const AV>, 4>> loadImagePool;
  LoadImage internLoadImage(AV image);
  void invalidateLoadImages(const Value *object) {
    loadImages.erase(object);
    loadSignatures.erase(object);
  }
  const Analysis *owner;
  std::string reportPath;
  const Instruction *at=nullptr;
  const char *rule="PT11 seeds";
  uint64_t ticks=0;
  enum class ReceiptState { Pending, Emitted };
  ReceiptState receiptState = ReceiptState::Pending;
  explicit AnalysisBudget(const Analysis *analysis, const Module &module)
      : work(module), owner(analysis) {
    if (completedReceipt.module != &module) {
      completedReceipt.document = nullptr;
      completedReceipt.module = &module;
    }
    // BennettPlugin.cpp owns this string option. Use LLVM's registered option
    // to honour the same destination even when fail() exits before its writer.
    auto &options = cl::getRegisteredOptions();
    auto report = options.find("bennett-report");
    if (report == options.end())
      fail("analysis-resource", "bennett-report option is not registered");
    reportPath = static_cast<cl::opt<std::string> *>(report->second)->getValue();
  }
  void emit(bool stopped) {
    // A failed output write can call fail() while the scope is still active.
    // Its exit handler must not print the receipt a second time.
    if (receiptState == ReceiptState::Emitted) return;
    receiptState = ReceiptState::Emitted;
    json::Value workJSON(work.report(clock.elapsedNanoseconds()));
    std::string receipt = formatv("{0}", workJSON).str();
    errs() << "bennett-analysis-work:" << receipt << '\n';
    if (!stopped) {
      completedReceipt.owner = owner;
      completedReceipt.json = receipt;
    }
    if (!reportPath.empty()) {
      json::Object report;
      // A later production analysis must preserve the main report's values,
      // regions and functions while updating its work receipt. On std::exit,
      // thread-local documents may already be destroyed; use only this scope.
      if (!stopped)
        if (auto *document = completedReceipt.document.getAsObject())
          report = *document;
      report["analysis_work"] = std::move(workJSON);
      std::error_code error;
      raw_fd_ostream output(reportPath, error);
      if (error) {
        if (!stopped) fail("output", error.message());
        errs() << "bennett: output: " << error.message() << '\n';
        return;
      }
      output << formatv("{0:2}\n", json::Value(std::move(report)));
    }
  }
  [[noreturn]] void exhausted(StringRef reason="S2 round limit") {
    std::string message="§5.2 "+std::string(rule)+" budget exhausted at AV(";
    raw_string_ostream out(message);
    if(at) {
      const Value *element=at;
      if(auto *store=dyn_cast<StoreInst>(at))element=store->getPointerOperand();
      if(auto *ret=dyn_cast<ReturnInst>(at);ret && ret->getReturnValue())element=ret->getReturnValue();
      // A void instruction has no SSA result to print. In particular lifetime
      // calls previously produced AV(<badref>) although their pointer is live.
      if(element->getType()->isVoidTy()) {
        element=at->getFunction();
        if(auto *call=dyn_cast<CallBase>(at)) {
          element=call->getCalledOperand();
          for(auto &arg:call->args())if(arg->getType()->isPointerTy()){element=arg;break;}
        } else for(auto &operand:at->operands())
          if(operand->getType()->isPointerTy() || operand->getType()->isIntegerTy()) {element=operand;break;}
      }
      element->printAsOperand(out,false);out<<") in @"<<at->getFunction()->getName();
    }
    else out<<"initial seeds)";
    out<<"; compiler resource allowance: "<<reason;
    fail("analysis-resource",out.str(),at);
  }
  void check(bool force=false) {
    if(force || (++ticks%1024)==0) {
      auto expired=clock.expired();
      if(!expired)fail("analysis-resource","S2 thread CPU clock unavailable",at);
      if(*expired)exhausted("thread CPU milliseconds");
    }
  }
};
thread_local AnalysisBudget *activeBudget=nullptr;
void budgetTick() {if(activeBudget)activeBudget->check();}
void memoryWork(uint64_t AnalysisWork::MemoryWork::*counter, uint64_t count = 1) {
  if (!activeBudget) return;
  activeBudget->work.memory.*counter += count;
  if (auto *f = activeBudget->work.currentFunction) f->memory.*counter += count;
}
AnalysisBudget::LoadImage AnalysisBudget::internLoadImage(AV image) {
  auto hash = hash_combine(image.top, image.atoms.size());
  for (const auto &a : image.atoms) {
    budgetTick();
    hash = hash_combine(hash, a.kind, a.object, a.offset, a.stride,
                        a.integer.getBitWidth(), a.integer, a.numerical);
  }
  auto &bucket = loadImagePool[static_cast<size_t>(hash)];
  for (auto it = bucket.begin(); it != bucket.end();) {
    if (auto prior = it->lock()) {
      // The hash selects candidates only. Full AV equality is required,
      // including integer widths, numerical provenance and explicit ROOTs.
      if (sameAV(*prior, image)) {
        memoryWork(&AnalysisWork::MemoryWork::loadImageInternHits);
        return prior;
      }
      ++it;
    } else it = bucket.erase(it);
  }
  auto result = std::make_shared<const AV>(std::move(image));
  bucket.push_back(result);
  return result;
}
struct BudgetScope {
  AnalysisBudget budget;
  AnalysisBudget *previous=activeBudget;
  BudgetScope(const Analysis *analysis, const Module &module)
      : budget(analysis, module) {
    // fail() uses std::exit, which leaves this automatic object alive and does
    // not run its destructor. This also covers failures in transfer helpers.
    static const int registered = std::atexit([] {
      if (activeBudget) activeBudget->emit(true);
    });
    activeBudget = &budget;
    if (registered != 0)
      fail("analysis-resource", "cannot register analysis work receipt");
  }
  ~BudgetScope() {
    budget.emit(false);
    activeBudget=previous;
  }
};
}
static AV atom(Atom::Kind k, const Value *o = nullptr, int64_t off = 0,
               int64_t stride = 0) {
  AV a;
  a.atoms.insert({k, o, off, stride, APInt(1, 0)});
  return a;
}
static AV integer(APInt n) {
  AV a;
  a.atoms.insert({Atom::Int, nullptr, 0, 0, n});
  return a;
}
bool Atom::operator<(const Atom &b) const {
  if(kind!=b.kind)return kind<b.kind;
  if(object!=b.object)return std::less<const Value *>{}(object,b.object);
  // Keep exact pointers contiguous so union can skip them when indexing
  // residue families. This is a set order, never an abstract-value widening.
  if(kind==Atom::Ptr && stride!=b.stride)return stride<b.stride;
  if(offset!=b.offset)return offset<b.offset;
  if(stride!=b.stride)return stride<b.stride;
  if(integer.getBitWidth()!=b.integer.getBitWidth())return integer.getBitWidth()<b.integer.getBitWidth();
  if(numerical!=b.numerical)return numerical<b.numerical;
  return integer.ult(b.integer);
}
static int64_t residue(int64_t offset, int64_t stride) {
  int64_t result = offset % stride;
  return result < 0 ? result + stride : result;
}
static void canonicalOffset(int64_t &offset, int64_t &stride) {
  if (stride == 1) stride = -1;
  if (stride == -1) offset = 0;
  else if (stride > 0) offset = residue(offset, stride);
}
static bool offsetContains(int64_t outerOffset, int64_t outerStride,
                           int64_t innerOffset, int64_t innerStride) {
  budgetTick();
  if (outerStride == -1) return true;
  if (!outerStride) return !innerStride && outerOffset == innerOffset;
  return innerStride != -1 && innerStride % outerStride == 0 &&
         residue(innerOffset, outerStride) == residue(outerOffset, outerStride);
}
static bool pointerContains(const Atom &outer, const Atom &inner) {
  budgetTick();
  memoryWork(&AnalysisWork::MemoryWork::pointerContainmentTests);
  return outer.kind == Atom::Ptr && inner.kind == Atom::Ptr &&
         outer.object == inner.object && outer.numerical == inner.numerical &&
         outer.integer == inner.integer &&
         offsetContains(outer.offset, outer.stride, inner.offset, inner.stride);
}
static bool contains(const AV &outer, const AV &inner) {
  if (inner.top && !outer.top) return false;
  // Reject missing explicit non-pointer alternatives before checking a large
  // pointer set. TOP absorbs integers, never a missing ROOT or FN.
  for (auto it = inner.atoms.rbegin(); it != inner.atoms.rend() && it->kind != Atom::Ptr; ++it) {
    budgetTick();
    if (it->kind == Atom::Int && outer.top) continue;
    if (!outer.atoms.count(*it)) return false;
  }
  SmallVector<const Atom *, 4> families;
  const Value *familyObject = nullptr;
  bool indexed = false;
  for (const auto &a : inner.atoms) {
    if (a.kind != Atom::Ptr) break;
    budgetTick();
    if (outer.atoms.count(a)) continue;
    if (!indexed || familyObject != a.object) {
      families.clear();
      Atom first{Atom::Ptr,a.object,INT64_MIN,INT64_MIN,APInt(1,0)};
      for (auto it = outer.atoms.lower_bound(first);
           it != outer.atoms.end() && it->kind == Atom::Ptr && it->object == a.object;) {
        budgetTick();
        if (!it->stride) {
          auto afterExact = first;
          afterExact.stride = 1;
          it = outer.atoms.lower_bound(afterExact);
        } else families.push_back(&*it++);
      }
      familyObject = a.object;
      indexed = true;
    }
    if (!llvm::any_of(families, [&](const Atom *b) { return pointerContains(*b, a); }))
      return false;
  }
  return true;
}
static std::optional<AV> coverageRequirement(const AV &value) {
  auto sameOrigin = [](const Atom &a, const Atom &b) {
    return a.kind == Atom::Ptr && b.kind == Atom::Ptr && a.object == b.object &&
           a.numerical == b.numerical && a.integer.getBitWidth() == b.integer.getBitWidth() &&
           a.integer == b.integer;
  };
  if (std::adjacent_find(value.atoms.begin(), value.atoms.end(), sameOrigin) == value.atoms.end())
    return std::nullopt;
  AV requirement; requirement.top = value.top;
  for (auto a : value.atoms) {
    budgetTick();
    if (a.kind == Atom::Ptr) { a.offset = 0; a.stride = -1; }
    requirement.atoms.insert(requirement.atoms.end(), std::move(a));
  }
  return requirement;
}
bool AV::merge(const AV &v) {
  if (activeBudget) {
    ++activeBudget->work.avMerges;
    if (auto *f = activeBudget->work.currentFunction) ++f->avMerges;
  }
  budgetTick();
  bool change = false;
  if (v.top && !top) {
    top = true;
    change = true;
  }
  if(&v==this)return change;
  bool insertedInteger=false;
  SmallVector<Atom, 4> families;
  bool indexedFamilies = false;
  const Value *familyObject = nullptr;
  for (auto a : v.atoms) {
    if(top && a.kind==Atom::Int)continue;
    if(a.kind==Atom::Ptr) {
      canonicalOffset(a.offset, a.stride);
      if (atoms.count(a)) continue;
      Atom first{Atom::Ptr,a.object,INT64_MIN,INT64_MIN,APInt(1,0)};
      // Only families of this object can contain this pointer. Incoming atoms
      // are grouped by object, so reuse that object's index throughout the
      // union instead of rescanning pointers of every other object.
      if (!indexedFamilies || familyObject != a.object) {
        families.clear();
        for (auto it = atoms.lower_bound(first);
             it != atoms.end() && it->kind == Atom::Ptr && it->object == a.object;) {
          memoryWork(&AnalysisWork::MemoryWork::mergeFamilyVisits);
          if (!it->stride) {
            auto afterExact = first;
            afterExact.stride = 1;
            it = atoms.lower_bound(afterExact);
            continue;
          }
          const auto &b = *it;
          families.push_back(b);
          ++it;
        }
        familyObject = a.object;
        indexedFamilies = true;
      }
      if (llvm::any_of(families, [&](const Atom &b) { return pointerContains(b, a); }))
        continue;
      // A proven coset absorbs exactly its members, with provenance intact.
      if (a.stride) {
        for (auto it = atoms.lower_bound(first);
             it != atoms.end() && it->kind == Atom::Ptr && it->object == a.object;)
          if (pointerContains(a, *it)) it = atoms.erase(it);
          else ++it;
        llvm::erase_if(families, [&](const Atom &b) { return pointerContains(a, b); });
        families.push_back(a);
      }
    }
    bool inserted=atoms.insert(a).second;
    change |= inserted;
    insertedInteger |= inserted && a.kind==Atom::Int;
  }
  unsigned n = 0;
  if (insertedInteger && !top && atoms.size() > 4096)
    for (auto &a : atoms)
      n += a.kind == Atom::Int;
  if (n > 4096) {
    top = true;
    change = true;
  }
  if (top)
    while (!atoms.empty()) {
      auto i = std::prev(atoms.end());
      memoryWork(&AnalysisWork::MemoryWork::mergeTopVisits);
      // Atom kinds are ordered and INT is last. TOP absorbs just this suffix,
      // retaining every explicit pointer, function and ROOT alternative.
      if (i->kind != Atom::Int) break;
      atoms.erase(i);
    }
  return change;
}
bool AV::roots() const {
  for (auto &a : atoms)
    if (a.kind == Atom::Root)
      return true;
  return false;
}
static void numericalUnknown(AV &result) {
  Atom ext{Atom::Ptr,nullptr,0,-1,APInt(1,0)};
  ext.numerical=true;
  result.atoms.insert(ext);
  result.top=true;
}
AV Analysis::convert(const AV &source,Type *from,Type *to,unsigned opcode) {
  if(opcode==Instruction::AddrSpaceCast) return source; // PT3 copies, not PT4.
  AV result;result.top=source.top;
  // Numeric TOP includes nonzero integers, whose inttoptr image carries EXT.
  // Retain that same image when the finite INT alternatives are absorbed.
  if (source.top && opcode == Instruction::IntToPtr) numericalUnknown(result);
  unsigned width=M.getDataLayout().getTypeSizeInBits(to).getKnownMinValue();
  unsigned input=M.getDataLayout().getTypeSizeInBits(from).getKnownMinValue();
  for(auto a:source.atoms) {
    if(a.kind==Atom::Int) {
      a.integer=opcode==Instruction::SExt?a.integer.sextOrTrunc(width):a.integer.zextOrTrunc(width);
      if(to->isPointerTy() && !a.integer.isZero()) numericalUnknown(result);
    } else if(a.kind==Atom::Ptr && a.object) {
      unsigned pointerWidth=M.getDataLayout().getPointerTypeSizeInBits(a.object->getType());
      bool widenedInteger=from->isIntegerTy() && to->isIntegerTy() && width>input;
      if(width<pointerWidth || widenedInteger) {
        a.offset=0;a.stride=-1;numericalUnknown(result);
      }
    }
    result.atoms.insert(a);
  }
  return result;
}
AV Analysis::displace(const AV &source,const APInt &delta,unsigned pointerWidth,bool gep) {
  if(delta.isZero()) return source;
  AV result;result.top=source.top;
  unsigned bits=delta.getBitWidth();
  for(auto a:source.atoms) {
    if(a.kind!=Atom::Ptr || !a.object) {result.atoms.insert(a);continue;}
    // All aligned low-bit patterns, including wrap with preserved high bits.
    if(gep && bits<pointerWidth && bits<63 && !a.stride) {
      uint64_t alignment=1,size=UINT64_MAX;
      if(auto *g=dyn_cast<GlobalVariable>(a.object)) {
        alignment=g->getAlign().valueOrOne().value();
        if(!g->getAlign()) alignment=M.getDataLayout().getABITypeAlign(g->getValueType()).value();
        size=M.getDataLayout().getTypeAllocSize(g->getValueType()).getKnownMinValue();
      } else if(auto *alloc=dyn_cast<AllocaInst>(a.object)) {
        alignment=alloc->getAlign().value();
        if(auto *count=dyn_cast<ConstantInt>(alloc->getArraySize()))
          size=(uint64_t)std::min<unsigned __int128>(UINT64_MAX,(unsigned __int128)count->getLimitedValue()*M.getDataLayout().getTypeAllocSize(alloc->getAllocatedType()).getKnownMinValue());
      }
      int64_t modulus=int64_t(1)<<bits;
      int64_t step=std::min<uint64_t>(alignment,modulus);
      int64_t residue=(a.offset%step+step)%step;
      int64_t low=residue,high=modulus-step+residue,d=delta.getSExtValue();
      auto include=[&](__int128 offset) {
        auto p=a;
        if(offset<INT64_MIN || offset>INT64_MAX) {p.offset=0;p.stride=-1;numericalUnknown(result);}
        else {p.offset=(int64_t)offset;if(offset<0 || (unsigned __int128)offset>=size) numericalUnknown(result);}
        result.atoms.insert(p);
      };
      if(low+d<modulus && high+d>=0) include((__int128)a.offset+d);
      if(high+d>=modulus) include((__int128)a.offset+d-modulus);
      if(low+d<0) include((__int128)a.offset+d+modulus);
    } else {
      auto offset=APInt(bits,a.offset,true)+delta;
      // Translation permutes a full-width power-of-two coset exactly. These
      // are the subgroups produced by modular pointer-cycle closure (PT2).
      if (a.stride > 0 && isPowerOf2_64(a.stride) && bits == pointerWidth &&
          bits <= 64 && Log2_64(a.stride) < bits) {
        a.offset = offset.getSExtValue();
        canonicalOffset(a.offset, a.stride);
        numericalUnknown(result);
      } else if(a.stride || !offset.isSignedIntN(64)) {
        a.offset=0;a.stride=-1;numericalUnknown(result);
      } else {
        a.offset=offset.getSExtValue();
        uint64_t size=UINT64_MAX;
        if(auto *g=dyn_cast<GlobalVariable>(a.object))
          size=M.getDataLayout().getTypeAllocSize(g->getValueType()).getKnownMinValue();
        else if(auto *alloc=dyn_cast<AllocaInst>(a.object))
          if(auto *count=dyn_cast<ConstantInt>(alloc->getArraySize()))
            size=(uint64_t)std::min<unsigned __int128>(UINT64_MAX,(unsigned __int128)count->getLimitedValue()*M.getDataLayout().getTypeAllocSize(alloc->getAllocatedType()).getKnownMinValue());
        if(a.offset<0 || (uint64_t)a.offset>=size)numericalUnknown(result);
      }
      result.atoms.insert(a);
    }
  }
  return result;
}
Function *resolve(Value *v) {
  if (auto *ga = dyn_cast<GlobalAlias>(v))
    v = ga->getAliaseeObject();
  auto *f = dyn_cast<Function>(v);
  if (!f)
    return nullptr;
  std::set<Function *> seen;
  Function *start = f;
  while (f && !f->isDeclaration() && f->size() == 1) {
    if (!seen.insert(f).second)
      return start; // A thunk on a cycle resolves to itself.
    auto &b = f->front();
    if (b.size() != 2)
      break;
    auto *c = dyn_cast<CallInst>(&b.front());
    auto *r = dyn_cast<ReturnInst>(&b.back());
    if (!c || !r || c->getCallingConv() != CallingConv::C ||
        c->hasOperandBundles() ||
        c->getFunctionType() != f->getFunctionType() ||
        c->arg_size() != f->arg_size())
      break;
    if (!f->getReturnType()->isVoidTy() && r->getReturnValue() != c)
      break;
    bool same = true;
    unsigned i = 0;
    for (Argument &a : f->args())
      same &= c->getArgOperand(i++) == &a;
    if (!same)
      break;
    Value *target = c->getCalledOperand();
    if (auto *ga = dyn_cast<GlobalAlias>(target))
      target = ga->getAliaseeObject();
    auto *g = dyn_cast<Function>(target);
    if (!g || g->isIntrinsic())
      break;
    f = g;
  }
  return f;
}
std::string regionKey(Function *f) {
  // Build the source call closure, including fixed S2 indirect candidates.
  // Normalisation can introduce linked helper edges; include those before
  // stripping names and hashing. H/source definitions remain untouched.
  Module &src = *f->getParent();
  std::vector<Function *> order;
  std::set<Function *> seen;
  std::unique_ptr<Analysis> reference;
  std::function<void(Function *)> dfs = [&](Function *g) {
    g = resolve(g);
    if (!g || g->isDeclaration() || !seen.insert(g).second)
      return;
    order.push_back(g);
    for (Instruction &i : instructions(g))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *t = resolve(c->getCalledOperand())) dfs(t);
        else {
          if(!reference) {reference=std::make_unique<Analysis>(src,f);reference->run();}
          auto candidates=reference->candidates(c->getCalledOperand(),c->getFunctionType());
          // §7.3 specifies direct preorder; preserve module order for the
          // additional indirect members rather than host pointer addresses.
          for(Function &target:src)if(candidates.count(&target))dfs(&target);
        }
  };
  dfs(f);
  ValueToValueMapTy map;
  auto clone = CloneModule(src, map);
  // CloneModule's WeakTrackingVH entries follow N22's RAUW. In particular,
  // stripped internal functions have no symbol by which to look them up.
  normaliseWideABI(*clone);
  std::vector<Function *> materialised;
  std::set<Function *> included;
  for(auto *g:order) {auto *c=cast<Function>(map[g]);materialised.push_back(c);included.insert(c);}
  for(unsigned n=0;n<materialised.size();++n) {
    auto *g=materialised[n];materialiseIntegerRuntime(*g);normaliseScalar(*g);
    for(auto &i:instructions(g))if(auto *call=dyn_cast<CallBase>(&i))
      if(auto *target=resolve(call->getCalledOperand())) {
        materialiseIntegerRuntime(*target);
        if(target->getFunctionType()==call->getFunctionType())call->setCalledFunction(target);
        if(!target->isDeclaration() && included.insert(target).second)materialised.push_back(target);
      }
  }
  std::map<CallBase *,std::vector<Function *>> indirect;
  if(reference)for(auto *g:order)for(auto &i:instructions(g))
    if(auto *call=dyn_cast<CallBase>(&i);call && !resolve(call->getCalledOperand())) {
      auto candidates=reference->candidates(call->getCalledOperand(),call->getFunctionType());
      auto *copy=cast<CallBase>(map[call]);
      for(Function &target:src)if(candidates.count(&target))indirect[copy].push_back(cast<Function>(map[&target]));
    }
  auto *root=materialised.front();materialised.clear();included.clear();
  std::function<void(Function *)> visit=[&](Function *g) {
    g=resolve(g);
    if(!g || g->isDeclaration() || !included.insert(g).second)return;
    materialised.push_back(g);
    for(auto &i:instructions(g))if(auto *call=dyn_cast<CallBase>(&i)) {
      if(auto *target=resolve(call->getCalledOperand()))visit(target);
      else for(auto *target:indirect[call])visit(target);
    }
  };visit(root);
  // Only closure definitions and their referenced data survive. In particular,
  // unrelated source bodies cannot keep each other's globals alive in a key.
  std::set<const Value *> used;
  std::function<void(const Value *)> retain=[&](const Value *v) {
    if(!used.insert(v).second || isa<Function>(v))return;
    if(auto *u=dyn_cast<User>(v))for(Value *operand:u->operands())retain(operand);
  };
  for(auto *g:materialised)for(auto &i:instructions(g))for(Value *v:i.operands())retain(v);
  for(Function &g:*clone)if(!g.isDeclaration() && !included.count(&g))g.deleteBody();
  for(auto &alias:clone->aliases())if(!used.count(&alias))alias.dropAllReferences();
  for(auto it=clone->alias_begin();it!=clone->alias_end();) {
    auto &alias=*it++;if(!used.count(&alias)) {alias.removeDeadConstantUsers();if(alias.use_empty())alias.eraseFromParent();}
  }
  for(auto &g:clone->globals())if(!used.count(&g))g.dropAllReferences();
  // CloneModule's constant-expression cache can retain dead GEP users even
  // after every unrelated function/initializer has been dropped. They are
  // not closure references; discard them before deciding whether data is live.
  for(auto &g:clone->globals())if(!used.count(&g))g.removeDeadConstantUsers();
  for(auto it=clone->global_begin();it!=clone->global_end();) {
    auto &g=*it++;
    if(!used.count(&g)) {if(!g.use_empty())fail("output","unretained region data still referenced",&g);g.eraseFromParent();}
  }
  order=std::move(materialised);
  StripDebugInfo(*clone);
  clone->setModuleIdentifier("");
  clone->setSourceFileName("");
  clone->setDataLayout("");
#if LLVM_VERSION_MAJOR >= 23
  clone->setTargetTriple(Triple());
#else
  clone->setTargetTriple("");
#endif

  while (!clone->named_metadata_empty())
    clone->eraseNamedMetadata(&*clone->named_metadata_begin());
  for (auto *g : order) {
    auto *c = g;
    clone->getFunctionList().splice(clone->end(), clone->getFunctionList(),
                                    c->getIterator());
  }
  unsigned n = 0;
  for (auto *g : order) {
    auto *c = g;
    c->setName("__canonical_" + std::to_string(n++));
  }
  for (auto *g : order) {
    auto *c = g;
    clone->getFunctionList().splice(clone->end(), clone->getFunctionList(),
                                    c->getIterator());
  }
  n = 0;
  for (auto *g : order) {
    auto *c = g;
    c->setName("f" + std::to_string(n++));
    c->setLinkage(GlobalValue::ExternalLinkage);
    c->setUnnamedAddr(GlobalValue::UnnamedAddr::None);
    for (Argument &a : c->args())
      a.setName("");
    for (BasicBlock &b : *c) {
      b.setName("");
      for (Instruction &i : b)
        i.setName("");
    }
  }
  // CloneModule retains unrelated declarations. Erase unused
  // declarations/globals.
  for (auto it = clone->alias_begin(); it != clone->alias_end();) {
    auto &a = *it++;
    if (a.use_empty())
      a.eraseFromParent();
  }
  bool again = true;
  while (again) {
    again = false;
    for (auto i = clone->global_begin(); i != clone->global_end();) {
      auto &g = *i++;
      if (g.use_empty()) {
        g.eraseFromParent();
        again = true;
      }
    }
    for (auto i = clone->begin(); i != clone->end();) {
      auto &g = *i++;
      if (g.isDeclaration() && g.use_empty()) {
        g.eraseFromParent();
        again = true;
      }
    }
  }
  // Declaration insertion order is not closure content. N32 may discover
  // ss_push/sf/pop in a different order from independently published output.
  std::vector<Function *> declarations;
  for(auto &g:*clone)if(g.isDeclaration())declarations.push_back(&g);
  std::sort(declarations.begin(),declarations.end(),[](auto *a,auto *b){return a->getName()<b->getName();});
  for(auto *g:declarations)clone->getFunctionList().splice(clone->end(),clone->getFunctionList(),g->getIterator());
  std::string text;
  raw_string_ostream out(text);
  clone->print(out, nullptr);
  auto hash = SHA256::hash(arrayRefFromStringRef(text));
  return toHex(hash, true);
}
void Analysis::releaseTransferGraphs() {
  for(auto &entry:fpTransfers)entry.second->dropAllReferences();
  fpTransfers.clear();
}
// PT2 is the same finite-width address image for scalar and vector lanes.
// Callers bind source operands (and source-keyed bounds), never joined vectors
// or temporary scalar instructions that would discard lane identity.
static AV gepImage(const GEPOperator &g, const DataLayout &dl, const AV &base,
                   function_ref<AV(Value *)> index,
                   function_ref<AV(const AV &, const APInt &, unsigned)> displace) {
  if (!base.top && base.atoms.empty()) return {};
  unsigned bits = dl.getIndexTypeSizeInBits(g.getType());
  unsigned pointerBits = dl.getPointerTypeSizeInBits(g.getType());
#if LLVM_VERSION_MAJOR >= 23
  SmallMapVector<Value *, APInt, 4> vars;
#else
  MapVector<Value *, APInt> vars;
#endif
  APInt off(bits, 0);
  if (!g.collectOffset(dl, bits, vars, off))
    unimplemented("§5 PT2 GEP offset", 2, &g);
  if (vars.empty()) return displace(base, off, pointerBits);

  std::vector<AV> domains;
  bool finite = true;
  for (const auto &entry : vars) {
    budgetTick();
    AV domain = index(entry.first);
    unsigned width = entry.first->getType()->getScalarSizeInBits();
    // Enumerate the complete small signed source domain, before truncation
    // or sign extension to I(a). K is the dialect's INT-set limit.
    constexpr unsigned SmallIndexBits = 12; // §5.1: K = 4096
    if (domain.top && width <= SmallIndexBits) {
      domain = {};
      for (unsigned n = 0; n < (1u << width); ++n)
        domain.merge(integer(APInt(width, n)));
    }
    if (!domain.top && domain.atoms.empty()) return {};
    finite &= !domain.top && llvm::all_of(domain.atoms,
        [](const Atom &a) { return a.kind == Atom::Int; });
    domains.push_back(std::move(domain));
  }
  if (finite) {
    std::set<APInt, bool(*)(const APInt &, const APInt &)> offsets(
        [](const APInt &a, const APInt &b) { return a.ult(b); });
    offsets.insert(off);
    unsigned n = 0;
    for (const auto &entry : vars) {
      auto old = std::move(offsets);
      offsets.clear();
      for (const auto &delta : old) for (const auto &v : domains[n].atoms) {
        budgetTick();
        offsets.insert(delta + v.integer.sextOrTrunc(bits) * entry.second);
      }
      ++n;
    }
    AV result;
    for (const auto &delta : offsets) {
      budgetTick();
      result.merge(displace(base, delta, pointerBits));
    }
    return result;
  }

  // A full-width unknown index generates a modular residue family. For a
  // partial-width address, preserved high bits can split that family; retain
  // every originating object with * when its image is not representable.
  AV result = base;
  unsigned n = 0;
  for (const auto &entry : vars) {
    const AV &domain = domains[n++];
    AV next;
    next.top = result.top;
    for (const auto &v : domain.atoms)
      if (v.kind == Atom::Root) next.atoms.insert(v);
    bool unknown = domain.top || llvm::any_of(domain.atoms,
        [](const Atom &a) { return a.kind != Atom::Int; });
    for (auto p : result.atoms) {
      budgetTick();
      if (p.kind != Atom::Ptr || !p.object) {
        next.atoms.insert(p);
        continue;
      }
      if (unknown) {
        auto q = p;
        unsigned zeros = entry.second.countr_zero();
        if (bits != pointerBits || zeros >= 63 || q.stride == -1)
          q.stride = -1;
        else q.stride = std::gcd(q.stride, int64_t(1) << zeros);
        canonicalOffset(q.offset, q.stride);
        next.atoms.insert(q);
      }
      for (const auto &v : domain.atoms) if (v.kind == Atom::Int) {
        budgetTick();
        next.merge(displace(AV{{p}, false},
            v.integer.sextOrTrunc(bits) * entry.second, pointerBits));
      }
    }
    result = std::move(next);
  }
  result = displace(result, off, pointerBits);
  numericalUnknown(result);
  return result;
}
AV Analysis::get(const Value *v) {
  if (auto *c = dyn_cast<ConstantInt>(v))
    return integer(c->getValue());
  if (auto *c=dyn_cast<ConstantFP>(v)) return integer(c->getValueAPF().bitcastToAPInt());
  if (isa<ConstantPointerNull>(v))
    return integer(APInt(M.getDataLayout().getPointerSizeInBits(), 0));
  if (auto *f = dyn_cast<Function>(v))
    return atom(Atom::Fn, f);
  if (auto *g = dyn_cast<GlobalVariable>(v))
    return atom(Atom::Ptr, g);
  if (auto *g = dyn_cast<GlobalAlias>(v))
    return get(g->getAliasee());
  if (auto *c = dyn_cast<ConstantExpr>(v)) {
    if (c->getOpcode()==Instruction::BitCast)
      return bitcast(c->getOperand(0),c->getType(),{});
    if (c->isCast()) {
      return convert(get(c->getOperand(0)),c->getOperand(0)->getType(),c->getType(),c->getOpcode());
    }
    if (c->getOpcode() == Instruction::GetElementPtr) {
      if (c->getType()->isVectorTy()) {
        AV result;
        unsigned lanes = cast<VectorType>(c->getType())->getElementCount().getKnownMinValue();
        for (unsigned k = 0; k < lanes; ++k) result.merge(field(c, {k}));
        return result;
      }
      return gepImage(*cast<GEPOperator>(c), M.getDataLayout(), get(c->getOperand(0)),
          [&](Value *v) { return get(v); },
          [&](const AV &base, const APInt &delta, unsigned width) {
            return displace(base, delta, width);
          });
    }
    AV a;
    a.top = true;
    return a;
  }
  if (isa<UndefValue>(v) || isa<PoisonValue>(v))
    return integer(APInt(std::max(1u, (unsigned)M.getDataLayout()
                                          .getTypeSizeInBits(v->getType())
                                          .getKnownMinValue()),
                         0));
  return values[v];
}
void Analysis::seed(Constant *c, const Value *obj, int64_t off, Type *t) {
  auto &dl = M.getDataLayout();
  if (t->isStructTy()) {
    auto *st = cast<StructType>(t);
    auto *layout = dl.getStructLayout(st);
    for (unsigned i = 0; i < st->getNumElements(); ++i)
      if (auto *e = c->getAggregateElement(i))
        seed(e, obj, off + layout->getElementOffset(i), st->getElementType(i));
  } else if (t->isArrayTy() || t->isVectorTy()) {
    Type *et = t->isArrayTy() ? t->getArrayElementType()
                              : cast<VectorType>(t)->getElementType();
    unsigned count =
        t->isArrayTy()
            ? t->getArrayNumElements()
            : cast<VectorType>(t)->getElementCount().getKnownMinValue();
    for (unsigned i = 0; i < count; ++i)
      if (auto *e = c->getAggregateElement(i))
        seed(e, obj, off + i * dl.getTypeAllocSize(et).getKnownMinValue(), et);
  } else {
    // Initialiser leaves are disjoint and visited exactly once by run().
    // Appending preserves their precise representation intervals without an
    // O(leaves^2) duplicate search (N22 exposes large shadow-stack tables).
    slots.push_back({obj,off,0,dl.getTypeStoreSize(t).getKnownMinValue(),get(c),false,false});
    changed=true;
  }
}
static bool overlaps(const Atom &p, const Slot &s, uint64_t size) {
  if (p.object != s.object)
    return false;
  if (p.stride == -1 || s.stride == -1)
    return true;
  if (p.stride == 0 && s.stride == 0)
    return (__int128)p.offset < (__int128)s.offset + s.bytes &&
           (__int128)s.offset < (__int128)p.offset + size;
  int64_t stride = std::gcd(p.stride, s.stride);
  if (stride == 0)
    return true;
  // Byte interval overlap, including non-aligned partial reads.
  if((__int128)size+s.bytes-1 >= stride) return true;
  __int128 distance=((__int128)p.offset-s.offset)%stride;
  if(distance<0) distance+=stride;
  return distance < s.bytes || distance+size>stride;
}
// PT8 intersects each represented storage interval with a finite copy. A
// residue family is an exact union of intervals, not a partially known value.
static void copySlotFamily(const Slot &slot, const Atom &source,
                           const Atom &destination, uint64_t length,
                           function_ref<void(const AV &, const AV &, uint64_t, bool)> write) {
  assert(slot.stride && !source.stride && !destination.stride);
  __int128 begin = source.offset, end = begin + length;
  __int128 first = std::max(begin - slot.bytes + 1, (__int128)INT64_MIN);
  __int128 last = std::min(end, (__int128)INT64_MAX + 1);
  int64_t step = slot.stride == -1 ? 1 : slot.stride;
  __int128 remainder = (first - slot.offset) % step;
  if (remainder < 0) remainder += step;
  if (remainder) first += step - remainder;
  for (__int128 offset = first; offset < last; offset += step) {
    budgetTick();
    __int128 lo = std::max(offset, begin), hi = std::min(offset + slot.bytes, end);
    if (lo >= hi) continue;
    auto target = destination;
    target.offset = (APInt(64, destination.offset) + APInt(64, uint64_t(lo - begin))).getSExtValue();
    AV address{{target}, false};
    if (slot.filled || (lo == offset && hi == offset + slot.bytes))
      write(slot.value, address, uint64_t(hi - lo), slot.filled);
    else {
      AV partial; partial.top = true;
      for (const auto &a : slot.value.atoms)
        if (a.kind == Atom::Root) partial.atoms.insert(a);
      write(partial, address, uint64_t(hi - lo), false);
    }
  }
}
void Analysis::indexSlot(size_t n) {
  auto &s=slots[n];
  if(!s.stride && !s.filled) {
    exactSlots[s.object][s.offset].push_back(n);
    maxSlotBytes[s.object]=std::max(maxSlotBytes[s.object],s.bytes);
  } else otherSlots[s.object].push_back(n);
}
std::vector<size_t> Analysis::overlappingSlots(const Atom &a,uint64_t bytes) {
  std::vector<size_t> result;
  auto test=[&](size_t n) {budgetTick();memoryWork(&AnalysisWork::MemoryWork::loadSlotTests);if(overlaps(a,slots[n],bytes))result.push_back(n);};
  if(auto it=otherSlots.find(a.object);it!=otherSlots.end())for(auto n:it->second)test(n);
  if(auto it=exactSlots.find(a.object);it!=exactSlots.end()) {
    auto &byOffset=it->second;
    if(a.stride)for(auto &entry:byOffset)for(auto n:entry.second)test(n);
    else {
      __int128 lo=(__int128)a.offset-maxSlotBytes[a.object]+1,hi=(__int128)a.offset+bytes;
      auto begin=byOffset.lower_bound((int64_t)std::max(lo,(__int128)INT64_MIN));
      for(auto p=begin;p!=byOffset.end() && (__int128)p->first<hi;++p)for(auto n:p->second)test(n);
    }
  }
  return result;
}
void Analysis::store(const AV &v, const AV &p, uint64_t size, bool filled) {
  std::set<const Value *> compactObjects;
  std::optional<AV> coverage;
  bool hasFamilies = !filled && llvm::any_of(p.atoms, [&](const Atom &a) {
    if (a.kind != Atom::Ptr) return false;
    auto found = otherSlots.find(a.object);
    return found != otherSlots.end() && !found->second.empty();
  });
  if (hasFamilies) coverage = coverageRequirement(v);
  auto coversWrittenValue = [&](const AV &prior) {
    // Covering all offsets of each origin proves coverage of these offsets.
    // This superset is only a proof requirement, never stored or propagated.
    // A failed proof still uses the exact test (notably for stride families).
    return (coverage && contains(prior, *coverage)) || contains(prior, v);
  };
  for (auto a : p.atoms)
    if (a.kind == Atom::Ptr) {
      if (activeBudget) {
        ++activeBudget->work.slotJoins;
        if (auto *f = activeBudget->work.currentFunction) ++f->slotJoins;
      }
      canonicalOffset(a.offset, a.stride);
      // Initial zero images with the same start are nested intervals. Their
      // exact union is the largest extent, not a new slot for every loop round.
      if(filled && !v.top && v.atoms.size()==1 && v.atoms.begin()->kind==Atom::Int && v.atoms.begin()->integer.isZero()) {
        bool found=false;
        for(size_t n:otherSlots[a.object]) {
          auto &s=slots[n];
          if(s.filled && s.offset==a.offset && s.stride==a.stride && s.numerical==a.numerical && !s.value.top && s.value.atoms.size()==1 && s.value.atoms.begin()->kind==Atom::Int && s.value.atoms.begin()->integer.isZero()) {
            if(size>s.bytes) {
              slotIndex.erase(SlotKey{s.object,s.offset,s.stride,s.bytes,s.filled,s.numerical});
              s.bytes=size;slotIndex.emplace(SlotKey{s.object,s.offset,s.stride,s.bytes,s.filled,s.numerical},n);changed=true;
              if (activeBudget) activeBudget->invalidateLoadImages(a.object);
            }
            found=true;break;
          }
        }
        if(found)continue;
      }
      // A narrower write may be omitted only when every one of its values is
      // already present throughout the covering family. Never spread a new
      // value from one exact address to the rest of a residue class.
      if (!filled && llvm::any_of(otherSlots[a.object], [&](size_t n) {
            const auto &s = slots[n];
            return !s.filled && s.bytes == size && s.numerical == a.numerical &&
                   offsetContains(s.offset, s.stride, a.offset, a.stride) &&
                   coversWrittenValue(s.value);
          })) continue;
      SlotKey key{a.object,a.offset,a.stride,size,filled,a.numerical};
      auto [it,inserted]=slotIndex.emplace(key,slots.size());
      if(inserted) {
        slots.push_back({a.object,a.offset,a.stride,size,v,filled,a.numerical});
        indexSlot(it->second);
        changed=true;
        if (activeBudget) activeBudget->invalidateLoadImages(a.object);
      } else if (slots[it->second].value.merge(v)) {
        changed = true;
        if (activeBudget) activeBudget->invalidateLoadImages(a.object);
      }
      if (!filled && a.stride) compactObjects.insert(a.object);
    }
  // Delete a redundant fact by moving the last slot into its place. Repair
  // only those two index entries; unrelated objects and their AVs stay put.
  auto positions = [&](const Slot &s) -> std::vector<size_t> & {
    return !s.stride && !s.filled ? exactSlots.at(s.object).at(s.offset)
                                 : otherSlots.at(s.object);
  };
  auto key = [](const Slot &s) {
    return SlotKey{s.object,s.offset,s.stride,s.bytes,s.filled,s.numerical};
  };
  auto eraseSlot = [&](size_t n) {
    auto &s = slots[n];
    slotIndex.erase(key(s));
    auto &old = positions(s);
    auto entry = llvm::find(old, n);
    assert(entry != old.end());
    old.erase(entry);
    size_t last = slots.size() - 1;
    if (n != last) {
      auto &moved = slots[last];
      auto &indices = positions(moved);
      auto entry = llvm::find(indices, last);
      assert(entry != indices.end());
      *entry = n;
      slotIndex.at(key(moved)) = n;
      slots[n] = std::move(moved);
      memoryWork(&AnalysisWork::MemoryWork::reindexedSlots);
    }
    slots.pop_back();
  };
  for (auto *object : compactObjects) {
    memoryWork(&AnalysisWork::MemoryWork::compactions);
    // Keep initial byte images and representation widths separate. Remove an
    // old slot only when the whole interval/value fact is represented by a
    // family. Snapshot keys, since swap removal changes positional indices.
    std::vector<SlotKey> candidates;
    for (auto n : otherSlots[object]) candidates.push_back(key(slots[n]));
    for (auto &entry : exactSlots[object])
      for (auto n : entry.second) candidates.push_back(key(slots[n]));
    for (auto &candidate : candidates) {
      budgetTick();
      memoryWork(&AnalysisWork::MemoryWork::compactSlots);
      size_t n = slotIndex.at(candidate);
      const auto &s = slots[n];
      bool covered = !s.filled && llvm::any_of(otherSlots[s.object], [&](size_t m) {
        const auto &family = slots[m];
        return m != n && !family.filled && family.bytes == s.bytes &&
               family.numerical == s.numerical &&
               offsetContains(family.offset, family.stride, s.offset, s.stride) &&
               contains(family.value, s.value);
      });
      if (covered) eraseSlot(n);
    }
  }
}
AV Analysis::read(Value *base, uint64_t offset, Type *t) {
  AV p=get(base), shifted;shifted.top=p.top;
  for(auto x:p.atoms) {if(x.kind==Atom::Ptr)x.offset+=offset;shifted.atoms.insert(x);}
  return load(shifted,t);
}
// A local straight-line reaching store is an independent proof of the actual
// descriptor field at this call. It does not change the normative S2 solution.
AV Analysis::readAt(CallBase &call, Value *base, uint64_t offset, Type *type) {
  auto address=get(base);
  if(address.top || address.atoms.size()!=1) return read(base,offset,type);
  auto p=*address.atoms.begin();
  if(p.kind!=Atom::Ptr || p.stride || !isa<AllocaInst>(p.object)) return read(base,offset,type);
  p.offset+=offset;
  uint64_t bytes=M.getDataLayout().getTypeStoreSize(type).getKnownMinValue();
  for(auto it=call.getIterator();it!=call.getParent()->begin();) {
    Instruction &i=*--it;
    if(auto *st=dyn_cast<StoreInst>(&i)) {
      auto dst=get(st->getPointerOperand());
      for(auto &d:dst.atoms) if(d.kind==Atom::Ptr && (!d.object || d.object==p.object)) {
        Slot written{d.object,d.offset,d.stride,M.getDataLayout().getTypeStoreSize(st->getValueOperand()->getType()).getKnownMinValue(),{},false};
        if(!d.object || overlaps(p,written,bytes)) {
          if(!dst.top && dst.atoms.size()==1 && !d.stride && d.offset==p.offset && written.bytes==bytes)
            return get(st->getValueOperand());
          // Decode actual constant bytes from a containing vector/aggregate
          // store. This is a call-local reaching definition, not an S2 union
          // of fragments (which would incorrectly reconstruct pointers).
          if(!dst.top && dst.atoms.size()==1 && !d.stride && d.offset<=p.offset &&
             (__int128)p.offset+bytes<=(__int128)d.offset+written.bytes)
            if(auto *value=dyn_cast<Constant>(st->getValueOperand()))
              if(auto *folded=ConstantFoldLoadFromConst(value,type,APInt(64,p.offset-d.offset),M.getDataLayout()))
                if(isa<ConstantInt>(folded)||isa<ConstantPointerNull>(folded))return get(folded);
          return read(base,offset,type);
        }
      }
      if(dst.top) return read(base,offset,type);
    } else if(auto *c=dyn_cast<CallBase>(&i)) {
      if(auto *intrinsic=dyn_cast<IntrinsicInst>(c)) {
        auto id=intrinsic->getIntrinsicID();
        if(id==Intrinsic::lifetime_start || id==Intrinsic::lifetime_end) continue;
      }
      if(auto *mem=dyn_cast<MemIntrinsic>(c)) {
        auto dst=get(mem->getDest()); auto *length=dyn_cast<ConstantInt>(mem->getLength());
        bool disjoint=!dst.top && length;
        for(auto &d:dst.atoms) if(d.kind==Atom::Ptr) {
          Slot written{d.object,d.offset,d.stride,length ? length->getLimitedValue() : 1,{},false};
          if(!d.object || overlaps(p,written,bytes)) disjoint=false;
        }
        if(disjoint) continue;
      }
      // These markers have no classical-memory writes: oracle descriptors
      // are read-only and oracle execution uses its private entry-state image.
      // Generation/effect markers are deliberately absent (they may write).
      if(auto *g=c->getCalledFunction()) {
        auto n=g->getName();
        if(n=="__bennett_qalloc"||n=="__bennett_qborrow"||n=="__bennett_qfree"||
           n=="__bennett_gate"||n=="__bennett_gate2"||n=="__bennett_gate3"||
           n=="__bennett_rot"||n=="__bennett_measure"||n=="__bennett_qload"||
           n=="__bennett_qstore"||n=="__bennett_qprep"||n=="__bennett_oracle"||
           n=="__bennett_inplace") continue;
      }
      // Any call could clobber an escaped local. Only cross calls before the
      // reaching store when no relevant field has yet been proven.
      return read(base,offset,type);
    }
  }
  return read(base,offset,type);
}
enum LoadPart { WholeValue = 1, PartialValue = 2, RepeatedBytes = 4 };
static unsigned classifyLoad(const Atom &a, const Slot &s, uint64_t size, Type *t) {
  if (s.filled && !a.stride && !s.stride && a.offset >= s.offset &&
      (__int128)a.offset + size <= (__int128)s.offset + s.bytes &&
      (t->isIntegerTy() || t->isPointerTy() || t->isFloatingPointTy()))
    return RepeatedBytes;
  int64_t spacing = std::gcd(a.stride, s.stride);
  __int128 difference = (__int128)a.offset - s.offset;
  bool sameStart = spacing ? difference % spacing == 0 : difference == 0;
  bool whole = size == s.bytes && sameStart;
  bool onlyWhole = whole && (!spacing || uint64_t(spacing) >= size);
  return (whole ? WholeValue : 0) | (onlyWhole ? 0 : PartialValue);
}
AV Analysis::load(const AV &p, Type *t) {
  AV r;
  std::set<const AV *> joinedImages;
  uint64_t size = M.getDataLayout().getTypeStoreSize(t).getKnownMinValue();
  r.top = p.top;
  for (auto &a : p.atoms)
    if (a.kind == Atom::Ptr) {
      memoryWork(&AnalysisWork::MemoryWork::loadAddresses);
      if (!a.object) {
        r.top = true;
        continue;
      }
      auto classify = [&]() {
        std::vector<std::pair<size_t, unsigned>> parts;
        for (auto n : overlappingSlots(a, size))
          parts.emplace_back(n, classifyLoad(a, slots[n], size, t));
        return parts;
      };
      auto image = [&](ArrayRef<std::pair<size_t, unsigned>> parts) {
        memoryWork(&AnalysisWork::MemoryWork::loadImageComputations);
        AV r;
        bool partial = false;
        for (auto [n, classification] : parts) {
            auto &s=slots[n];
            if (classification == RepeatedBytes) {
              AV decoded;
              decoded.top = s.value.top;
              for (auto &x : s.value.atoms)
                if (x.kind == Atom::Int) {
                  APInt bits(M.getDataLayout().getTypeSizeInBits(t).getKnownMinValue(), 0);
                  for (unsigned b = 0; b < size; ++b)
                    bits |= x.integer.zextOrTrunc(bits.getBitWidth()).shl(b * 8);
                  decoded.merge(integer(bits));
                }
              r.merge(decoded);
              continue;
            }
            // A family can have both identical-interval and partial-overlap
            // members. PT6 retains the whole FN/ROOT/pointer alternatives from
            // the former even when the latter also contribute non-handle TOP.
            if (classification & WholeValue) r.merge(s.value);
            if (classification & PartialValue) {
              partial = true;
              for (auto &b : s.value.atoms)
                if (b.kind == Atom::Root)
                  r.atoms.insert(b);
            }
          }
        // Immutable initialiser bytes reconstruct whole integer loads exactly.
        if (auto *g = dyn_cast<GlobalVariable>(a.object);
            g && g->isConstant() && t->isIntegerTy() && a.stride == 0) {
          SmallVector<size_t, 4> byteSlots;
          for (auto [n, classification] : parts)
            if (!slots[n].stride) byteSlots.push_back(n);
          // Any slot covering a requested byte overlaps the load interval.
          // Preserve the original first-match order while excluding unrelated
          // objects and intervals, including entirely out-of-object reads.
          llvm::sort(byteSlots);
          APInt bits(t->getIntegerBitWidth(), 0);
          bool known = true;
          for (unsigned b = 0; b < size; ++b) {
            bool found = false;
            for (auto n : byteSlots) {
              memoryWork(&AnalysisWork::MemoryWork::loadByteSlotTests);
              budgetTick();
              const auto &s = slots[n];
              if (s.object == a.object && s.stride == 0 &&
                  s.offset <= a.offset + b &&
                  a.offset + b < s.offset + (int64_t)s.bytes &&
                  s.value.atoms.size() == 1) {
                auto &x = *s.value.atoms.begin();
                if (x.kind != Atom::Int)
                  continue;
                unsigned bi = a.offset + b - s.offset;
                unsigned shift = M.getDataLayout().isLittleEndian()
                                     ? bi * 8
                                     : (s.bytes - 1 - bi) * 8;
                uint64_t byte = x.integer.lshr(shift).getLimitedValue() & 255;
                unsigned dest = M.getDataLayout().isLittleEndian()
                                    ? b * 8
                                    : (size - 1 - b) * 8;
                bits |= APInt(bits.getBitWidth(), byte).shl(dest);
                found = true;
                break;
              }
            }
            known &= found;
          }
          if (known) {
            r.merge(integer(bits));
            partial = false;
          }
        }
        if (partial)
          r.top = true;
        return r;
      };
      if (activeBudget) {
        auto &images = activeBudget->loadImages[a.object];
        auto key = std::make_pair(a, t);
        auto found = images.find(key);
        if (found == images.end()) {
          memoryWork(&AnalysisWork::MemoryWork::loadImageMisses);
          auto parts = classify();
          std::vector<AnalysisBudget::LoadPartKey> keys;
          for (auto [n, classification] : parts) {
            auto &s = slots[n];
            keys.emplace_back(s.offset, s.stride, s.bytes, s.filled, s.numerical, classification);
          }
          llvm::sort(keys);
          // PT6 depends on the slot facts and their interval classifications.
          // Immutable integer reconstruction additionally reads exact bytes.
          // Stable keys survive unrelated slot swaps; every growing write to
          // this object invalidates both address and transfer-image caches.
          std::optional<int64_t> byteOffset;
          if (auto *g = dyn_cast<GlobalVariable>(a.object);
              g && g->isConstant() && t->isIntegerTy() && !a.stride)
            byteOffset = a.offset;
          auto signature = std::make_tuple(t, std::move(keys), byteOffset);
          auto &memo = activeBudget->loadSignatures[a.object];
          auto prior = memo.find(signature);
          if (prior == memo.end())
            prior = memo.emplace(std::move(signature),
                                 activeBudget->internLoadImage(image(parts))).first;
          else memoryWork(&AnalysisWork::MemoryWork::loadSignatureHits);
          found = images.emplace(key, prior->second).first;
        } else memoryWork(&AnalysisWork::MemoryWork::loadImageHits);
        // The immutable image already joined for another represented address
        // contributes no new alternatives; retain the entire union once.
        if (joinedImages.insert(found->second.get()).second) r.merge(*found->second);
        else memoryWork(&AnalysisWork::MemoryWork::loadImageUnionSkips);
      } else r.merge(image(classify()));
    }
  return r;
}
std::set<Function *> Analysis::candidates(Value *v, FunctionType *type) {
  AV a = get(v);
  std::set<Function *> r;
  for (auto &x : a.atoms)
    if (x.kind == Atom::Fn)
      if (auto *f = resolve(const_cast<Value *>(x.object)))
        r.insert(f);
  bool top = a.top;
  for (auto &x : a.atoms)
    top |= x.kind == Atom::Ptr;
  if (top)
    for (Function &f : M)
      if (f.hasAddressTaken() && (!type || f.getFunctionType() == type) &&
          !markers().count(f.getName().str()))
        r.insert(resolve(&f));
  return r;
}
struct Leaf {
  std::vector<unsigned> path;
  uint64_t offset;
  Type *type;
};
static std::vector<Leaf> leaves(Type *t, const DataLayout &dl) {
  std::vector<Leaf> result;
  std::function<void(Type *, std::vector<unsigned>, uint64_t)> walk =
      [&](Type *ty, std::vector<unsigned> p, uint64_t offset) {
        if (auto *st = dyn_cast<StructType>(ty)) {
          auto *layout = dl.getStructLayout(st);
          for (unsigned i = 0; i < st->getNumElements(); ++i) {
            auto q = p;
            q.push_back(i);
            walk(st->getElementType(i), q,
                 offset + layout->getElementOffset(i));
          }
        } else if (auto *at = dyn_cast<ArrayType>(ty)) {
          for (unsigned i = 0; i < at->getNumElements(); ++i) {
            auto q = p;
            q.push_back(i);
            walk(at->getElementType(), q,
                 offset + i * dl.getTypeAllocSize(at->getElementType())
                                  .getKnownMinValue());
          }
        } else if (auto *vt = dyn_cast<VectorType>(ty)) {
          unsigned bits =
              dl.getTypeSizeInBits(vt->getElementType()).getKnownMinValue();
          for (unsigned i = 0; i < vt->getElementCount().getKnownMinValue(); ++i) {
            auto q = p;
            q.push_back(i);
            walk(vt->getElementType(), q, offset + i * bits / 8);
          }
        } else
          result.push_back({p, offset, ty});
      };
  walk(t, {}, 0);
  return result;
}
void Analysis::bind(CallBase &c, Function *f) {
  if (!f) return;
  if(f->isDeclaration()) {
    AV unknown;unknown.top=true;
    if(c.getType()->isAggregateType() || c.getType()->isVectorTy())
      for(auto &leaf:leaves(c.getType(),M.getDataLayout()))setField(&c,leaf.path,unknown);
    else changed|=values[&c].merge(unknown);
    std::set<const Value *> reachable;bool opaque=false;
    for(Value *v:c.args())if(v->getType()->isPointerTy()) {
      auto address=get(v);opaque|=address.top;
      for(auto &p:address.atoms)if(p.kind==Atom::Ptr) {
        if(!p.object)opaque=true;else reachable.insert(p.object);
      }
    }
    bool more=true;
    while(more) {
      more=false;
      for(auto &slot:slots)if(opaque || reachable.count(slot.object))
        for(auto &p:slot.value.atoms)if(p.kind==Atom::Ptr) {
          if(!p.object && !opaque){opaque=true;more=true;}
          else more|=reachable.insert(p.object).second;
        }
    }
    if(opaque)for(auto &slot:slots)reachable.insert(slot.object);
    for(auto *object:reachable)store(unknown,atom(Atom::Ptr,object,0,-1),1);
    return;
  }
  edges[c.getFunction()].insert(f);
  unsigned i = 0;
  for (Argument &a : f->args()) {
    if (i < c.arg_size()) {
      if (a.getType()->isAggregateType() || a.getType()->isVectorTy())
        copyFields(&a, c.getArgOperand(i));
      else if (a.hasByValAttr()) {
        // PT9: the callee copy is a distinct abstract object, not an alias.
        changed |= values[&a].merge(atom(Atom::Ptr, &a));
        auto src = get(c.getArgOperand(i));
        uint64_t size = M.getDataLayout().getTypeAllocSize(a.getParamByValType()).getKnownMinValue();
        auto snapshot = slots;
        for (auto &p : src.atoms)
          if (p.kind == Atom::Ptr)
            for (auto &slot : snapshot)
              if (slot.object == p.object && slot.stride == 0 && p.stride == 0 &&
                  slot.offset >= p.offset && slot.offset + slot.bytes <= p.offset + size)
                store(slot.value, atom(Atom::Ptr, &a, slot.offset - p.offset), slot.bytes, slot.filled);
      } else
        changed |= values[&a].merge(get(c.getArgOperand(i)));
    }
    ++i;
  }
  for (BasicBlock &b : *f)
    if (auto *r = dyn_cast<ReturnInst>(b.getTerminator()))
      if (r->getReturnValue()) {
        if (c.getType()->isAggregateType() || c.getType()->isVectorTy())
          copyFields(&c, r->getReturnValue());
        else
          changed |= values[&c].merge(get(r->getReturnValue()));
      }
}
static bool allocation(const Function *f) {
  if (!f)
    return false;
  static const std::set<std::string> names = {"malloc",
                                              "calloc",
                                              "realloc",
                                              "aligned_alloc",
                                              "posix_memalign",
                                              "memalign",
                                              "strdup",
                                              "strndup",
                                              "_Znwm",
                                              "_Znam",
                                              "_ZnwmRKSt9nothrow_t",
                                              "_ZnamRKSt9nothrow_t",
                                              "_ZnwmSt11align_val_t",
                                              "_ZnamSt11align_val_t",
                                              "__rust_alloc",
                                              "__rust_alloc_zeroed",
                                              "__rust_realloc",
                                              "julia.gc_alloc_obj",
                                              "ijl_gc_alloc_typed",
                                              "jl_gc_alloc",
                                              "ijl_gc_small_alloc",
                                              "ijl_gc_big_alloc",
                                              "__bennett_nz_alloc"};
  return names.count(f->getName().str()) ||
         f->hasFnAttribute(Attribute::AllocSize) ||
         (f->hasFnAttribute(Attribute::AllocKind) &&
          (uint64_t(f->getFnAttribute(Attribute::AllocKind).getAllocKind()) & uint64_t(AllocFnKind::Alloc)));
}
AV Analysis::field(const Value *v, const Path &path) {
  if (path.empty())
    return get(v);
  if (auto *expr=dyn_cast<ConstantExpr>(v);expr && expr->getOpcode()==Instruction::BitCast)
    return bitcast(expr->getOperand(0),expr->getType(),path);
  if (auto *g = dyn_cast<GEPOperator>(v); g && isa<ConstantExpr>(v)) {
    auto operand = [&](const Value *value) {
      return value->getType()->isVectorTy() ? field(value, path) : get(value);
    };
    return gepImage(*g, M.getDataLayout(), operand(g->getPointerOperand()), operand,
        [&](const AV &base, const APInt &delta, unsigned width) {
          return displace(base, delta, width);
        });
  }
  if (auto *c = dyn_cast<Constant>(v)) {
    Constant *cur = const_cast<Constant *>(c);
    for (unsigned n : path) {
      cur = cur->getAggregateElement(n);
      if (!cur) {
        AV a;
        a.top = true;
        return a;
      }
    }
    return get(cur);
  }
  return fields[{v, path}];
}
void Analysis::setField(const Value *v, const Path &path, const AV &a) {
  if (activeBudget) {
    ++activeBudget->work.fieldJoins;
    if (auto *f = activeBudget->work.currentFunction) ++f->fieldJoins;
  }
  if (path.empty())
    changed |= values[v].merge(a);
  else
    changed |= fields[{v, path}].merge(a);
  changed |= values[v].merge(a);
}
void Analysis::copyFields(const Value *dst, const Value *src) {
  for (auto &l : leaves(dst->getType(), M.getDataLayout()))
    setField(dst, l.path, field(src, l.path));
}
AV Analysis::bitcast(const Value *source, Type *destination, const Path &path) {
  const auto &dl=M.getDataLayout();
    auto src = leaves(source->getType(), dl), dst = leaves(destination, dl);
    if (src.size()==dst.size() && dl.getTypeSizeInBits(src[0].type)==dl.getTypeSizeInBits(dst[0].type)) {
      for(unsigned k=0;k<src.size();++k) if(dst[k].path==path) return field(source,src[k].path);
    }
    unsigned total = dl.getTypeSizeInBits(destination).getKnownMinValue();
    // Bitcast vector lanes are packed, with endian-dependent bit order.
    for (unsigned di=0;di<dst.size();++di) {
      auto &d=dst[di];
      if(d.path!=path) continue;
      unsigned dw = dl.getTypeSizeInBits(d.type).getFixedValue();
      unsigned db = dl.isLittleEndian() ? di * dw : total - di * dw - dw;
      AV result; std::set<APInt, bool(*)(const APInt &, const APInt &)> bits(
          [](const APInt &a, const APInt &b) { return a.ult(b); });
      bits.insert(APInt(dw, 0));
      for (unsigned si=0;si<src.size();++si) {
        auto &l=src[si];
        unsigned sw = dl.getTypeSizeInBits(l.type).getFixedValue();
        unsigned sb = dl.isLittleEndian() ? si * sw : total - si * sw - sw;
        unsigned lo = std::max(sb, db), hi = std::min(sb + sw, db + dw);
        if (lo >= hi) continue;
        AV v = field(source, l.path);
        result.top |= v.top;
        std::vector<APInt> parts;
        for (auto &x : v.atoms) {
          if (x.kind == Atom::Int)
            parts.push_back(x.integer.lshr(lo - sb).zextOrTrunc(dw) & APInt::getLowBitsSet(dw, hi - lo));
          else if (lo == sb && hi == sb + sw && sw == dw)
            result.atoms.insert(x);
          else {
            result.top = true;
            if (x.kind == Atom::Root) result.atoms.insert(x);
          }
        }
        auto old = bits; bits.clear();
        for (auto &a : old) for (auto &b : parts) {
          bits.insert(a | b.shl(lo - db));
          if (bits.size() > 4096) break;
        }
        if (bits.size() > 4096) { result.top = true; bits.clear(); }
      }
      if (!result.top) for (auto &x : bits) result.merge(integer(x));
      return result;
    }
  llvm_unreachable("invalid bitcast lane path");
}
static AV laneBinary(unsigned opcode,const AV &x,const AV &y,Module &m) {
  AV value;value.top=x.top || y.top;
  for(auto &a:x.atoms)for(auto &b:y.atoms) {
    if(a.kind==Atom::Int && b.kind==Atom::Int) {
      auto *left=ConstantInt::get(m.getContext(),a.integer),*right=ConstantInt::get(m.getContext(),b.integer);
      Constant *fold=ConstantFoldBinaryOpOperands(opcode,left,right,m.getDataLayout());
      if(auto *c=dyn_cast_or_null<ConstantInt>(fold))value.merge(integer(c->getValue()));
      else if(fold && (isa<PoisonValue>(fold)||isa<UndefValue>(fold))) {
        // Only N14 totalises a dynamic operation to zero. A divide fault
        // produces no result; N7 zeroes constants, not a faulting operation.
        if(opcode==Instruction::Shl || opcode==Instruction::LShr || opcode==Instruction::AShr)
          value.merge(integer(APInt(a.integer.getBitWidth(),0)));
      }
      else value.top=true;
    } else {
      value.top=true;
      if(a.kind==Atom::Root)value.atoms.insert(a);
      if(b.kind==Atom::Root)value.atoms.insert(b);
    }
  }
  return value;
}
bool Analysis::composite(Instruction &i) {
  const auto &dl = M.getDataLayout();
  if(auto *call=dyn_cast<IntrinsicInst>(&i)) {
    auto name=call->getCalledFunction()->getName();
    auto base=Intrinsic::getBaseName(call->getIntrinsicID()).drop_front(5);
    bool extrema=base=="smax"||base=="smin"||base=="umax"||base=="umin";
    bool overflow=base=="uadd.with.overflow"||base=="usub.with.overflow"||base=="sadd.with.overflow"||base=="ssub.with.overflow";
    if((extrema || overflow) && call->getArgOperand(0)->getType()->isIntegerTy()) {
      auto x=get(call->getArgOperand(0)),y=get(call->getArgOperand(1));
      if(extrema) {x.merge(y);setField(&i,{},x);return true;}
      bool sub=base.contains("sub"),sign=base.starts_with("s");
      auto sum=laneBinary(sub?Instruction::Sub:Instruction::Add,x,y,M);AV left=sub?x:sum,right=sub?y:x;
      auto predicate=CmpInst::ICMP_ULT;
      if(sign) {
        left=laneBinary(Instruction::And,laneBinary(Instruction::Xor,x,sum,M),laneBinary(Instruction::Xor,sub?x:y,sub?y:sum,M),M);
        right=integer(APInt(call->getArgOperand(0)->getType()->getIntegerBitWidth(),0));predicate=CmpInst::ICMP_SLT;
      }
      AV flag;
      if(left.top || right.top) {flag.merge(integer(APInt(1,0)));flag.merge(integer(APInt(1,1)));}
      for(auto &a:left.atoms)for(auto &b:right.atoms)if(a.kind==Atom::Int && b.kind==Atom::Int)
        flag.merge(integer(APInt(1,ICmpInst::compare(a.integer,b.integer,predicate))));
      setField(&i,{0},sum);setField(&i,{1},flag);return true;
    }
    if(base=="ctpop" || base=="ctlz" || base=="cttz") {
      auto helper="__bennett_rt_"+base.str()+"_i"+std::to_string(i.getType()->getScalarSizeInBits());
      if(auto *f=M.getFunction(helper))bind(*call,f);
      else {AV top;top.top=true;setField(&i,{},top);}
      return true;
    }
    if(name.starts_with("llvm.vp.merge.") || name.starts_with("llvm.vp.select.")) {
      unsigned n=cast<VectorType>(i.getType())->getElementCount().getKnownMinValue();
      for(unsigned k=0;k<n;++k) {
        AV value=field(call->getArgOperand(1),{k});value.merge(field(call->getArgOperand(2),{k}));
        if(name.starts_with("llvm.vp.select."))value.merge(integer(APInt(dl.getTypeSizeInBits(cast<VectorType>(i.getType())->getElementType()).getKnownMinValue(),0)));
        setField(&i,{k},value);
      }
      return true;
    }
    bool vp=name.starts_with("llvm.vp.reduce."),reduce=name.starts_with("llvm.vector.reduce.");
    if(vp || reduce) {
      auto op=name.drop_front(vp?15:19).split('.').first;
      unsigned opcode=op=="add"?Instruction::Add:op=="mul"?Instruction::Mul:op=="and"?Instruction::And:op=="or"?Instruction::Or:op=="xor"?Instruction::Xor:0;
      if(opcode) {
        auto *vector=call->getArgOperand(vp?1:0);unsigned n=cast<VectorType>(vector->getType())->getElementCount().getKnownMinValue();
        AV acc=vp?get(call->getArgOperand(0)):field(vector,{0});
        for(unsigned k=vp?0:1;k<n;++k) {
          auto next=laneBinary(opcode,acc,field(vector,{k}),M);
          if(vp)next.merge(acc);acc=next;
        }
        setField(&i,{},acc);return true;
      }
    }
  }
  if(i.getType()->isVectorTy() && !isa<BitCastInst>(i) && (isa<BinaryOperator>(i)||isa<CmpInst>(i)||isa<CastInst>(i))) {
    for(auto &leaf:leaves(i.getType(),dl)) {
      auto x=field(i.getOperand(0),leaf.path);AV value;
      if(auto *c=dyn_cast<CastInst>(&i))value=convert(x,cast<VectorType>(c->getOperand(0)->getType())->getElementType(),leaf.type,c->getOpcode());
      else if(auto *cmp=dyn_cast<ICmpInst>(&i)) {
        auto y=field(i.getOperand(1),leaf.path);
        if(x.top || y.top) {value.merge(integer(APInt(1,0)));value.merge(integer(APInt(1,1)));}
        for(auto &a:x.atoms)for(auto &b:y.atoms)
          if(a.kind==Atom::Int && b.kind==Atom::Int)value.merge(integer(APInt(1,ICmpInst::compare(a.integer,b.integer,cmp->getPredicate()))));
      } else if(isa<FCmpInst>(i)) {value.merge(integer(APInt(1,0)));value.merge(integer(APInt(1,1)));}
      else value=laneBinary(i.getOpcode(),x,field(i.getOperand(1),leaf.path),M);
      setField(&i,leaf.path,value);
    }
    return true;
  }
  if (auto *c = dyn_cast<BitCastInst>(&i)) {
    for (auto &leaf:leaves(c->getType(),dl))
      setField(c,leaf.path,bitcast(c->getOperand(0),c->getType(),leaf.path));
    return true;
  }
  if(auto *cmp=dyn_cast<AtomicCmpXchgInst>(&i)) {
    auto old=load(get(cmp->getPointerOperand()),cmp->getCompareOperand()->getType());
    auto expected=get(cmp->getCompareOperand()); AV success;
    if(old.top || expected.top) {success.merge(integer(APInt(1,0)));success.merge(integer(APInt(1,1)));}
    for(auto &x:old.atoms) for(auto &y:expected.atoms) {
      if(x.kind==Atom::Int && y.kind==Atom::Int)
        success.merge(integer(APInt(1,x.integer==y.integer)));
      else {success.merge(integer(APInt(1,0)));success.merge(integer(APInt(1,1)));}
    }
    setField(cmp,{0},old);setField(cmp,{1},success);
    // Exactly PT3 over N9's select in accepted 0.2.10 (flow insensitive).
    AV next=old;next.merge(get(cmp->getNewValOperand()));
    store(next,get(cmp->getPointerOperand()),dl.getTypeStoreSize(cmp->getCompareOperand()->getType()).getKnownMinValue());
    return true;
  }
  if (auto *e = dyn_cast<ExtractValueInst>(&i)) {
    Path prefix(e->idx_begin(), e->idx_end());
    for (auto &l : leaves(i.getType(), dl)) {
      auto p = prefix;
      p.insert(p.end(), l.path.begin(), l.path.end());
      setField(&i, l.path, field(e->getAggregateOperand(), p));
    }
    return true;
  }
  if (auto *e = dyn_cast<InsertValueInst>(&i)) {
    Path prefix(e->idx_begin(), e->idx_end());
    for (auto &l : leaves(i.getType(), dl)) {
      bool inserted = l.path.size() >= prefix.size() &&
                      std::equal(prefix.begin(), prefix.end(), l.path.begin());
      Path sub = inserted ? Path(l.path.begin() + prefix.size(), l.path.end())
                          : l.path;
      setField(&i, l.path,
               field(inserted ? e->getInsertedValueOperand()
                              : e->getAggregateOperand(),
                     sub));
    }
    return true;
  }
  if (auto *e = dyn_cast<ExtractElementInst>(&i)) {
    auto idx = get(e->getIndexOperand());
    auto *vt = cast<VectorType>(e->getVectorOperand()->getType());
    for (unsigned k = 0; k < vt->getElementCount().getKnownMinValue(); ++k) {
      bool possible = idx.top;
      for (auto &x : idx.atoms)
        possible |= x.kind == Atom::Int && x.integer == k;
      if (possible)
        setField(&i, {}, field(e->getVectorOperand(), {k}));
    }
    bool outside = idx.top && (APInt::getMaxValue(e->getIndexOperand()->getType()->getIntegerBitWidth()).uge(vt->getElementCount().getKnownMinValue()));
    for(auto &x:idx.atoms) if(x.kind==Atom::Int) outside |= x.integer.uge(vt->getElementCount().getKnownMinValue());
    if(outside) setField(&i,{},integer(APInt(dl.getTypeSizeInBits(i.getType()).getKnownMinValue(),0)));
    return true;
  }
  if (auto *e = dyn_cast<InsertElementInst>(&i)) {
    auto idx = get(e->getOperand(2));
    unsigned n = cast<VectorType>(i.getType())->getElementCount().getKnownMinValue();
    for (unsigned k = 0; k < n; ++k) {
      bool possible = idx.top, other = idx.top;
      for (auto &x : idx.atoms)
        if (x.kind == Atom::Int) {
          possible |= x.integer == k;
          other |= x.integer != k;
        }
      if (other)
        setField(&i, {k}, field(e->getOperand(0), {k}));
      if (possible)
        setField(&i, {k}, get(e->getOperand(1)));
    }
    return true;
  }
  if (auto *sh = dyn_cast<ShuffleVectorInst>(&i)) {
    auto mask = sh->getShuffleMask();
    unsigned n =
        cast<VectorType>(sh->getOperand(0)->getType())->getElementCount().getKnownMinValue();
    for (unsigned k = 0; k < mask.size(); ++k) {
      int j = mask[k];
      // N7 zeroes the mask element, which selects source lane zero.
      if (j < 0) j = 0;
        setField(&i, {k},
                 field(sh->getOperand(j >= n ? 1 : 0), {(unsigned)j % n}));
    }
    return true;
  }
  if (auto *st = dyn_cast<StoreInst>(&i);
      st && (st->getValueOperand()->getType()->isAggregateType() ||
             st->getValueOperand()->getType()->isVectorTy())) {
    auto ptr = get(st->getPointerOperand());
    for (auto &l : leaves(st->getValueOperand()->getType(), dl)) {
      AV p;
      for (auto x : ptr.atoms) {
        if (x.kind == Atom::Ptr)
          x.offset += l.offset;
        p.atoms.insert(x);
      }
      p.top = ptr.top;
      store(field(st->getValueOperand(), l.path), p,
            dl.getTypeStoreSize(l.type).getKnownMinValue());
    }
    return true;
  }
  if (!(i.getType()->isAggregateType() || i.getType()->isVectorTy()))
    return false;
  if (auto *l = dyn_cast<LoadInst>(&i)) {
    auto ptr = get(l->getPointerOperand());
    for (auto &leaf : leaves(i.getType(), dl)) {
      AV p;
      for (auto x : ptr.atoms) {
        if (x.kind == Atom::Ptr)
          x.offset += leaf.offset;
        p.atoms.insert(x);
      }
      p.top = ptr.top;
      setField(&i, leaf.path, load(p, leaf.type));
    }
    return true;
  }
  if (auto *p = dyn_cast<PHINode>(&i)) {
    for (Value *v : p->incoming_values())
      copyFields(&i, v);
    return true;
  }
  if (auto *s = dyn_cast<SelectInst>(&i)) {
    copyFields(&i, s->getTrueValue());
    copyFields(&i, s->getFalseValue());
    return true;
  }
  if (isa<FreezeInst>(i)) {
    copyFields(&i, i.getOperand(0));
    return true;
  }
  if (isa<LandingPadInst>(i)) {
    for (auto &l : leaves(i.getType(), dl)) {
      AV a;
      a.top = true;
      if (l.type->isPointerTy())
        a.merge(atom(Atom::Ptr));
      setField(&i, l.path, a);
    }
    return true;
  }
  if (isa<CallBase>(i))
    return false; // PT9 binds leaf paths below.
  unimplemented("§5 PT10 composite operation", 1, &i);
}
// Solve additive integer cycles directly. Flow-insensitive PT3/PT5/PT7 includes
// every iteration, even when a source branch bounds executions. An additive
// cycle with period >4096 therefore reaches normative TOP; this is exact
// acceleration, not a precision-changing widening.
static bool longAdditiveCycle(Value *value, Value *source,
                              std::function<AV(Value *)> facts, bool bitwise = false) {
  // PT3 copy edges can hide an additive recurrence behind arbitrarily many
  // phis/selects (e.g. hashtable count -> exit phi -> header phi). Following
  // those edges is exact: every traversal adds the same constant modulo W.
  if(source->getType()->isIntegerTy()) {
    unsigned width=source->getType()->getIntegerBitWidth();
    std::set<Value *> path;
    std::function<bool(Value *,APInt)> walk=[&](Value *v,APInt delta) {
      if(v==source)return !delta.isZero() && width-delta.countr_zero()>12;
      if(v->getType()!=source->getType() || !path.insert(v).second)return false;
      bool found=false;
      if(auto *p=dyn_cast<PHINode>(v)) {
        for(Value *in:p->incoming_values())if(walk(in,delta)) {found=true;break;}
      } else if(auto *s=dyn_cast<SelectInst>(v))found=walk(s->getTrueValue(),delta)||walk(s->getFalseValue(),delta);
      else if(isa<FreezeInst>(v))found=walk(cast<Instruction>(v)->getOperand(0),delta);
      else if(auto *b=dyn_cast<BinaryOperator>(v)) {
        if(auto *c=dyn_cast<ConstantInt>(b->getOperand(1))) {
          if(b->getOpcode()==Instruction::Add)found=walk(b->getOperand(0),delta+c->getValue());
          if(b->getOpcode()==Instruction::Sub)found=walk(b->getOperand(0),delta-c->getValue());
        } else if(b->getOpcode()==Instruction::Add)
          if(auto *c=dyn_cast<ConstantInt>(b->getOperand(0)))found=walk(b->getOperand(1),delta+c->getValue());
        // PT3's independent operand union admits an additive path through a
        // bitwise identity already in the other operand's finite domain.
        // musl mode |= mode-1 starts with zero, so its abstract store equation
        // contains the complete -1 additive orbit even though runtime stops.
        if(bitwise && !found && (b->getOpcode()==Instruction::Or || b->getOpcode()==Instruction::Xor || b->getOpcode()==Instruction::And)) {
          for(unsigned k=0;k<2 && !found;++k) {
            auto other=facts(b->getOperand(1-k));
            for(auto &atom:other.atoms)if(atom.kind==Atom::Int &&
                (b->getOpcode()==Instruction::And?atom.integer.isAllOnes():atom.integer.isZero()))
              if(walk(b->getOperand(k),delta)) {found=true;break;}
          }
        }
      }
      path.erase(v);return found;
    };
    if(walk(value,APInt(width,0)))return true;
  }
  auto *b = dyn_cast<BinaryOperator>(value);
  if (!b || !b->getType()->isIntegerTy())
    return false;
  if (b->getOpcode() != Instruction::Add && b->getOpcode() != Instruction::Sub)
    return false;
  Value *other = nullptr;
  if (b->getOperand(0) == source)
    other = b->getOperand(1);
  else if (b->getOpcode() == Instruction::Add && b->getOperand(1) == source)
    other = b->getOperand(0);
  if (!other)
    return false;
  auto vs = facts(other);
  for (auto &x : vs.atoms)
    if (x.kind == Atom::Int && !x.integer.isZero() &&
        x.integer.getBitWidth() - x.integer.countr_zero() > 12)
      return true;
  return false;
}
// A closed walk in a full-width pointer-copy/GEP graph is a translation in
// Z/(2^width). Its repeated image is the coset generated by its displacement;
// several walks generate the subgroup with the minimum trailing-zero count.
// Only witnessed finite index alternatives contribute generators. New facts
// are reconsidered on subsequent transfers; no size threshold widens AV.
static void closePointerOrbit(Value &source, ArrayRef<Value *> incoming,
                              const DataLayout &layout, AV &facts,
                              function_ref<AV(Value *, const Instruction *)> indices) {
  Type *type = source.getType();
  if (!type->isPointerTy() && !type->isIntegerTy()) return;
  unsigned width = type->isPointerTy() ? layout.getPointerTypeSizeInBits(type)
                                      : type->getIntegerBitWidth();
  if (width > 64 || (type->isPointerTy() &&
                    width != layout.getIndexTypeSizeInBits(type))) return;
  unsigned zeros = width;
  std::set<Value *> path;
  std::function<void(Value *, APInt)> walk = [&](Value *value, APInt delta) {
    budgetTick();
    if (value == &source) {
      if (!delta.isZero()) zeros = std::min(zeros, delta.countr_zero());
      return;
    }
    if (!path.insert(value).second) return;
    if (auto *gep = dyn_cast<GEPOperator>(value)) {
      if (layout.getPointerTypeSizeInBits(gep->getType()) == width &&
          layout.getIndexTypeSizeInBits(gep->getType()) == width) {
        APInt offset(width, 0);
#if LLVM_VERSION_MAJOR >= 23
        SmallMapVector<Value *, APInt, 4> variables;
#else
        MapVector<Value *, APInt> variables;
#endif
        if (gep->collectOffset(layout, width, variables, offset)) {
          std::vector<APInt> offsets{offset};
          for (auto &variable : variables) {
            AV domain = indices(variable.first, dyn_cast<Instruction>(value));
            // PT2 can enumerate every value of a small unknown index exactly.
            constexpr unsigned SmallIndexBits = 12; // normative INT limit K=4096
            if (domain.top && variable.first->getType()->isIntegerTy() &&
                variable.first->getType()->getIntegerBitWidth() <= SmallIndexBits) {
              unsigned bits = variable.first->getType()->getIntegerBitWidth();
              domain = {};
              for (unsigned n = 0; n < (1u << bits); ++n)
                domain.merge(integer(APInt(bits, n)));
            }
            if (domain.top) { offsets.clear(); break; }
            std::vector<APInt> next;
            for (const auto &a : domain.atoms)
              if (a.kind == Atom::Int)
                for (const auto &d : offsets)
                  next.push_back(d + a.integer.sextOrTrunc(width) * variable.second);
            offsets = std::move(next);
          }
          for (const auto &d : offsets) walk(gep->getPointerOperand(), delta + d);
        }
      }
    } else if (auto *cast = dyn_cast<CastInst>(value)) {
      // Full-width ptrtoint/inttoptr preserve the originating-object image.
      // Truncation and integer extension are not translation edges.
      if ((cast->getOpcode() == Instruction::PtrToInt ||
           cast->getOpcode() == Instruction::IntToPtr) &&
          layout.getTypeSizeInBits(cast->getType()) == width &&
          layout.getTypeSizeInBits(cast->getOperand(0)->getType()) == width)
        walk(cast->getOperand(0), delta);
    } else if (auto *binary = dyn_cast<BinaryOperator>(value)) {
      if (binary->getType()->isIntegerTy(width)) {
        if (auto *constant = dyn_cast<ConstantInt>(binary->getOperand(1))) {
          if (binary->getOpcode() == Instruction::Add)
            walk(binary->getOperand(0), delta + constant->getValue());
          else if (binary->getOpcode() == Instruction::Sub)
            walk(binary->getOperand(0), delta - constant->getValue());
        } else if (binary->getOpcode() == Instruction::Add)
          if (auto *constant = dyn_cast<ConstantInt>(binary->getOperand(0)))
            walk(binary->getOperand(1), delta + constant->getValue());
      }
    } else if (auto *other = dyn_cast<PHINode>(value)) {
      for (Value *incoming : other->incoming_values()) walk(incoming, delta);
    } else if (auto *select = dyn_cast<SelectInst>(value)) {
      walk(select->getTrueValue(), delta); walk(select->getFalseValue(), delta);
    } else if (auto *freeze = dyn_cast<FreezeInst>(value)) {
      walk(freeze->getOperand(0), delta);
    }
    path.erase(value);
  };
  for (Value *value : incoming) walk(value, APInt(width, 0));
  // A 2^63 stride has just two members and the ordinary transfer enumerates
  // them. Larger signed strides do not fit Atom's existing representation.
  if (zeros == width || zeros >= 63) return;
  AV closure; closure.top = facts.top;
  bool objectOrbit = false;
  int64_t stride = int64_t(1) << zeros;
  for (auto a : facts.atoms) {
    if (a.kind == Atom::Ptr && a.object &&
        layout.getPointerTypeSizeInBits(a.object->getType()) == width) {
      if (a.stride != -1) {
        a.stride = std::gcd(a.stride, stride);
        canonicalOffset(a.offset, a.stride);
      }
      objectOrbit = true;
    }
    closure.merge(AV{{a}, false});
  }
  // External pointers, FN and ROOT are copied by GEP. A concrete object orbit
  // also reaches outside that object, as the enumerating transfer would.
  if (objectOrbit) numericalUnknown(closure);
  facts = std::move(closure);
}
static void closeStoredPointerOrbit(StoreInst &store, const DataLayout &layout,
                                    AV &written, function_ref<AV(Value *)> facts,
                                    function_ref<AV(Value *, const Instruction *)> indices) {
  if (!store.getValueOperand()->getType()->isPointerTy()) return;
  AV address = facts(store.getPointerOperand());
  if (!llvm::any_of(address.atoms, [](const Atom &a) {
        return a.kind == Atom::Ptr && a.object;
      })) return;
  // A whole pointer load from this same SSA address reads every value written
  // here (PT6/PT7). This is an exact feedback edge even without an SSA phi.
  // Partial accesses and EXT-only loads do not establish that edge.
  std::set<Value *> seen;
  std::function<void(Value *)> visit = [&](Value *value) {
    if (!seen.insert(value).second) return;
    if (auto *load = dyn_cast<LoadInst>(value)) {
      if (load->getPointerOperand() == store.getPointerOperand() &&
          load->getType() == store.getValueOperand()->getType())
        closePointerOrbit(*load, {store.getValueOperand()}, layout, written, indices);
    } else if (auto *gep = dyn_cast<GEPOperator>(value)) {
      visit(gep->getPointerOperand());
    } else if (auto *phi = dyn_cast<PHINode>(value)) {
      for (Value *incoming : phi->incoming_values()) visit(incoming);
    } else if (auto *select = dyn_cast<SelectInst>(value)) {
      visit(select->getTrueValue()); visit(select->getFalseValue());
    } else if (auto *freeze = dyn_cast<FreezeInst>(value)) {
      visit(freeze->getOperand(0));
    }
  };
  visit(store.getValueOperand());
}
// PT5 is a union of numerical and originating-object images. Numeric TOP
// fast paths must not suppress the independent conservative pointer image.
static AV binaryPointers(Instruction &i, const AV &left, const AV &right,
                         function_ref<AV(const Atom &, const APInt &)> displace) {
  AV result;
  auto image = [&](const AV &pointers, const AV &other, bool rhs) {
    bool displacement = i.getOpcode() == Instruction::Add ||
                        (i.getOpcode() == Instruction::Sub && !rhs);
    for (const auto &pointer : pointers.atoms) {
      if (pointer.kind != Atom::Ptr) continue;
      bool conservative = !displacement || other.top;
      if (displacement)
        for (const auto &value : other.atoms) {
          if (value.kind != Atom::Int) { conservative = true; continue; }
          auto delta = i.getOpcode() == Instruction::Sub ? -value.integer
                                                       : value.integer;
          result.merge(displace(pointer, delta));
        }
      if (conservative) {
        auto p = pointer;
        p.offset = 0;
        p.stride = -1;
        result.atoms.insert(p);
        numericalUnknown(result);
      }
    }
  };
  image(left, right, false);
  image(right, left, true);
  return result;
}
void Analysis::step(Instruction &i) {
  if(activeBudget) {
    ++activeBudget->work.worklistPops;
    if (auto *f = activeBudget->work.currentFunction) ++f->dispatches;
    activeBudget->at=&i;
    activeBudget->rule=isa<LoadInst>(i)?"PT6":isa<StoreInst>(i)?"PT7":isa<GetElementPtrInst>(i)?"PT2":isa<CallBase>(i)?"PT8/PT9/PT12":isa<PHINode>(i)||isa<SelectInst>(i)?"PT3":i.getType()->isAggregateType()?"PT10":"PT4/PT5";
    activeBudget->check(true);
  }
  // Pure scalar transfers depend only on their operand AVs. Re-evaluating a
  // stable finite Cartesian product in every module round is quadratic work
  // with no new facts. Stores depend only on their written value and address;
  // loads and calls deliberately remain live.
  bool scalar=i.getType()->isIntegerTy() || i.getType()->isPointerTy() || isa<StoreInst>(i);
  bool pure=isa<StoreInst>(i)||isa<BinaryOperator>(i)||isa<ICmpInst>(i)||isa<CastInst>(i)||isa<GetElementPtrInst>(i)||isa<SelectInst>(i)||isa<PHINode>(i)||isa<FreezeInst>(i);
  for(Value *v:i.operands())scalar &= v->getType()->isIntegerTy() || v->getType()->isPointerTy() || (isa<StoreInst>(i) && (v->getType()->isAggregateType() || v->getType()->isVectorTy()));
  if(scalar && pure) {
    std::vector<AV> inputs;for(Value *v:i.operands())
      for(auto &leaf:leaves(v->getType(),M.getDataLayout()))inputs.push_back(field(v,leaf.path));
    auto &old=pureInputs[&i];
    if(old.size()==inputs.size() && std::equal(old.begin(),old.end(),inputs.begin(),sameAV))return;
    old=std::move(inputs);
  }
  if (activeBudget) {
    ++activeBudget->work.transferApplications;
    if (auto *f = activeBudget->work.currentFunction) ++f->transfers;
  }
  // S2 evaluates precisely the same N9/N32/N33 graph on private instructions.
  // Operands retain source identities; host IR and its attributes stay untouched.
  bool fp=false;
  if(auto *r=dyn_cast<AtomicRMWInst>(&i))fp=r->getType()->isFloatingPointTy();
  fp|=i.getOpcode()==Instruction::FNeg || isa<FCmpInst>(i) || (isa<BinaryOperator>(i) && i.getType()->isFloatingPointTy());
  if(auto *c=dyn_cast<CastInst>(&i))fp|=c->getOpcode()==Instruction::SIToFP||c->getOpcode()==Instruction::UIToFP||c->getOpcode()==Instruction::FPToSI||c->getOpcode()==Instruction::FPToUI||c->getOpcode()==Instruction::FPExt||c->getOpcode()==Instruction::FPTrunc;
  if(auto *c=dyn_cast<IntrinsicInst>(&i)) {
    auto base=Intrinsic::getBaseName(c->getIntrinsicID());
    fp|=c->getType()->isFloatingPointTy();
    for(auto &arg:c->args())fp|=arg->getType()->isFloatingPointTy();
    fp|=base=="llvm.get.rounding" || base=="llvm.set.rounding" || base.ends_with(".fpenv") || base.ends_with(".fpmode");
    fp|=base=="llvm.is.fpclass" || base.starts_with("llvm.fptosi.sat") || base.starts_with("llvm.fptoui.sat");
  }
  if(fp && !virtualFP) {
    auto &slice=fpTransfers[&i];
    if(!slice) {
      auto *f=Function::Create(FunctionType::get(i.getType(),false),GlobalValue::InternalLinkage,"",M);
      auto *bb=BasicBlock::Create(M.getContext(),"",f);auto *copy=i.clone();copy->setName(i.getName());copy->insertInto(bb,bb->end());
      ReturnInst::Create(M.getContext(),i.getType()->isVoidTy()?nullptr:copy,bb);normaliseScalar(*f,false,true);materialiseFPBits(*f);f->removeFromParent();slice.reset(f);
    }
    virtualFP=true;
    for(auto &v:instructions(*slice))if(!isa<ReturnInst>(v))step(v);
    auto *result=cast<ReturnInst>(slice->back().getTerminator())->getReturnValue();
    if(result) {if(i.getType()->isAggregateType())copyFields(&i,result);else changed|=values[&i].merge(get(result));}
    for(auto *callee:edges[slice.get()])edges[i.getFunction()].insert(callee);
    virtualFP=false;return;
  }
  auto gepIndex = [&](Value *v, const Instruction *at) {
    AV domain = get(v);
    if (auto bound = indexBounds.find({at, v}); bound != indexBounds.end()) {
      if (domain.top) domain = bound->second;
      else for (auto it = domain.atoms.begin(); it != domain.atoms.end();)
        if (it->kind == Atom::Int && !bound->second.atoms.count(*it))
          it = domain.atoms.erase(it);
        else ++it;
    }
    return domain;
  };
  if (auto *g = dyn_cast<GetElementPtrInst>(&i)) {
    auto evaluate = [&](const Path &path) {
      auto operand = [&](Value *v) {
        return v->getType()->isVectorTy() ? field(v, path) : gepIndex(v, g);
      };
      return gepImage(*cast<GEPOperator>(g), M.getDataLayout(),
          operand(g->getPointerOperand()), operand,
          [&](const AV &base, const APInt &delta, unsigned width) {
            return displace(base, delta, width);
          });
    };
    if (i.getType()->isVectorTy()) {
      for (const auto &leaf : leaves(i.getType(), M.getDataLayout())) {
        budgetTick();
        setField(&i, leaf.path, evaluate(leaf.path));
      }
    } else changed |= values[&i].merge(evaluate({}));
    return;
  }
  AV a;
  if (composite(i))
    return;
  if (auto *rmw = dyn_cast<AtomicRMWInst>(&i)) {
    a = load(get(rmw->getPointerOperand()), rmw->getType());
    AV next, operand = get(rmw->getValOperand()); next.top = a.top || operand.top;
    if (rmw->getOperation() == AtomicRMWInst::Xchg)
      next = operand; // Includes pointers/FN/ROOT, not just integer pairs.
    else if (rmw->getOperation() == AtomicRMWInst::Min ||
             rmw->getOperation() == AtomicRMWInst::Max ||
             rmw->getOperation() == AtomicRMWInst::UMin ||
             rmw->getOperation() == AtomicRMWInst::UMax) {
      // S2 models N9's select using PT3's unconditional operand union.
      next = a;
      next.merge(operand);
    } else for (auto &x : a.atoms) for (auto &y : operand.atoms)
      if (x.kind == Atom::Int && y.kind == Atom::Int) {
        APInt n = x.integer; const APInt &v = y.integer;
        switch (rmw->getOperation()) {
        case AtomicRMWInst::Xchg: n = v; break;
        case AtomicRMWInst::Add: n += v; break;
        case AtomicRMWInst::Sub: n -= v; break;
        case AtomicRMWInst::And: n &= v; break;
        case AtomicRMWInst::Nand: n = ~(n & v); break;
        case AtomicRMWInst::Or: n |= v; break;
        case AtomicRMWInst::Xor: n ^= v; break;
        case AtomicRMWInst::Max: n = n.sgt(v) ? n : v; break;
        case AtomicRMWInst::Min: n = n.slt(v) ? n : v; break;
        case AtomicRMWInst::UMax: n = n.ugt(v) ? n : v; break;
        case AtomicRMWInst::UMin: n = n.ult(v) ? n : v; break;
        case AtomicRMWInst::UIncWrap:
          // N9's guard is not a path refinement in PT3: retain both arms.
          next.merge(integer(APInt(n.getBitWidth(),0)));n+=1;break;
        case AtomicRMWInst::UDecWrap:
          next.merge(operand);n-=1;break;
#if LLVM_VERSION_MAJOR >= 23
        case AtomicRMWInst::USubCond:
          next.merge(a);n-=v;break;
        case AtomicRMWInst::USubSat:
          next.merge(integer(APInt(n.getBitWidth(),0)));n-=v;break;
#endif
        default: unimplemented("§5 PT12 atomic transfer", 1, rmw);
        }
        next.merge(integer(n));
      }
    store(next, get(rmw->getPointerOperand()), M.getDataLayout().getTypeStoreSize(rmw->getType()).getFixedValue());
  } else if (auto *alloc = dyn_cast<AllocaInst>(&i)) {
    a = atom(Atom::Ptr, &i);
    auto counts = get(alloc->getArraySize());
    uint64_t bytes = 0;
    for (auto &x : counts.atoms) if (x.kind == Atom::Int)
      bytes = std::max(bytes, (uint64_t)std::min<unsigned __int128>(UINT64_MAX,
          (unsigned __int128)x.integer.getLimitedValue() *
          M.getDataLayout().getTypeAllocSize(alloc->getAllocatedType()).getKnownMinValue()));
    if (counts.top) bytes = UINT64_MAX; // symbolic possible allocated bytes
    if (bytes) store(integer(APInt(8,0)), a, bytes, true);
  }
  else if (auto *l = dyn_cast<LoadInst>(&i))
    a = load(get(l->getPointerOperand()), l->getType());
  else if (auto *s = dyn_cast<StoreInst>(&i)) {

    AV written = get(s->getValueOperand());
    closeStoredPointerOrbit(*s, M.getDataLayout(), written,
                            [&](Value *v) { return get(v); }, gepIndex);
    if (auto *b = dyn_cast<BinaryOperator>(s->getValueOperand()))
      for (Value *operand : b->operands())
        if (auto *l = dyn_cast<LoadInst>(operand);
            l && l->getPointerOperand() == s->getPointerOperand() &&
            longAdditiveCycle(b, l, [&](Value *v) { return get(v); },ReversibleEntry) &&
            !get(l).atoms.empty())
          written.top = true;
    store(written, get(s->getPointerOperand()),
          M.getDataLayout()
              .getTypeStoreSize(s->getValueOperand()->getType())
              .getKnownMinValue());
  } else if (auto *p = dyn_cast<PHINode>(&i)) {
    for (Value *v : p->incoming_values())
      a.merge(get(v));
    if (!a.atoms.empty())
      for (Value *v : p->incoming_values())
        if (longAdditiveCycle(v, p, [&](Value *x) { return get(x); },ReversibleEntry))
          a.top = true;
    SmallVector<Value *, 4> incoming(p->incoming_values());
    closePointerOrbit(*p, incoming, M.getDataLayout(), a, gepIndex);
    // Exact finite additive closure, including small counters: enumerate the
    // subgroup once instead of waiting one whole-program round per element.
    if (!a.top && p->getType()->isIntegerTy()) {
      unsigned width=p->getType()->getIntegerBitWidth();
      for(Value *v:p->incoming_values()) if(auto *b=dyn_cast<BinaryOperator>(v)) {
        Value *step=nullptr;
        if((b->getOpcode()==Instruction::Add || b->getOpcode()==Instruction::Sub) && b->getOperand(0)==p) step=b->getOperand(1);
        else if(b->getOpcode()==Instruction::Add && b->getOperand(1)==p) step=b->getOperand(0);
        if(!step)continue;
        auto increments=get(step);unsigned zeros=width;
        for(auto &x:increments.atoms)if(x.kind==Atom::Int)zeros=std::min(zeros,x.integer.countr_zero());
        if(width-zeros>12 || zeros==width)continue;
        auto seeds=a.atoms;APInt delta=APInt::getOneBitSet(width,zeros);
        std::set<uint64_t> residues;
        for(auto &seed:seeds)if(seed.kind==Atom::Int) {
          auto residue=(seed.integer & (delta-1)).getLimitedValue();
          if(!residues.insert(residue).second)continue;
          APInt next=seed.integer;
          do {a.merge(integer(next));next+=delta;}while(next!=seed.integer);
        }
      }
    }
  } else if (auto *s = dyn_cast<SelectInst>(&i)) {
    a = get(s->getTrueValue());
    a.merge(get(s->getFalseValue()));
  } else if (auto *c = dyn_cast<CastInst>(&i)) {
    a=convert(get(c->getOperand(0)),c->getOperand(0)->getType(),c->getType(),c->getOpcode());
  } else if (isa<FreezeInst>(i))
    a = get(i.getOperand(0));
  else if (auto *c = dyn_cast<CallBase>(&i)) {
    Function *f = resolve(c->getCalledOperand());
    StringRef n = f ? f->getName() : StringRef();
    if (n == "__bennett_qalloc" || n == "__bennett_qborrow")
      a = atom(Atom::Root, c);
    else if (isa<MemTransferInst>(c) || n=="__bennett_rt_memmove") {
      AV src = get(c->getArgOperand(1)), dst = get(c->getArgOperand(0));
      auto *len = dyn_cast<ConstantInt>(c->getArgOperand(2));
      auto snapshot = slots;
      for (auto s : snapshot)
        for (auto &p : src.atoms)
          if (p.kind == Atom::Ptr && p.object == s.object)
            for (auto &d : dst.atoms)
              if (d.kind == Atom::Ptr) {
                if (s.stride && len && !p.stride && !d.stride) {
                  copySlotFamily(s, p, d, len->getZExtValue(),
                      [&](const AV &value, const AV &address, uint64_t bytes, bool filled) {
                        store(value, address, bytes, filled);
                      });
                } else if (s.filled && len && p.stride==0 && d.stride==0 && s.stride==0 && overlaps(p,s,len->getZExtValue())) {
                  int64_t lo=std::max(p.offset,s.offset);
                  __int128 hi=std::min((__int128)p.offset+len->getZExtValue(),(__int128)s.offset+s.bytes);
                  if(hi>lo) store(s.value,atom(Atom::Ptr,d.object,d.offset+lo-p.offset),hi-lo,true);
                } else if (len && p.stride == 0 && d.stride == 0 && s.stride == 0 &&
                    s.offset >= p.offset &&
                    s.offset + (int64_t)s.bytes <=
                        p.offset + (int64_t)len->getZExtValue())
                  store(
                      s.value,
                      atom(Atom::Ptr, d.object, d.offset + s.offset - p.offset),
                      s.bytes, s.filled);
                else if (!len || overlaps(p, s, len->getZExtValue())) {
                  AV partial;
                  partial.top = true;
                  for (auto &x : s.value.atoms)
                    if (x.kind == Atom::Root)
                      partial.atoms.insert(x);
                  if(len && !p.stride && !d.stride && !s.stride) {
                    auto lo=std::max((__int128)p.offset,(__int128)s.offset);
                    auto hi=std::min((__int128)p.offset+len->getLimitedValue(),(__int128)s.offset+s.bytes);
                    store(partial,atom(Atom::Ptr,d.object,d.offset+(int64_t)(lo-p.offset)),hi-lo);
                  } else store(partial, atom(Atom::Ptr, d.object, d.offset, -1),s.bytes);
                }
              }
    } else if (isa<MemSetInst>(c) || n=="__bennett_rt_memset") {
      auto *len = dyn_cast<ConstantInt>(c->getArgOperand(2));
      auto p = get(c->getArgOperand(0));
      if (len && len->getValue().getActiveBits() < 63)
        store(get(c->getArgOperand(1)), p, len->getZExtValue(), true);
      else {
        AV top;
        top.top = true;
        AV dst;
        for (auto x : p.atoms) {
          if (x.kind == Atom::Ptr)
            x.stride = -1;
          dst.atoms.insert(x);
        }
        store(top, dst, 1);
      }
    } else if (virtualFP && n=="__bennett_rt_ss_pop") {
      // Private conversion temporary; lifetime is lexical in the virtual graph.
    } else if (allocation(f) || (virtualFP && n=="__bennett_rt_ss_push")) {
      a = atom(Atom::Ptr, c);
      // §5.2 initial image, not immutable memory. Dynamic extent retains the
      // possible zero bytes symbolically; PT6 only uses wholly contained reads.
      unsigned sizeArg = n == "calloc" || n == "aligned_alloc" || n == "realloc" ? 1 : 0;
      if (n == "posix_memalign") sizeArg = 2;
      uint64_t extent = UINT64_MAX;
      if (sizeArg < c->arg_size()) {
        // Bottom has no possible allocated bytes yet. Only TOP justifies a
        // symbolic extent; treating bottom as TOP leaves spurious zero facts
        // behind when the size becomes finite on a later scan.
        auto maximum = [](const AV &sizes) {
          uint64_t result = sizes.top ? UINT64_MAX : 0;
          for (auto &v : sizes.atoms)
            if (v.kind == Atom::Int)
              result = std::max(result, v.integer.getLimitedValue());
          return result;
        };
        extent = maximum(get(c->getArgOperand(sizeArg)));
        if (n == "calloc")
          extent = (uint64_t)std::min<unsigned __int128>(
              UINT64_MAX, (unsigned __int128)extent *
                              maximum(get(c->getArgOperand(0))));
      }
      if (extent) store(integer(APInt(8,0)), a, extent, true);
      if (n == "posix_memalign") {
        store(a, get(c->getArgOperand(0)), M.getDataLayout().getPointerSize());
        a={};a.top = true;
      }
    } else if (f && !f->isDeclaration())
      bind(*c, f);
    else if (!f) {
      for (auto *g : candidates(c->getCalledOperand(), c->getFunctionType()))
        bind(*c, g);
    } else if (!markers().count(n.str()) && !f->isIntrinsic() && n != "free" && n != "__bennett_nz_free") {
      bind(*c,f);
    }
    if (f && markers().count(n.str()))
      for (unsigned pos : regionOperands(n)) {
        bool oracle = n == "__bennett_oracle" ||
                      (n == "__bennett_inplace" &&
                       !(auditLegality() && c->arg_size() == 3));
        auto *rt =
            FunctionType::get(Type::getVoidTy(M.getContext()),
                              {PointerType::get(M.getContext(), 0)}, false);
        for (auto *g : candidates(c->getArgOperand(pos), oracle ? nullptr : rt))
          if (!g->isDeclaration()) {
            // Region edges bind env, but do not inherit the caller tier.
            if (!oracle && g->arg_size() == 1)
              changed |= values[&*g->arg_begin()].merge(get(c->getArgOperand(
                  n == "__bennett_ctrl_v" ? 4 : c->arg_size() - 1)));
          }
      }
  } else if (isa<BinaryOperator>(i) || isa<ICmpInst>(i)) {
    AV x = get(i.getOperand(0)), y = get(i.getOperand(1));
    // Every PT5 Cartesian image is empty when either factor is bottom.
    // TOP is a nonempty numeric factor even when it has no explicit atoms.
    if ((!x.top && x.atoms.empty()) || (!y.top && y.atoms.empty())) return;
    bool dense=!x.top && !y.top && (i.getOpcode()==Instruction::And || i.getOpcode()==Instruction::Or || i.getOpcode()==Instruction::Xor);
    for(auto &v:x.atoms)dense &= v.kind==Atom::Int && v.integer.getActiveBits()<=12;
    for(auto &v:y.atoms)dense &= v.kind==Atom::Int && v.integer.getActiveBits()<=12;
    if(dense) {
      bool bits[4096]={};std::vector<unsigned> left,right;
      for(auto &v:x.atoms)left.push_back(v.integer.getZExtValue());
      for(auto &v:y.atoms)right.push_back(v.integer.getZExtValue());
      for(unsigned l:left) {budgetTick();for(unsigned r:right)
        bits[i.getOpcode()==Instruction::And?(l&r):i.getOpcode()==Instruction::Or?(l|r):(l^r)]=true;}
      for(unsigned n=0;n<4096;++n)if(bits[n])a.merge(integer(APInt(i.getType()->getIntegerBitWidth(),n)));
    } else if ((x.top || y.top) && i.getOpcode() == Instruction::And) {
      auto *mask = dyn_cast<ConstantInt>(i.getOperand(1));
      if (!mask)
        mask = dyn_cast<ConstantInt>(i.getOperand(0));
      if (mask && mask->getValue().popcount() <= 12) {
        auto m = mask->getValue();
        APInt sub = m;
        do {
          a.merge(integer(sub));
          if (sub.isZero())
            break;
          sub = (sub - 1) & m;
        } while (true);
      } else
        a.top = true;
    } else if (x.top && i.getOpcode() == Instruction::URem &&
               isa<ConstantInt>(i.getOperand(1)) &&
               cast<ConstantInt>(i.getOperand(1))->getValue().ule(4096) &&
               !cast<ConstantInt>(i.getOperand(1))->isZero()) {
      auto *m = cast<ConstantInt>(i.getOperand(1));
      for (unsigned k = 0; k < m->getZExtValue(); ++k)
        a.merge(integer(APInt(m->getBitWidth(), k)));
    } else {
      a.top = x.top || y.top;
      for (auto &v : x.atoms) {
        for (auto &w : y.atoms) {
          if (v.kind == Atom::Int && w.kind == Atom::Int &&
              v.integer.getBitWidth() == w.integer.getBitWidth()) {
            APInt b = v.integer, c = w.integer, r = b;
            bool valid = true;
            switch (i.getOpcode()) {
            case Instruction::Add:
              r = b + c;
              break;
            case Instruction::Sub:
              r = b - c;
              break;
            case Instruction::Mul:
              r = b * c;
              break;
            case Instruction::And:
              r = b & c;
              break;
            case Instruction::Or:
              r = b | c;
              break;
            case Instruction::Xor:
              r = b ^ c;
              break;
            case Instruction::Shl:
              r = c.uge(b.getBitWidth()) ? APInt(b.getBitWidth(), 0) : b.shl(c);
              break;
            case Instruction::LShr:
              r = c.uge(b.getBitWidth()) ? APInt(b.getBitWidth(), 0)
                                         : b.lshr(c);
              break;
            case Instruction::AShr:
              r = c.uge(b.getBitWidth()) ? APInt(b.getBitWidth(), 0)
                                         : b.ashr(c);
              break;
            case Instruction::UDiv:
            case Instruction::SDiv:
            case Instruction::URem:
            case Instruction::SRem:
              if (c.isZero()) {
                valid = false;
                break;
              }
              r = i.getOpcode() == Instruction::UDiv   ? b.udiv(c)
                  : i.getOpcode() == Instruction::SDiv ? b.sdiv(c)
                  : i.getOpcode() == Instruction::URem ? b.urem(c)
                                                       : b.srem(c);
              break;
            case Instruction::ICmp:
              r = APInt(
                  1, ICmpInst::compare(b, c, cast<ICmpInst>(i).getPredicate()));
              break;
            default:
              valid = false;
            }
            if (valid)
              a.merge(integer(r));
            if (a.top)
              goto done;
          }
        }
      }
    }
  done:;
    auto pointers = binaryPointers(i, x, y, [&](const Atom &p, const APInt &delta) {
      return displace(AV{{p}, false}, delta, delta.getBitWidth(), false);
    });
    if (pointers.top || !pointers.atoms.empty()) a.merge(pointers);
    if (isa<ICmpInst>(i) && a.atoms.empty() &&
        (x.top || y.top || !x.atoms.empty() || !y.atoms.empty())) {
      a.top = false;
      a.merge(integer(APInt(1, 0)));
      a.merge(integer(APInt(1, 1)));
    }
  }
  changed |= values[&i].merge(a);
}
void Analysis::run() {
  BudgetScope scope(this, M);
  // PT2 permits sound bounds on GEP indices. Obtain them without changing the
  // reference value sets: mem2reg only on a private analysis clone, then SCEV.
  // In particular, a bounded array loop must not contaminate an adjacent field
  // when its flow-insensitive counter value set saturates to TOP.
  {
    ValueToValueMapTy map;
    auto clone = CloneModule(M, map);
    for (Function &f : M)
      if (!f.isDeclaration()) {
        auto *cf = cast<Function>(map[&f]);
#if LLVM_VERSION_MAJOR >= 19
        for (Argument &arg : cf->args())
          arg.removeAttr(Attribute::Range);
#endif
        for (Instruction &instruction : instructions(*cf)) {
          instruction.dropPoisonGeneratingFlags();
          instruction.setMetadata(LLVMContext::MD_range, nullptr);
#if LLVM_VERSION_MAJOR >= 19
          if (auto *call = dyn_cast<CallBase>(&instruction))
            call->removeRetAttr(Attribute::Range);
#endif
        }
        DominatorTree dt(*cf);
        SmallVector<AllocaInst *> promote;
        for (Instruction &i : instructions(*cf))
          if (auto *a = dyn_cast<AllocaInst>(&i);
              a && a->getAllocatedType()->isIntegerTy() &&
              isAllocaPromotable(a))
            promote.push_back(a);
        PromoteMemToReg(promote, dt);
        LoopInfo loops(dt);
        AssumptionCache ac(*cf);
        TargetLibraryInfoImpl impl(Triple(M.getTargetTriple()));
        TargetLibraryInfo tli(impl);
        ScalarEvolution se(*cf, tli, ac, dt, loops);
        for (Instruction &i : instructions(f))
          if (auto *g = dyn_cast<GetElementPtrInst>(&i)) {
            auto *cg = cast<GetElementPtrInst>(map[g]);
            for (unsigned n = 1; n < g->getNumOperands(); ++n)
              if (!isa<ConstantInt>(g->getOperand(n)) &&
                  cg->getOperand(n)->getType()->isIntegerTy()) {
                auto *expression = se.getSCEV(cg->getOperand(n));
                auto range = se.getUnsignedRange(expression);
                // SCEV's global addrec range includes the loop's exit value. At
                // a particular GEP, dominating source guards can exclude that
                // value. Candidate bounds come from actual comparisons, never
                // array sizes.
                for (Instruction &guard : instructions(*cf))
                  if (auto *cmp = dyn_cast<ICmpInst>(&guard))
                    for (Value *operand : cmp->operands())
                      if (auto *constant = dyn_cast<ConstantInt>(operand)) {
                        uint64_t bound = constant->getValue().getLimitedValue();
                        for (uint64_t limit :
                             {bound, bound < 4096 ? bound + 1 : bound})
                          if (limit > 0 && limit <= 4096) {
                            unsigned width = cg->getOperand(n)
                                                 ->getType()
                                                 ->getIntegerBitWidth();
                            if (APInt(width, limit).getLimitedValue() != limit)
                              continue;
                            if (se.isKnownPredicateAt(
                                    ICmpInst::ICMP_ULT, expression,
                                    se.getConstant(APInt(width, limit)), cg))
                              range = range.intersectWith(ConstantRange(
                                  APInt(width, 0), APInt(width, limit)));
                          }
                      }
                if (!range.isFullSet() && !range.isEmptySet() &&
                    range.getLower().ult(range.getUpper()) &&
                    (range.getUpper() - range.getLower()).ule(4096)) {
                  AV bound;
                  for (APInt x = range.getLower(); x != range.getUpper(); ++x)
                    bound.merge(integer(x));
                  indexBounds[{g, g->getOperand(n)}] = bound;
                }
              }
          }
      }
  }
  for (GlobalVariable &g : M.globals())
    if (g.hasInitializer())
      seed(g.getInitializer(), &g, 0, g.getValueType());
  for(size_t n=0;n<slots.size();++n) {
    auto &s=slots[n];slotIndex.emplace(SlotKey{s.object,s.offset,s.stride,s.bytes,s.filled,s.numerical},n);indexSlot(n);
  }
  std::set<Function *> host,entries;
  for(Function &f:M)if(!ReversibleEntry && !f.isDeclaration() && !f.hasLocalLinkage())host.insert(&f);
  if(Entry)entries.insert(Entry);
  auto seedParameters=[&](Function *f,bool boundary) {
    if(!f || f->isDeclaration())return;
    for(Argument &arg:f->args())for(auto &leaf:leaves(arg.getType(),M.getDataLayout())) {
      AV value;
      if(leaf.type->isPointerTy()) {
        value=atom(Atom::Ptr,nullptr,0,-1);
        if(boundary)value.merge(atom(Atom::Root,&arg));
      } else value.top=true;
      setField(&arg,leaf.path,value);
    }
  };
  // Host reachability, address uses and device boundaries grow together with
  // PT9 and region candidates. An address used only by device code is not a
  // host seed. Region edges start a new entry and do not inherit H.
  auto seeds=[&]() {
    for(auto *f:host) {
      std::set<Value *> visited;
      std::function<void(Value *)> use=[&](Value *v) {
        if(!visited.insert(v).second)return;
        if(auto *g=resolve(v)) {if(!g->isDeclaration())changed|=host.insert(g).second;return;}
        if(auto *g=dyn_cast<GlobalVariable>(v)) {if(g->hasInitializer())use(g->getInitializer());return;}
        if(auto *c=dyn_cast<Constant>(v))for(Value *operand:c->operands())use(operand);
      };
      bool markersHere=false;
      for(auto &i:instructions(f)) {
        auto *call=dyn_cast<CallBase>(&i);auto *callee=call?call->getCalledFunction():nullptr;
        if(callee && markers().count(callee->getName().str())) {markersHere=true;continue;}
        for(Value *operand:i.operands())use(operand);
      }
      for(auto *g:edges[f])changed|=host.insert(g).second;
      if(markersHere)changed|=entries.insert(f).second;
      // A non-local launch boundary may only stash its handle for a later
      // entry. Seed that candidate ROOT before solving the cross-entry memory
      // paths; §6.6 pruning removes it unless it actually reaches a handle use.
      seedParameters(f,entries.count(f) || !f->hasLocalLinkage());
    }
    for(Function &f:M)for(auto &i:instructions(f))if(auto *call=dyn_cast<CallBase>(&i))
      if(auto *g=call->getCalledFunction())for(unsigned p:regionOperands(g->getName()))
        for(auto *candidate:candidates(call->getArgOperand(p)))
          if(!candidate->isDeclaration())changed|=entries.insert(candidate).second;
    for(auto *f:entries)seedParameters(f,!(ReversibleEntry && f==Entry));
  };
  unsigned rounds = 0;
  do {
    changed = false;
    seeds();
    const Instruction *lastChanged=nullptr;const char *lastRule=nullptr;
    size_t functionIndex = 0;
    for (Function &f : M) {
      if (f.isDeclaration()) continue;
      ++scope.budget.work.functionVisits;
      scope.budget.work.currentFunction = &scope.budget.work.functions[functionIndex++];
      ++scope.budget.work.currentFunction->visits;
      for (Instruction &i : instructions(f)) {
        bool prior=changed;changed=false;
        step(i);
        if(changed) {lastChanged=&i;lastRule=scope.budget.rule;}
        changed|=prior;
      }
      ++scope.budget.work.currentFunction->rounds;
    }
    scope.budget.work.currentFunction = nullptr;
    ++scope.budget.work.roundsCompleted;
    if (++rounds >= MaxAnalysisRounds && changed) {
      scope.budget.at=lastChanged;scope.budget.rule=lastRule?lastRule:"PT11 seeds";
      scope.budget.exhausted();
    }
  } while (changed);
  analysisRounds=rounds;
  // Candidate entry roots that never reach a handle operand are removed (§6.6).
  std::set<const Value *> live;
  for (Function &f : M)
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction())
          for (unsigned p : handleOperands(g->getName()))
            for (auto &x : get(c->getArgOperand(p)).atoms)
              if (x.kind == Atom::Root)
                live.insert(x.object);
  auto prune = [&](AV &v) {
    for (auto it = v.atoms.begin(); it != v.atoms.end();)
      if (it->kind == Atom::Root && isa<Argument>(it->object) &&
          !live.count(it->object))
        it = v.atoms.erase(it);
      else
        ++it;
  };
  for (auto &e : values)
    prune(e.second);
  for (auto &e : fields)
    prune(e.second);
  for (auto &s : slots)
    prune(s.value);
  // Tiers and graph are derived from the same fixed candidate/ROOT solution.
  std::map<Function *, std::set<Function *>> full = edges;
  for (Function &f : M)
    if (!f.isDeclaration()) {
      if (host.count(&f))tiers[&f].insert("H");
      if (&f==Entry)tiers[&f].insert(ReversibleEntry?"R":"CC");
      for (Argument &a : f.args())
        if (get(&a).roots())
          tiers[&f].insert("CC");
      for (Instruction &i : instructions(f)) {
        if (auto *l = dyn_cast<LoadInst>(&i); l && get(l).roots())
          tiers[&f].insert("CC");
        if (auto *c = dyn_cast<CallBase>(&i))
          if (auto *g = c->getCalledFunction();
              g && markers().count(g->getName().str())) {
            tiers[&f].insert("CC");
            auto n = g->getName();
            for (unsigned p : regionOperands(n))
              for (auto *r : candidates(c->getArgOperand(p))) {
                full[&f].insert(r);
                tiers[r].insert(
                    n == "__bennett_oracle" || n == "__bennett_inplace" ? "L"
                    : n == "__bennett_reversible"                       ? "R"
                                                                        : "CC");
              }
          }
      }
    }
  bool more = true;
  while (more) {
    more = false;
    for (auto &e : edges)
      for (auto *f : e.second)
        for (auto &t : tiers[e.first])
          more |= tiers[f].insert(t).second;
  }
  // §3.8 source-effect lies, including indirect and region edges.
  std::set<Function *> reaches;
  for (Function &f : M)
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction();
            g && markers().count(g->getName().str()))
          reaches.insert(&f);
  more = true;
  while (more) {
    more = false;
    for (auto &e : full)
      for (auto *g : e.second)
        if (reaches.count(g))
          more |= reaches.insert(e.first).second;
  }
  for (Function &f : M)
    if (reaches.count(&f) &&
        (f.onlyReadsMemory() || f.hasFnAttribute(Attribute::WillReturn) ||
         f.hasFnAttribute(Attribute::Speculatable)))
      fail("BD-E-EFFECT-LIE", "§3.8", &f);
}
void Analysis::checkHandles() {
  unsigned pw = M.getDataLayout().getPointerSizeInBits();
  for (Function &f : M)
    for (Instruction &i : instructions(f)) {
      for (unsigned k = 0; k < i.getNumOperands(); ++k) {
        Value *v = i.getOperand(k);
        if (!get(v).roots())
          continue;
        bool good = false;
        if (isa<PHINode>(i) || isa<FreezeInst>(i) || isa<ReturnInst>(i) ||
            isa<InsertValueInst>(i) || isa<ExtractValueInst>(i) ||
            isa<ShuffleVectorInst>(i))
          good = true;
        if (isa<InsertElementInst>(i))
          good = k != 2;
        if (isa<ExtractElementInst>(i))
          good = k == 0;
        if (isa<SelectInst>(i))
          good = k != 0;
        if (auto *c = dyn_cast<CastInst>(&i))
          good = (c->getOpcode() == Instruction::PtrToInt &&
                  c->getType()->isIntegerTy(pw)) ||
                 (c->getOpcode() == Instruction::IntToPtr &&
                  c->getOperand(0)->getType()->isIntegerTy(pw)) ||
                 (c->getOpcode() == Instruction::BitCast &&
                  M.getDataLayout().getTypeSizeInBits(c->getType()) ==
                      M.getDataLayout().getTypeSizeInBits(
                          c->getOperand(0)->getType()));
        if (auto *cmp = dyn_cast<ICmpInst>(&i))
          good = cmp->isEquality() &&
                 (get(cmp->getOperand(1 - k)).roots() ||
                  isa<ConstantPointerNull>(cmp->getOperand(1 - k)) ||
                  PatternMatch::match(cmp->getOperand(1 - k),
                                      PatternMatch::m_Zero()));
        if (auto *s = dyn_cast<StoreInst>(&i))
          good = k == 0;
        if (auto *c = dyn_cast<CallBase>(&i)) {
          Function *g = resolve(c->getCalledOperand());
          good = g && !g->isDeclaration() && k < c->arg_size();
          if (!g && k < c->arg_size()) {
            auto rr = candidates(c->getCalledOperand(), c->getFunctionType());
            good = !rr.empty();
            for (auto *target : rr)
              good &= !target->isDeclaration();
            if (!good)
              fail("BD-E-HANDLE-ESCAPE", "§6.4 opaque indirect argument", c);
          }
          if (g && markers().count(g->getName().str()))
            for (unsigned p : handleOperands(g->getName()))
              good |= k == p;
          if (!good && g && g->isDeclaration() &&
              !markers().count(g->getName().str()))
            fail("BD-E-HANDLE-ESCAPE", "§6.4 external argument", c);
        }
        if (!good)
          fail("BD-E-HANDLE-USE", "§6.2", &i);
      }
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction())
          for (unsigned p : handleOperands(g->getName()))
            if (!auditLegality() && !get(c->getArgOperand(p)).roots())
              fail("BD-E-HANDLE-UNTRACKED", "§6.2", c);
      if (auto *l = dyn_cast<LoadInst>(&i); l && get(l).roots()) {
        for (auto &leaf : leaves(l->getType(), M.getDataLayout()))
          if (field(l, leaf.path).roots()) {
            Type *lt = leaf.type;
            if (!lt->isPointerTy() && !lt->isIntegerTy(pw))
              fail("BD-E-HANDLE-USE", "§6.2 partial handle read", l);
            auto p = get(l->getPointerOperand());
            for (auto x : p.atoms) {
              if (x.kind == Atom::Ptr)
                x.offset += leaf.offset;
              for (auto &s : slots)
                if (s.value.roots() && overlaps(x, s,
                                                M.getDataLayout()
                                                    .getTypeStoreSize(lt)
                                                    .getKnownMinValue()))
                  if (s.bytes != pw / 8 ||
                      (x.stride == 0 && s.stride == 0 && x.offset != s.offset))
                    fail("BD-E-HANDLE-USE", "§6.2 overlapping read", l);
            }
          }
      }
      if (auto *r = dyn_cast<ReturnInst>(&i);
          r && r->getReturnValue() && get(r->getReturnValue()).roots() &&
          !f.hasLocalLinkage() && !tiers[&f].count("CC"))
        fail("BD-E-HANDLE-ESCAPE", "§6.4 exported return", r);
    }
  for (auto &s : slots)
    if (!s.object && !s.numerical && s.value.roots())
      fail("BD-E-HANDLE-ESCAPE", "§6.4 EXT slot");
  // Reachable pointee slots crossing opaque calls are also escapes.
  for (Function &f : M)
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction();
            g && g->isDeclaration() && !g->isIntrinsic() &&
            g->getName() != "free" && !markers().count(g->getName().str()))
          for (Value *v : c->args()) {
            std::set<const Value *> objects;
            for (auto &p : get(v).atoms)
              if (p.kind == Atom::Ptr)
                objects.insert(p.object);
            bool more = true;
            while (more) {
              more = false;
              for (auto &s : slots)
                if (objects.count(s.object)) {
                  if (s.value.roots())
                    fail("BD-E-HANDLE-ESCAPE", "§6.4 external reachable slot",
                         c);
                  for (auto &p : s.value.atoms)
                    if (p.kind == Atom::Ptr)
                      more |= objects.insert(p.object).second;
                }
            }
          }
}
void Analysis::checkRegions() {
  if(ReversibleEntry)for(auto &f:M)if(tiers[&f].count("R"))for(auto &i:instructions(f))
    if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g && g->getName()=="__bennett_measure")
      fail("BD-E-REVERSIBLE-MEASURE","§19.2/§7.5(b)",c);
  bool defer = false;
  if (auto *md = dyn_cast_or_null<MDString>(
          M.getModuleFlag("bennett.measure_in_unitary")))
    defer = md->getString() == "defer";
  for (Function &f : M)
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction())
          for (unsigned p : regionOperands(g->getName())) {
            auto rr = candidates(c->getArgOperand(p));
            if (rr.size() != 1)
              continue;
            auto *r = *rr.begin();
            if (g->getName() == "__bennett_oracle" ||
                g->getName() == "__bennett_inplace")
              continue;
            auto *rt =
                FunctionType::get(Type::getVoidTy(M.getContext()),
                                  {PointerType::get(M.getContext(), 0)}, false);
            if (r->getFunctionType() != rt)
              fail("BD-E-REGION-TYPE", "§7.2", c);
            std::set<Function *> seen;
            std::vector<Function *> todo = {r};
            while (!todo.empty()) {
              auto *h = todo.back();
              todo.pop_back();
              if (!seen.insert(h).second)
                continue;
              for (Instruction &j : instructions(h))
                if (auto *cb = dyn_cast<CallBase>(&j))
                  if (auto *called = cb->getCalledFunction();
                      called && called->getName() == "__bennett_measure") {
                    if (g->getName() == "__bennett_reversible")
                      fail("BD-E-REVERSIBLE-MEASURE", "§7.5(b)", cb);
                    if (!defer)
                      fail("BD-E-REGION-MEASURE", "§7.5(a)", cb);
                  }
              for (auto *next : edges[h])
                todo.push_back(next);
            }
          }
}
static std::string label(const Value *v) {
  std::string s;
  raw_string_ostream o(s);
  v->printAsOperand(o, false);
  return s;
}
static json::Object valuePremise(Analysis &analysis, Module &module) {
  json::Array globals, calls;
  for (const GlobalVariable &g : module.globals())
    if (!g.hasInitializer()) globals.push_back(label(&g));
  for (Function &f : module)
    for (Instruction &i : instructions(f))
      if (auto *call = dyn_cast<CallBase>(&i); call && !call->getCalledFunction()) {
        std::set<std::string> names;
        for (auto *candidate : analysis.candidates(call->getCalledOperand(),
                                                   call->getFunctionType()))
          names.insert(candidate->getName().str());
        json::Array candidates;
        for (const auto &name : names) candidates.push_back(name);
        calls.push_back(json::Object{{"function", f.getName().str()},
                                     {"value", label(&i)},
                                     {"candidates", std::move(candidates)}});
      }
  return json::Object{
      {"status", "conditional"},
      {"applies_to", "all values"},
      {"concrete_unreachability", "not-established"},
      {"requires", json::Array{
          "All concrete entry arguments, initial memory bytes and subsequent "
          "external writes must be included in the PT1-PT12 seeds and effects. "
          "An external global without an initializer has no initial-byte seed; "
          "later stores do not establish its entry contents.",
          "Every concrete call target must be included in the reported candidate "
          "set, with arguments, returns and memory effects covered by PT9/PT12. "
          "Standalone units do not establish this for external callbacks.",
          "Link and analyse the complete materialised program and its boundary "
          "state before using excluded values as concrete unreachability. "
          "Bottom denotes no derivation from these module seeds, not proof "
          "that an instruction cannot execute in a completed external context."}},
      {"external_globals", std::move(globals)},
      {"indirect_calls", std::move(calls)}};
}
json::Object Analysis::report() {
  if (completedReceipt.owner != this)
    fail("analysis-resource", "report must follow this analysis run");
  auto work = json::parse(completedReceipt.json);
  if (!work)
    fail("analysis-resource", "invalid analysis work receipt: " +
         toString(work.takeError()));
  json::Array funcs, regions, vals;
  for (Function &f : M)
    if (!f.isDeclaration()) {
      json::Array ts, es;
      for (auto &t : tiers[&f])
        ts.push_back(t);
      for (auto *g : edges[&f])
        es.push_back(g->getName().str());
      funcs.push_back(json::Object{{"name", f.getName().str()},
                                   {"tiers", std::move(ts)},
                                   {"callees", std::move(es)}});
      for (Instruction &i : instructions(f)) {
        AV a = get(&i);
        if (!i.getType()->isVoidTy()) {
          json::Array atoms;
          for (auto &x : a.atoms) {
            if (x.kind == Atom::Int) {
              SmallString<40> s;
              x.integer.toString(s, 10, false);
              atoms.push_back("INT(" + s.str().str() + ")");
            } else
              atoms.push_back(std::string(x.kind == Atom::Root ? "ROOT("
                                          : x.kind == Atom::Fn ? "FN("
                                                               : "PTR(") +
                              (x.object ? label(x.object) : "EXT") + "," +
                              std::to_string(x.offset) + "," +
                              std::to_string(x.stride) + ")");
          }
          vals.push_back(json::Object{{"function", f.getName().str()},
                                      {"value", label(&i)},
                                      {"top", a.top},
                                      {"atoms", std::move(atoms)}});
        }
        if (auto *c = dyn_cast<CallBase>(&i))
          if (auto *g = c->getCalledFunction())
            for (unsigned p : regionOperands(g->getName())) {
              json::Array rr;
              for (auto *r : candidates(c->getArgOperand(p)))
                rr.push_back(json::Object{
                    {"name", r->getName().str()},
                    {"key", r->isDeclaration() ? "external" : regionKey(r)}});
              regions.push_back(json::Object{{"function", f.getName().str()},
                                             {"marker", g->getName().str()},
                                             {"operand", (int64_t)p},
                                             {"candidates", std::move(rr)}});
            }
      }
    }
  json::Object result{{"dialect", "0.2.13"},
                      {"isa", "0.8"},
                      {"mode", "analysis-only"},
                      {"analysis_rounds", analysisRounds},
                      {"analysis_work", std::move(*work)},
                      {"value_premise", valuePremise(*this, M)},
                      {"functions", std::move(funcs)},
                      {"regions", std::move(regions)},
                      {"values", std::move(vals)}};
  errs() << "bennett: conditional AVs: concrete unreachability is not established; "
            "see report value_premise for required boundary coverage\n";
  completedReceipt.document = json::Value(json::Object(result));
  return result;
}
} // namespace bennett
