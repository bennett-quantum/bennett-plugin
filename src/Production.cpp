#include "Bennett.h"
#include "ComparisonLayout.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/ADT/MapVector.h"
#include "llvm/ADT/PostOrderIterator.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/Analysis/InstructionSimplify.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InlineAsm.h"
#include "llvm/IR/CFG.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Intrinsics.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/Program.h"
#include <cstdlib>
#include "llvm/Transforms/Utils/Cloning.h"
#include <regex>
using namespace llvm;
namespace bennett {
namespace {
std::string hash(StringRef s) {
  return toHex(SHA256::hash(arrayRefFromStringRef(s)), true);
}
std::string jcs(const json::Value &v) {
  if (auto *o = v.getAsObject()) {
    std::map<std::string, const json::Value *> sorted;
    for (auto &e : *o)
      sorted[e.first.str()] = &e.second;
    std::string s = "{";
    for (auto &e : sorted) {
      if (s.size() > 1)
        s += ",";
      s += jcs(json::Value(e.first)) + ":" + jcs(*e.second);
    }
    return s + "}";
  }
  if (auto *a = v.getAsArray()) {
    std::string s = "[";
    for (auto &e : *a) {
      if (s.size() > 1)
        s += ",";
      s += jcs(e);
    }
    return s + "]";
  }
  return formatv("{0}", v).str();
}
json::Value parse(StringRef text) {
  auto v = json::parse(text);
  if (!v)
    fail("output", toString(v.takeError()));
  return std::move(*v);
}
std::string read(StringRef path) {
  auto b = MemoryBuffer::getFile(path);
  if (!b)
    fail("output", b.getError().message());
  return (*b)->getBuffer().str();
}
void write(StringRef path, StringRef text) {
  std::error_code ec;
  raw_fd_ostream o(path, ec);
  if (ec)
    fail("output", ec.message());
  o << text;
}
std::string join(const std::vector<std::string> &v, StringRef sep = ", ") {
  std::string s;
  for (auto &x : v) {
    if (!s.empty())
      s += sep;
    s += x;
  }
  return s;
}
std::string decimal(const APInt &v) {
  SmallString<48> s;
  v.toString(s, 10, false);
  return s.str().str();
}
uint64_t integer(AV v, const Value *at) {
  if (v.top || v.atoms.size() != 1 || v.atoms.begin()->kind != Atom::Int)
    unimplemented("§8.4 scalar descriptor finite dispatch", 1, at);
  return v.atoms.begin()->integer.getLimitedValue();
}
const char *budgetNames[] = {"steps", "heap", "stack", "depth", "sstack"};
json::Object tuple(const std::vector<uint64_t> &v) {
  json::Object o;
  for (unsigned i = 0; i < 5; ++i) o[budgetNames[i]] = std::to_string(v[i]);
  return o;
}
struct BudgetTable {
  std::vector<uint64_t> defaults, capacities;
  json::Value document = json::Object{};
  bool enabled;
  uint64_t number(const json::Value &v) {
    auto s = v.getAsString(); uint64_t n;
    if (!s || s->empty() || (s->size() > 1 && (*s)[0] == '0') || s->getAsInteger(10,n))
      fail("input", "§9.2 budget components require unsigned decimal strings");
    return n;
  }
  BudgetTable(std::vector<uint64_t> d, StringRef path) : defaults(d), capacities(d), enabled(!path.empty()) {
    if (!enabled) return;
    auto bytes = read(path); document = parse(bytes);
    auto *o = document.getAsObject();
    if (!o || o->getString("version") != "0.2" || !o->getArray("entries") ||
        jcs(document) != StringRef(bytes).rtrim())
      fail("input", "§9.2 budget table must be version 0.2 JCS");
    for (auto &v : *o) if (v.first != "version" && v.first != "defaults" && v.first != "entries")
      fail("input", "§9.2 unknown budget-table field");
    if (auto *defs = o->getObject("defaults")) {
      for (auto &v : *defs) {
        unsigned i = 0; for (; i < 5; ++i) if (v.first == budgetNames[i]) break;
        if (i == 5) fail("input", "§9.2 unknown default component");
        defaults[i] = number(v.second);
      }
    } else if (o->get("defaults")) fail("input", "§9.2 defaults must be an object");
    capacities = defaults;
    for (auto &v : *o->getArray("entries")) {
      auto *entry = v.getAsObject(); unsigned selectors = 0;
      if (!entry) fail("input", "§9.2 entry must be an object");
      for (auto &field : *entry) {
        if (field.first == "symbol" || field.first == "region_key" || field.first == "identity") {
          ++selectors; auto str = field.second.getAsString();
          if (!str || (field.first != "symbol" && !std::regex_match(str->str(), std::regex("[0-9a-f]{64}"))))
            fail("input", "§9.2 invalid selector");
        } else {
          unsigned i = 0; for (; i < 5; ++i) if (field.first == budgetNames[i]) break;
          if (i == 5) fail("input", "§9.2 unknown entry component");
          capacities[i] = std::max(capacities[i], number(field.second));
        }
      }
      if (selectors != 1) fail("input", "§9.2 entry requires exactly one selector");
    }
  }
  bool glob(StringRef pattern, StringRef name) {
    std::string re = "^";
    for (char c : pattern) {
      if (c == '*') re += ".*";
      else if (c == '?') re += ".";
      else { if (StringRef(".[]{}()^$|+\\").contains(c)) re += '\\'; re += c; }
    }
    return std::regex_match(name.str(), std::regex(re + "$"));
  }
  std::vector<uint64_t> baseline(Function &f) {
    auto result = defaults;
    if (!enabled) return result;
    auto key = regionKey(&f);
    for (unsigned i = 0; i < 5; ++i) {
      bool found = false;
      for (auto selector : {"region_key", "symbol"}) {
        for (auto &v : *document.getAsObject()->getArray("entries")) {
          auto *e = v.getAsObject(); auto sel = e->getString(selector);
          if (!sel || !e->get(budgetNames[i])) continue;
          if ((StringRef(selector) == "region_key" && *sel == key) ||
              (StringRef(selector) == "symbol" && glob(*sel, f.getName()))) {
            result[i] = number(*e->get(budgetNames[i])); found = true; break;
          }
        }
        if (found) break;
      }
    }
    return result;
  }
  void overlay(std::vector<uint64_t> &budget, StringRef selection) {
    if (!enabled) return;
    for (unsigned i = 0; i < 5; ++i)
      for (auto &v : *document.getAsObject()->getArray("entries")) {
        auto *e = v.getAsObject();
        if (e->getString("identity") == selection && e->get(budgetNames[i])) {
          budget[i] = number(*e->get(budgetNames[i])); break;
        }
      }
  }
};
std::string oracleIdentity(StringRef object) {
  auto text = object.split("section symbols\n").second.split('\n').first;
  auto syms = parse(text);
  for (auto &v : *syms.getAsObject())
    if (v.second.getAsObject()->getString("name") == "ref")
      return v.second.getAsObject()->getString("interface_hash")->str();
  fail("output", "missing reference identity");
}
struct Entry {
  Module &m;
  Analysis &a;
  Function &f;
  std::string out;
  unsigned stack;
  BudgetTable &table;
  json::Array resolvedShapes;
  std::map<const Value *, std::string> names;
  std::map<const BasicBlock *, std::string> blocks;
  std::set<const Value *> descriptorObjects;
  bool memoryDescriptors = false;
  bool rTier = false;
  bool argvService = false;
  std::set<std::string> effectModels;
  std::string diskImage, diskDataKey;
  json::Array asmPoints;
  GlobalVariable *rSteps = nullptr, *rEH = nullptr;
  void rReturn() {
    for(auto &p:localMemory)rows.push_back("free "+p);
    std::vector<std::string> values;
    for(auto &t:resultTypes) {
      auto z=number(0);if(t=="ptr")z=emit("ptr","inttoptr "+z);
      else if(t!="i64")z=emit(t,"trunc."+t+" "+z);
      values.push_back(z);
    }
    rows.push_back("ret"+(values.empty()?"":" "+join(values," ")));
  }
  void propagateExit() {
    if(!rTier || !rEH)return;
    auto p=operand(rEH),active=emit("i32","load.i32 "+p);
    auto four=operand(ConstantInt::get(Type::getInt32Ty(m.getContext()),4));
    auto exiting=emit("i1","icmp.eq "+active+" "+four);
    auto id=std::to_string(dispatchBlock++);
    rows.push_back("br "+exiting+" ^exit"+id+"() ^continue"+id+"()");
    rows.push_back("^exit"+id+"():");rReturn();rows.push_back("^continue"+id+"():");
  }
  void countRStep() {
    auto p=operand(rSteps),left=emit("i64","load.i64 "+p),zero=number(0);
    auto exhausted=emit("i1","icmp.eq "+left+" "+zero);
    auto id=std::to_string(dispatchBlock++);
    rows.push_back("br "+exhausted+" ^budget"+id+"() ^step"+id+"()");
    rows.push_back("^budget"+id+"():");rows.push_back("trap");
    rows.push_back("^step"+id+"():");auto one=number(1),remaining=emit("i64","sub "+left+" "+one);
    rows.push_back("store.i64 "+p+" "+remaining);
  }
  std::set<std::string> ccGlobals;
  uint64_t ccHeapBytes = 0, allocatedBytes = 0;
  const Value *activeRoot = nullptr;
  bool generalUsed = false;
  bool allocatorFaultService = false;
  bool usesCCCalls = false;
  std::map<Function *, std::string> *ccNames = nullptr;
  std::map<std::string, std::pair<std::string,std::string>> ccFunctions;
  std::vector<std::string> regs, rows, params, results, paramTypes, resultTypes;
  std::vector<json::Object> budgets;
  std::string reference, shape, refPath;
  std::vector<std::string> references;
  std::vector<std::map<std::string,std::string>> referenceGlobals;
  json::Array coverage;
  std::map<std::string, std::pair<std::string, std::string>> actions;
  unsigned next = 0, ordinal = 0;
  struct PhysicalSlot { std::string q, tag; unsigned identity; };
  std::vector<const Value *> fileOrder;
  std::map<const Value *, PhysicalSlot> files;
  std::vector<std::string> localMemory;
  bool tagged(AV v) {
    for (auto &x : v.atoms) if (x.kind == Atom::Root && files.count(x.object)) return true;
    return false;
  }
  void withHandle(Value *v, const std::function<void(std::string)> &body, bool retire = false, std::string result = "", const Value *returned = nullptr) {
    auto provenance = a.get(v);
    if (!tagged(provenance)) { body(operand(v)); return; }
    auto id = std::to_string(dispatchBlock++), done = "handle" + id + "done";
    auto value = operand(v);
    for (auto *site : fileOrder) {
      bool candidate=false;
      for(auto &x:provenance.atoms) if(x.kind==Atom::Root && x.object==site)candidate=true;
      if(!candidate)continue;
      auto &slot = files.at(site);
      auto eq = fresh("i1"), live = fresh("i1"), ok = fresh("i1"), liveTag = fresh("i" + std::to_string(m.getDataLayout().getPointerSizeInBits()));
      rows.push_back(liveTag + " = load.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + slot.tag);
      auto zero = operand(ConstantInt::get(m.getDataLayout().getIntPtrType(m.getContext()),0));
      auto leaf = "handle" + std::to_string(dispatchBlock++), next = leaf + "next";
      rows.push_back(eq + " = icmp.eq " + value + " " + liveTag);
      rows.push_back(live + " = icmp.ne " + liveTag + " " + zero);
      rows.push_back(ok + " = and " + eq + " " + live);
      rows.push_back("br " + ok + " ^" + leaf + "() ^" + next + "()");
      rows.push_back("^" + leaf + "():"); activeRoot=site; body(slot.q); activeRoot=nullptr;
      if (retire) rows.push_back("store.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + slot.tag + " " + zero);
      rows.push_back("br ^" + done + "(" + (result.empty() ? "" : names.at(returned)) + ")"); rows.push_back("^" + next + "():");
    }
    rows.push_back("trap"); rows.push_back("^" + done + "(" + (result.empty() ? "" : result+":i1") + "):");
  }
  unsigned width(Type *t) {
    if(t->isPointerTy())return m.getDataLayout().getPointerTypeSizeInBits(t);
    if(t->isFloatingPointTy())return t->getPrimitiveSizeInBits();
    if (t->isIntegerTy() && t->getIntegerBitWidth() <= 128)
      return t->getIntegerBitWidth();
    unimplemented("§17.4 CC scalar carrier", 1, &f);
  }
  std::string fresh(std::string type) {
    auto n = "v" + std::to_string(next++);
    regs.push_back(n + ":" + type);
    return n;
  }
  std::string operand(Value *v) {
    if (names.count(v))
      return names[v];
    if(auto *c=dyn_cast<ConstantFP>(v))return operand(ConstantInt::get(c->getContext(),c->getValueAPF().bitcastToAPInt()));
    if (auto *c = dyn_cast<ConstantInt>(v)) {
      auto n = fresh("i" + std::to_string(c->getBitWidth()));
      rows.push_back(n + " = const.i" + std::to_string(c->getBitWidth()) + " " +
                     decimal(c->getValue()));
      return n;
    }
    if (auto *fn = resolve(v); fn && v->getType()->isPointerTy()) {
      auto n=fresh("ptr");auto address=operand(ConstantInt::get(m.getDataLayout().getIntPtrType(m.getContext()),functionAddress(fn)));
      rows.push_back(n+" = inttoptr "+address);return n;
    }
    if (auto *g=dyn_cast<ConstantExpr>(v);g && g->getOpcode()==Instruction::GetElementPtr)return gep(cast<GEPOperator>(g));
    if(auto *g=dyn_cast<GlobalVariable>(v)) {
      ccGlobals.insert(scalarGlobalKey(*g));auto n=fresh("ptr");
      // Resolved by the unified object linker, in the same namespace as L.
      auto pw=m.getDataLayout().getPointerSizeInBits();auto bits=fresh("i"+std::to_string(pw));
      rows.push_back(bits+" = const.i"+std::to_string(pw)+" CCADDRESS"+std::to_string(std::distance(m.global_begin(),g->getIterator())));
      rows.push_back(n+" = inttoptr "+bits);return n;
    }
    if (isa<ConstantPointerNull>(v)) {
      auto n = fresh("ptr"); auto z = operand(ConstantInt::get(m.getDataLayout().getIntPtrType(m.getContext()),0));
      rows.push_back(n + " = inttoptr " + z); return n;
    }
    unimplemented("§17.4 CC operand / §6.5 handle environment", 1, v);
  }
  // §17.4: aggregates travel as depth-first scalar tuples, including
  // recursive call arguments/results and parallel phi bindings.
  struct Field { std::vector<unsigned> path; Type *type; uint64_t offset; };
  std::vector<Field> fields(Type *t) {
    std::vector<Field> out;
    std::function<void(Type *,std::vector<unsigned>,uint64_t)> visit =
      [&](Type *t,std::vector<unsigned> path,uint64_t offset) {
        if(t->isAggregateType()) {
          unsigned n=t->isStructTy()?cast<StructType>(t)->getNumElements():t->getArrayNumElements();
          for(unsigned k=0;k<n;++k) {
            auto p=path;p.push_back(k);
            auto *e=t->isStructTy()?t->getStructElementType(k):t->getArrayElementType();
            auto off=t->isStructTy()?m.getDataLayout().getStructLayout(cast<StructType>(t))->getElementOffset(k):k*m.getDataLayout().getTypeAllocSize(e).getFixedValue();
            visit(e,p,offset+off);
          }
        } else out.push_back({path,t,offset});
      };
    visit(t,{},0);return out;
  }
  std::map<const Value *,std::vector<std::string>> tuples;
  std::string fieldType(Type *t) {
    return t->isPointerTy()?"ptr":"i"+std::to_string(width(t));
  }
  std::vector<std::string> operands(Value *v) {
    if(!v->getType()->isAggregateType())return {operand(v)};
    if(auto it=tuples.find(v);it!=tuples.end())return it->second;
    if(auto *c=dyn_cast<Constant>(v)) {
      std::vector<std::string> out;
      for(auto &field:fields(v->getType())) {
        auto *e=c;for(auto k:field.path)e=e->getAggregateElement(k);
        out.push_back(operand(e));
      }
      return out;
    }
    unimplemented("§17.4 aggregate CC operand",2,v);
  }
  std::vector<std::string> destinations(Value *v) {
    if(!v->getType()->isAggregateType()) {auto n=fresh(type(v));names[v]=n;return {n};}
    std::vector<std::string> out;
    for(auto &field:fields(v->getType()))out.push_back(fresh(fieldType(field.type)));
    tuples[v]=out;return out;
  }
  std::string fieldPointer(const std::string &p,uint64_t offset) {
    if(!offset)return p;
    auto t="i"+std::to_string(m.getDataLayout().getPointerSizeInBits());
    auto bits=emit(t,"ptrtoint."+t+" "+p);
    auto off=operand(ConstantInt::get(m.getDataLayout().getIntPtrType(m.getContext()),offset));
    bits=emit(t,"add "+bits+" "+off);return emit("ptr","inttoptr "+bits);
  }
  const Value *root(AV v, const Value *at) {
    if (v.top || v.atoms.size() != 1 || v.atoms.begin()->kind != Atom::Root)
      unimplemented("§6.5 descriptor handle dispatch", 1, at);
    return v.atoms.begin()->object;
  }
  unsigned qwidth(AV v, const Value *at) {
    unsigned width = 0;
    if (v.top || v.atoms.empty()) unimplemented("§6.5 handle width dispatch", 1, at);
    for (auto &atom : v.atoms) {
      if(activeRoot && atom.kind==Atom::Root && atom.object!=activeRoot)continue;
      auto *c = atom.kind == Atom::Root ? dyn_cast<CallBase>(atom.object) : nullptr;
      if (!c && atom.kind == Atom::Int && atom.integer.isZero()) continue;
      if (!c) unimplemented("§6.6 scalar boundary handles", 1, at);
      auto w = integer(a.get(c->getArgOperand(1)), at);
      if (width && width != w) unimplemented("§6.5 mixed-width handle dispatch", 1, at);
      width = w;
    }
    return width;
  }
  std::string type(Value *v) {
    if (tagged(a.get(v))) return "i" + std::to_string(m.getDataLayout().getPointerSizeInBits());
    if (v->getType()->isPointerTy() && !a.get(v).roots()) return "ptr";
    if (v->getType()->isPointerTy() && a.get(v).roots())
      return "qreg[" + std::to_string(qwidth(a.get(v), v)) + "]";
    return "i" + std::to_string(width(v->getType()));
  }
  std::string handle(AV v, const Value *at) {
    if (generalDescriptor) { auto *r=root(v,at); return files.count(r) ? files.at(r).q : names.at(r); }
    auto *r = root(v, at);
    if (!names.count(r))
      unimplemented("§6.5 handle not in live register environment", 1, at);
    if (files.count(r)) {
      std::string q;
      withHandle(const_cast<Value *>(r), [&](std::string n) { q = n; });
      return q;
    }
    return names[r];
  }
  // Call-local reaching definitions are a virtual descriptor load. Never use
  // a flow-insensitive union as the runtime field value.
  Value *fieldValue(CallBase &c, uint64_t off, Type *t) {
    auto base = a.get(c.getArgOperand(2));
    if (base.top || base.atoms.size() != 1) return nullptr;
    auto p = *base.atoms.begin();
    for (auto it = c.getIterator(); it != c.getParent()->begin();) {
      auto &i = *--it;
      if (auto *st = dyn_cast<StoreInst>(&i)) {
        auto dst = a.get(st->getPointerOperand());
        if (dst.top) break;
        for (auto &d : dst.atoms) if (d.object == p.object) {
          auto bytes = m.getDataLayout().getTypeStoreSize(st->getValueOperand()->getType()).getFixedValue();
          if (d.stride || (d.offset < int64_t(p.offset + off + m.getDataLayout().getTypeStoreSize(t).getFixedValue()) &&
                          d.offset + int64_t(bytes) > int64_t(p.offset + off))) {
            if (!d.stride && dst.atoms.size() == 1 && d.offset == int64_t(p.offset + off) && st->getValueOperand()->getType() == t)
              return st->getValueOperand();
            return nullptr;
          }
        }
      } else if (auto *call = dyn_cast<CallBase>(&i)) {
        auto *g = call->getCalledFunction();
        if (!g || (!g->getName().starts_with("__bennett_") && !g->getName().starts_with("llvm.lifetime."))) break;
      }
    }
    return nullptr;
  }
  AV descriptorField(CallBase &c,uint64_t off,Type *t) {
    if(automaticSnapshot && !memoryDescriptors)if(auto *v=fieldValue(c,off,t))return a.get(v);
    return a.readAt(c,c.getArgOperand(2),off,t);
  }
  // The fast path above is an optimisation only. All other reads use the
  // actual caller memory at the marker, including predecessor stores/phis.
  std::string fieldOperand(CallBase &c, uint64_t off, Type *t) {
    if (!memoryDescriptors)
      if (auto *v = fieldValue(c, off, t)) return operand(v);
    auto p = operand(c.getArgOperand(2));
    auto pw = m.getDataLayout().getPointerSizeInBits();
    auto bits = fresh("i"+std::to_string(pw));
    rows.push_back(bits+" = ptrtoint.i"+std::to_string(pw)+" "+p);
    auto k = operand(ConstantInt::get(IntegerType::get(m.getContext(),pw),off));
    auto sum = fresh("i"+std::to_string(pw)), address = fresh("ptr");
    rows.push_back(sum+" = add "+bits+" "+k);
    rows.push_back(address+" = inttoptr "+sum);
    auto w = t->isPointerTy() ? pw : width(t);
    auto value = fresh("i"+std::to_string(w));
    rows.push_back(value+" = load.i"+std::to_string(w)+" "+address);
    return value;
  }
  std::string gep(GEPOperator *g) {
    auto &dl = m.getDataLayout();
    unsigned p = dl.getPointerTypeSizeInBits(g->getType()), i = dl.getIndexTypeSizeInBits(g->getType());
    auto base = fresh("i"+std::to_string(p));
    rows.push_back(base+" = ptrtoint.i"+std::to_string(p)+" "+operand(g->getPointerOperand()));
    auto op = [&](unsigned w, std::string text) { auto n=fresh("i"+std::to_string(w)); rows.push_back(n+" = "+text); return n; };
    auto acc = i<p ? op(i,"trunc.i"+std::to_string(i)+" "+base) : base;
#if LLVM_VERSION_MAJOR >= 23
    SmallMapVector<Value *, APInt, 4> vars;
#else
    MapVector<Value *, APInt> vars;
#endif
    APInt offset(i,0);
    if (!g->collectOffset(dl,i,vars,offset)) unimplemented("§16.4 CC GEP",2,&f);
    for (auto &v : vars) {
      auto idx=operand(v.first);auto w=width(v.first->getType());
      if(w!=i)idx=op(i,std::string(w<i ? "sext.i" : "trunc.i")+std::to_string(i)+" "+idx);
      if(v.second!=1)idx=op(i,"mul "+idx+" "+operand(ConstantInt::get(m.getContext(),v.second)));
      acc=op(i,"add "+acc+" "+idx);
    }
    if(!offset.isZero())acc=op(i,"add "+acc+" "+operand(ConstantInt::get(m.getContext(),offset)));
    if(i<p) {
      auto lo=op(p,"zext.i"+std::to_string(p)+" "+acc);
      auto hi=op(p,"and "+base+" "+operand(ConstantInt::get(m.getContext(),APInt::getHighBitsSet(p,p-i))));
      acc=op(p,"or "+hi+" "+lo);
    }
    auto result=fresh("ptr");rows.push_back(result+" = inttoptr "+acc);return result;
  }
  bool compilingInplace = false;
  std::string inplaceTarget, inplaceFault;
  json::Array inplaceEvidence;
  std::map<std::string,std::pair<uint64_t,uint64_t>> verifiedPairs;
  std::map<uint64_t, AV> selectedFields;
  unsigned dispatchBlock = 0;
  Function *selectedCallee = nullptr;
  bool generalDescriptor = false;
  uint64_t functionAddress(Function *fn) {
    if (auto address = comparisonFunctionAddress(*fn)) return *address;
    if (hasComparisonLayout())
      fail("BD-E-COMPARISON-LAYOUT", "missing function address", fn);
    // Standalone comparison link, matching the module-order convention used
    // for data by the scalar linker. The production driver owns §19.5 layout.
    uint64_t address=4096;
    for(auto &g:m.globals())address=alignTo(address,m.getDataLayout().getPreferredAlign(&g))+m.getDataLayout().getTypeAllocSize(g.getValueType()).getFixedValue();
    address=alignTo(address,uint64_t(4096));
    for(auto &g:m) { if(&g==fn)return address; address+=16; }
    llvm_unreachable("function missing from comparison link");
  }
  AV intValue(uint64_t n, unsigned w=64) { Atom x; x.kind=Atom::Int;x.integer=APInt(w,n); AV v;v.atoms.insert(x);return v; }
  bool singletonInt(AV v) { return !v.top && v.atoms.size()==1 && v.atoms.begin()->kind==Atom::Int; }
  // The same unsigned, balanced compare tree serves candidate addresses,
  // fields, register identities and finite allocation widths (§14.2).
  void compareTree(std::string value, unsigned w, const std::vector<uint64_t> &keys,
                   const std::function<void(uint64_t)> &body, const std::string &bad) {
    std::function<void(unsigned,unsigned)> tree=[&](unsigned lo,unsigned hi) {
      if(lo==hi){rows.push_back("br ^"+bad+"()");return;}
      unsigned mid=(lo+hi)/2;auto key=keys[mid];
      auto k=operand(ConstantInt::get(IntegerType::get(m.getContext(),w),key)),eq=fresh("i1");
      auto leaf="dispatch"+std::to_string(dispatchBlock++),rest=leaf+"rest";
      rows.push_back(eq+" = icmp.eq "+value+" "+k);
      rows.push_back("br "+eq+" ^"+leaf+"() ^"+rest+"()");rows.push_back("^"+leaf+"():");body(key);
      rows.push_back("^"+rest+"():");
      if(hi-lo==1){rows.push_back("br ^"+bad+"()");return;}
      auto lt=fresh("i1"),left=rest+"left",right=rest+"right";
      rows.push_back(lt+" = icmp.ult "+value+" "+k);rows.push_back("br "+lt+" ^"+left+"() ^"+right+"()");
      rows.push_back("^"+left+"():");tree(lo,mid);rows.push_back("^"+right+"():");tree(mid+1,hi);
    };tree(0,keys.size());
  }
  void descriptor(CallBase &c) {
    auto &ctx=m.getContext();auto *u32=Type::getInt32Ty(ctx),*u64=Type::getInt64Ty(ctx);auto *ptr=PointerType::get(ctx,0);
    auto candidates=a.candidates(c.getArgOperand(0));
    auto *hl=m.getDataLayout().getStructLayout(StructType::get(ctx,{u32,u32,u32,u32,ptr,ptr}));
    auto *bl=m.getDataLayout().getStructLayout(StructType::get(ctx,{u32,u32,ptr,u64,u64}));
    bool general=memoryDescriptors || candidates.size()!=1 || !resolve(c.getArgOperand(0));
    // Keep the established straight-line encoding exactly when no new shape
    // field requires dispatch. ARG value bits remain runtime arguments.
    for(auto *fn:candidates) {
      for(unsigned off:{8u,unsigned(hl->getElementOffset(4)),unsigned(hl->getElementOffset(5))}) {
        auto v=descriptorField(c,off,off==8?static_cast<Type *>(u32):ptr);
        general |= v.top || v.atoms.size()!=1;
      }
      for(unsigned i=0;i<fn->arg_size();++i) {
        auto off=hl->getSizeInBytes()+i*bl->getSizeInBytes();auto k=descriptorField(c,off,u32);
        auto q=descriptorField(c,off+bl->getElementOffset(2),ptr);
        general |= q.top || q.atoms.size()!=1;
        if(!singletonInt(k) || integer(k,&c)!=2) {
          auto size=descriptorField(c,off+bl->getElementOffset(4),u64);general |= size.top || size.atoms.size()!=1;
        }
      }
      auto nd=descriptorField(c,8,u32);
      if(singletonInt(nd))for(unsigned j=0;j<integer(nd,&c);++j) {
        auto off=hl->getSizeInBytes()+fn->arg_size()*bl->getSizeInBytes()+j*24;
        for(unsigned d:{0u,8u,16u}){auto v=descriptorField(c,off+d,d==0?static_cast<Type *>(u32):d==8?static_cast<Type *>(ptr):u64);general |= v.top || v.atoms.size()!=1;}
      }
    }
    if(!general){descriptorLegacy(c);return;}
    generalDescriptor=true; generalUsed=true;
    auto id=std::to_string(dispatchBlock++),done="dispatch"+id+"done",bad="dispatch"+id+"bad";
    auto field=[&](uint64_t off,Type *t){return descriptorField(c,off,t);};
    auto pw=m.getDataLayout().getPointerSizeInBits();
    auto choose=[&](uint64_t off,Type *t,std::vector<AV> choices,const std::function<void(AV)> &body) {
      auto actual=field(off,t);std::map<uint64_t,AV> keyed;
      for(auto v:choices)for(auto x:v.atoms) {
        if(!actual.top && !actual.atoms.count(x))continue;
        uint64_t key=x.kind==Atom::Root ? (files.count(x.object)?files.at(x.object).identity:0) : x.integer.getLimitedValue();keyed[key]=v;
      }
      if(keyed.empty()){rows.push_back("br ^"+bad+"()");return;}
      auto leaf=[&](uint64_t key){selectedFields[off]=keyed.at(key);body(keyed.at(key));selectedFields.erase(off);};
      if(!actual.top && actual.atoms.size()==1 && keyed.size()==1){leaf(keyed.begin()->first);return;}
      std::vector<uint64_t> keys;for(auto &x:keyed)keys.push_back(x.first);
      auto value=fieldOperand(c,off,t);
      if(t->isPointerTy() && !memoryDescriptors) {
        if(auto *v=fieldValue(c,off,t); v && !tagged(a.get(v))) {auto n=fresh("i"+std::to_string(pw));rows.push_back(n+" = ptrtoint.i"+std::to_string(pw)+" "+value);value=n;}
      }
      compareTree(value,t->isPointerTy()?pw:width(t),keys,leaf,bad);
    };
    auto ints=[&](std::vector<uint64_t> ns,unsigned w){std::vector<AV> vs;for(auto n:ns)vs.push_back(intValue(n,w));return vs;};
    auto handles=[&](uint64_t off,bool null,const std::function<bool(unsigned)> &valid) {
      auto v=field(off,ptr);std::vector<AV> vs;
      if(null)vs.push_back(intValue(0,pw));
      for(auto &x:v.atoms)if(x.kind==Atom::Root && valid(qwidth(AV{{x},false},&c)))vs.push_back(AV{{x},false});
      return vs;
    };
    auto compile=[&](Function *fn) {
      selectedCallee=fn;
      choose(0,u32,ints({2},32),[&](AV){choose(4,u32,ints({fn->arg_size()},32),[&](AV){choose(12,u32,ints({0},32),[&](AV){
      choose(8,u32,ints({0,1,2,3,4},32),[&](AV nd){
      choose(hl->getElementOffset(4),ptr,handles(hl->getElementOffset(4),true,[](unsigned){return true;}),[&](AV){
      choose(hl->getElementOffset(5),ptr,handles(hl->getElementOffset(5),false,[](unsigned w){return w==4;}),[&](AV){
        std::function<void(unsigned)> devices;
        devices=[&](unsigned j) {
          if(j==integer(nd,&c)){
            std::set<const Value *> used;
            for(auto &v:selectedFields)for(auto &x:v.second.atoms)if(x.kind==Atom::Root) {
              if(!used.insert(x.object).second){rows.push_back("br ^"+bad+"()");return;}
              if(files.count(x.object)) {
                auto &slot=files.at(x.object);auto live=fresh("i"+std::to_string(pw)),ok=fresh("i1"),next="dispatch"+std::to_string(dispatchBlock++);
                rows.push_back(live+" = load.i"+std::to_string(pw)+" "+slot.tag);
                rows.push_back(ok+" = icmp.eq "+live+" "+operand(ConstantInt::get(IntegerType::get(ctx,pw),slot.identity)));
                rows.push_back("br "+ok+" ^"+next+"() ^"+bad+"()");rows.push_back("^"+next+"():");
              }
            }
            descriptorLeaf(c);rows.push_back("br ^"+done+"()");return;
          }
          auto off=hl->getSizeInBytes()+fn->arg_size()*bl->getSizeInBytes()+j*24;
          choose(off,u32,ints({1,2,3,4},32),[&](AV model){
            auto code=integer(model,&c);bool duplicate=false;
            for(unsigned k=0;k<j;++k)duplicate |= integer(selectedFields.at(off-(j-k)*24),&c)==code;
            if(duplicate){rows.push_back("br ^"+bad+"()");return;}
            choose(off+4,u32,ints({0},32),[&](AV){
              if(code==3){devices(j+1);return;}
              choose(off+8,ptr,handles(off+8,code==4,[&](unsigned w){auto unit=code==2?4096u:8u;return w%unit==0 && (code==4 || isPowerOf2_64(w/unit));}),[&](AV){
                // value is reserved outside CLOCK and does not affect a shape.
                selectedFields[off+16]=intValue(0);devices(j+1);selectedFields.erase(off+16);
              });
            });
          });
        };
        std::function<void(unsigned)> params;
        params=[&](unsigned i) {
          if(i==fn->arg_size()){devices(0);return;}
          auto *t=fn->getArg(i)->getType();auto off=hl->getSizeInBytes()+i*bl->getSizeInBytes();
          choose(off,u32,ints(t->isPointerTy()?std::vector<uint64_t>{1,2,3,4}:std::vector<uint64_t>{1,2},32),[&](AV kind){
            auto code=integer(kind,&c);
            choose(off+4,u32,ints(code==1?std::vector<uint64_t>{0,1}:std::vector<uint64_t>{0},32),[&](AV){
              if(code==2){params(i+1);return;}
              choose(off+bl->getElementOffset(2),ptr,handles(off+bl->getElementOffset(2),false,[&](unsigned w){return code==1?w<=(t->isPointerTy()?pw:width(t)):w%8==0 && w>0 && (code!=3 || isPowerOf2_64(w/8));}),[&](AV q){
                if(code==1){params(i+1);return;}
                auto n=qwidth(q,&c)/8;
                choose(off+bl->getElementOffset(4),u64,ints({n},64),[&](AV){params(i+1);});
              });
            });
          });
        };params(0);
      });});});});});});
      selectedCallee=nullptr;
    };
    if(candidates.size()==1 && resolve(c.getArgOperand(0)))compile(*candidates.begin());
    else {
      std::map<uint64_t,Function *> ordered;for(auto *fn:candidates)if(!fn->isDeclaration())ordered[functionAddress(fn)]=fn;
      auto address=fresh("i"+std::to_string(pw));rows.push_back(address+" = ptrtoint.i"+std::to_string(pw)+" "+operand(c.getArgOperand(0)));
      std::vector<uint64_t> keys;for(auto &v:ordered)keys.push_back(v.first);compareTree(address,pw,keys,[&](uint64_t k){compile(ordered.at(k));},bad);
    }
    rows.push_back("^"+bad+"():");rows.push_back("trap");rows.push_back("^"+done+"():");generalDescriptor=false;
  }
  void descriptorLegacy(CallBase &c) {
    auto &ctx = m.getContext();
    auto *u32 = Type::getInt32Ty(ctx), *u64 = Type::getInt64Ty(ctx);
    auto *ptr = PointerType::get(ctx, 0);
    auto *h = StructType::get(ctx, {u32,u32,u32,u32,ptr,ptr});
    auto *b = StructType::get(ctx, {u32,u32,ptr,u64,u64});
    auto *hl = m.getDataLayout().getStructLayout(h), *bl = m.getDataLayout().getStructLayout(b);
    std::vector<std::pair<uint64_t,std::vector<uint64_t>>> fields;
    auto domain = [&](uint64_t off, Type *t, std::vector<uint64_t> valid) {
      auto v = descriptorField(c,off,t);
      if (!v.top && v.atoms.size() == 1) return;
      if (!v.top) {
        std::vector<uint64_t> finite;
        for (auto &x : v.atoms) if (x.kind == Atom::Int &&
            std::find(valid.begin(),valid.end(),x.integer.getLimitedValue()) != valid.end()) finite.push_back(x.integer.getLimitedValue());
        valid = finite;
      }
      fields.push_back({off, valid});
    };
    auto candidates = a.candidates(c.getArgOperand(0));
    if (candidates.size() != 1) unimplemented("§7.2 production region dispatch",1,&c);
    auto *callee = *candidates.begin();
    domain(0,u32,{2}); domain(4,u32,{callee->arg_size()}); domain(12,u32,{0});
    unsigned idx = 0;
    for (auto &p : callee->args()) {
      auto off = hl->getSizeInBytes() + idx++ * bl->getSizeInBytes();
      domain(off,u32,p.getType()->isPointerTy() ? std::vector<uint64_t>{1,2,3,4} : std::vector<uint64_t>{1,2});
      domain(off+4,u32,{0,1});
    }
    if (fields.empty()) { descriptorLeaf(c); return; }
    auto id = std::to_string(dispatchBlock++), done = "dispatch" + id + "done", bad = "dispatch" + id + "bad";
    std::function<void(unsigned)> select = [&](unsigned index) {
      if (index == fields.size()) { descriptorLeaf(c); rows.push_back("br ^" + done + "()"); return; }
      auto off = fields[index].first;
      auto value = fieldOperand(c,off,u32);
      auto &keys = fields[index].second;
      std::function<void(unsigned,unsigned)> tree = [&](unsigned lo,unsigned hi) {
        if (lo == hi) { rows.push_back("br ^" + bad + "()"); return; }
        auto mid = (lo+hi)/2; auto key = keys[mid];
        auto k = operand(ConstantInt::get(u32,key)), eq = fresh("i1");
        auto leaf = "dispatch" + std::to_string(dispatchBlock++), rest = leaf + "rest";
        rows.push_back(eq + " = icmp.eq " + value + " " + k);
        rows.push_back("br " + eq + " ^" + leaf + "() ^" + rest + "()");
        rows.push_back("^" + leaf + "():");
        Atom atom; atom.kind = Atom::Int; atom.integer = APInt(32,key); AV v; v.atoms.insert(atom); selectedFields[off] = v;
        select(index+1); selectedFields.erase(off);
        rows.push_back("^" + rest + "():");
        if (hi-lo == 1) { rows.push_back("br ^" + bad + "()"); return; }
        auto lt = fresh("i1"), left = rest + "left", right = rest + "right";
        rows.push_back(lt + " = icmp.ult " + value + " " + k);
        rows.push_back("br " + lt + " ^" + left + "() ^" + right + "()");
        rows.push_back("^" + left + "():"); tree(lo,mid);
        rows.push_back("^" + right + "():"); tree(mid+1,hi);
      };
      tree(0,keys.size());
    };
    select(0); rows.push_back("^" + bad + "():"); rows.push_back("trap"); rows.push_back("^" + done + "():");
  }
  void descriptorLeaf(CallBase &c) {
    auto *desc = c.getArgOperand(2);
    auto &ctx = m.getContext();
    auto *u32 = Type::getInt32Ty(ctx), *u64 = Type::getInt64Ty(ctx);
    auto *ptr = PointerType::get(ctx, 0);
    auto *h = StructType::get(ctx, {u32, u32, u32, u32, ptr, ptr});
    auto *b = StructType::get(ctx, {u32, u32, ptr, u64, u64});
    auto &dl = m.getDataLayout();
    auto *hl = dl.getStructLayout(h), *bl = dl.getStructLayout(b);
    auto field = [&](uint64_t off, Type *t) {
      return selectedFields.count(off) ? selectedFields.at(off) : descriptorField(c, off, t);
    };
    if (integer(field(0, u32), &c) != 2 || integer(field(12, u32), &c) != 0)
      fail("T-IFACE", "§8.1 descriptor header", &c);
    auto ndev = integer(field(8, u32), &c);
    auto candidates = a.candidates(c.getArgOperand(0));
    auto *callee = selectedCallee ? selectedCallee : *candidates.begin();
    if (integer(field(4, u32), &c) != callee->arg_size())
      fail("T-IFACE", "§8.2 descriptor arity", &c);
    auto target = field(hl->getElementOffset(4), ptr),
         fault = field(hl->getElementOffset(5), ptr);
    if (!compilingInplace && qwidth(fault, &c) != 4)
      fail("T-SIZE", "§8.2 fault width", &c);
    bool discard = !target.top && target.atoms.size() == 1 &&
                   target.atoms.begin()->kind == Atom::Int &&
                   target.atoms.begin()->integer.isZero();
    std::vector<std::string> ins, args, mems;
    AV output = target;
    std::vector<AV> outputs;
    if (!discard) outputs.push_back(target);
    bool bufferOutput = false;
    std::string current;
    unsigned index = 0;
    for (Argument &p : callee->args()) {
      auto off = hl->getSizeInBytes() + index++ * bl->getSizeInBytes();
      auto kind = integer(field(off, u32), &c),
           mode = integer(field(off + bl->getElementOffset(1), u32), &c);
      if (!current.empty())
        current += ",";
      if (kind == 1 && mode <= 1) {
        auto q = field(off + bl->getElementOffset(2), ptr);
        current += "IN(" + std::to_string(qwidth(q, &c)) + "," +
                   (mode ? "sext" : "zext") + ")";
        ins.push_back(handle(q, &c));
      } else if (kind == 2) {
        auto w = width(p.getType());
        auto low = field(off + bl->getElementOffset(3), u64), high = field(off + bl->getElementOffset(4), u64);
        auto singleton = [](AV v) { return !v.top && v.atoms.size()==1 && v.atoms.begin()->kind==Atom::Int; };
        std::string n;
        if (singleton(low) && singleton(high)) {
          APInt val = APInt(128,integer(low,&c)) | (APInt(128,integer(high,&c)) << 64);
          n = fresh("i" + std::to_string(w));
          rows.push_back(n + " = const.i" + std::to_string(w) + " " + decimal(val.zextOrTrunc(w)));
        } else {
          auto cast = [&](std::string x, unsigned from) {
            if (w == from) return x;
            auto d = fresh("i" + std::to_string(w));
            rows.push_back(d + (w < from ? " = trunc.i" : " = zext.i") + std::to_string(w) + " " + x); return d;
          };
          auto part = [&](AV v, uint64_t offset) { return singleton(v) ? operand(ConstantInt::get(u64,integer(v,&c))) : fieldOperand(c,offset,u64); };
          n = cast(part(low,off+bl->getElementOffset(3)),64);
          if (w > 64) {
            auto hi = cast(part(high,off+bl->getElementOffset(4)),64);
            auto shift = operand(ConstantInt::get(IntegerType::get(ctx,w),64)), bits = fresh("i"+std::to_string(w)), combined = fresh("i"+std::to_string(w));
            rows.push_back(bits + " = shl " + hi + " " + shift); rows.push_back(combined + " = or " + n + " " + bits); n = combined;
          }
        }
        args.push_back(n);
        current += "ARG(" + std::to_string(w) + ")";
      } else if (kind == 3 || kind == 4) {
        if (!p.getType()->isPointerTy() || mode)
          fail("T-IFACE", "§8.2 memory binding carrier/mode", &c);
        auto q = field(off + bl->getElementOffset(2), ptr);
        auto size = integer(field(off + bl->getElementOffset(4), u64), &c);
        if (!size || size > UINT64_MAX / 8 || qwidth(q, &c) != size * 8)
          fail("T-SIZE", "§8.2 memory binding width", &c);
        if (kind == 3) {
          if (!isPowerOf2_64(size)) fail("T-SIZE", "§8.2 MEM_IN power of two", &c);
          current += "MEM_IN(" + std::to_string(size) + ")";
          mems.push_back(handle(q, &c));
        } else {
          current += "OUT(" + std::to_string(size) + ")";
          outputs.push_back(q);
          output = q; bufferOutput = true;
        }
      } else
        fail("T-IFACE", "§8.2 oracle binding kind", &c);
    }
    std::vector<std::string> deviceMems;
    std::set<uint64_t> models;
    for (unsigned j = 0; j < ndev; ++j) {
      auto off = hl->getSizeInBytes() + index * bl->getSizeInBytes() + j * 24;
      auto model = integer(field(off, u32), &c);
      if (!models.insert(model).second || integer(field(off + 4, u32), &c))
        fail("T-IFACE", "§8.3 duplicate model or device mode", &c);
      auto q = field(off + 8, ptr);
      auto clock=field(off+16,u64);
      auto value = model==3 && singletonInt(clock) ? integer(clock,&c) : 0;
      auto separator = j ? std::string("+") : std::string(";dev=");
      if (model == 3) {
        if(singletonInt(clock))current += separator + "CLOCK(" + std::to_string(value) + ")";
        else { current += separator + "CLOCK_ARG(0)"; args.insert(args.begin(),fieldOperand(c,off+16,u64)); }
      }
      else if (model == 2 || model == 1) {
        auto w = qwidth(q, &c), bytes = w / 8;
        auto unit = model == 2 ? 512 : 1;
        if (w % 8 || bytes < unit || !isPowerOf2_64(bytes / unit))
          fail("T-SIZE", "§8.3 device input extent", &c);
        current += separator + (model == 2 ? "BLOCK(" : "ENTROPY(") +
                   std::to_string(Log2_64(bytes / unit)) + ")";
        deviceMems.push_back(handle(q, &c));
      } else if (model == 4) {
        bool null = !q.top && q.atoms.size()==1 && q.atoms.begin()->kind==Atom::Int && q.atoms.begin()->integer.isZero();
        auto w = null ? 0 : qwidth(q, &c);
        if (w % 8) fail("T-SIZE", "§8.3 console width", &c);
        current += separator + "CONSOLE(" + std::to_string(w / 8) + ")";
        if (!null) { outputs.push_back(q); output = q; bufferOutput = true; }
      } else fail("T-IFACE", "§8.3 unknown device model", &c);
    }
    mems.insert(mems.begin(),deviceMems.begin(),deviceMems.end());
    struct Slice { AV output; unsigned lo, width; };
    std::vector<Slice> slices;
    for (auto &o : outputs) { auto w=qwidth(o,&c); for (unsigned lo=0;lo<w;lo+=128) slices.push_back({o,lo,std::min(128u,w-lo)}); }
    bool multi = slices.size()>1;
    current += ";tgt=" + ((multi ? discard : discard && !bufferOutput) ? std::string("null")
                                  : std::to_string(qwidth(multi ? target : output, &c)));
    discard = discard && !bufferOutput;
    // Null selects the resolved default. Explicit records use the published
    // four i64 fields + fault handle; all-ones means table/default lookup.
    auto baseline = table.baseline(*callee);
    std::vector<uint64_t> budget = baseline, explicitFields(5, UINT64_MAX);
    if (!isa<ConstantPointerNull>(c.getArgOperand(1))) {
      auto *bp = c.getArgOperand(1);
      for (unsigned i = 0; i < 4; ++i) {
        auto n = integer(a.readAt(c, bp, 8 * i, u64), &c);
        explicitFields[i] = n;
        if (n != UINT64_MAX) budget[i] = n;
      }
    }
    for (int projection = multi ? int(slices.size())-1 : -1; projection >= (multi ? 0 : -1); --projection) {
    budget = baseline;
    for (unsigned i=0;i<5;++i) if (explicitFields[i]!=UINT64_MAX) budget[i]=explicitFields[i];
    std::string refName = "ref";
    ValueToValueMapTy vm;
    auto clone = CloneModule(m, vm);
    auto *cf = cast<Function>(vm[callee]);
    cf=normaliseWideABI(*clone,cf);
    normaliseScalar(*cf);
    auto path = out + "/oracle-" + std::to_string(references.size());
    auto capacities = table.capacities;
    std::map<std::string,std::string> globalNames;
    lowerScalar(*clone, *cf, current, path, capacities[2], capacities[1], projection, &globalNames, baseline[4], automaticSnapshot?snapshotExponent:0);
    auto candidate = read(path + "/ref.bennett");
    auto selection = oracleIdentity(candidate);
    table.overlay(budget, selection);
    for (unsigned i = 0; i < 5; ++i)
      if (explicitFields[i] != UINT64_MAX) budget[i] = explicitFields[i];
    // §9.2: one overlay, then a fresh generation under the SAME capacities.
    // Never reuse the provisional module: N24/runtime materialisation mutates it.
    if (budget[4] != baseline[4]) {
      ValueToValueMapTy finalMap;
      auto finalModule = CloneModule(m, finalMap);
      auto *finalFunction = cast<Function>(finalMap[callee]);
      finalFunction=normaliseWideABI(*finalModule,finalFunction);
      normaliseScalar(*finalFunction);
      globalNames.clear();
      lowerScalar(*finalModule, *finalFunction, current, path, capacities[2],
                  capacities[1], projection, &globalNames, budget[4], automaticSnapshot?snapshotExponent:0);
      candidate = read(path + "/ref.bennett");
    }
    if (table.enabled) resolvedShapes.push_back(json::Object{
      {"region_key", regionKey(callee)}, {"symbol", callee->getName()}, {"shape", current},
      {"selection_identity", selection}, {"identity", oracleIdentity(candidate)},
      {"baseline", tuple(baseline)}, {"resolved", tuple(budget)}});
    unsigned ri = 0;
    while (ri < references.size() && (references[ri] != candidate || referenceGlobals[ri] != globalNames)) ++ri;
    if (ri == references.size()) { references.push_back(candidate); referenceGlobals.push_back(globalNames); }
    else sys::fs::remove_directories(path);
    if (ri) refName += std::to_string(ri);
    if (reference.empty()) { reference = candidate; shape = current; refPath = path; }
    // Tokens are minted by the host, positional launch parameters per ISA §10.
    std::string tk = "tk" + std::to_string(budgets.size());
    params.push_back(tk + ":token");
    paramTypes.push_back("token");
    budgets.push_back(json::Object{{"token", tk},
                                   {"selection_identity", selection},
                                   {"steps", std::to_string(budget[0])},
                                   {"heap", std::to_string(budget[1])},
                                   {"stack", std::to_string(budget[2])},
                                   {"depth", std::to_string(budget[3])},
                                   {"sstack", std::to_string(budget[4])}});
    if (refName != "ref") budgets.back()["region"] = refName;
    std::string tgt, faultRegister = compilingInplace ? inplaceFault : handle(fault,&c);
    if (multi) {
      auto &slice = slices[projection];
      if (projection) {
        tgt = fresh("qreg["+std::to_string(slice.width)+"]");
        rows.push_back(tgt+" = qreg.new any "+std::to_string(slice.width));
        faultRegister=fresh("qreg[4]");rows.push_back(faultRegister+" = qreg.new any 4");
      } else { tgt=fresh("qreg["+std::to_string(slice.width)+"]"); rows.push_back(tgt+" = qreg.slice "+handle(slice.output,&c)+" "+std::to_string(slice.lo)+" "+std::to_string(slice.width)); }
    } else if (discard) {
      tgt = fresh("qreg[1]"); rows.push_back(tgt + " = qreg.new any 1");
    } else tgt = compilingInplace ? inplaceTarget : handle(output, &c);
    std::string snapshotData,snapshotQ;
    auto callMems=mems;
    if(automaticSnapshot){snapshotData=buildSnapshot();snapshotQ=prepareSnapshot(snapshotData);callMems.insert(callMems.begin(),snapshotQ);}
    auto call = "oracle_call @" + refName + " " + tk + " (" + join(ins) + ") " + tgt + " " + faultRegister + " (" + join(callMems) + ") (" + join(args) + ")";
    rows.push_back(call);
    if (multi && projection) {
      auto &slice=slices[projection];auto view=fresh("qreg["+std::to_string(slice.width)+"]");
      rows.push_back(view+" = qreg.slice "+handle(slice.output,&c)+" "+std::to_string(slice.lo)+" "+std::to_string(slice.width));
      auto w=std::to_string(slice.width);
      auto xorAction=action("d:wire["+w+"] mut","s:wire["+w+"] in",w,w,"qxor s d");
      rows.push_back("action_call @"+xorAction+" ("+view+") ("+tgt+") () ()");rows.push_back(call);
      rows.push_back("qreg.free "+faultRegister);rows.push_back("qreg.free "+tgt);
    } else if (discard) rows.push_back("qreg.free " + tgt);
    if(automaticSnapshot)releaseSnapshot(snapshotQ,snapshotData);
    }
  }
  void verifyInverse(unsigned forward, unsigned inverse, unsigned bits, CallBase &at) {
    auto key=hash(references.at(forward)+references.at(inverse));
    auto checkBudget=[&](uint64_t stepsMinimum,uint64_t stackMinimum) {
      for(unsigned i=budgets.size()-2;i<budgets.size();++i) {
        auto &b=budgets[i];uint64_t steps,cells,depth;
        b.getString("steps")->getAsInteger(10,steps);b.getString("stack")->getAsInteger(10,cells);b.getString("depth")->getAsInteger(10,depth);
        if(steps<stepsMinimum || cells<stackMinimum || depth<1)fail("BD-E-INPLACE-NOT-INVERSE","§8.7 budget below exhaustive B_min",&at);
      }
    };
    if(verifiedPairs.count(key)) { auto minima=verifiedPairs.at(key);checkBudget(minima.first,minima.second);return; }
    if(bits>24)unimplemented("§8.7 sampled inverse evidence and sound universal budget bound",1,&at);
    for(auto i:{forward,inverse}) {
      auto object=StringRef(references.at(i));auto body=object.split("lproc @L1").second;
      if(object.contains("lift.alloc") || object.contains("lift.load") || object.contains("lift.store") || body.contains("lift.call"))
        unimplemented("§8.7 general inverse reference budget verification",1,&at);
    }
    const char *configured=std::getenv("BENNETT_ISA_REF");
    auto tool=sys::findProgramByName(configured ? configured : "bennett-isa-ref");
    if(!tool)fail("input","§8.7 requires bennett-isa-ref (or BENNETT_ISA_REF)",&at);
    auto output=out+"/inplace-reference.json";
    uint64_t maxSteps=0,minStack=0;
    auto evaluate=[&](unsigned ref,uint64_t x,uint64_t cells) {
      auto path=out+"/oracle-"+std::to_string(ref)+"/ref.bennett";
      auto text=std::to_string(x),budget="18446744073709551615,0,"+std::to_string(cells)+",1";
      SmallVector<StringRef> args{*tool,"run-oracle",path,"ref","--input",text,"--budget",budget};
      std::optional<StringRef> redirects[]={StringRef(),StringRef(output),StringRef()};
      sys::fs::remove(output);
      std::string error;auto status=sys::ExecuteAndWait(*tool,args,std::nullopt,redirects,0,0,&error);
      if(status)fail("output","§8.7 reference interpreter failed: "+error,&at);
      return parse(read(output));
    };
    for(auto ref:{forward,inverse}) {
      auto layout=parse(objectSectionsForInverse(references.at(ref)));
      uint64_t capacity=uint64_t(1)<<*layout.getAsObject()->getInteger("S_cells");
      // One direct lproc has one fixed frame shape on every input (§3.7).
      // With no memory or nested calls, heap minimum is zero and depth one.
      uint64_t lo=0,hi=capacity;
      while(lo<hi) {auto mid=(lo+hi)/2;auto v=evaluate(ref,0,mid);if(v.getAsObject()->getInteger("code")==0)hi=mid;else lo=mid+1;}
      minStack=std::max(minStack,lo);
    }
    uint64_t count=uint64_t(1)<<bits;
    for(uint64_t x=0;x<count;++x) {
      auto y=evaluate(forward,x,minStack);auto *yo=y.getAsObject();auto payload=yo->getInteger("payload");
      if(yo->getInteger("code")!=0 || !payload)fail("BD-E-INPLACE-NOT-INVERSE","§8.7 forward fault",&at);
      auto z=evaluate(inverse,*payload,minStack);auto *zo=z.getAsObject();
      if(zo->getInteger("code")!=0 || zo->getInteger("payload")!=int64_t(x))fail("BD-E-INPLACE-NOT-INVERSE","§8.7 inverse mismatch",&at);
      maxSteps=std::max({maxSteps,uint64_t(*yo->getInteger("steps")),uint64_t(*zo->getInteger("steps"))});
    }
    checkBudget(maxSteps,minStack);
    inplaceEvidence.push_back(json::Object{{"kind","exhaustive"},{"bits",bits},{"inputs",int64_t(count)},
      {"forward",hash(references.at(forward))},{"inverse",hash(references.at(inverse))},
      {"B_min",json::Object{{"steps",int64_t(maxSteps)},{"heap",0},{"stack",int64_t(minStack)},{"depth",1}}},
      {"interpreter_sha256",hash(read(*tool))},{"checked_executable_claim",false}});
    verifiedPairs[key]={maxSteps,minStack};write(out+"/inplace-evidence.json",jcs(json::Value(parse(jcs(json::Value(std::move(inplaceEvidence))))))+"\n");
    // Keep the evidence array available for another pair in this entry.
    auto evidence=parse(read(out+"/inplace-evidence.json"));inplaceEvidence=std::move(*evidence.getAsArray());
    sys::fs::remove(output);
  }
  std::string objectSectionsForInverse(StringRef object) {
    return object.split("section layout\n").second.split('\n').first.str();
  }
  void inplace(CallBase &c) {
    auto &ctx=m.getContext();auto *u32=Type::getInt32Ty(ctx);auto *ptr=PointerType::get(ctx,0);
    auto *desc=c.getArgOperand(3);
    auto header=a.readAt(c,desc,0,u32),flags=a.readAt(c,desc,12,u32),np=a.readAt(c,desc,4,u32);
    if(integer(header,&c)!=2 || integer(flags,&c)!=0)fail("T-IFACE","§8.7 descriptor header",&c);
    auto target=a.readAt(c,desc,16,ptr);
    if(target.top || target.atoms.size()!=1 || target.atoms.begin()->kind!=Atom::Int || !target.atoms.begin()->integer.isZero())fail("T-IFACE","§8.7 target must be null",&c);
    if(integer(np,&c)!=1 || integer(a.readAt(c,desc,8,u32),&c)!=0 || integer(a.readAt(c,desc,32,u32),&c)!=5)
      unimplemented("§8.7 general INOUT parameter and device bindings",1,&c);
    auto q=a.readAt(c,desc,40,ptr);auto w=qwidth(q,&c);auto x=handle(q,&c);
    auto t=fresh("qreg["+std::to_string(w)+"]"),fr=fresh("qreg[4]");
    rows.push_back(t+" = qreg.new any "+std::to_string(w));rows.push_back(fr+" = qreg.new any 4");
    auto oracle=m.getOrInsertFunction("__bennett_oracle",FunctionType::get(Type::getVoidTy(ctx),{ptr,ptr,ptr},false));
    Atom kind;kind.kind=Atom::Int;kind.integer=APInt(32,1);AV in;in.atoms.insert(kind);
    selectedFields[32]=in;selectedFields[16]=q;
    compilingInplace=true;inplaceTarget=t;inplaceFault=fr;
    unsigned refs[2];
    for(unsigned i=0;i<2;++i) {
      auto *call=CallInst::Create(oracle,{c.getArgOperand(i),c.getArgOperand(2),desc},"",&c);
      auto before=budgets.size();descriptorLeaf(*call);
      auto region=budgets.at(before).getString("region").value_or("ref");
      refs[i]=region=="ref"?0:std::stoul(region.drop_front(3).str());call->eraseFromParent();
      if(!i) {
        auto width=std::to_string(w);auto swap=action("x:wire["+width+"] mut, t:wire["+width+"] mut","",width+","+width,"","qexch x t");
        rows.push_back("action_call @"+swap+" ("+x+", "+t+") () () ()");
      }
    }
    compilingInplace=false;selectedFields.clear();
    verifyInverse(refs[0],refs[1],w,c);
    rows.push_back("qreg.free "+fr);rows.push_back("qreg.free "+t);
  }
  std::string action(std::string mut, std::string in, std::string widths,
                     std::string inWidths, std::string ops) {
    auto n = "M" + std::to_string(actions.size());
    std::string sig = "{\"abi\":\"0.8\",\"args\":[],\"bounds\":[],\"in\":[" +
                      inWidths + "],\"kind\":\"action\",\"mem\":[],\"mut\":[" +
                      widths + "],\"tier\":\"q\"}";
    actions[n] = {sig, "action @" + n + " (" + mut + ") (" + in +
                           ") () () ()\n^entry():\n" + ops};
    return n;
  }
  void gate(CallBase &c) {
    auto measurement = c.getCalledFunction()->getName() == "__bennett_measure";
    auto *v = c.getArgOperand(measurement ? 0 : 1);
    auto result = measurement && tagged(a.get(v)) ? fresh("i1") : "";
    withHandle(v, [&](std::string q) { gateOn(c,q); }, false, result, &c);
    if(!result.empty())names[&c]=result;
  }
  void gateOn(CallBase &c, std::string src) {
    auto n = c.getCalledFunction()->getName();
    bool measurement = n == "__bennett_measure";
    auto q = a.get(c.getArgOperand(measurement ? 0 : 1));
    auto w = qwidth(q, &c);
    auto i = integer(a.get(c.getArgOperand(measurement ? 1 : 2)), &c);
    if (i >= w)
      fail("T-INDEX", "§18.3 gate/measurement index", &c);
    if (measurement) {
      auto name =
          action("d:wire[1] mut", "s:wire[" + std::to_string(w) + "] in", "1",
                 std::to_string(w), "cx s[" + std::to_string(i) + "] d[0]");
      auto copy = fresh("qreg[1]");
      rows.push_back(copy + " = qreg.new any 1");
      rows.push_back("action_call @" + name + " (" + copy + ") (" + src +
                     ") () ()");
      auto value = fresh("i1");
      names[&c] = value;
      rows.push_back(value + " = measure " + copy);
    } else {
      static const char *ops[] = {"", "x", "h", "s", "sdg", "t", "tdg"};
      auto op = integer(a.get(c.getArgOperand(0)), &c);
      std::string wire = "s[" + std::to_string(i) + "]", row;
      if (op >= 1 && op <= 6)
        row = std::string(ops[op]) + " " + wire;
      else if (op == 7)
        row = "s " + wire + "\ns " + wire;
      else if (op == 8)
        row = "sdg " + wire + "\nx " + wire + "\ns " + wire;
      else
        fail("T-OP", "§3.4 gate opcode", &c);
      auto name = action("s:wire[" + std::to_string(w) + "] mut", "",
                         std::to_string(w), "", row);
      rows.push_back("action_call @" + name + " (" + src + ") () () ()");
    }
  }
#include "runtime/CallerSnapshot.inc"
  void lower() {
    setupSnapshot();
    // Descriptor memory has no device representation: its fields are virtual
    // operands. Elide only local storage whose complete use closure is records.
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (c->getCalledFunction() &&
            (c->getCalledFunction()->getName() == "__bennett_oracle" || c->getCalledFunction()->getName() == "__bennett_inplace")) {
          bool ip=c->getCalledFunction()->getName()=="__bennett_inplace";
          descriptorObjects.insert(getUnderlyingObject(c->getArgOperand(ip?3:2)));
          for(auto &base:a.get(c->getArgOperand(ip?3:2)).atoms)if(base.kind==Atom::Ptr && base.object)descriptorObjects.insert(base.object);
          if (!isa<ConstantPointerNull>(c->getArgOperand(ip?2:1)))
            descriptorObjects.insert(getUnderlyingObject(c->getArgOperand(ip?2:1)));
        }
    // Preserve elision for straight-line record-only descriptors. Once an
    // address escapes that proof, lower the storage and all its ordinary uses.
    for (Instruction &i : instructions(f)) {
      if (auto *c = dyn_cast<CallBase>(&i); c && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_oracle") {
        auto base=a.get(c->getArgOperand(2));
        if(base.top || base.atoms.size()!=1 || !isa<AllocaInst>(getUnderlyingObject(c->getArgOperand(2))))memoryDescriptors=true;
        for(auto &x:base.atoms) for(auto &j:instructions(f))
          if(auto *st=dyn_cast<StoreInst>(&j); st && st->getParent()!=c->getParent())
            for(auto &d:a.get(st->getPointerOperand()).atoms)if(d.object==x.object)memoryDescriptors=true;
      }
      if (auto *ld=dyn_cast<LoadInst>(&i); ld && descriptorObjects.count(getUnderlyingObject(ld->getPointerOperand())))memoryDescriptors=true;
    }
    std::set<const Value *> visited;
    std::function<void(const Value *)> validate = [&](const Value *v) {
      if (!visited.insert(v).second)
        return;
      for (const User *u : v->users()) {
        if (isa<GetElementPtrInst>(u) || isa<BitCastInst>(u)) {
          validate(u);
          continue;
        }
        if (auto *s = dyn_cast<StoreInst>(u); s && s->getPointerOperand() == v)
          continue;
        if (auto *c = dyn_cast<CallBase>(u))
          if (auto *g = c->getCalledFunction();
              g && (g->getName() == "__bennett_oracle" || g->getName() == "__bennett_inplace" ||
                    g->getName().starts_with("llvm.lifetime.") ||
                    g->getName().starts_with("llvm.memset.")))
            continue;
        unimplemented("§8.1 escaping descriptor storage", 1, u);
      }
    };
    if (!memoryDescriptors) for (auto *v : descriptorObjects) validate(v);
    // Acyclic entry-local files have one physical instance per allocation
    // site. General N(s), recursive environments and surviving-entry files
    // require the interprocedural bound/table implementation, never slot reuse.
    std::set<const Value *> memoryRoots;
    for (Instruction &i : instructions(f)) if (auto *st = dyn_cast<StoreInst>(&i))
      if (memoryDescriptors || !descriptorObjects.count(getUnderlyingObject(st->getPointerOperand())))
        for (auto &x : a.get(st->getValueOperand()).atoms) if (x.kind == Atom::Root) memoryRoots.insert(x.object);
    for(Instruction &i:instructions(f)) if(isa<SelectInst>(i) || isa<PHINode>(i)) {
      bool descriptorUse=i.getName().starts_with("width.handle");
      for(auto *u:i.users())if(auto *st=dyn_cast<StoreInst>(u))descriptorUse |= descriptorObjects.count(getUnderlyingObject(st->getPointerOperand()));
      auto v=a.get(&i); if(descriptorUse && v.roots())for(auto &x:v.atoms)if(x.kind==Atom::Root)memoryRoots.insert(x.object);
    }
    bool enlarged=true;
    while(enlarged) {
      enlarged=false;
      for(Instruction &i:instructions(f)) {
        auto v=a.get(&i);bool shares=false;
        for(auto &x:v.atoms) if(x.kind==Atom::Root && memoryRoots.count(x.object)) shares=true;
        if(shares) for(auto &x:v.atoms) if(x.kind==Atom::Root) enlarged |= memoryRoots.insert(x.object).second;
      }
    }
    if (!memoryRoots.empty()) {
      for (Instruction &i : instructions(f)) {
        if (auto *st = dyn_cast<StoreInst>(&i); st && a.get(st->getValueOperand()).roots() &&
            !isa<AllocaInst>(getUnderlyingObject(st->getPointerOperand())) &&
            !descriptorObjects.count(getUnderlyingObject(st->getPointerOperand())))
          unimplemented("§6.5 persistent static-file tag allocator",1,st);
        if (auto *r = dyn_cast<ReturnInst>(&i); r && r->getReturnValue() && a.get(r->getReturnValue()).roots())
          unimplemented("§6.5 static-file result environment",1,r);
      }
      std::set<const BasicBlock *> visiting, visited;
      for(auto *root:memoryRoots)if(auto *site=dyn_cast<Instruction>(root)) {
        visiting.clear();visited.clear();
        std::function<bool(const BasicBlock *)> returns=[&](const BasicBlock *block){
          if(!visited.insert(block).second)return false;
          for(auto *to:successors(block))if(to==site->getParent() || returns(to))return true;
          return false;
        };
        if(returns(site->getParent()))unimplemented("§6.5 cyclic static-file instance bound",3,site);
      }
      for (Instruction &i : instructions(f)) if (memoryRoots.count(&i)) {
        auto *r = &i;
        auto *call = dyn_cast<CallBase>(r);
        if (!call || call->getFunction() != &f) unimplemented("§6.5 interprocedural static-file environment",1,r);
        auto w = qwidth(a.get(r),r);
        files[r] = {fresh("qreg[" + std::to_string(w) + "]"), fresh("ptr"), unsigned(fileOrder.size()+1)};
        fileOrder.push_back(r);
      }
    }
    for (Argument &p : f.args()) {
      if(p.getType()->isAggregateType()) {
        std::vector<std::string> ns;unsigned k=0;
        for(auto &field:fields(p.getType())) {
          auto n="a"+std::to_string(p.getArgNo())+"_"+std::to_string(k++),t=fieldType(field.type);
          ns.push_back(n);params.push_back(n+":"+t);paramTypes.push_back(t);
        }
        tuples[&p]=ns;
      } else {
        auto n="a"+std::to_string(p.getArgNo()),t=type(&p);
        names[&p]=n;params.push_back(n+":"+t);paramTypes.push_back(t);
      }
    }
    if (!f.getReturnType()->isVoidTy()) {
      unsigned k=0;
      for(auto &field:fields(f.getReturnType())) {
        auto t=fieldType(field.type);
        results.push_back("result"+(f.getReturnType()->isAggregateType()?std::to_string(k++):"")+":"+t);
        resultTypes.push_back(t);
      }
    }
    unsigned bn = 0;
    for (BasicBlock &bb : f)
      blocks[&bb] = "b" + std::to_string(bn++);
    for (BasicBlock &bb : f)
      for (PHINode &p : bb.phis()) destinations(&p);
    auto edge = [&](BasicBlock *to, BasicBlock *from) {
      std::vector<std::string> values;
      for (PHINode &p : to->phis()) {auto vs=operands(p.getIncomingValueForBlock(from));values.insert(values.end(),vs.begin(),vs.end());}
      return "^" + blocks[to] + ("(" + join(values) + ")");
    };
    // Linked/LTO block order need not place dominators before uses. Preserve
    // the established order elsewhere; visit new allocator CFGs in RPO.
    std::vector<BasicBlock *> order;
    if(f.hasFnAttribute("bennett.cc.allocator") || (ccNames && ccNames->size()>1)) {
      for(auto *bb:ReversePostOrderTraversal<Function *>(&f))order.push_back(bb);
      for(auto &bb:f)if(!is_contained(order,&bb))order.push_back(&bb);
    } else for(auto &bb:f)order.push_back(&bb);
    for (auto *block : order) {
      auto &bb=*block;
      std::vector<std::string> bindings;
      for (PHINode &p : bb.phis()) {
        auto ns=operands(&p);auto fs=fields(p.getType());
        for(unsigned k=0;k<ns.size();++k)bindings.push_back(ns[k]+":"+(p.getType()->isAggregateType()?fieldType(fs[k].type):type(&p)));
      }
      rows.push_back("^" + blocks[&bb] + "(" + join(bindings) + "):");
      ordinal = 0;
      if (&bb == &f.getEntryBlock()) for (auto *site : fileOrder) {
        auto zero = operand(ConstantInt::get(m.getDataLayout().getIntPtrType(m.getContext()),0));
        auto size = operand(ConstantInt::get(Type::getInt64Ty(m.getContext()),m.getDataLayout().getPointerSize()));
        auto p = files.at(site).tag; rows.push_back(p + " = alloc " + size); localMemory.push_back(p); allocatedBytes+=m.getDataLayout().getPointerSize();recordAllocation(p,size);
        rows.push_back("store.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + p + " " + zero);
      }
      for (Instruction &i : bb) {
        bool record = false;
        if (auto *g = dyn_cast<GetElementPtrInst>(&i))
          record = descriptorObjects.count(getUnderlyingObject(g));
        if (auto *s = dyn_cast<StoreInst>(&i))
          record = descriptorObjects.count(
              getUnderlyingObject(s->getPointerOperand()));
        if (auto *al = dyn_cast<AllocaInst>(&i))
          record = descriptorObjects.count(al);
        if ((!memoryDescriptors && record) || isa<PHINode>(i))
          continue;
        if(rTier && !isa<DbgInfoIntrinsic>(i)) {
          auto *call=dyn_cast<CallBase>(&i);auto *target=call?call->getCalledFunction():nullptr;
          if(!target || (!target->getName().starts_with("llvm.dbg.") && !target->getName().starts_with("llvm.lifetime.") && !target->getName().starts_with("__bennett_nz_rstep")))countRStep();
        }
        if (auto *c = dyn_cast<CallBase>(&i)) {
          auto *g = resolve(c->getCalledOperand());
          if(!g && ccNames && !c->isInlineAsm()) {
            auto pointer=operand(c->getCalledOperand());auto pw=m.getDataLayout().getPointerSizeInBits();
            auto value=emit("i"+std::to_string(pw),"ptrtoint.i"+std::to_string(pw)+" "+pointer);
            std::map<uint64_t,Function *> candidates;std::vector<uint64_t> keys;
            for(auto *candidate:a.candidates(c->getCalledOperand(),c->getFunctionType()))
              if(ccNames->count(candidate))candidates[functionAddress(candidate)]=candidate;
            for(auto &candidate:candidates)keys.push_back(candidate.first);
            std::vector<std::string> args;for(auto &arg:c->args()) {auto vs=operands(arg);args.insert(args.end(),vs.begin(),vs.end());}
            auto result=c->getType()->isVoidTy()?std::vector<std::string>{}:destinations(c);
            auto id=std::to_string(dispatchBlock++),done="call"+id+"done",bad="call"+id+"bad";
            compareTree(value,pw,keys,[&](uint64_t key) {
              auto call="call @"+ccNames->at(candidates.at(key))+(args.empty()?"":" "+join(args," "));
              std::vector<std::string> values;
              if(!c->getType()->isVoidTy())for(auto &field:fields(c->getType()))values.push_back(fresh(fieldType(field.type)));
              rows.push_back((values.empty()?"":(values.size()==1?values[0]:"("+join(values)+")")+" = ")+call);
              propagateExit();rows.push_back("br ^"+done+"("+join(values)+")");
            },bad);
            rows.push_back("^"+bad+"():");rows.push_back("trap");
            std::vector<std::string> bindings;
            if(!result.empty()) {auto fs=fields(c->getType());for(unsigned k=0;k<result.size();++k)bindings.push_back(result[k]+":"+fieldType(fs[k].type));}
            rows.push_back("^"+done+"("+join(bindings)+"):");usesCCCalls=true;continue;
          }
          if (!g)
            unimplemented("§17.4 indirect CC call", 1, c);
          auto n = g->getName();
          if (n.starts_with("llvm.lifetime.") ||
              (!memoryDescriptors && n.starts_with("llvm.memset.") &&
               descriptorObjects.count(
                   getUnderlyingObject(c->getArgOperand(0)))))
            continue;
          if(rTier && n.starts_with("__bennett_effect_")) {
            auto suffix=n.drop_front(StringRef("__bennett_effect_").size());auto parts=suffix.split('_');
            effectModels.insert(parts.first.str());std::vector<std::string> args;
            for(auto &v:c->args())args.push_back(operand(v));
            rows.push_back("effect "+parts.first.str()+"."+parts.second.str()+" "+join(args," "));continue;
          }
          if (n == "__bennett_nz_fault") {
            if(auto *asmMD=c->getMetadata("bennett.asm")) {
              std::string block;unsigned ordinal=0;
              for(auto &row:rows)if(StringRef(row).starts_with("^")) {block=StringRef(row).drop_front().split('(').first.str();ordinal=0;}else ++ordinal;
              asmPoints.push_back(json::Object{{"symbol",ccNames->at(&f)},{"block",block},{"ordinal",ordinal},
                {"reason",cast<MDString>(asmMD->getOperand(0))->getString()}});
            }
            // Newly materialised allocator closures report the explicit code
            // through §11.5 before trapping. The payload is private storage,
            // not an extra logical heap allocation on a failing path.
            if (!rTier && f.hasFnAttribute("bennett.cc.allocator")) {
              allocatorFaultService = true;
              auto *payload = m.getGlobalVariable("__bennett_cc_fault_payload",true);
              if (!payload) payload = new GlobalVariable(m,Type::getInt64Ty(m.getContext()),false,
                  GlobalValue::InternalLinkage,ConstantInt::get(Type::getInt64Ty(m.getContext()),0),"__bennett_cc_fault_payload");
              auto p=operand(payload),code=operand(c->getArgOperand(0));
              rows.push_back("store.i64 "+p+" "+code);
              emit("i"+std::to_string(m.getDataLayout().getPointerSizeInBits()),"hostcall bennett.fault "+p+" "+number(8));
            }
            rows.push_back("trap"); break;
          }
          if (n == "llvm.trap") { rows.push_back("trap"); break; }
          if (n == "__bennett_qalloc" || n == "__bennett_qborrow") {
            auto cls = integer(a.get(c->getArgOperand(0)), c),
                 w = integer(a.get(c->getArgOperand(1)), c);
            if (cls)
              unimplemented("§3.4 configured register class", 1, c);
            auto q = files.count(c) ? files.at(c).q : fresh("qreg[" + std::to_string(w) + "]");
            if (files.count(c)) {
              // No site is executed twice in this acyclic entry-local file.
              // Distinct nonzero identities are stable across stores and loads;
              // free retires the live tag before any later use can match it.
              auto tag = fresh("i" + std::to_string(m.getDataLayout().getPointerSizeInBits()));
              rows.push_back(tag + " = const.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + std::to_string(files.at(c).identity));
              names[c] = tag;
              rows.push_back("store.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + files.at(c).tag + " " + tag);
            } else names[c] = q;
            rows.push_back(q + " = qreg.new any " + std::to_string(w));
          } else if (n == "__bennett_qfree")
            withHandle(c->getArgOperand(0), [&](std::string q) { rows.push_back("qreg.free " + q); }, true);
          else if (n == "__bennett_oracle")
            descriptor(*c);
          else if (n == "__bennett_inplace")
            inplace(*c);
          else if (n == "__bennett_gate" || n == "__bennett_measure")
            gate(*c);
          else if(n=="__bennett_nz_alloc") {
            auto size=operand(c->getArgOperand(0));auto p=fresh("ptr");rows.push_back(p+" = alloc "+size);names[c]=p;recordAllocation(p,size);ccHeapBytes=table.capacities[1];
          } else if(n=="__bennett_nz_free") {
            auto p=operand(c->getArgOperand(0));auto bits=emit("i64","ptrtoint.i64 "+p);auto zero=number(0);auto isNull=emit("i1","icmp.eq "+bits+" "+zero);
            auto id=std::to_string(dispatchBlock++),live="free"+id,done=live+"done";rows.push_back("br "+isNull+" ^"+done+"() ^"+live+"()");rows.push_back("^"+live+"():");rows.push_back("free "+p);recordFree(p);rows.push_back("br ^"+done+"()");rows.push_back("^"+done+"():");
          } else if (ccNames && ccNames->count(g)) {
            usesCCCalls=true;
            // §14.1: LLVM fastcc/tail are source ABI/optimisation details.
            // ISA calls bind typed operands, keep a callee environment and
            // retain nested frames for LIFO reversal (§9.3 leaves CC dynamic).
            std::vector<std::string> args;
            for(auto &arg:c->args()) {auto vs=operands(arg);args.insert(args.end(),vs.begin(),vs.end());}
            auto call="call @"+ccNames->at(g)+(args.empty()?"":" "+join(args," "));
            if(c->getType()->isVoidTy())rows.push_back(call);
            else {auto ns=destinations(c);rows.push_back((ns.size()==1?ns[0]:"("+join(ns)+")")+" = "+call);}
            propagateExit();
          } else
            unimplemented("§17.4 CC marker/call lowering", 1, c);
        } else if(auto *insert=dyn_cast<InsertValueInst>(&i)) {
          auto vs=operands(insert->getAggregateOperand()),part=operands(insert->getInsertedValueOperand());
          auto fs=fields(insert->getType());unsigned k=0;
          for(unsigned j=0;j<fs.size();++j)if(ArrayRef<unsigned>(fs[j].path).take_front(insert->getNumIndices())==insert->getIndices())vs[j]=part.at(k++);
          tuples[insert]=vs;
        } else if(auto *extract=dyn_cast<ExtractValueInst>(&i)) {
          auto vs=operands(extract->getAggregateOperand());auto fs=fields(extract->getAggregateOperand()->getType());
          std::vector<std::string> out;
          for(unsigned j=0;j<fs.size();++j)if(ArrayRef<unsigned>(fs[j].path).take_front(extract->getNumIndices())==extract->getIndices())out.push_back(vs[j]);
          if(extract->getType()->isAggregateType())tuples[extract]=out;else names[extract]=out.at(0);
        } else if (auto *g = dyn_cast<GetElementPtrInst>(&i)) {
          names[g] = gep(cast<GEPOperator>(g));
        } else if (auto *al = dyn_cast<AllocaInst>(&i)) {
          auto n = m.getDataLayout().getTypeAllocSize(al->getAllocatedType()).getFixedValue();
          auto *count = dyn_cast<ConstantInt>(al->getArraySize());
          if (!count) unimplemented("§17.3 dynamic CC stack extent",1,al);
          auto bytes = operand(ConstantInt::get(Type::getInt64Ty(m.getContext()),n*count->getZExtValue()));
          auto p = fresh("ptr"); rows.push_back(p + " = alloc " + bytes); names[al] = p; localMemory.push_back(p); allocatedBytes+=std::max(uint64_t(1),n*count->getZExtValue());recordAllocation(p,bytes);
        } else if (auto *st = dyn_cast<StoreInst>(&i)) {
          if(st->getValueOperand()->getType()->isAggregateType()) {
            auto vs=operands(st->getValueOperand());auto p=operand(st->getPointerOperand());auto fs=fields(st->getValueOperand()->getType());
            for(unsigned k=0;k<fs.size();++k) {
              auto value=vs[k],address=fieldPointer(p,fs[k].offset),t="i"+std::to_string(width(fs[k].type));
              if(fs[k].type->isPointerTy())value=emit(t,"ptrtoint."+t+" "+value);
              rows.push_back("store."+t+" "+address+" "+value);
            }
            continue;
          }
          auto value = operand(st->getValueOperand()), p = operand(st->getPointerOperand());
          auto w = st->getValueOperand()->getType()->isPointerTy() ? m.getDataLayout().getPointerSizeInBits() : width(st->getValueOperand()->getType());
          if (st->getValueOperand()->getType()->isPointerTy() && !tagged(a.get(st->getValueOperand()))) {
            auto d = fresh("i" + std::to_string(w)); rows.push_back(d + " = ptrtoint.i" + std::to_string(w) + " " + value); value = d;
          }
          rows.push_back("store.i" + std::to_string(w) + " " + p + " " + value);
        } else if (auto *ld = dyn_cast<LoadInst>(&i)) {
          if(ld->getType()->isAggregateType()) {
            auto p=operand(ld->getPointerOperand());std::vector<std::string> ns;
            for(auto &field:fields(ld->getType())) {
              auto address=fieldPointer(p,field.offset),t="i"+std::to_string(width(field.type));
              auto n=emit(t,"load."+t+" "+address);
              if(field.type->isPointerTy())n=emit("ptr","inttoptr "+n);
              ns.push_back(n);
            }
            tuples[ld]=ns;continue;
          }
          auto p = operand(ld->getPointerOperand());
          auto w = ld->getType()->isPointerTy() ? m.getDataLayout().getPointerSizeInBits() : width(ld->getType());
          auto value = fresh("i" + std::to_string(w)); rows.push_back(value + " = load.i" + std::to_string(w) + " " + p);
          if (ld->getType()->isPointerTy() && !tagged(a.get(ld))) { auto d = fresh("ptr"); rows.push_back(d + " = inttoptr " + value); value=d; }
          names[ld] = value;
        } else if (auto *r = dyn_cast<ReturnInst>(&i)) {
          auto v = r->getReturnValue() ? join(operands(r->getReturnValue())," ") : "";
          for (auto &p : localMemory) rows.push_back("free " + p);
          rows.push_back("ret" + (v.empty() ? "" : " " + v));
        } else if (auto *br = dyn_cast<BranchInst>(&i)) {
          if (br->isUnconditional())
            rows.push_back("br " + edge(br->getSuccessor(0), &bb));
          else {
            auto p = operand(br->getCondition());
            auto yes = edge(br->getSuccessor(0), &bb), no = edge(br->getSuccessor(1), &bb);
            rows.push_back("br " + p + " " + yes + " " + no);
          }
        } else if (auto *sw = dyn_cast<SwitchInst>(&i)) {
          // §§14.8/16.4: unsigned sorted compare tree, not a jump table.
          // Capture original-predecessor phi arguments before creating any
          // synthetic block. ISA §3.4 transfers each tuple in parallel; this
          // also preserves duplicate destinations and loop-carried swaps.
          auto cond = operand(sw->getCondition());
          auto fallback = edge(sw->getDefaultDest(), &bb);
          std::vector<std::pair<APInt, std::string>> keys;
          for (auto c : sw->cases())
            keys.emplace_back(c.getCaseValue()->getValue(), edge(c.getCaseSuccessor(), &bb));
          llvm::sort(keys, [](auto &a, auto &b) { return a.first.ult(b.first); });
          std::vector<std::string> ids = {"^" + blocks[&bb] + "()"};
          std::vector<std::vector<std::string>> chunks(1);
          auto newBlock = [&]() {
            unsigned n = ids.size();
            ids.push_back("^" + blocks[&bb] + ".s" + std::to_string(n) + "()");
            chunks.emplace_back();
            return n;
          };
          std::function<void(int, int, unsigned)> tree = [&](int lo, int hi, unsigned cur) {
            auto begin = rows.size();
            auto save = [&]() {
              chunks[cur].insert(chunks[cur].end(), rows.begin() + begin, rows.end());
              rows.resize(begin);
            };
            if (hi < lo) {
              rows.push_back("br " + fallback);
            } else if (hi - lo + 1 <= 3) {
              for (int j = lo; j <= hi; ++j) {
                auto c = operand(ConstantInt::get(m.getContext(), keys[j].first));
                auto t = fresh("i1");
                rows.push_back(t + " = icmp.eq " + cond + " " + c);
                unsigned next = j < hi ? newBlock() : 0;
                rows.push_back("br " + t + " " + keys[j].second + " " + (j < hi ? ids[next] : fallback));
                save(); cur = next;
              }
              return;
            } else {
              int mid = (lo + hi) / 2;
              auto c = operand(ConstantInt::get(m.getContext(), keys[mid].first));
              auto t = fresh("i1");
              rows.push_back(t + " = icmp.ult " + cond + " " + c);
              unsigned l = newBlock(), r = newBlock();
              rows.push_back("br " + t + " " + ids[l] + " " + ids[r]);
              save();
              tree(lo, mid - 1, l); tree(mid, hi, r);
              return;
            }
            save();
          };
          tree(0, int(keys.size()) - 1, 0);
          // Text order follows creation order (L then R, then descendants).
          for (unsigned n = 0; n < chunks.size(); ++n) {
            if (n) rows.push_back(ids[n] + ":");
            rows.insert(rows.end(), chunks[n].begin(), chunks[n].end());
          }
        } else if (auto *b = dyn_cast<BinaryOperator>(&i)) {
          auto x = operand(b->getOperand(0)), y = operand(b->getOperand(1)),
               d = fresh("i" + std::to_string(width(b->getType())));
          names[b] = d;
          rows.push_back(d + " = " + b->getOpcodeName() + " " + x + " " + y);
        } else if (auto *sel = dyn_cast<SelectInst>(&i)) {
          if(sel->getType()->isAggregateType()) {
            auto p=operand(sel->getCondition());
            auto xs=operands(sel->getTrueValue()),ys=operands(sel->getFalseValue()),ns=destinations(sel);
            for(unsigned k=0;k<ns.size();++k)rows.push_back(ns[k]+" = select "+p+" "+xs[k]+" "+ys[k]);
            continue;
          }
          auto p = operand(sel->getCondition()),
               x = operand(sel->getTrueValue()),
               y = operand(sel->getFalseValue()),
               d = fresh(type(sel));
          if(sel->getType()->isPointerTy() && !tagged(a.get(sel))) {
            auto pw=m.getDataLayout().getPointerSizeInBits();
            auto xb=fresh("i"+std::to_string(pw)),yb=fresh("i"+std::to_string(pw)),bits=fresh("i"+std::to_string(pw));
            rows.push_back(xb+" = ptrtoint.i"+std::to_string(pw)+" "+x);rows.push_back(yb+" = ptrtoint.i"+std::to_string(pw)+" "+y);
            rows.push_back(bits+" = select "+p+" "+xb+" "+yb);rows.push_back(d+" = inttoptr "+bits);
          } else rows.push_back(d + " = select " + p + " " + x + " " + y);
          names[sel] = d;
        } else if (auto *cmp = dyn_cast<ICmpInst>(&i)) {
          auto pred = cmp->getPredicate();
          auto *xv = cmp->getOperand(0), *yv = cmp->getOperand(1);
          // §6.3: every allocation identity is nonzero, including stale copies.
          // A qreg is not an ISA pointer/integer operand of icmp. For an exact
          // non-null provenance this observation is independent of its value;
          // nullable unions still require their scalar generation tags.
          auto nonnullHandle = [&](Value *v) {
            auto av = a.get(v);
            return !av.top && !av.atoms.empty() &&
              llvm::all_of(av.atoms, [](const Atom &x) { return x.kind == Atom::Root; });
          };
          if ((pred == CmpInst::ICMP_EQ || pred == CmpInst::ICMP_NE) &&
              ((isa<ConstantPointerNull>(xv) && nonnullHandle(yv)) ||
               (isa<ConstantPointerNull>(yv) && nonnullHandle(xv)))) {
            names[cmp] = operand(ConstantInt::get(cmp->getType(), pred == CmpInst::ICMP_NE));
            continue;
          }
          if (pred == CmpInst::ICMP_UGT || pred == CmpInst::ICMP_UGE ||
              pred == CmpInst::ICMP_SGT || pred == CmpInst::ICMP_SGE) {
            pred = CmpInst::getSwappedPredicate(pred);
            std::swap(xv, yv);
          }
          auto x = operand(xv), y = operand(yv), d = fresh("i1");
          // Keep this pass local to the newly materialised numerical closure;
          // unrelated CC objects retain their recorded §17.4 lowering.
          if((rTier || f.hasFnAttribute("bennett.cc.softfloat") || f.hasFnAttribute("bennett.cc.softfloat.callee")) &&
             xv->getType()->isPointerTy() && !tagged(a.get(xv)) && !tagged(a.get(yv))) {
            auto t="i"+std::to_string(width(xv->getType()));
            x=emit(t,"ptrtoint."+t+" "+x);y=emit(t,"ptrtoint."+t+" "+y);
          }
          names[cmp] = d;
          rows.push_back(d + " = icmp." +
                         CmpInst::getPredicateName(pred).str() + " " + x + " " +
                         y);
        } else if (auto *cast = dyn_cast<CastInst>(&i); cast && (isa<PtrToIntInst>(cast) || isa<IntToPtrInst>(cast))) {
          auto x=operand(cast->getOperand(0));auto w=m.getDataLayout().getPointerSizeInBits();
          auto source=isa<PtrToIntInst>(cast)?w:width(cast->getOperand(0)->getType());
          auto target=isa<IntToPtrInst>(cast)?w:width(cast->getType());
          if(isa<PtrToIntInst>(cast)){auto n=fresh("i"+std::to_string(w));rows.push_back(n+" = ptrtoint.i"+std::to_string(w)+" "+x);x=n;}
          if(source!=target){auto n=fresh("i"+std::to_string(target));rows.push_back(n+std::string(source<target?" = zext.i":" = trunc.i")+std::to_string(target)+" "+x);x=n;}
          if(isa<IntToPtrInst>(cast)){auto n=fresh("ptr");rows.push_back(n+" = inttoptr "+x);x=n;}names[cast]=x;
        } else if(auto *c=dyn_cast<BitCastInst>(&i)) {
          names[c]=operand(c->getOperand(0));
        } else if (auto *c = dyn_cast<CastInst>(&i);
                   c && (isa<ZExtInst>(c) || isa<SExtInst>(c) ||
                         isa<TruncInst>(c))) {
          auto x = operand(c->getOperand(0)),
               d = fresh("i" + std::to_string(width(c->getType())));
          names[c] = d;
          rows.push_back(d + " = " + c->getOpcodeName() + ".i" +
                         std::to_string(width(c->getType())) + " " + x);
        } else if (isa<UnreachableInst>(i)) {
          rows.push_back("trap");
        } else
          unimplemented("§17.4 production CC instruction", 1, &i);
      }
    }
  }
};
// ISA envelopes are derived from generated functions and reference metadata.
// Keep the standalone reference object untouched for byte-exact comparison.
std::map<std::string,std::string> objectSections(StringRef object) {
  std::map<std::string,std::string> sections;
  auto pos=object.find("\n\nsection ");
  while(pos!=StringRef::npos) {
    auto start=pos+10,end=object.find('\n',start),next=object.find("\n\nsection ",end);
    sections[object.slice(start,end).str()]=object.slice(end+1,next).rtrim().str();pos=next;
  }
  return sections;
}
// Unified production layout. Standalone reference files retain their original
// images/layout/hash for independent published-object comparisons.
std::string linkReferences(Entry &e) {
  auto &dl=e.m.getDataLayout(); auto pw=dl.getPointerSizeInBits();
  std::string prefix="isa=0.8\nptr_width="+std::to_string(pw)+"\n";
  struct Symbol { std::string name,kind,body; json::Value sig; };
  std::vector<Symbol> functions;
  std::map<std::string,std::string> globalSymbols, data, dataSignatures;
  std::map<std::string,uint64_t> bases,sizes;
  std::set<std::string> used=e.ccGlobals;
  for (auto &names:e.referenceGlobals) for (auto &n:names) used.insert(n.second);
  // Include pointer relocation targets for every tier. A data image can name
  // another source global or a function even when no instruction loads it.
  std::set<const Value *> relocationVisited;
  std::function<void(const Value *)> relocation=[&](const Value *v) {
    if (!relocationVisited.insert(v).second) return;
    if (auto *g=dyn_cast<GlobalVariable>(v)) {
      used.insert(scalarGlobalKey(*g));e.ccGlobals.insert(scalarGlobalKey(*g));
      if (g->hasInitializer()) relocation(g->getInitializer());
      return;
    }
    if (auto *fn=dyn_cast<Function>(v)) {
      auto address=e.functionAddress(const_cast<Function *>(fn));
      const_cast<Function *>(fn)->setMetadata("bennett.address",MDNode::get(e.m.getContext(),
          ConstantAsMetadata::get(ConstantInt::get(dl.getIntPtrType(e.m.getContext()),address))));
      return;
    }
    if(auto *constant=dyn_cast<Constant>(v))for(auto &operand:constant->operands())relocation(operand);
  };
  for (auto &g:e.m.globals())if(used.count(scalarGlobalKey(g)))relocation(&g);
  if(e.argvService) {
    std::set<const Value *> visited;
    std::function<void(const Value *)> include=[&](const Value *v) {
      if(!visited.insert(v).second)return;
      if(auto *g=dyn_cast<GlobalVariable>(v)) {used.insert(scalarGlobalKey(*g));e.ccGlobals.insert(scalarGlobalKey(*g));if(g->hasInitializer())include(g->getInitializer());return;}
      if(isa<Function>(v))return;
      if(auto *constant=dyn_cast<Constant>(v))for(auto &operand:constant->operands())include(operand);
    };
    for(auto &g:e.m.globals())if(used.count(scalarGlobalKey(g)))include(&g);
    // The shared image and the indirect compare trees use the same addresses.
    for(auto &f:e.m) {
      if (hasComparisonLayout() && !comparisonFunctionAddress(f)) continue;
      auto address=e.functionAddress(&f);
      f.setMetadata("bennett.address",MDNode::get(e.m.getContext(),ConstantAsMetadata::get(ConstantInt::get(e.m.getDataLayout().getIntPtrType(e.m.getContext()),address))));
    }
  }
  uint64_t base=4096;
  for (auto &g:e.m.globals()) if (used.count(scalarGlobalKey(g))) {
    auto key=scalarGlobalKey(g),name="G"+std::to_string(globalSymbols.size()+1);
    globalSymbols[key]=name;base=alignTo(base,dl.getPreferredAlign(&g));bases[name]=comparisonGlobalAddress(g).value_or(base);
    sizes[name]=dl.getTypeAllocSize(g.getValueType()).getFixedValue();base=std::max(base,bases[name]+sizes[name]);
  }
  for(auto &key:used) if(!globalSymbols.count(key)) {
    // Model state materialised only in a scalar clone has the published i64
    // default image; its source name still identifies it across wrappers.
    if(!StringRef(key).starts_with("name:__bennett_dev_")) unimplemented("§19.5 unnamed unified global",1,&e.f);
    auto name="G"+std::to_string(globalSymbols.size()+1);globalSymbols[key]=name;
    if (hasComparisonLayout())fail("BD-E-COMPARISON-LAYOUT", "materialised model global missing from source module");
    base=alignTo(base,uint64_t(8));bases[name]=base;sizes[name]=8;base+=8;
  }
  std::map<const GlobalVariable *,uint64_t> sourceBases;
  for(auto &g:e.m.globals()) if(globalSymbols.count(scalarGlobalKey(g)))sourceBases[&g]=bases.at(globalSymbols.at(scalarGlobalKey(g)));
  json::Object globals,interfaces;
  uint64_t heap=comparisonHeapBase().value_or(alignTo(base,uint64_t(4096))),heapLimit=0,stack=0;
  std::vector<std::map<std::string,std::string>> parsed;
  for(auto &ref:e.references) {
    parsed.push_back(objectSections(ref));auto layout=parse(parsed.back().at("layout"));
    heapLimit=std::max(heapLimit,uint64_t(*layout.getAsObject()->getInteger("heap_limit_max")));
    stack=std::max(stack,uint64_t(*layout.getAsObject()->getInteger("S_cells")));
  }
  heapLimit=std::max(heapLimit,e.ccHeapBytes);
  if(parsed.empty())while((uint64_t(1)<<stack)<std::max(uint64_t(e.stack),e.table.capacities[2]))++stack;
  uint64_t endAddress=heap+heapLimit,memCount=0;
  for(auto &g:e.m.globals())if(e.ccGlobals.count(scalarGlobalKey(g))) {
    auto name=globalSymbols.at(scalarGlobalKey(g)),image=scalarGlobalImage(g,sourceBases);
    data[name]=image;dataSignatures[name]="{\"abi\":\"0.8\",\"kind\":\"data\",\"size\":"+std::to_string(sizes.at(name))+",\"tier\":\"-\"}";
    globals[name]=json::Object{{"base",int64_t(bases.at(name))},{"size",int64_t(sizes.at(name))},{"image",name}};
    auto marker="CCADDRESS"+std::to_string(std::distance(e.m.global_begin(),g.getIterator()));
    for(auto &row:e.rows)row=std::regex_replace(row,std::regex(marker+"\\b"),std::to_string(bases.at(name)));
    for(auto &fn:e.ccFunctions)fn.second.second=std::regex_replace(fn.second.second,std::regex(marker+"\\b"),std::to_string(bases.at(name)));
  }
  for(unsigned i=0;i<parsed.size();++i) {
    auto &sec=parsed[i];auto syms=parse(sec.at("symbols"));auto suffix=i?std::to_string(i):"";
    std::map<std::string,std::string> rename;
    rename["ref"]="ref"+suffix;rename["L1"]=i?"L1_"+suffix:"L1";
    for(auto &v:*syms.getAsObject()) {auto *sym=v.second.getAsObject();auto n=sym->getString("name")->str();if(sym->getString("kind")=="lproc")rename[n]=i?n+"_"+suffix:n;}
    for(auto &g:e.referenceGlobals[i]) rename[g.first]=globalSymbols.at(g.second);
    auto replace=[&](std::string text) {
      std::string result;size_t last=0;std::regex refs(R"(@([A-Za-z_][A-Za-z_0-9]*))");
      for(std::sregex_iterator it(text.begin(),text.end(),refs),end;it!=end;++it) {
        auto name=(*it)[1].str();result+=text.substr(last,it->position()-last)+"@"+(rename.count(name)?rename.at(name):name);last=it->position()+it->length();
      }
      return result+text.substr(last);
    };
    auto body=sec.at("functions");
    for(auto &v:*syms.getAsObject()) {
      auto *sym=v.second.getAsObject();auto name=sym->getString("name")->str(),kind=sym->getString("kind")->str();
      if(kind=="data") {
        auto renamed=rename.at(name);auto bytes=StringRef(sec.at("data")).split(name+" ").second.split('\n').first.str();
        auto source=e.referenceGlobals[i].at(name);
        for(auto &g:e.m.globals()) if(scalarGlobalKey(g)==source) bytes=scalarGlobalImage(g,sourceBases);
        if(data.count(renamed) && data.at(renamed)!=bytes) fail("output","inconsistent shared global image",&e.f);
        data[renamed]=bytes;dataSignatures[renamed]=jcs(*sym->get("signature"));
        globals[renamed]=json::Object{{"base",int64_t(bases.at(renamed))},{"size",int64_t(sizes.at(renamed))},{"image",renamed}};
      } else {
        std::string marker=(kind=="oracle"?"oracle @":"lproc @")+name+" ";auto begin=body.find(marker);
        auto finish=body.find("\nlproc @",begin+1);
        auto text=StringRef(body).slice(begin,finish).rtrim().str();
        functions.push_back({rename.at(name),kind,replace(text),parse(jcs(*sym->get("signature")))});
        if(kind=="oracle") {
          json::Object regions;std::regex mem(R"(([A-Za-z_][A-Za-z_0-9]*):region\[([0-9]+),([0-9]+)\])");
          auto header=StringRef(text).split('\n').first.str();
          for(std::sregex_iterator it(header.begin(),header.end(),mem),end;it!=end;++it) {
            uint64_t size=(uint64_t(1)<<std::stoul((*it)[2]))*std::stoul((*it)[3])/8;
            endAddress=alignTo(endAddress,size);regions[(*it)[1].str()]=json::Object{{"base",int64_t(endAddress)}};endAddress+=size;++memCount;
          }
          interfaces[rename.at(name)]=std::move(regions);
        }
      }
    }
  }
  unsigned h=0,tab=0;
  while((uint64_t(1)<<h)<endAddress)++h;
  while((uint64_t(1)<<tab)<data.size()+memCount+heapLimit)++tab;
  if(e.automaticSnapshot) {
    // A_tab bounds one oracle's pre-entries, not the union of all oracle
    // interface maps. Keep the same static table capacity used to size S.
    uint64_t largest=0;for(auto &owner:interfaces)largest=std::max(largest,uint64_t(owner.second.getAsObject()->size()));
    if(data.size()+largest+heapLimit>(uint64_t(1)<<e.snapshotTableExponent))fail("output","snapshot allocation-table capacity underestimated",&e.f);
    tab=e.snapshotTableExponent;
  }
  json::Object layout{{"A_tab",tab},{"H",h},{"S_cells",int64_t(stack)},{"globals",std::move(globals)},
    {"heap_base",int64_t(heap)},{"heap_limit_max",int64_t(heapLimit)},{"interface_regions",std::move(interfaces)},{"null_size",4096},{"ptr_width",pw}};
  if(!e.diskDataKey.empty())layout["block_image"]=globalSymbols.at(e.diskDataKey);
  std::map<std::string,std::string> allLeaves;
  for(auto &v:layout) {
    if(v.first=="globals") for(auto &g:*v.second.getAsObject()) allLeaves["globals."+g.first.str()]=jcs(g.second);
    else if(v.first=="interface_regions") for(auto &o:*v.second.getAsObject()) for(auto &r:*o.second.getAsObject()) allLeaves["interface_regions."+o.first.str()+"."+r.first.str()]=jcs(r.second);
    else allLeaves[v.first.str()]=jcs(v.second);
  }
  // JSON Object iteration differs between LLVM majors. Definition order is
  // part of the full object bytes even when all interface hashes agree.
  std::sort(functions.begin(),functions.end(),[](const Symbol &a,const Symbol &b) { return a.name < b.name; });
  std::map<std::string,std::string> hashes;json::Object symbols;
  auto addSymbol=[&](std::string name,std::string kind,json::Value sig,std::string ih) {
    symbols[std::to_string(symbols.size())]=json::Object{{"name",name},{"kind",kind},{"signature",std::move(sig)},{"interface_hash",ih}};
  };
  for(auto &v:data) { hashes[v.first]=hash(prefix+dataSignatures.at(v.first)+"\n"+v.first+" "+v.second+"\n"); addSymbol(v.first,"data",parse(dataSignatures.at(v.first)),hashes.at(v.first)); }
  // Hash arbitrary linked closures, including recursive SCCs, after relocation.
  std::map<std::string,Symbol *> members;
  for(auto &f:functions)members[f.name]=&f;
  std::regex token(R"(@([A-Za-z_][A-Za-z_0-9]*))");
  std::map<std::string,std::set<std::string>> edges;
  for(auto &f:functions) {auto rest=f.body.substr(f.body.find('\n')+1);for(std::sregex_iterator it(rest.begin(),rest.end(),token),end;it!=end;++it)if(members.count((*it)[1]))edges[f.name].insert((*it)[1]);}
  auto reaches=[&](std::string from,std::string to) {std::set<std::string> seen;std::function<bool(std::string)> walk=[&](std::string n){if(n==to)return true;if(!seen.insert(n).second)return false;for(auto &v:edges[n])if(walk(v))return true;return false;};return walk(from);};
  std::function<void(std::string)> hashFunction=[&](std::string name) {
    if(hashes.count(name))return;
    std::vector<std::string> group;for(auto &v:members)if(reaches(name,v.first)&&reaches(v.first,name))group.push_back(v.first);
    std::set<std::string> inside(group.begin(),group.end());bool cyclic=group.size()>1 || edges[name].count(name);
    for(auto &n:group)for(auto &edge:edges[n])if(!inside.count(edge))hashFunction(edge);
    std::string envelopes;
    for(auto &n:group) {
      auto &f=*members.at(n);auto newline=f.body.find('\n');std::string canonical=f.body.substr(0,newline+1),refs;auto rest=f.body.substr(newline+1);
      std::set<std::string> referenced;size_t last=0;
      for(std::sregex_iterator it(rest.begin(),rest.end(),token),end;it!=end;++it) {
        auto v=(*it)[1].str();std::string replacement;
        if(cyclic && inside.count(v))replacement="$"+std::to_string(std::find(group.begin(),group.end(),v)-group.begin());
        else if(hashes.count(v)) {replacement=hashes.at(v);if(referenced.insert(v).second)refs+=replacement+"\n";}
        else {auto *owner=layout.getObject("interface_regions")->getObject(f.name);if(f.kind!="oracle" || !owner || !owner->get(v))fail("output","unresolved production symbol "+v,&e.f);replacement=v;}
        canonical+=rest.substr(last,it->position()-last)+"@"+replacement;last=it->position()+it->length();
      }
      canonical+=rest.substr(last);std::string images,leaves;
      for(auto &v:data)if(f.kind=="oracle" || referenced.count(v.first))images+="data "+v.first+" "+v.second+"\n";
      for(auto &v:allLeaves) {
        bool include=f.kind=="oracle" ? !StringRef(v.first).starts_with("interface_regions.") || StringRef(v.first).starts_with("interface_regions."+f.name+".") : false;
        if(f.kind=="lproc" && StringRef(v.first).starts_with("globals."))include=referenced.count(StringRef(v.first).drop_front(8).str());
        if(include)leaves+="layout "+v.first+" "+v.second+"\n";
      }
      envelopes+=prefix+jcs(f.sig)+"\n"+canonical+"\n"+images+leaves+refs;
    }
    auto digest=hash(envelopes);for(unsigned i=0;i<group.size();++i)hashes[group[i]]=cyclic?hash(digest+":"+std::to_string(i)):digest;
  };
  for(auto kind:{"lproc","oracle"})for(auto &f:functions)if(f.kind==kind)hashFunction(f.name);
  for(auto kind:{"lproc","oracle"})for(auto &f:functions)if(f.kind==kind)addSymbol(f.name,f.kind,parse(jcs(f.sig)),hashes.at(f.name));
  std::string object=e.reference.substr(0,e.reference.find("\n\nsection "))+"\n\nsection symbols\n"+jcs(json::Value(std::move(symbols)))+"\n\nsection functions\n";
  for(auto &f:functions)object+=f.body+"\n";
  if(!data.empty()) { object+="\nsection data\n";for(auto &v:data)object+=v.first+" "+v.second+"\n"; }
  object+="\nsection layout\n"+jcs(json::Value(std::move(layout)))+"\n";return object;
}
// Hash CC call SCCs only after the entire shared memory layout is fixed.
#include "CCCalls.inc"
std::string launchObject(Entry &e, json::Object &record,
                         json::Object &certificate) {
  std::map<std::string, std::string> sections;
  std::string ref = e.reference;
  bool unified = false;
  if (e.references.size()>1) {
    auto first=objectSections(ref);
    for (auto &r:e.references) {
      auto sec=objectSections(r); auto layout=parse(sec.at("layout")); bool mapped=false;
      for(auto &owner:*layout.getAsObject()->getObject("interface_regions")) if(!owner.second.getAsObject()->empty()) mapped=true;
      if(sec["layout"]!=first["layout"] || !e.referenceGlobals.front().empty() || mapped) unified=true;
    }
  }
  unified |= (e.ccHeapBytes>0 || !e.ccGlobals.empty()) && !e.references.empty();
  if(unified || (e.references.empty() && !e.ccGlobals.empty())) {
    ref=linkReferences(e);
    if(e.references.empty()) ref="bennett-object isa=0.8 object=0.8 launch=0.8 sched=0.8 cert=0.8 coverage=0.8 target=0.8 ptr_width="+
        std::to_string(e.m.getDataLayout().getPointerSizeInBits())+ref;
  }
  size_t pos = ref.find("\n\nsection ");
  std::string header =
      pos == std::string::npos
          ? "bennett-object isa=0.8 object=0.8 launch=0.8 sched=0.8 cert=0.8 "
            "coverage=0.8 target=0.8 ptr_width=" +
                std::to_string(e.m.getDataLayout().getPointerSizeInBits())
          : ref.substr(0, pos);
  while (pos != std::string::npos) {
    auto start = pos + 10, end = ref.find('\n', start),
         next = ref.find("\n\nsection ", end-1);
    sections[ref.substr(start, end - start)] =
        StringRef(ref.substr(end + 1,
                             next == std::string::npos ? next : (next > end ? next - end - 1 : 0)))
            .rtrim()
            .str();
    pos = next;
  }
  if(sections.count("functions") && sections["functions"].empty())sections.erase("functions");
  if (!sections.count("layout") && (!e.localMemory.empty() || e.ccHeapBytes || e.usesCCCalls)) {
    uint64_t heap = std::max(e.table.capacities[1],e.ccHeapBytes); unsigned h = 0, tab = 0, sc = 0;
    while ((uint64_t(1)<<h) < 4096 + heap) ++h;
    while ((uint64_t(1)<<tab) < ((e.f.hasFnAttribute("bennett.cc.allocator") || e.usesCCCalls) ? heap : e.localMemory.size())) ++tab;
    while ((uint64_t(1)<<sc) < ((e.f.hasFnAttribute("bennett.cc.allocator") || e.usesCCCalls) ? std::max(uint64_t(e.stack),e.table.capacities[2]) : e.stack)) ++sc;
    sections["layout"] = jcs(json::Value(json::Object{{"A_tab",tab},{"H",h},{"S_cells",sc},
      {"globals",json::Object{}},{"heap_base",4096},{"heap_limit_max",int64_t(heap)},
      {"interface_regions",json::Object{}},{"null_size",4096},{"ptr_width",e.m.getDataLayout().getPointerSizeInBits()}}));
  }
  if(e.allocatorFaultService || e.argvService) {
    auto devices=sections.count("devices")?parse(sections["devices"]):json::Value(json::Object{{"models",json::Object{}},{"services",json::Object{}}});
    auto *services=devices.getAsObject()->getObject("services");
    if(!services) {(*devices.getAsObject())["services"]=json::Object{};services=devices.getAsObject()->getObject("services");}
    if(e.allocatorFaultService)(*services)["bennett.fault"]=json::Object{{"version","0.2.10"}};
    if(e.argvService)(*services)["bennett.argv"]=json::Object{{"version","0.2.10"}};
    if(e.argvService) {
      auto *models=devices.getAsObject()->getObject("models");
      for(auto &model:e.effectModels)(*models)[model]=json::Object{{"version","0.8"}};
      if(!e.diskDataKey.empty())(*models)["block"]=json::Object{{"version","0.8"}};
    }
    sections["devices"]=jcs(devices);
  }
  auto symbols = sections.count("symbols") ? parse(sections["symbols"])
                                           : json::Value(json::Object{});
  auto *so = symbols.getAsObject();
  std::string oracleHash;
  for (auto &s : *so)
    if (s.second.getAsObject()->getString("name") == "ref")
      oracleHash = s.second.getAsObject()->getString("interface_hash")->str();
  std::map<std::string, std::string> referenceHashes;
  referenceHashes["ref"] = oracleHash;
  if(unified) for(auto &s:*so) if(s.second.getAsObject()->getString("kind")=="oracle")
    referenceHashes[s.second.getAsObject()->getString("name")->str()]=s.second.getAsObject()->getString("interface_hash")->str();
  for (unsigned i = 1; !unified && i < e.references.size(); ++i) {
    std::map<std::string, std::string> extra;
    auto text = e.references[i];
    size_t p = text.find("\n\nsection ");
    while (p != std::string::npos) {
      auto start = p + 10, end = text.find('\n', start), next = text.find("\n\nsection ", end);
      extra[text.substr(start, end - start)] = StringRef(text.substr(end + 1, next == std::string::npos ? next : (next > end ? next - end - 1 : 0))).rtrim().str();
      p = next;
    }
    if (extra["layout"] != sections["layout"] || (extra.count("data") ? extra.at("data") : "") != (sections.count("data") ? sections.at("data") : ""))
      unimplemented("§16.3 multi-region unified layout", 1, &e.f);
    auto suffix = std::to_string(i);
    auto syms = parse(extra["symbols"]);
    for (auto &v : *syms.getAsObject()) {
      auto *sym = v.second.getAsObject();
      auto name = sym->getString("name")->str();
      if (name == "ref" || name == "L1") {
        auto renamed = name == "ref" ? "ref" + suffix : "L1_" + suffix;
        extra["functions"] = std::regex_replace(extra["functions"], std::regex("@" + name + "\\b"), "@" + renamed);
        // Definition names participate in the envelope; recompute both hashes.
        (*sym)["name"] = renamed;
      } else continue; // shared data was checked byte-identical above
    }
    // Rehash in dependency order, retaining the reference envelope's layout.
    std::map<std::string, std::string> changed;
    for (auto name : {"L1_" + suffix, "ref" + suffix}) {
      json::Object *sym = nullptr;
      for (auto &v : *syms.getAsObject())
        if (v.second.getAsObject()->getString("name") == name) sym = v.second.getAsObject();
      auto begin = extra["functions"].find(name[0] == 'L' ? "lproc @" + name : "oracle @" + name);
      auto end = extra["functions"].find("\nlproc @", begin + 1);
      auto body = extra["functions"].substr(begin, end == std::string::npos ? end : end - begin);
      // For memory-free lprocs only signatures/body/references enter; oracle
      // envelopes include all scalar layout leaves, as in lowerScalar.
      std::string env = "isa=0.8\nptr_width=" + std::to_string(e.m.getDataLayout().getPointerSizeInBits()) + "\n" + jcs(*sym->get("signature")) + "\n";
      std::string refs;
      for (auto &x : changed) {
        if (body.find("@" + x.first) != std::string::npos) refs += x.second + "\n";
        body = std::regex_replace(body, std::regex("@" + x.first + "\\b"), "@" + x.second);
      }
      env += body + "\n";
      if (name[0] != 'L') {
        auto layout = parse(extra["layout"]);
        std::map<std::string, std::string> leaves;
        for (auto &v : *layout.getAsObject()) {
          if (v.first == "globals" || v.first == "interface_regions") {
            if (v.first == "globals" && !v.second.getAsObject()->empty()) unimplemented("§16.3 multi-region data layout", 1, &e.f);
            if (v.first == "interface_regions") for (auto &r : *v.second.getAsObject())
              if (!r.second.getAsObject()->empty()) unimplemented("§16.3 multi-region interface layout", 1, &e.f);
          } else leaves[v.first.str()] = jcs(v.second);
        }
        for (auto &v : leaves) env += "layout " + v.first + " " + v.second + "\n";
      }
      changed[name] = hash(env + refs);
      (*sym)["interface_hash"] = changed[name];
      (*so)[std::to_string(so->size())] = parse(jcs(json::Value(std::move(*sym))));
    }
    referenceHashes["ref" + suffix] = changed["ref" + suffix];
    sections["functions"] += "\n" + extra["functions"];
  }
  json::Array pt, rt;
  for (auto &x : e.paramTypes)
    pt.push_back(x);
  for (auto &x : e.resultTypes)
    rt.push_back(x);
  json::Object sig{{"abi", "0.8"},
                   {"kind", "cc"},
                   {"params", std::move(pt)},
                   {"results", std::move(rt)},
                   {"tier", "cc"}};
  std::string body = "fn cc @" + e.f.getName().str() + " (" + join(e.params) +
                     ") (" + join(e.results) + ") () () ()\n";
  body += join(e.rows, "\n");
  std::map<std::string, std::string> hashes;
  hashes = referenceHashes;
  std::string actionBodies;
  for (auto &x : e.actions) {
    auto ah = hash("isa=0.8\nptr_width=" +
                   std::to_string(e.m.getDataLayout().getPointerSizeInBits()) +
                   "\n" + x.second.first + "\n" + x.second.second + "\n");
    hashes[x.first] = ah;
    (*so)[std::to_string(so->size())] =
        json::Object{{"interface_hash", ah},
                     {"kind", "action"},
                     {"name", x.first},
                     {"signature", parse(x.second.first)}};
    actionBodies += "\n" + x.second.second;
  }
  if(e.usesCCCalls)linkCCCalls(e,sections,sig,body,hashes,*so,actionBodies);
  std::function<void(std::string)> helper=[&](std::string name) {
    if(hashes.count(name))return;
    auto &item=e.snapshotFunctions.at(name);auto text=item.second;auto nl=text.find('\n');auto rest=text.substr(nl+1);std::string canonical=text.substr(0,nl+1),refs;size_t last=0;std::set<std::string> seen;
    std::regex token(R"(@([A-Za-z_][A-Za-z_0-9]*))");
    for(std::sregex_iterator it(rest.begin(),rest.end(),token),end;it!=end;++it) {auto n=(*it)[1].str();helper(n);canonical+=rest.substr(last,it->position()-last)+"@"+hashes.at(n);last=it->position()+it->length();if(seen.insert(n).second)refs+=hashes.at(n)+"\n";}
    canonical+=rest.substr(last);
    std::string memoryEnvelope;
    if(sections.count("layout")) {
      if(sections.count("data")){SmallVector<StringRef> lines;StringRef(sections["data"]).split(lines,'\n');for(auto line:lines)memoryEnvelope+="data "+line.str()+"\n";}
      auto layout=parse(sections["layout"]);std::map<std::string,std::string> leaves;
      for(auto &v:*layout.getAsObject()) {
        if(v.first=="globals")for(auto &g:*v.second.getAsObject())leaves["globals."+g.first.str()]=jcs(g.second);
        else if(v.first=="interface_regions" && name!="xor128") {for(auto &owner:*v.second.getAsObject())for(auto &region:*owner.second.getAsObject())leaves["interface_regions."+owner.first.str()+"."+region.first.str()]=jcs(region.second);}
        else if(v.first!="interface_regions")leaves[v.first.str()]=jcs(v.second);
      }
      for(auto &leaf:leaves)memoryEnvelope+="layout "+leaf.first+" "+leaf.second+"\n";
    }
    hashes[name]=hash("isa=0.8\nptr_width="+std::to_string(e.m.getDataLayout().getPointerSizeInBits())+"\n"+item.first+"\n"+canonical+"\n"+memoryEnvelope+refs);
    (*so)[std::to_string(so->size())]=json::Object{{"name",name},{"kind",name=="xor128"?"oracle":"cc"},{"signature",parse(item.first)},{"interface_hash",hashes.at(name)}};
    actionBodies+="\n"+text;
  };
  for(auto &item:e.snapshotFunctions)helper(item.first);
  std::string canonical, refs;
  std::set<std::string> referenced;
  std::regex token(R"(@(ref[0-9]*|M[0-9]+|B[0-9]+|U[0-9]+|xor128)\b)");
  size_t last = 0;
  for (std::sregex_iterator it(body.begin(), body.end(), token), end; it != end;
       ++it) {
    auto name = (*it)[1].str();
    canonical +=
        body.substr(last, it->position() - last) + "@" + hashes.at(name);
    last = it->position() + it->length();
    if (referenced.insert(name).second)
      refs += hashes.at(name) + "\n";
  }
  canonical += body.substr(last);
  std::map<std::string, std::string> leaves;
  if (sections.count("layout")) {
    auto layout = parse(sections["layout"]);
    for (auto &x : *layout.getAsObject()) {
      auto n = x.first.str();
      if (n == "globals" || n == "interface_regions") {
        for (auto &y : *x.second.getAsObject())
          if (n == "globals")
            leaves[n + "." + y.first.str()] = jcs(y.second);
          else
            for (auto &z : *y.second.getAsObject())
              leaves[n + "." + y.first.str() + "." + z.first.str()] =
                  jcs(z.second);
      } else
        leaves[n] = jcs(x.second);
    }
  }
  std::string envelope =
      "isa=0.8\nptr_width=" +
      std::to_string(e.m.getDataLayout().getPointerSizeInBits()) + "\n" +
      jcs(json::Value(std::move(sig))) + "\n" + canonical + "\n";
  auto signature = parse(StringRef(envelope)
                             .split('\n')
                             .second.split('\n')
                             .second.split('\n')
                             .first);
  if (sections.count("data")) {
    SmallVector<StringRef> lines;
    StringRef(sections["data"]).split(lines, '\n');
    for (auto l : lines)
      envelope += "data " + l.str() + "\n";
  }
  for (auto &x : leaves)
    envelope += "layout " + x.first + " " + x.second + "\n";
  if(e.allocatorFaultService) envelope += "device bennett.fault {\"version\":\"0.2.10\"}\n";
  envelope += refs;
  auto ih = e.usesCCCalls ? hashes.at(e.f.getName().str()) : hash(envelope);
  std::string block;
  unsigned ordinal = 0;
  for (auto &line : e.rows) {
    if (line[0] == '^') {
      block = line.substr(1, line.find('(') - 1);
      ordinal = 0;
      continue;
    }
    e.coverage.push_back(
        json::Object{{"point", json::Array{ih, block, ordinal++}},
                     {"source", "dialect-0.2.10:17.4"},
                     {"classification", "lowered"},
                     {"reason", "CC scalar/marker lowering"}});
  }
  (*so)[std::to_string(so->size())] =
      json::Object{{"interface_hash", ih},
                   {"kind", "cc"},
                   {"name", e.f.getName()},
                   {"signature", std::move(signature)}};
  std::string object =
      header + "\n\nsection symbols\n" + jcs(symbols) +
      "\n\nsection functions\n" + body +
      (sections.count("functions") ? "\n" + sections["functions"] : "") +
      actionBodies + "\n";
  for (auto name : {"data", "devices", "layout"})
    if (sections.count(name))
      object += "\nsection " + std::string(name) + "\n" + sections[name] + "\n";
  json::Array budgets;
  for (auto &b : e.budgets) {
    auto name = b.getString("region").value_or("ref").str();
    if (!b.get("selection_identity")) b["selection_identity"] = hashes.at(name);
    b["identity"] = hashes.at(name);
    budgets.push_back(std::move(b));
  }
  record["budgets"] = std::move(budgets);
  record["budget_table_sha256"] = record.get("budget_table") ? hash(jcs(*record.get("budget_table"))) : hash(jcs(*record.get("budgets")));
  record["layout"] = sections.count("layout") ? parse(sections["layout"])
                                              : json::Value(json::Object{});
  record["build_flags"] =
      json::Object{{"scalar_stack", e.stack},
                   {"launch_target", "environment:BENNETT_TARGET"}};
  record["runtimes_sha256"] = nullptr;
  record["arith_sha256"] = nullptr;
  record["asm_table_sha256"] = nullptr;
  record["snapshot_sha256"] = nullptr;
  record["cpuid"] = json::Object{};
  record["entry"] = e.f.getName();
  record["interface_hash"] = ih;
  record["object_hash"] = hash(object);
  certificate["bindings"] = json::Object{{"object_hash", hash(object)},
                                         {"interface_hash", ih},
                                         {"closure_hash", ih},
                                         {"reference_program_hash", oracleHash},
                                         {"dialect_mapping_version", "0.2.9"}};
  return object;
}
// Supplementary coverage preserves the existing CC coverage sidecar's bytes.
json::Object completeCoverage(StringRef object) {
  auto symbols = parse(object.split("section symbols\n").second.split('\n').first);
  std::map<std::string, std::string> hashes;
  for (auto &v : *symbols.getAsObject()) {
    auto *sym = v.second.getAsObject();
    hashes[sym->getString("name")->str()] = sym->getString("interface_hash")->str();
  }
  json::Array entries;
  auto body = object.split("section functions\n").second.split("\n\nsection ").first;
  SmallVector<StringRef> lines; body.split(lines, '\n');
  std::string symbol, block, rule; unsigned ordinal = 0;
  for (auto line : lines) {
    if (line.starts_with("fn cc @") || line.starts_with("fn r @") || line.starts_with("oracle @") ||
        line.starts_with("lproc @") || line.starts_with("action @")) {
      symbol = line.split('@').second.split(' ').first.str();
      rule = line.starts_with("fn cc") ? "17.4" : line.starts_with("action") ? "18.3" : "16.4";
    } else if (line.starts_with("^")) {
      block = line.drop_front().split('(').first.str(); ordinal = 0;
    } else if (!line.empty() && !line.starts_with("regs ")) {
      entries.push_back(json::Object{{"point", json::Array{hashes.at(symbol), block, ordinal++}},
        {"source", "dialect-0.2.10:" + rule}, {"classification", "lowered"},
        {"reason", "materialised scalar production instruction"}});
    }
  }
  return json::Object{{"entries", std::move(entries)}};
}
// The host uses only the published launch 0.8 C ABI. BENNETT_TARGET supplies
// the target JSON at runtime; it is copied by bennett_load before launch.
void hostStub(Function &f, StringRef object, const json::Object &record) {
  Module &m = *f.getParent();
  auto &ctx = m.getContext();
  auto *ptr = PointerType::get(ctx, 0);
  auto *i32 = Type::getInt32Ty(ctx), *i64 = Type::getInt64Ty(ctx);
  auto *size = m.getDataLayout().getIntPtrType(ctx);
  auto linkage = f.getLinkage();
  auto attrs = f.getAttributes();
  SmallVector<AttributeSet> paramAttrs;
  for (unsigned i = 0; i < f.arg_size(); ++i)
    paramAttrs.push_back(attrs.getParamAttrs(i));
  f.deleteBody();
  f.setLinkage(linkage);
  // The body now performs I/O through the launch library, but native parameter
  // and result attributes (signext/zeroext) still describe the caller's ABI.
  f.setAttributes(
      AttributeList::get(ctx, AttributeSet(), attrs.getRetAttrs(), paramAttrs));
  auto *entry = BasicBlock::Create(ctx, "launch", &f),
       *bad = BasicBlock::Create(ctx, "launch.failed", &f);
  IRBuilder<> b(entry);
  IRBuilder<> err(bad);
  auto intrinsic = [&](Intrinsic::ID id,
                       ArrayRef<Type *> types = ArrayRef<Type *>()) {
#if LLVM_VERSION_MAJOR >= 23
    return Intrinsic::getOrInsertDeclaration(&m, id, types);
#else
    return Intrinsic::getDeclaration(&m, id, types);
#endif
  };
  auto string = [&](StringRef s, StringRef name = "") {
    return b.CreateGlobalString(s, name);
  };
  err.CreateCall(intrinsic(Intrinsic::trap));
  err.CreateUnreachable();
  auto api = [&](StringRef n, Type *ret, ArrayRef<Type *> types) {
    return m.getOrInsertFunction(n, FunctionType::get(ret, types, false));
  };
  auto status = [&](Value *v) {
    auto *ok = BasicBlock::Create(ctx, "launch.ok", &f);
    b.CreateCondBr(b.CreateICmpEQ(v, b.getInt32(0)), ok, bad);
    b.SetInsertPoint(ok);
  };
  auto require = [&](Value *v) {
    auto *ok = BasicBlock::Create(ctx, "launch.valid", &f);
    b.CreateCondBr(v, ok, bad);
    b.SetInsertPoint(ok);
  };
  auto slot = [&](Type *t) { return b.CreateAlloca(t); };
  auto *program = slot(ptr), *args = slot(ptr), *run = slot(i64),
       *result = slot(ptr), *request = slot(ptr);
  auto *target =
      b.CreateCall(api("getenv", ptr, {ptr}), {string("BENNETT_TARGET")});
  require(b.CreateIsNotNull(target));
  auto *targetSize = b.CreateCall(api("strlen", size, {ptr}), {target});
  status(b.CreateCall(api("bennett_load", i32, {ptr, size, ptr, size, ptr}),
                      {string(object, "bennett.object"),
                       ConstantInt::get(size, object.size()), target,
                       targetSize, program}));
  auto *p = b.CreateLoad(ptr, program);
  auto *bs = record.getArray("budgets");
  status(
      b.CreateCall(api("bennett_args_new", i32, {size, ptr}),
                   {ConstantInt::get(size, (record.getString("mode")=="reversible"?0:f.arg_size()) + bs->size()), args}));
  auto *av = b.CreateLoad(ptr, args);
  unsigned index = 0;
  for (Argument &arg : f.args()) {
    if(record.getString("mode")=="reversible")break;
    auto w = arg.getType()->getIntegerBitWidth(), bytes = (w + 7) / 8;
    auto *storage = slot(IntegerType::get(ctx, bytes * 8));
    auto *value = b.CreateZExtOrTrunc(&arg, IntegerType::get(ctx, bytes * 8));
    // Launch integers are little endian even on a big endian host.
    if (!m.getDataLayout().isLittleEndian() && bytes > 1)
      value = b.CreateCall(intrinsic(Intrinsic::bswap, {value->getType()}),
                           {value});
    b.CreateStore(value, storage);
    status(b.CreateCall(
        api("bennett_args_set_int", i32, {ptr, size, i32, ptr}),
        {av, ConstantInt::get(size, index++), b.getInt32(w), storage}));
  }
  for (auto &bv : *bs) {
    auto *budget = bv.getAsObject();
    auto *tk = slot(i64);
    auto number = [&](StringRef name) {
      uint64_t n;
      if (budget->getString(name)->getAsInteger(10, n))
        fail("output", "invalid resolved budget");
      return b.getInt64(n);
    };
    status(b.CreateCall(
        api("bennett_budget", i32, {ptr, ptr, i64, i64, i64, i64, ptr}),
        {p, string(budget->getString("region").value_or("ref")), number("steps"), number("heap"), number("stack"),
         number("depth"), tk}));
    status(b.CreateCall(
        api("bennett_args_set_token", i32, {ptr, size, i64}),
        {av, ConstantInt::get(size, index++), b.CreateLoad(i64, tk)}));
  }
  status(
      b.CreateCall(api("bennett_run", i32, {ptr, ptr, ptr, ptr, size, ptr}),
                   {p, string(f.getName()), av, ConstantPointerNull::get(ptr),
                    ConstantInt::get(size, 0), run}));
  b.CreateCall(api("bennett_args_free", b.getVoidTy(), {ptr}), {av});
  auto *id = b.CreateLoad(i64, run);
  status(b.CreateCall(api("bennett_wait", i32, {ptr, i64, ptr, ptr}),
                      {p, id, result, request}));
  if(record.getString("mode")=="reversible") {
    // §19.2's one launch request. Entries needing argv/envp byte storage
    // remain an explicit bp-ivy mechanic, rather than passing host pointers.
    auto *req=b.CreateLoad(ptr,request);require(b.CreateIsNotNull(req));
    auto *service=b.CreateCall(api("bennett_request_service",ptr,{ptr}),{req});
    auto *same=b.CreateCall(api("strcmp",i32,{ptr,ptr}),{service,string("bennett.argv")});require(b.CreateICmpEQ(same,b.getInt32(0)));
    auto *replyType=ArrayType::get(b.getInt8Ty(),4+2*m.getDataLayout().getPointerSize());auto *reply=slot(replyType);
    b.CreateStore(ConstantAggregateZero::get(replyType),reply);
    Value *argc=f.arg_empty()?(Value *)b.getInt32(0):f.getArg(0);
    if(!m.getDataLayout().isLittleEndian())argc=b.CreateCall(intrinsic(Intrinsic::bswap,{i32}),{argc});
    b.CreateStore(argc,reply);
    status(b.CreateCall(api("bennett_reply",i32,{ptr,i64,ptr,size}),{p,id,reply,ConstantInt::get(size,replyType->getNumElements())}));
    b.CreateCall(api("bennett_request_free",b.getVoidTy(),{ptr}),{req});
    status(b.CreateCall(api("bennett_wait",i32,{ptr,i64,ptr,ptr}),{p,id,result,request}));
  }
  require(b.CreateIsNull(b.CreateLoad(ptr, request)));
  auto *res = b.CreateLoad(ptr, result);
  require(b.CreateIsNotNull(res));
  require(b.CreateICmpEQ(
      b.CreateCall(api("bennett_result_nfaults", size, {ptr}), {res}),
      ConstantInt::get(size, 0)));
  Value *ret = nullptr;
  if (!f.getReturnType()->isVoidTy()) {
    auto *kind = slot(i32), *width = slot(i32);
    auto w = f.getReturnType()->getIntegerBitWidth(), bytes = (w + 7) / 8;
    auto *carrier = IntegerType::get(ctx, bytes * 8);
    auto *storage = slot(carrier);
    status(b.CreateCall(
        api("bennett_result_get", i32, {ptr, size, ptr, ptr, ptr, size}),
        {res, ConstantInt::get(size, 0), kind, width, storage,
         ConstantInt::get(size, bytes)}));
    require(b.CreateICmpEQ(b.CreateLoad(i32, kind), b.getInt32(0)));
    require(b.CreateICmpEQ(b.CreateLoad(i32, width), b.getInt32(w)));
    ret = b.CreateLoad(carrier, storage);
    if (!m.getDataLayout().isLittleEndian() && bytes > 1)
      ret = b.CreateCall(intrinsic(Intrinsic::bswap, {carrier}), {ret});
    ret = b.CreateTruncOrBitCast(ret, f.getReturnType());
  }
  status(b.CreateCall(api("bennett_run_close", i32, {ptr, i64}), {p, id}));
  b.CreateCall(api("bennett_result_free", b.getVoidTy(), {ptr}), {res});
  status(b.CreateCall(api("bennett_unload", i32, {ptr}), {p}));
  if (ret)
    b.CreateRet(ret);
  else
    b.CreateRetVoid();
}

} // namespace
#include "Reversible.inc"
void lowerProduction(Module &m, Analysis &a, StringRef out, unsigned stack,
                     StringRef budgetDefault, StringRef budgetFile) {
  // Finite source widths become distinct static roots before register-file
  // construction. Unbounded widths retain the explicit BLK-1 obligation.
  std::vector<std::pair<CallInst *,std::vector<uint64_t>>> allocations;
  for(auto &f:m)if(a.tiers[&f].count("CC"))for(auto &i:instructions(f))
    if(auto *c=dyn_cast<CallInst>(&i);c && c->getCalledFunction() &&
       (c->getCalledFunction()->getName()=="__bennett_qalloc" || c->getCalledFunction()->getName()=="__bennett_qborrow") && !isa<ConstantInt>(c->getArgOperand(1))) {
      auto v=a.get(c->getArgOperand(1));std::vector<uint64_t> widths;
      if(v.top)unimplemented("§25.1 BLK-1 dynamic widths (blocked: bp-2tw)",3,c);
      for(auto &x:v.atoms)if(x.kind==Atom::Int)widths.push_back(x.integer.getLimitedValue());
      std::sort(widths.begin(),widths.end());widths.erase(std::unique(widths.begin(),widths.end()),widths.end());allocations.push_back({c,widths});
    }
  if(!allocations.empty()) {
    for(auto &site:allocations) {
      auto *c=site.first;auto *head=c->getParent();auto *fn=head->getParent();
      auto *done=head->splitBasicBlock(c->getIterator(),"width.done");head->getTerminator()->eraseFromParent();
      auto *phi=PHINode::Create(c->getType(),site.second.size(),"width.handle",&done->front());
      auto *bad=BasicBlock::Create(m.getContext(),"width.bad",fn,done);IRBuilder<> failBuilder(bad);
      failBuilder.CreateCall(
#if LLVM_VERSION_MAJOR >= 23
        Intrinsic::getOrInsertDeclaration(&m,Intrinsic::trap)
#else
        Intrinsic::getDeclaration(&m,Intrinsic::trap)
#endif
      );failBuilder.CreateUnreachable();
      std::function<void(BasicBlock *,unsigned,unsigned)> tree=[&](BasicBlock *block,unsigned lo,unsigned hi) {
        IRBuilder<> b(block);if(lo==hi){b.CreateBr(bad);return;}
        auto mid=(lo+hi)/2;auto *key=ConstantInt::get(c->getArgOperand(1)->getType(),site.second[mid]);
        auto *leaf=BasicBlock::Create(m.getContext(),"width.leaf",fn,done),*rest=BasicBlock::Create(m.getContext(),"width.rest",fn,done);
        b.CreateCondBr(b.CreateICmpEQ(c->getArgOperand(1),key),leaf,rest);
        IRBuilder<> lb(leaf);auto *allocation=cast<CallInst>(c->clone());allocation->setName("width.static");allocation->setArgOperand(1,key);lb.Insert(allocation);lb.CreateBr(done);phi->addIncoming(allocation,leaf);
        IRBuilder<> rb(rest);auto *left=BasicBlock::Create(m.getContext(),"width.left",fn,done),*right=BasicBlock::Create(m.getContext(),"width.right",fn,done);
        rb.CreateCondBr(rb.CreateICmpULT(c->getArgOperand(1),key),left,right);tree(left,lo,mid);tree(right,mid+1,hi);
      };tree(head,0,site.second.size());c->replaceAllUsesWith(phi);c->eraseFromParent();
    }
    Analysis specialised(m);specialised.run();lowerProduction(m,specialised,out,stack,budgetDefault,budgetFile);return;
  }

  SmallVector<StringRef> components;
  budgetDefault.split(components, ',');
  std::vector<uint64_t> defaults;
  for (auto c : components) {
    uint64_t n;
    if (c.getAsInteger(10, n))
      fail("input", "§9.2 invalid budget default");
    defaults.push_back(n);
  }
  if (defaults.size() != 5)
    fail("input", "§9.2 budget default needs five components");
  BudgetTable table(defaults, budgetFile);
  {
    auto *u64 = Type::getInt64Ty(m.getContext());
    for (Function &f : m) for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i); c && c->getCalledFunction() &&
          (c->getCalledFunction()->getName() == "__bennett_oracle" || c->getCalledFunction()->getName() == "__bennett_inplace") &&
          !isa<ConstantPointerNull>(c->getArgOperand(c->getCalledFunction()->getName()=="__bennett_inplace"?2:1)))
        for (unsigned j = 0; j < 4; ++j) {
          auto v = a.readAt(*c, c->getArgOperand(c->getCalledFunction()->getName()=="__bennett_inplace"?2:1), 8*j, u64);
          if (!v.top) for (auto &atom : v.atoms)
            if (atom.kind == Atom::Int && !atom.integer.isAllOnes())
              table.capacities[j] = std::max(table.capacities[j], atom.integer.getLimitedValue());
        }
  }
  // CC arithmetic uses the same linked definitions as L and native comparison.
  // Keep recursive numerical closures as §14.1 CC calls; acyclic closures
  // retain their established inlining and object identities.
  bool preparedFP=false;
  for(auto &fn:m)if(!fn.isDeclaration() && a.tiers[&fn].count("CC") && !fn.hasFnAttribute("bennett.cc.softfloat")) {
    bool needed=false;
    for(auto &i:instructions(fn)) {
      needed|=isa<FCmpInst>(i) || (isa<BinaryOperator>(i) && i.getType()->isFloatingPointTy());
      if(auto *c=dyn_cast<CastInst>(&i))needed|=c->getOpcode()==Instruction::SIToFP||c->getOpcode()==Instruction::UIToFP||c->getOpcode()==Instruction::FPToSI||c->getOpcode()==Instruction::FPToUI||c->getOpcode()==Instruction::FPExt||c->getOpcode()==Instruction::FPTrunc;
      if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())needed|=g->getName().starts_with("__bennett_sf_") || (g->isIntrinsic() && c->getType()->isFloatingPointTy());
    }
    if(!needed)continue;
    a.releaseTransferGraphs();
    fn.addFnAttr("bennett.cc.softfloat");preparedFP=true;normaliseScalar(fn);materialiseFPBits(fn);
    // A back edge is a real call frame, never an inlining refusal.
    bool recursive=false;
    std::set<Function *> active,done;
    std::function<void(Function *)> check=[&](Function *f) {
      requireSoftFloat(*f);if(f->isDeclaration() || done.count(f))return;
      if(!active.insert(f).second) {recursive=true;return;}
      normaliseScalar(*f);materialiseFPBits(*f);
      for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g && !markers().count(g->getName().str()))check(g);
      active.erase(f);done.insert(f);
    };
    for(auto &i:instructions(fn))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction();g && g->getName().starts_with("__bennett_sf_"))check(g);
    if(recursive) {
      for(auto *g:done)g->addFnAttr("bennett.cc.softfloat.callee");
      auto *entry=normaliseWideABI(m,&fn);
      for(auto &g:m)if(!g.isDeclaration()) {normaliseScalar(g);materialiseFPBits(g);}
      for(auto &g:m)if(!g.use_empty())materialiseIntegerRuntime(g);
      prepareStack(m,*entry,table.capacities[4]);
      if(auto *init=m.getFunction("__bennett_rt_ss_init");init && !init->isDeclaration()) {
        IRBuilder<> b(&*entry->getEntryBlock().getFirstInsertionPt());b.CreateCall(init,{b.getInt64(table.capacities[4])});
      }
      for(auto &g:m)if(!g.isDeclaration()) {normaliseScalar(g);materialiseFPBits(g);}
      // N22/N27 and N24 introduce additional linked runtime definitions.
      // All reachable helpers execute in this entry, including externally
      // named slot helpers; their H bodies must not become launch stubs.
      std::set<Function *> closure;
      std::function<void(Function *)> retain=[&](Function *g) {
        if(g->isDeclaration() || !closure.insert(g).second)return;
        if(g!=entry)g->addFnAttr("bennett.cc.softfloat.callee");
        for(auto &i:instructions(g))if(auto *c=dyn_cast<CallBase>(&i))
          if(auto *target=resolve(c->getCalledOperand()))retain(target);
      };retain(entry);
      Analysis prepared(m);prepared.run();lowerProduction(m,prepared,out,stack,budgetDefault,budgetFile);return;
    }
    while(true) {
      CallBase *site=nullptr;
      for(auto &i:instructions(fn))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && done.count(c->getCalledFunction())) {site=c;break;}
      if(!site)break;InlineFunctionInfo info;
      if(!InlineFunction(*site,info).isSuccess())fail("output","§13.1 CC helper inlining failed",site);
    }
  }
  if(preparedFP) {Analysis prepared(m);prepared.run();lowerProduction(m,prepared,out,stack,budgetDefault,budgetFile);return;}
  bool preparedCaller=false;
  std::vector<Function *> callers;
  for(auto &fn:m)if(!fn.isDeclaration() && a.tiers[&fn].count("CC"))callers.push_back(&fn);
  for(auto *fn:callers) {
    Entry probe{m,a,*fn,"",stack,table};if(!probe.wantsSnapshot() || fn->hasFnAttribute("bennett.cc.snapshot"))continue;
    fn->addFnAttr("bennett.cc.snapshot");preparedCaller=true;
    for(auto &i:instructions(fn))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_oracle")
      if(auto *al=dyn_cast<AllocaInst>(getUnderlyingObject(c->getArgOperand(2))))al->setMetadata("bennett.cc.descriptor",MDNode::get(m.getContext(),{}));
    prepareStack(m,*fn,table.capacities[4]);
    if(auto *init=m.getFunction("__bennett_rt_ss_init");init && !init->isDeclaration()) {IRBuilder<> b(&*fn->getEntryBlock().getFirstInsertionPt());b.CreateCall(init,{b.getInt64(table.capacities[4])});}
    // Materialised classical helpers use this same CC allocator and memory.
    // Inline acyclic calls before the ordinary SSA/CFG lowering, including
    // logical-stack bookkeeping. Marker calls stay as launch operations.
    while(true) {
      CallBase *site=nullptr;
      for(auto &i:instructions(fn))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && !c->getCalledFunction()->isDeclaration() && !markers().count(c->getCalledFunction()->getName().str())) {site=c;break;}
      if(!site)break;
      if(site->getCalledFunction()==fn)break;
      InlineFunctionInfo info;if(!InlineFunction(*site,info).isSuccess())fail("output","caller snapshot helper inlining failed",site);
    }
    normaliseScalar(*fn);
  }
  if(preparedCaller) {Analysis prepared(m);prepared.run();lowerProduction(m,prepared,out,stack,budgetDefault,budgetFile);return;}
  // §19.1/§17.4: follow linked allocator bodies, never substitute libc
  // summaries. Normalise before inlining (notably calloc's N27 overflow
  // arithmetic and N26 memset), then retain every primitive and byte access.
  bool preparedAllocator=false;
  for(auto *fn:callers) {
    auto allocator=[](StringRef n) {return n=="malloc" || n=="calloc" || n=="free" || n=="memset";};
    bool needed=false;
    for(auto &i:instructions(*fn))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=resolve(c->getCalledOperand()))needed|=allocator(g->getName());
    if(!needed || fn->hasFnAttribute("bennett.cc.allocator"))continue;
    fn->addFnAttr("bennett.cc.allocator");preparedAllocator=true;
    normaliseScalar(*fn);
    std::set<Function *> active,done;
    std::function<void(Function *)> visit=[&](Function *g) {
      materialiseIntegerRuntime(*g);
      if(g->isDeclaration() || markers().count(g->getName().str()) || done.count(g))return;
      if(!active.insert(g).second)unimplemented("§17.4 recursive CC allocator closure",2,g);
      normaliseScalar(*g);
      for(auto &i:instructions(*g))if(auto *c=dyn_cast<CallBase>(&i))if(auto *target=resolve(c->getCalledOperand()))visit(target);
      active.erase(g);done.insert(g);
    };
    // Only calls in the allocator closure are expanded in this pass.
    for(auto &i:instructions(*fn))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=resolve(c->getCalledOperand());g && (allocator(g->getName()) || g->getName()=="__bennett_rt_memset"))visit(g);
    while(true) {
      CallBase *site=nullptr;
      for(auto &i:instructions(*fn))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=resolve(c->getCalledOperand());g && done.count(g)) {site=c;break;}
      if(!site)break;
      InlineFunctionInfo info;if(!InlineFunction(*site,info).isSuccess())fail("output","§17.4 allocator closure inlining failed",site);
    }
    // N27 produces field shells for the overflow result. Project those SSA
    // fields without running an optimiser that could erase heap history.
    SmallVector<Instruction *> fields;
    for(auto &i:instructions(*fn))if(isa<ExtractValueInst>(i))fields.push_back(&i);
    for(auto *i:fields)if(auto *v=simplifyInstruction(i,SimplifyQuery(m.getDataLayout()))) {i->replaceAllUsesWith(v);i->eraseFromParent();}
    bool dead=true;while(dead) {
      dead=false;SmallVector<Instruction *> shells;
      for(auto &i:instructions(*fn))if(isa<InsertValueInst>(i) && i.use_empty())shells.push_back(&i);
      for(auto *i:shells) {i->eraseFromParent();dead=true;}
    }
  }
  if(preparedAllocator) {Analysis prepared(m);prepared.run();lowerProduction(m,prepared,out,stack,budgetDefault,budgetFile);return;}
  if (auto ec = sys::fs::create_directories(out)) fail("output", ec.message());
  ValueToValueMapTy vm;
  auto device = CloneModule(m, vm);
  std::vector<Function *> entries;
  for (Function &f : m)
    if (!f.isDeclaration() && a.tiers[&f].count("CC")) {
      // Internal direct-only callees execute in their caller's launch and
      // memory. Keep their H body; no host launch ABI is crossed here.
      if(f.hasFnAttribute("bennett.cc.softfloat.callee") || f.hasFnAttribute("bennett.stack.internal"))continue;
      bool internal=f.hasLocalLinkage();
      for(auto *u:f.users()) {
        auto *c=dyn_cast<CallBase>(u);
        internal &= c && c->getCalledOperand()==&f && a.tiers[c->getFunction()].count("CC");
      }
      for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))
        if(auto *g=resolve(c->getCalledOperand());g && markers().count(g->getName().str()))internal=false;
      if(!internal)entries.push_back(&f);
    }
  json::Array launches;
  for (Function *f : entries) {
    std::string dir = out.str() + "/" + f->getName().str();
    if (auto ec = sys::fs::create_directories(dir))
      fail("output", ec.message());
    Entry e{m, a, *f, dir, stack, table};
    std::map<Function *,std::string> ccNames;
    ccNames[f]=f->getName().str();
    std::vector<Function *> closure{f};
    auto include = [&](Function *g) {
      if (g && !g->isDeclaration() && !markers().count(g->getName().str()) && !ccNames.count(g)) {
        auto name="C"+std::to_string(closure.size()-1);
        if(name==f->getName())name+="callee";
        ccNames[g]=name;closure.push_back(g);
      }
    };
    for(unsigned k=0;k<closure.size();++k)for(auto &i:instructions(*closure[k]))
      if(auto *c=dyn_cast<CallBase>(&i)) {
        if(auto *g=resolve(c->getCalledOperand())) include(g);
        else {
          auto candidates=a.candidates(c->getCalledOperand(),c->getFunctionType());
          for(auto &g:m)if(candidates.count(&g))include(&g);
        }
      }
    e.ccNames=&ccNames;
    e.lower();
    for(unsigned k=1;k<closure.size();++k) {
      Entry callee{m,a,*closure[k],dir,stack,table};callee.ccNames=&ccNames;
      // One object owns the memory, references and action namespace, while
      // each CC body has its own SSA registers and block parameters.
      callee.actions=e.actions;callee.references=e.references;callee.reference=e.reference;
      callee.referenceGlobals=e.referenceGlobals;callee.snapshotFunctions=e.snapshotFunctions;
      callee.budgets=std::move(e.budgets);
      callee.lower();
      e.actions=std::move(callee.actions);e.references=std::move(callee.references);e.reference=std::move(callee.reference);
      e.referenceGlobals=std::move(callee.referenceGlobals);e.snapshotFunctions=std::move(callee.snapshotFunctions);
      e.budgets=std::move(callee.budgets);
      e.ccGlobals.insert(callee.ccGlobals.begin(),callee.ccGlobals.end());
      e.ccHeapBytes=std::max(e.ccHeapBytes,callee.ccHeapBytes);e.allocatedBytes+=callee.allocatedBytes;
      e.allocatorFaultService|=callee.allocatorFaultService;
      json::Array pt,rt;for(auto &t:callee.paramTypes)pt.push_back(t);for(auto &t:callee.resultTypes)rt.push_back(t);
      auto sig=jcs(json::Value(json::Object{{"abi","0.8"},{"kind","cc"},{"params",std::move(pt)},{"results",std::move(rt)},{"tier","cc"}}));
      auto name=ccNames.at(closure[k]);
      e.ccFunctions[name]={sig,"fn cc @"+name+" ("+join(callee.params)+") ("+join(callee.results)+") () () ()\n"+join(callee.rows,"\n")};
    }
    if(e.automaticSnapshot)e.ccHeapBytes=e.table.capacities[1];
    else if(e.memoryDescriptors || e.generalUsed)e.ccHeapBytes=e.allocatedBytes;
    json::Object record{{"dialect", "0.2.10"},
                        {"isa", "0.8"},
                        {"llvm_version", LLVM_VERSION_STRING},
                        {"pipeline", "bennett"},
                        {"shape", e.shape}};
    if(auto *id=dyn_cast_or_null<MDString>(m.getModuleFlag("bennett.arith.bitcode.sha256")))record["arith_bitcode_sha256"]=id->getString();
    if (table.enabled) {
      json::Object resolved{{"version", "0.2"}, {"defaults", tuple(table.defaults)},
        {"capacities", tuple(table.capacities)}, {"shapes", std::move(e.resolvedShapes)},
        {"input", parse(jcs(table.document))}};
      auto resolvedText = jcs(json::Value(std::move(resolved)));
      record["resolved_table_sha256"] = hash(resolvedText);
      record["budget_table"] = parse(resolvedText);
    }
    json::Object cert{
        {"versions", json::Object{{"isa", "0.8"}, {"cert", "0.8"}}},
        {"regions", json::Object{}},
        {"composition",
         json::Object{{"multiplicities", json::Object{}},
                      {"epsilon_total", json::Object{{"diamond", 0}}},
                      {"method", "sum_over_multiplicities"}}}};
    auto obj = launchObject(e, record, cert);
    write(dir + "/launch.bennett", obj);
    write(dir + "/all-coverage.json", jcs(json::Value(completeCoverage(obj))) + "\n");
    auto build = jcs(json::Value(std::move(record)));

    write(dir + "/build.json", build + "\n");
    cert["producer"] = json::Object{
        {"name", "bennett-plugin"},
        {"version", "0.2.10+build." + hash(build)},
        {"materialisation", json::Object{{"llvm_version", LLVM_VERSION_STRING},
                                         {"pipeline", "bennett"},
                                         {"normaliser_version", "0.2.8"}}}};
    write(dir + "/certificate.json", jcs(json::Value(std::move(cert))) + "\n");
    write(dir + "/coverage.json",
          jcs(json::Value(json::Object{{"entries", std::move(e.coverage)}})) +
              "\n");
    write(dir + "/blockers.json", "[]\n");
    launches.push_back(
        json::Object{{"entry", f->getName()},
                     {"object", f->getName().str() + "/launch.bennett"},
                     {"build_sha256", hash(build)}});
  }
  // Snapshot analysis of every entry sees the linked source memory, before
  // native stubs add embedded objects and launch-API string globals.
  a.releaseTransferGraphs();
  for(auto *entry:entries) {
    auto dir=out.str()+"/"+entry->getName().str();auto build=parse(read(dir+"/build.json"));
    hostStub(*entry,read(dir+"/launch.bennett"),*build.getAsObject());
  }
  normaliseWideABI(*device);
  for (Function &f : *device)
    if (!f.isDeclaration() && a.tiers[m.getFunction(f.getName())].count("L"))
      normaliseScalar(f);
  std::error_code ec;
  raw_fd_ostream bc(out.str() + "/device.bc", ec);
  if (ec)
    fail("output", ec.message());
  checkComparisonMaterialisation(*device);
  WriteBitcodeToFile(*device, bc);
  for(auto &f:m)if(!f.isDeclaration())normaliseFP(f);
  for(auto &f:m)for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())requireSoftFloat(*g);
  raw_fd_ostream host(out.str() + "/host.bc", ec);
  if (ec)
    fail("output", ec.message());
  WriteBitcodeToFile(m, host);
  write(out.str() + "/launches.json",
        jcs(json::Value(std::move(launches))) + "\n");
  bc.close(); host.close();
  // Hash only closed, final artifacts. The record is not included in its own
  // inventory, and never upgrades metadata to a checked executable claim.
  for (Function *f : entries) {
    std::string dir = f->getName().str();
    json::Object artifacts;
    auto add = [&](const std::string &path) {
      auto bytes = read(out.str() + "/" + path);
      artifacts[path] = json::Object{{"bytes", int64_t(bytes.size())}, {"sha256", hash(bytes)}};
    };
    for (auto file : {"host.bc", "device.bc", "launches.json"}) add(file);
    for (auto file : {"launch.bennett", "build.json", "certificate.json", "coverage.json", "all-coverage.json", "blockers.json"}) add(dir + "/" + file);
    if(sys::fs::exists(out.str()+"/"+dir+"/inplace-evidence.json")) add(dir+"/inplace-evidence.json");
    for (unsigned i = 0;; ++i) {
      auto path = dir + "/oracle-" + std::to_string(i) + "/ref.bennett";
      if (!sys::fs::exists(out.str() + "/" + path)) break;
      add(path);
    }
    auto build = parse(read(out.str() + "/" + dir + "/build.json"));
    json::Object record{{"schema", "bennett-plugin-launch-record-1"},
      {"entry", dir}, {"object_hash", *build.getAsObject()->getString("object_hash")},
      {"artifacts", std::move(artifacts)}, {"certificate_acceptance", "metadata_only"},
      {"target_source", "runtime:BENNETT_TARGET"},
      {"checked_executable_claims", false}, {"linked_runtime_acceptance", false},
      {"required_acceptance", json::Array{"target/schedule-bound checked executable claims", "real linked launch-library execution"}}};
    if (hasComparisonLayout()) record["comparison_layout_sha256"] = comparisonLayoutDigest();
    write(out.str() + "/" + dir + "/launch-record.json", jcs(json::Value(std::move(record))) + "\n");
  }

}
} // namespace bennett
