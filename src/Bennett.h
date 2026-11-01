#pragma once
#include <functional>
#include <initializer_list>
#include <iterator>
#include <unordered_map>
#include <unordered_set>
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/JSON.h"
#include <map>
#include <set>
#include <string>
#include <vector>
#include <tuple>
namespace bennett {
[[noreturn]] void fail(llvm::StringRef code, llvm::StringRef section,
                       const llvm::Value *at = nullptr);
[[noreturn]] void unimplemented(llvm::StringRef section, unsigned milestone,
                                const llvm::Value *at = nullptr);
bool auditLegality();
const std::map<std::string, std::string> &markers();
std::vector<unsigned> regionOperands(llvm::StringRef name);
std::vector<unsigned> handleOperands(llvm::StringRef name);
llvm::Function *resolve(llvm::Value *v);
std::string regionKey(llvm::Function *f);
// A representation interval is retained with each memory fact. Never union
// integer components to represent a partial/spanning load (PT6).
struct Atom {
  enum Kind { Ptr, Fn, Root, Int } kind;
  const llvm::Value *object = nullptr;
  int64_t offset = 0, stride = 0; // stride=-1: arbitrary, >0: residue, 0: exact
  llvm::APInt integer = llvm::APInt(1, 0);
  // An unknown numerical address is not a host/opaque origin (PT2/PT4/PT5).
  bool numerical = false;
  bool operator<(const Atom &b) const;
};
// A set of interned atoms, held as a sorted id vector: union is a linear merge of
// integers (bp-fj1, SQLite carries millions of atoms). An id carries two flag bits, so
// the (X,*) and INT segments are found without touching the atom table:
//   ordinary atoms (by id), then (X,*) atoms (by id), then INT atoms (by width, value).
// Iteration therefore gives INT atoms in ascending order, as dispatch tables expect.
class AtomSet {
  mutable std::vector<uint32_t> ids;
  mutable size_t ordered = 0;
  void normalise() const;
  friend struct AV;
public:
  class iterator {
    const uint32_t *at;
  public:
    using iterator_category = std::forward_iterator_tag;
    using value_type = Atom;
    using difference_type = std::ptrdiff_t;
    using pointer = const Atom *;
    using reference = const Atom &;
    explicit iterator(const uint32_t *p) : at(p) {}
    const Atom &operator*() const;
    const Atom *operator->() const { return &**this; }
    iterator &operator++() { ++at; return *this; }
    iterator operator++(int) { auto old = *this; ++at; return old; }
    bool operator==(const iterator &o) const { return at == o.at; }
    bool operator!=(const iterator &o) const { return at != o.at; }
  };
  AtomSet() = default;
  AtomSet(std::initializer_list<Atom> list) { for (auto &a : list) insert(a); }
  void insert(const Atom &);
  iterator begin() const { normalise(); return iterator(ids.data()); }
  iterator end() const { normalise(); return iterator(ids.data() + ids.size()); }
  size_t size() const { normalise(); return ids.size(); }
  bool empty() const { return ids.empty(); }
  size_t count(const Atom &) const;
  void eraseIf(const std::function<bool(const Atom &)> &);
};
struct AV {
  AtomSet atoms;
  bool top = false;
  bool merge(const AV &v);
  // Sequential merges of many sets, ending in one canonicalisation.
  static void startAbsorbing();
  void absorb(const AV &v);
  void settle();
  bool roots() const;
};
struct Slot {
  const llvm::Value *object;
  int64_t offset, stride;
  uint64_t bytes;
  AV value;
  bool filled = false;
  bool numerical = false;
};
class Analysis {
  llvm::Module &M;
  llvm::Function *Entry;
  bool ReversibleEntry;
  bool changed = false;
  bool virtualFP = false;
  std::map<llvm::Instruction *, std::unique_ptr<llvm::Function>> fpTransfers;
  std::map<const llvm::Value *, AV> values;
  // Solver state (bp-fj1). A step records what it reads; a write re-enters only the
  // steps that read the written value or object. Same equations, same fixpoint.
  int currentStep = -1;
  bool seedsDue = true;
  std::vector<char> dirty;
  std::unordered_map<const llvm::Value *, std::unordered_set<int>> valueReaders;
  std::unordered_map<const llvm::Value *, std::unordered_set<int>> objectReaders;
  std::unordered_set<int> anySlotReaders;
  std::vector<llvm::Function *> addressTaken;
  bool addressTakenKnown = false;
  void readValue(const llvm::Value *v) { if (currentStep >= 0) valueReaders[v].insert(currentStep); }
  void readObject(const llvm::Value *o) { if (currentStep >= 0) objectReaders[o].insert(currentStep); }
  void touchValue(const llvm::Value *);
  void touchObject(const llvm::Value *);
  void mergeValue(const llvm::Value *, const AV &);
  std::vector<size_t> slotsOf(const llvm::Value *);
  std::vector<Slot> slots;
  using SlotKey = std::tuple<const llvm::Value *, int64_t, int64_t, uint64_t, bool, bool>;
  std::map<SlotKey, size_t> slotIndex;
  unsigned analysisRounds = 0;
  std::map<const llvm::Value *, std::map<int64_t, std::vector<size_t>>> exactSlots;
  std::map<const llvm::Value *, std::vector<size_t>> otherSlots;
  std::map<const llvm::Value *, uint64_t> maxSlotBytes;
  void indexSlot(size_t);
  std::vector<size_t> overlappingSlots(const Atom &, uint64_t);
  std::map<std::pair<const llvm::Instruction *, const llvm::Value *>, AV>
      indexBounds;
  using Path = std::vector<unsigned>;
  std::map<std::pair<const llvm::Value *, Path>, AV> fields;
  AV field(const llvm::Value *, const Path &);
  void setField(const llvm::Value *, const Path &, const AV &);
  AV bitcast(const llvm::Value *, llvm::Type *, const Path &);
  void copyFields(const llvm::Value *, const llvm::Value *);
  bool composite(llvm::Instruction &);
  std::map<llvm::Function *, std::set<llvm::Function *>> edges;
  void seed(llvm::Constant *, const llvm::Value *, int64_t, llvm::Type *);
  void step(llvm::Instruction &);
  void store(const AV &, const AV &, uint64_t, bool filled = false);
  AV load(const AV &, llvm::Type *);
  AV convert(const AV &, llvm::Type *, llvm::Type *, unsigned);
  AV displace(const AV &, const llvm::APInt &, unsigned, bool gep = true);
  struct GEPIndex { AV values; llvm::APInt scale; unsigned width; };
  AV gepImage(const AV &base, const llvm::APInt &offset, const std::vector<GEPIndex> &indices, unsigned pointerBits);
  void vectorGEP(llvm::GetElementPtrInst &);
  void bind(llvm::CallBase &, llvm::Function *);

public:
  // End the lifetime of private S2 graphs before rewriting their source IR.
  // The caller must rerun analysis before using transfer-derived results.
  void releaseTransferGraphs();
  explicit Analysis(llvm::Module &m, llvm::Function *entry = nullptr, bool reversible = false) : M(m), Entry(entry), ReversibleEntry(reversible) {}
  AV get(const llvm::Value *);
  AV read(llvm::Value *, uint64_t, llvm::Type *);
  AV readAt(llvm::CallBase &, llvm::Value *, uint64_t, llvm::Type *);
  std::set<llvm::Function *> candidates(llvm::Value *,
                                        llvm::FunctionType *type = nullptr);
  std::map<llvm::Function *, std::set<std::string>> tiers;
  void run();
  void checkHandles();
  void checkRegions();
  llvm::json::Object report();
};
void lowerReversible(llvm::Module &, Analysis &, llvm::Function &, llvm::StringRef, unsigned, llvm::StringRef, llvm::StringRef, llvm::StringRef);
void lowerProduction(llvm::Module &, Analysis &, llvm::StringRef, unsigned, llvm::StringRef, llvm::StringRef);
std::string scalarGlobalKey(const llvm::GlobalVariable &);
std::string scalarGlobalImage(llvm::GlobalVariable &, const std::map<const llvm::GlobalVariable *,uint64_t> &);
void validateResidual(llvm::Module &, bool classical = false,
                      const std::set<llvm::Function *> *variants = nullptr);
void normaliseScalar(llvm::Function &, bool wide = true, bool privateTransfer = false);
void normaliseFP(llvm::Function &);
void materialiseFPBits(llvm::Function &);
void normaliseWideFP(llvm::Function &);
llvm::Value *n22Packing(llvm::Value *);
llvm::Function *normaliseWideABI(llvm::Module &, llvm::Function *root = nullptr);
void linkArith(llvm::Module &);
void prepareNativeComparison(llvm::Module &);
void requireSoftFloat(llvm::Function &);
void materialiseStackRuntime(llvm::Module &, uint64_t);
bool prepareStack(llvm::Module &, llvm::Function &, uint64_t);
std::vector<llvm::GlobalVariable *> entryGlobals(llvm::Module &);
void prepareEntryReplay(llvm::Module &, unsigned);
void lowerScalar(llvm::Module &, llvm::Function &, llvm::StringRef desc,
                 llvm::StringRef out, unsigned stackCells, uint64_t heapCapacity = 0, int projection = -1, std::map<std::string,std::string> *globalNames = nullptr, uint64_t sstack = 0, unsigned autoSnapshot = 0);
} // namespace bennett

namespace bennett { void normaliseInteger(llvm::Function &); void materialiseIntegerRuntime(llvm::Function &); }

namespace bennett { void materialiseMemoryRuntime(llvm::Function &); }
