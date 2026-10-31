#include "Bennett.h"
#include "llvm/ADT/SmallString.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Analysis/AssumptionCache.h"
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
#include "llvm/Support/SHA256.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include "llvm/Transforms/Utils/PromoteMemToReg.h"
#include <numeric>
#include <tuple>
using namespace llvm;
namespace bennett {
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
  auto x = std::make_tuple(kind, object, offset, stride, integer.getBitWidth());
  auto y = std::make_tuple(b.kind, b.object, b.offset, b.stride,
                           b.integer.getBitWidth());
  return x < y || (x == y && integer.ult(b.integer));
}
bool AV::merge(const AV &v) {
  bool change = false;
  if (v.top && !top) {
    top = true;
    change = true;
  }
  for (auto &a : v.atoms)
    if (!(top && a.kind == Atom::Int))
      change |= atoms.insert(a).second;
  unsigned n = 0;
  if (atoms.size() > 4096)
    for (auto &a : atoms)
      n += a.kind == Atom::Int;
  if (n > 4096) {
    top = true;
    change = true;
  }
  if (top)
    for (auto i = atoms.begin(); i != atoms.end();)
      if (i->kind == Atom::Int)
        i = atoms.erase(i);
      else
        ++i;
  return change;
}
bool AV::roots() const {
  for (auto &a : atoms)
    if (a.kind == Atom::Root)
      return true;
  return false;
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
    if (!g)
      break;
    f = g;
  }
  return f;
}
std::string regionKey(Function *f) {
  // Clone only the direct closure, strip non-semantic names/metadata, and give
  // closure members DFS names. Retain external references such as marker names.
  Module &src = *f->getParent();
  std::vector<Function *> order;
  std::set<Function *> seen;
  std::function<void(Function *)> dfs = [&](Function *g) {
    g = resolve(g);
    if (!g || g->isDeclaration() || !seen.insert(g).second)
      return;
    order.push_back(g);
    for (Instruction &i : instructions(g))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *t = resolve(c->getCalledOperand()))
          dfs(t);
  };
  dfs(f);
  std::set<const GlobalVariable *> globals;
  std::set<const Value *> visited;
  std::function<void(const Value *)> data = [&](const Value *v) {
    if (!visited.insert(v).second)
      return;
    if (auto *g = dyn_cast<GlobalVariable>(v)) {
      globals.insert(g);
      if (g->hasInitializer())
        data(g->getInitializer());
      return;
    }
    if (isa<Function>(v))
      return;
    if (auto *u = dyn_cast<User>(v))
      for (Value *operand : u->operands())
        data(operand);
  };
  for (auto *g : order)
    for (Instruction &i : instructions(g))
      for (Value *v : i.operands())
        data(v);
  ValueToValueMapTy map;
  auto clone = CloneModule(src, map, [&](const GlobalValue *v) {
    return seen.count(const_cast<Function *>(dyn_cast<Function>(v))) ||
           globals.count(dyn_cast<GlobalVariable>(v));
  });
  // §7.3 identity is over the materialised body, with H left untouched.
  // This is the implemented scalar N-rule slice; full N0–N35/V1–V16 remains
  // an explicit M1 key-audit obligation for regions outside that slice.
  for(auto *g:order) normaliseScalar(*cast<Function>(map[g]));
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
    auto *c = cast<Function>(map[g]);
    clone->getFunctionList().splice(clone->end(), clone->getFunctionList(),
                                    c->getIterator());
  }
  unsigned n = 0;
  for (auto *g : order) {
    auto *c = cast<Function>(map[g]);
    c->setName("__canonical_" + std::to_string(n++));
  }
  for (auto *g : order) {
    auto *c = cast<Function>(map[g]);
    clone->getFunctionList().splice(clone->end(), clone->getFunctionList(),
                                    c->getIterator());
  }
  n = 0;
  for (auto *g : order) {
    auto *c = cast<Function>(map[g]);
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
  std::string text;
  raw_string_ostream out(text);
  clone->print(out, nullptr);
  auto hash = SHA256::hash(arrayRefFromStringRef(text));
  return toHex(hash, true);
}
AV Analysis::get(const Value *v) {
  if (auto *c = dyn_cast<ConstantInt>(v))
    return integer(c->getValue());
  if (isa<ConstantFP>(v)) {
    AV a;
    a.top = true;
    return a;
  }
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
      auto a = get(c->getOperand(0));
      if (c->getOpcode() == Instruction::IntToPtr && !a.roots())
        a.top = true;
      return a;
    }
    if (c->getOpcode() == Instruction::GetElementPtr) {
      auto *g = cast<GEPOperator>(c);
      APInt off(M.getDataLayout().getIndexTypeSizeInBits(g->getType()), 0);
      auto a = get(c->getOperand(0));
      if (g->accumulateConstantOffset(M.getDataLayout(), off)) {
        AV r;
        for (auto b : a.atoms) {
          if (b.kind == Atom::Ptr)
            b.offset += off.getSExtValue();
          r.atoms.insert(b);
        }
        r.top = a.top;
        return r;
      }
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
  } else
    store(get(c), atom(Atom::Ptr, obj, off),
          dl.getTypeStoreSize(t).getKnownMinValue());
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
void Analysis::store(const AV &v, const AV &p, uint64_t size, bool filled) {
  for (auto &a : p.atoms)
    if (a.kind == Atom::Ptr) {
      for (auto &s : slots)
        if (s.object == a.object && s.offset == a.offset &&
            s.stride == a.stride && s.bytes == size && s.filled == filled) {
          changed |= s.value.merge(v);
          goto next;
        }
      slots.push_back({a.object, a.offset, a.stride, size, v, filled});
      changed = true;
    next:;
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
      // Any call could clobber an escaped local. Only cross calls before the
      // reaching store when no relevant field has yet been proven.
      return read(base,offset,type);
    }
  }
  return read(base,offset,type);
}
AV Analysis::load(const AV &p, Type *t) {
  AV r;
  uint64_t size = M.getDataLayout().getTypeStoreSize(t).getKnownMinValue();
  r.top = p.top;
  for (auto &a : p.atoms)
    if (a.kind == Atom::Ptr) {
      if (!a.object) {
        r.top = true;
        continue;
      }
      bool partial = false;
      for (auto &s : slots)
        if (overlaps(a, s, size)) {
          if (s.filled && a.stride == 0 && s.stride == 0 &&
              a.offset >= s.offset &&
              (__int128)a.offset + size <= (__int128)s.offset + s.bytes &&
              (t->isIntegerTy() || t->isPointerTy())) {
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
          bool exact = a.stride == 0 && s.stride == 0 && a.offset == s.offset &&
                       size == s.bytes;
          bool sameClass = size == s.bytes &&
                           ((a.offset - s.offset) % (int64_t)size == 0) &&
                           (a.stride == 0 || a.stride % (int64_t)size == 0) &&
                           (s.stride == 0 || s.stride % (int64_t)size == 0);
          if (exact || sameClass)
            r.merge(s.value);
          else {
            partial = true;
            for (auto &b : s.value.atoms)
              if (b.kind == Atom::Root)
                r.atoms.insert(b);
          }
        }
      // Immutable initialiser bytes reconstruct whole integer loads exactly.
      if (auto *g = dyn_cast<GlobalVariable>(a.object);
          g && g->isConstant() && t->isIntegerTy() && a.stride == 0) {
        APInt bits(t->getIntegerBitWidth(), 0);
        bool known = true;
        for (unsigned b = 0; b < size; ++b) {
          bool found = false;
          for (auto &s : slots)
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
          known &= found;
        }
        if (known) {
          r.merge(integer(bits));
          partial = false;
        }
      }
      if (partial)
        r.top = true;
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
void Analysis::bind(CallBase &c, Function *f) {
  if (!f || f->isDeclaration())
    return;
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
         f->hasFnAttribute(Attribute::AllocKind);
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
AV Analysis::field(const Value *v, const Path &path) {
  if (path.empty())
    return get(v);
  if (auto *expr=dyn_cast<ConstantExpr>(v);expr && expr->getOpcode()==Instruction::BitCast)
    return bitcast(expr->getOperand(0),expr->getType(),path);
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
bool Analysis::composite(Instruction &i) {
  const auto &dl = M.getDataLayout();
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
      if (j < 0)
        setField(
            &i, {k},
            integer(APInt(dl.getTypeSizeInBits(
                                cast<VectorType>(i.getType())->getElementType())
                              .getKnownMinValue(),
                          0)));
      else
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
                              std::function<AV(Value *)> facts) {
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
void Analysis::step(Instruction &i) {
  AV a;
  if (composite(i))
    return;
  if (auto *rmw = dyn_cast<AtomicRMWInst>(&i)) {
    a = load(get(rmw->getPointerOperand()), rmw->getType());
    AV next, operand = get(rmw->getValOperand()); next.top = a.top || operand.top;
    for (auto &x : a.atoms) for (auto &y : operand.atoms)
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
  else if (auto *g = dyn_cast<GetElementPtrInst>(&i)) {
    auto base = get(g->getPointerOperand());
    unsigned bits = M.getDataLayout().getIndexTypeSizeInBits(g->getType());
#if LLVM_VERSION_MAJOR >= 23
    SmallMapVector<Value *, APInt, 4> vars;
#else
    MapVector<Value *, APInt> vars;
#endif
    APInt off(bits, 0);
    if (!g->collectOffset(M.getDataLayout(), bits, vars, off))
      unimplemented("§5 PT2 GEP offset", 2, g);
    a = base;
    for (auto &entry : vars) {
      AV r;
      auto indices = get(entry.first);
      if (auto it = indexBounds.find({g, entry.first}); it != indexBounds.end())
        indices = it->second;
      for (auto p : a.atoms)
        if (p.kind == Atom::Ptr) {
          if (indices.top) {
            p.stride =
                p.stride == -1
                    ? -1
                    : std::gcd(p.stride, std::abs(entry.second.getSExtValue()));
            if (p.stride == 1)
              p.stride = -1;
            r.atoms.insert(p);
          }
          for (auto &v : indices.atoms)
            if (v.kind == Atom::Int) {
              auto q = p;
              q.offset +=
                  (v.integer.sextOrTrunc(bits) * entry.second).getSExtValue();
              r.atoms.insert(q);
            }
        }
      r.top = a.top;
      a = r;
    }
    AV r;
    for (auto p : a.atoms) {
      if (p.kind == Atom::Ptr)
        p.offset += off.getSExtValue();
      r.atoms.insert(p);
    }
    r.top = a.top;
    a = r;
  } else if (auto *l = dyn_cast<LoadInst>(&i))
    a = load(get(l->getPointerOperand()), l->getType());
  else if (auto *s = dyn_cast<StoreInst>(&i)) {

    AV written = get(s->getValueOperand());
    if (auto *b = dyn_cast<BinaryOperator>(s->getValueOperand()))
      for (Value *operand : b->operands())
        if (auto *l = dyn_cast<LoadInst>(operand);
            l && l->getPointerOperand() == s->getPointerOperand() &&
            longAdditiveCycle(b, l, [&](Value *v) { return get(v); }) &&
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
        if (longAdditiveCycle(v, p, [&](Value *x) { return get(x); }))
          a.top = true;
  } else if (auto *s = dyn_cast<SelectInst>(&i)) {
    a = get(s->getTrueValue());
    a.merge(get(s->getFalseValue()));
  } else if (auto *c = dyn_cast<CastInst>(&i)) {
    a = get(c->getOperand(0));
    if (c->getOpcode() == Instruction::IntToPtr) {
      bool hasFn = false;
      for (auto &x : a.atoms)
        hasFn |= x.kind == Atom::Fn;
      if (!a.roots() && !hasFn) {
        a.top = true;
        a.merge(atom(Atom::Ptr));
      }
    } else if (c->getType()->isIntegerTy()) {
      AV r;
      r.top = a.top;
      for (auto x : a.atoms) {
        if (x.kind == Atom::Int) {
          unsigned w = c->getType()->getIntegerBitWidth();
          x.integer = c->getOpcode() == Instruction::SExt
                          ? x.integer.sextOrTrunc(w)
                          : x.integer.zextOrTrunc(w);
        }
        r.atoms.insert(x);
      }
      a = r;
    }
  } else if (isa<FreezeInst>(i))
    a = get(i.getOperand(0));
  else if (auto *c = dyn_cast<CallBase>(&i)) {
    Function *f = resolve(c->getCalledOperand());
    StringRef n = f ? f->getName() : StringRef();
    if (n == "__bennett_qalloc" || n == "__bennett_qborrow")
      a = atom(Atom::Root, c);
    else if (auto *mem = dyn_cast<MemTransferInst>(c)) {
      AV src = get(mem->getSource()), dst = get(mem->getDest());
      auto *len = dyn_cast<ConstantInt>(mem->getLength());
      auto snapshot = slots;
      for (auto s : snapshot)
        for (auto &p : src.atoms)
          if (p.kind == Atom::Ptr && p.object == s.object)
            for (auto &d : dst.atoms)
              if (d.kind == Atom::Ptr) {
                if (s.filled && len && p.stride==0 && d.stride==0 && s.stride==0 && overlaps(p,s,len->getZExtValue())) {
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
                  store(partial, atom(Atom::Ptr, d.object, d.offset, -1),
                        s.bytes);
                }
              }
    } else if (auto *fill = dyn_cast<MemSetInst>(c)) {
      auto *len = dyn_cast<ConstantInt>(fill->getLength());
      auto p = get(fill->getDest());
      if (len && len->getValue().getActiveBits() < 63)
        store(get(fill->getValue()), p, len->getZExtValue(), true);
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
    } else if (allocation(f)) {
      a = atom(Atom::Ptr, c);
      // §5.2 initial image, not immutable memory. Dynamic extent retains the
      // possible zero bytes symbolically; PT6 only uses wholly contained reads.
      unsigned sizeArg = n == "calloc" || n == "aligned_alloc" || n == "realloc" ? 1 : 0;
      if (n == "posix_memalign") sizeArg = 2;
      uint64_t extent = UINT64_MAX;
      if (sizeArg < c->arg_size()) {
        auto sizes = get(c->getArgOperand(sizeArg));
        if (!sizes.top && !sizes.atoms.empty()) {
          extent=0;
          for (auto &v:sizes.atoms) if(v.kind==Atom::Int)
            extent=std::max(extent,v.integer.getLimitedValue());
          if(n=="calloc") {
            auto count=get(c->getArgOperand(0));
            uint64_t maxCount=count.top ? UINT64_MAX : 0;
            for(auto &v:count.atoms) if(v.kind==Atom::Int) maxCount=std::max(maxCount,v.integer.getLimitedValue());
            extent=(uint64_t)std::min<unsigned __int128>(UINT64_MAX,(unsigned __int128)extent*maxCount);
          }
        }
      }
      if (extent) store(integer(APInt(8,0)), a, extent, true);
      if (n == "posix_memalign") {
        store(a, get(c->getArgOperand(0)), M.getDataLayout().getPointerSize());
        a.top = true;
      }
    } else if (f && !f->isDeclaration())
      bind(*c, f);
    else if (!f) {
      for (auto *g : candidates(c->getCalledOperand(), c->getFunctionType()))
        bind(*c, g);
    } else if (!markers().count(n.str()) && !f->isIntrinsic() && n != "free" && n != "__bennett_nz_free") {
      a.top = true;
      std::set<const Value *> reachable;
      for (Value *v : c->args())
        for (auto &p : get(v).atoms)
          if (p.kind == Atom::Ptr)
            reachable.insert(p.object);
      bool more = true;
      while (more) {
        more = false;
        for (auto &slot : slots)
          if (reachable.count(slot.object))
            for (auto &p : slot.value.atoms)
              if (p.kind == Atom::Ptr)
                more |= reachable.insert(p.object).second;
      }
      for (auto *obj : reachable) {
        AV top;
        top.top = true;
        store(top, atom(Atom::Ptr, obj, 0, -1), 1);
      }
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
    if ((x.top || y.top) && i.getOpcode() == Instruction::And) {
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
      for (auto &v : x.atoms)
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
          } else if (v.kind == Atom::Ptr) {
            auto p = v;
            if (w.kind == Atom::Int && (i.getOpcode() == Instruction::Add ||
                                        i.getOpcode() == Instruction::Sub))
              p.offset = (i.getOpcode()==Instruction::Add
                              ? APInt(64,p.offset)+w.integer.zextOrTrunc(64)
                              : APInt(64,p.offset)-w.integer.zextOrTrunc(64)).getSExtValue();
            else
              p.stride = -1;
            a.atoms.insert(p);
          }
        }
    }
  done:;
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
  for (Function &f : M)
    if (!f.isDeclaration() && (!f.hasLocalLinkage() || f.hasAddressTaken()))
      for (Argument &a : f.args()) {
        if (a.getType()->isPointerTy()) {
          values[&a].merge(atom(Atom::Ptr));
          values[&a].merge(atom(Atom::Root, &a));
        } else
          values[&a].top = true;
      }
  unsigned rounds = 0;
  do {
    changed = false;
    for (Function &f : M)
      for (Instruction &i : instructions(f))
        step(i);
    if (++rounds > 16384)
      unimplemented("§5 fixpoint resource exhaustion", 1);
  } while (changed);
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
      if (!f.hasLocalLinkage())
        tiers[&f].insert("H");
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
    if (!s.object && s.value.roots())
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
json::Object Analysis::report() {
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
  return json::Object{{"dialect", "0.2.10"},
                      {"isa", "0.8"},
                      {"mode", "analysis-only"},
                      {"functions", std::move(funcs)},
                      {"regions", std::move(regions)},
                      {"values", std::move(vals)}};
}
} // namespace bennett
