#pragma once
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/Support/JSON.h"
#include <map>
#include <set>
#include <string>
#include <vector>
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
struct AV {
  std::set<Atom> atoms;
  bool top = false;
  bool merge(const AV &v);
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
  bool changed = false;
  std::map<const llvm::Value *, AV> values;
  std::vector<Slot> slots;
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
  AV displace(const AV &, const llvm::APInt &, unsigned);
  void bind(llvm::CallBase &, llvm::Function *);

public:
  explicit Analysis(llvm::Module &m) : M(m) {}
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
void lowerProduction(llvm::Module &, Analysis &, llvm::StringRef, unsigned, llvm::StringRef, llvm::StringRef);
void normaliseScalar(llvm::Function &);
void lowerScalar(llvm::Module &, llvm::Function &, llvm::StringRef desc,
                 llvm::StringRef out, unsigned stackCells, uint64_t heapCapacity = 0, int projection = -1);
} // namespace bennett
