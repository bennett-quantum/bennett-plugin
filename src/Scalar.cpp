#include "Bennett.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Operator.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/SHA256.h"
#include <regex>
using namespace llvm;
namespace bennett {
static std::string sha(StringRef s) {
  return toHex(SHA256::hash(arrayRefFromStringRef(s)), true);
}
static std::string number(const APInt &n) {
  SmallString<48> s;
  n.toString(s, 10, false);
  return s.str().str();
}
static std::string join(const std::vector<std::string> &v,
                        StringRef sep = ", ") {
  std::string s;
  for (auto &x : v) {
    if (!s.empty())
      s += sep;
    s += x;
  }
  return s;
}
static std::string canonicalJSON(const json::Value &v) {
  if(auto *o=v.getAsObject()) {
    std::map<std::string,const json::Value *> sorted;for(auto &e:*o)sorted[e.first.str()]=&e.second;
    std::string out="{";for(auto &e:sorted){if(out.size()>1)out+=",";out+=canonicalJSON(json::Value(e.first))+":"+canonicalJSON(*e.second);}return out+"}";
  }
  if(auto *a=v.getAsArray()) {std::string out="[";for(auto &e:*a){if(out.size()>1)out+=",";out+=canonicalJSON(e);}return out+"]";}
  return formatv("{0}",v).str();
}
struct Scalar {
  Module &m;
  Function &f;
  std::map<const Value *, std::string> names;
  std::vector<std::string> regs, lines;
  unsigned constants = 0, temps = 0, expressions = 0;
  // Linked runtime microvectors may retain their explicitly supplied register
  // spelling. Source functions always use the canonical §16.3 numbering.
  bool runtimeNames() {return f.hasFnAttribute("bennett.runtime.locations");}
  std::map<std::string,std::string> runtimeConstants;

  std::map<const GlobalVariable *, std::string> globals;
  std::map<Function *, std::string> functions;
  Analysis *analysis = nullptr;
  unsigned width(Type *t) {
    if (t->isIntegerTy() && t->getIntegerBitWidth() <= 128)
      return t->getIntegerBitWidth();
    if (t->isPointerTy())
      return m.getDataLayout().getPointerTypeSizeInBits(t);
    if (t->isVoidTy())
      return 1;
    if (t->isFloatingPointTy())
      return t->getPrimitiveSizeInBits();
    if (auto *st = dyn_cast<StructType>(t)) {
      unsigned n = 0;
      for (Type *field : st->elements()) n += width(field);
      if (n && n <= 128) return n;
    }
    unimplemented("§12.6/§12.7 vector/aggregate/wide scalar", 2, &f);
  }
  void dest(std::string n, unsigned w) {
    regs.push_back(n + ":reg[" + std::to_string(w) + "]");
  }
  std::string constant(APInt n) {
    auto key=std::to_string(n.getBitWidth())+":"+number(n);
    if(runtimeNames() && runtimeConstants.count(key))return runtimeConstants[key];
    std::string s = "c" + std::to_string(constants++);
    if(runtimeNames()) {
      auto attr=f.getFnAttribute("bennett.runtime.constants").getValueAsString();
      SmallVector<StringRef> list;attr.split(list,',');
      if(constants<=list.size() && !list[constants-1].empty())s=list[constants-1].str();
      runtimeConstants[key]=s;
    }
    dest(s, n.getBitWidth());
    lines.push_back(s + " = lift.const.i" + std::to_string(n.getBitWidth()) +
                    " " + number(n));
    return s;
  }
  std::string temp(unsigned w, std::string row) {
    std::string s = "t" + std::to_string(temps++);
    dest(s, w);
    lines.push_back(s + " = " + row);
    return s;
  }
  std::string value(Value *v) {
    if (isa<UndefValue>(v) || isa<PoisonValue>(v) ||
        isa<ConstantPointerNull>(v))
      return constant(APInt(width(v->getType()), 0));
    if (auto *g = dyn_cast<GlobalVariable>(v)) {
      if (!globals.count(g)) unimplemented("§19.5 comparison global layout",2,g);
      if(runtimeNames() && names.count(g))return names[g];
      std::string n = "c" + std::to_string(constants++);
      if(runtimeNames()) {n="g";--constants;names[g]=n;}
      dest(n,width(g->getType())); lines.push_back(n+" = lift.addr @"+globals[g]); return n;
    }
    if (auto *c = dyn_cast<ConstantFP>(v))
      return constant(c->getValueAPF().bitcastToAPInt());
    if (auto *c = dyn_cast<ConstantInt>(v))
      return constant(c->getValue());
    if (auto *c = dyn_cast<ConstantExpr>(v)) {
      if (c->getOpcode() == Instruction::GetElementPtr)
        return gep(cast<GEPOperator>(c),
                   "expr" + std::to_string(expressions++));
      if (c->isCast()) {
        auto a = value(c->getOperand(0));
        unsigned from = width(c->getOperand(0)->getType()),
                 to = width(c->getType());
        if (from == to)
          return a;
        return temp(to,
                    std::string(from < to ? "lift.zext.i" : "lift.trunc.i") +
                        std::to_string(to) + " " + a);
      }
      unimplemented("§16.4 constant expression", 2, v);
    }
    if (names.count(v))
      return names[v];
    unimplemented("§16.4 non-scalar operand", 2, v);
  }
  std::string gep(GEPOperator *g, std::string output) {
    unsigned p = width(g->getType()),
             i = m.getDataLayout().getIndexTypeSizeInBits(g->getType());
    if (i > 128 || p > 128)
      unimplemented("§12.7 wide pointer limbs", 2, &f);
    std::string base = value(g->getPointerOperand()), acc = base;
    if (i < p)
      acc = temp(i, "lift.trunc.i" + std::to_string(i) + " " + base);
// collectOffset preserves insertion order of dynamic indices.
#if LLVM_VERSION_MAJOR >= 23
    SmallMapVector<Value *, APInt, 4> vars;
#else
    MapVector<Value *, APInt> vars;
#endif
    APInt off(i, 0);
    if (!g->collectOffset(m.getDataLayout(), i, vars, off))
      unimplemented("§16.4 GEP", 2, &f);
    std::vector<std::pair<Value *, APInt>> dynamic;
    for (auto &e : vars)
      dynamic.push_back(e);
    for (unsigned k = 0; k < dynamic.size(); ++k) {
      auto &e = dynamic[k];
      std::string idx = value(e.first);
      unsigned w = width(e.first->getType());
      if (w != i)
        idx = temp(i, std::string(w < i ? "lift.sext.i" : "lift.trunc.i") +
                          std::to_string(i) + " " + idx);
      if (e.second != 1) {
        auto c = constant(e.second);
        idx = temp(i, "lift.mul " + idx + " " + c);
      }
      bool last = k + 1 == dynamic.size() && off.isZero() && i == p;
      if (last && !output.empty()) {
        dest(output, p);
        lines.push_back(output + " = lift.add " + acc + " " + idx);
        acc = output;
      } else
        acc = temp(i, "lift.add " + acc + " " + idx);
    }
    if (!off.isZero()) {
      auto c = constant(off);
      if (i == p && !output.empty()) {
        dest(output, p);
        lines.push_back(output + " = lift.add " + acc + " " + c);
        acc = output;
      } else
        acc = temp(i, "lift.add " + acc + " " + c);
    }
    if (i < p) {
      auto lo = temp(p, "lift.zext.i" + std::to_string(p) + " " + acc);
      auto c = constant(APInt::getHighBitsSet(p, p - i));
      auto hi = temp(p, "lift.and " + base + " " + c);
      if (output.empty())
        return temp(p, "lift.or " + hi + " " + lo);
      dest(output, p);
      lines.push_back(output + " = lift.or " + hi + " " + lo);
      return output;
    }
    if (acc == base && !output.empty()) {
      dest(output, p);
      lines.push_back(output + " = lift.mov " + base);
      return output;
    }
    return acc;
  }
  std::string body() {
    unsigned k = 0;
    for (Argument &a : f.args())
      names[&a] = "a" + std::to_string(k++);
    k = 0;
    for (Instruction &i : instructions(f))
      if (!i.getType()->isVoidTy())
        names[&i] = runtimeNames() && i.hasName() ? i.getName().str() : "v" + std::to_string(k++);
    std::map<BasicBlock *, unsigned> blockIndex;
    k = 0;
    for (BasicBlock &b : f)
      blockIndex[&b] = k++;
    auto blockName = [&](BasicBlock *b) {
      return std::string("^b") + std::to_string(blockIndex[b]);
    };
    auto moves = [&](BasicBlock *from, BasicBlock *to) {
      std::vector<std::string> dst, src;
      for (PHINode &phi : to->phis()) {
        dst.push_back(names[&phi]);
        src.push_back(value(phi.getIncomingValueForBlock(from)));
        dest(names[&phi], width(phi.getType()));
      }
      if (!dst.empty())
        lines.push_back("(" + join(dst) + ") = lift.parmov (" + join(src) +
                        ")");
    };
    for (BasicBlock &bb : f) {
      lines.push_back(blockName(&bb) + "():");
      std::set<BasicBlock *> edgeBlocks;
      auto target = [&](BasicBlock *b) {
        if (b->phis().empty())
          return blockName(b);
        edgeBlocks.insert(b);
        return blockName(&bb) + ".e" + std::to_string(blockIndex[b]);
      };
      for (Instruction &i : bb) {
        if (isa<PHINode>(i))
          continue;
        auto branch=[&](Value *condition,BasicBlock *yes,BasicBlock *no) {
          if(!condition || yes==no) {moves(&bb,yes);lines.push_back("qjump "+blockName(yes));}
          else {auto cond=value(condition);auto y=target(yes),n=target(no);lines.push_back("qbranch "+cond+" "+y+" "+n);}
        };
#if LLVM_VERSION_MAJOR >= 23
        if(auto *br=dyn_cast<UncondBrInst>(&i)) {branch(nullptr,br->getSuccessor(0),nullptr);continue;}
        if(auto *br=dyn_cast<CondBrInst>(&i)) {branch(br->getCondition(),br->getSuccessor(0),br->getSuccessor(1));continue;}
#else
        if(auto *br=dyn_cast<BranchInst>(&i)) {branch(br->isUnconditional()?nullptr:br->getCondition(),br->getSuccessor(0),br->isUnconditional()?nullptr:br->getSuccessor(1));continue;}
#endif
        if(auto *br=dyn_cast<IndirectBrInst>(&i)) {
          auto address=value(br->getAddress());
          // §14.9: B(F)+k, with k counting non-entry address-taken blocks in
          // layout order. Comparison layout must provide the backing object.
          auto *object=m.getGlobalVariable("__bennett_rt_blk."+f.getName().str(),true);
          if(!object || !globals.count(object)) unimplemented("§14.9 blockaddress comparison layout",2,br);
          uint64_t base=4096;
          for(GlobalVariable &g:m.globals()) if(globals.count(&g)) {
            base=alignTo(base,m.getDataLayout().getPreferredAlign(&g));
            if(&g==object) break;
            base+=m.getDataLayout().getTypeAllocSize(g.getValueType()).getFixedValue();
          }
          std::vector<std::pair<uint64_t,BasicBlock *>> candidates;
          uint64_t ordinal=0;
          for(BasicBlock &b:f) if(&b!=&f.getEntryBlock() && b.hasAddressTaken()) {
            bool listed=false;
            for(unsigned k=0;k<br->getNumDestinations();++k) listed|=br->getDestination(k)==&b;
            if(listed) candidates.push_back({base+ordinal,&b});
            ++ordinal;
          }
          // Addresses are sorted by layout; the short-domain linear tree is
          // the <=3 leaf case of §14.2. Larger domains need its balanced tree.
          if(candidates.size()>3) unimplemented("§14.9 balanced indirectbr tree",2,br);
          for(unsigned k=0;k<candidates.size();++k) {
            if(k) lines.push_back(blockName(&bb)+".s"+std::to_string(k)+"():");
            auto c=constant(APInt(width(br->getAddress()->getType()),candidates[k].first));
            auto t=temp(1,"lift.icmp.eq "+address+" "+c);
            auto next=k+1<candidates.size()?blockName(&bb)+".s"+std::to_string(k+1):blockName(&bb)+".d";
            lines.push_back("qbranch "+t+" "+target(candidates[k].second)+" "+next);
          }
          lines.push_back(blockName(&bb)+".d():");lines.push_back("fault 4");
          continue;
        }
        if (auto *sw = dyn_cast<SwitchInst>(&i)) {
          std::string cond = value(sw->getCondition()),
                      fallback = target(sw->getDefaultDest());
          std::vector<std::pair<APInt, std::string>> keys;
          for (auto c : sw->cases())
            keys.emplace_back(c.getCaseValue()->getValue(),
                              target(c.getCaseSuccessor()));
          std::sort(keys.begin(), keys.end(),
                    [](auto &a, auto &b) { return a.first.ult(b.first); });
          // Allocate compare blocks in creation order; emit rows in that same
          // order.
          std::vector<std::string> ids = {blockName(&bb)};
          std::vector<std::vector<std::string>> chunks(1);
          auto newBlock = [&]() {
            unsigned n = ids.size();
            ids.push_back(blockName(&bb) + ".s" + std::to_string(n));
            chunks.emplace_back();
            return n;
          };
          std::function<void(int, int, unsigned)> tree = [&](int lo, int hi,
                                                             unsigned cur) {
            size_t begin = lines.size();
            if (hi < lo)
              lines.push_back("qjump " + fallback);
            else if (hi - lo + 1 <= 3) {
              for (int j = lo; j <= hi; ++j) {
                auto c = constant(keys[j].first);
                auto t = temp(1, "lift.icmp.eq " + cond + " " + c);
                unsigned next = j < hi ? newBlock() : 0;
                lines.push_back("qbranch " + t + " " + keys[j].second + " " +
                                (j < hi ? ids[next] : fallback));
                chunks[cur].insert(chunks[cur].end(), lines.begin() + begin,
                                   lines.end());
                lines.resize(begin);
                cur = next;
              }
              return;
            } else {
              int mid = (lo + hi) / 2;
              auto c = constant(keys[mid].first);
              auto t = temp(1, "lift.icmp.ult " + cond + " " + c);
              unsigned l = newBlock(), r = newBlock();
              lines.push_back("qbranch " + t + " " + ids[l] + " " + ids[r]);
              chunks[cur].insert(chunks[cur].end(), lines.begin() + begin,
                                 lines.end());
              lines.resize(begin);
              tree(lo, mid - 1, l);
              tree(mid, hi, r);
              return;
            }
            chunks[cur].insert(chunks[cur].end(), lines.begin() + begin,
                               lines.end());
            lines.resize(begin);
          };
          // Destinations must be numbered by output text order, not DFS
          // recursion order. Build shape above, then remap constants/temps by
          // first appearance below.
          tree(0, (int)keys.size() - 1, 0);
          for (unsigned n = 0; n < chunks.size(); ++n) {
            if (n)
              lines.push_back(ids[n] + "():");
            lines.insert(lines.end(), chunks[n].begin(), chunks[n].end());
          }
          continue;
        }
        if (auto *g = dyn_cast<GetElementPtrInst>(&i)) {
          gep(cast<GEPOperator>(g), names[&i]);
          continue;
        }
        if (auto *r = dyn_cast<ReturnInst>(&i)) {
          Value *rv = r->getReturnValue();
          std::string v = "r";
          if (rv && rv->getType()->isAggregateType()) {
            // §16.4: evaluate all flattened fields first, then pack without padding.
            std::vector<std::pair<std::string,unsigned>> parts;
            std::function<void(Constant *)> flatten = [&](Constant *c) {
              if (auto *st = dyn_cast<StructType>(c->getType())) {
                for (unsigned k = 0; k < st->getNumElements(); ++k) flatten(c->getAggregateElement(k));
              } else if (auto *at = dyn_cast<ArrayType>(c->getType())) {
                for (unsigned k = 0; k < at->getNumElements(); ++k) flatten(c->getAggregateElement(k));
              } else parts.emplace_back(value(c),width(c->getType()));
            };
            auto *aggregate = dyn_cast<Constant>(rv);
            if (!aggregate) unimplemented("§16.4 nonconstant aggregate return",2,r);
            flatten(aggregate); unsigned packed = width(rv->getType()), offset = 0;
            for (auto &part : parts) {
              auto n = part.first;
              if (part.second != packed) n = temp(packed,"lift.zext.i"+std::to_string(packed)+" "+n);
              if (offset) { auto c = constant(APInt(packed,offset)); n = temp(packed,"lift.shl "+n+" "+c); }
              v = offset ? temp(packed,"lift.or "+v+" "+n) : n;
              offset += part.second;
            }
          } else if (rv) v = value(rv);
          lines.push_back("lift.ret " + v);
          continue;
        }
        if (isa<UnreachableInst>(i)) {
          lines.push_back("fault 4");
          continue;
        }
        if (auto *call = dyn_cast<CallBase>(&i)) {
          if (auto *g = call->getCalledFunction();
              g && g->getName() == "__bennett_nz_fault") {
            auto *c = dyn_cast<ConstantInt>(call->getArgOperand(0));
            if (!c)
              unimplemented("§12.3 nonliteral fault", 2, call);
            lines.push_back("fault " + number(c->getValue()));
            break;
          }
          auto *g = call->getCalledFunction();
          if(!g)g=resolve(call->getCalledOperand());
          std::vector<std::string> args;
          for (Value *v : call->args()) args.push_back(value(v));
          auto name = g ? g->getName() : StringRef();
          if (name == "__bennett_nz_alloc") {
            dest(names[call],width(call->getType()));
            lines.push_back(names[call]+" = lift.alloc "+args[0]); continue;
          }
          if (name == "__bennett_nz_free") {lines.push_back("lift.free "+args[0]);continue;}
          auto result = names[call];
          if (call->getType()->isVoidTy()) {result="t"+std::to_string(temps++);dest(result,1);}
          else dest(result,width(call->getType()));
          if (g && functions.count(g)) {
            lines.push_back(result+" = lift.call @"+functions[g]+" ("+join(args)+")");continue;
          }
          if (!g && analysis) {
            auto candidates=analysis->candidates(call->getCalledOperand(),call->getFunctionType());
            std::vector<Function *> sorted(candidates.begin(),candidates.end());
            auto address=[](Function *f) -> uint64_t {
              auto *md=f->getMetadata("bennett.address");
              if (!md) unimplemented("§19.5 comparison function addresses",4,f);
              return cast<ConstantInt>(cast<ConstantAsMetadata>(md->getOperand(0))->getValue())->getZExtValue();
            };
            std::sort(sorted.begin(),sorted.end(),[&](auto *a,auto *b){return address(a)<address(b);});
            auto callee=value(call->getCalledOperand());
            unsigned ordinal=1;for (Instruction &prev:bb) {if (&prev==call) break;if(auto *c=dyn_cast<CallBase>(&prev)) if(!resolve(c->getCalledOperand())) ++ordinal;}
            auto prefix=blockName(&bb)+".q"+std::to_string(ordinal);
            unsigned serial=0;
            std::function<void(int,int)> tree=[&](int lo,int hi) {
              if(hi<lo) {lines.push_back("qjump "+prefix+"d");return;}
              if(hi-lo+1<=3) {
                for(int k=lo;k<=hi;++k) {
                  auto c=constant(APInt(width(call->getCalledOperand()->getType()),address(sorted[k])));
                  auto t=temp(1,"lift.icmp.eq "+callee+" "+c);
                  auto next=k<hi?blockName(&bb)+".s"+std::to_string(++serial):prefix+"d";
                  lines.push_back("qbranch "+t+" "+prefix+"c"+std::to_string(k)+" "+next);
                  if(k<hi) lines.push_back(next+"():");
                }
              } else {
                int mid=(lo+hi)/2;
                auto c=constant(APInt(width(call->getCalledOperand()->getType()),address(sorted[mid])));
                auto t=temp(1,"lift.icmp.ult "+callee+" "+c);
                auto l=blockName(&bb)+".s"+std::to_string(++serial),r=blockName(&bb)+".s"+std::to_string(++serial);
                lines.push_back("qbranch "+t+" "+l+" "+r);lines.push_back(l+"():");tree(lo,mid-1);lines.push_back(r+"():");tree(mid,hi);
              }
            };
            tree(0,int(sorted.size())-1);
            for(unsigned k=0;k<sorted.size();++k) {
              lines.push_back(prefix+"c"+std::to_string(k)+"():");
              lines.push_back(result+" = lift.call @"+functions.at(sorted[k])+" ("+join(args)+")");
              lines.push_back("qjump "+prefix+"r");
            }
            lines.push_back(prefix+"d():");lines.push_back("fault 4");lines.push_back(prefix+"r():");continue;
          }
          unimplemented("§14 calls (missing linked definition)", 2, call);
        }
        if (auto *l = dyn_cast<LoadInst>(&i)) {
          unsigned w = width(l->getType());
          if (w % 8) unimplemented("§12 N22 nonbyte load",2,l);
          auto p = value(l->getPointerOperand());lines.push_back("lift.boundscheck "+p+" "+std::to_string(w/8));
          dest(names[l],w);lines.push_back(names[l]+" = lift.load.i"+std::to_string(w)+" "+p);continue;
        }
        if (auto *st = dyn_cast<StoreInst>(&i)) {
          auto v=value(st->getValueOperand()),p=value(st->getPointerOperand());
          unsigned w=width(st->getValueOperand()->getType());
          if(w%8)unimplemented("§12 N22 nonbyte store",2,st);
          lines.push_back("lift.boundscheck "+p+" "+std::to_string(w/8));
          lines.push_back("lift.store.i"+std::to_string(w)+" "+p+" "+v);continue;
        }
        if (isa<AllocaInst>(i)) unimplemented("§17.3 shadow stack",2,&i);
        if (i.getType()->isFPOrFPVectorTy())
          unimplemented("§13 soft-float", 2, &i);
        std::string row;
        if (auto *c = dyn_cast<ICmpInst>(&i)) {
          auto a = value(c->getOperand(0)), b = value(c->getOperand(1));
          auto pred = c->getPredicate();
          if (pred == CmpInst::ICMP_UGT || pred == CmpInst::ICMP_UGE ||
              pred == CmpInst::ICMP_SGT || pred == CmpInst::ICMP_SGE) {
            pred = CmpInst::getSwappedPredicate(pred);
            std::swap(a, b);
          }
          row = "lift.icmp." + CmpInst::getPredicateName(pred).str() + " " + a +
                " " + b;
        } else if (auto *b = dyn_cast<BinaryOperator>(&i)) {
          auto a = value(b->getOperand(0)), c = value(b->getOperand(1));
          // ISA shifts define >=W as zero; the materialised scalar semantics
          // agrees.
          row = "lift." + std::string(b->getOpcodeName()) + " " + a + " " + c;
        } else if (auto *s = dyn_cast<SelectInst>(&i)) {
          auto c = value(s->getCondition()), a = value(s->getTrueValue()),
               b = value(s->getFalseValue());
          row = "lift.select " + c + " " + a + " " + b;
        } else if (auto *c = dyn_cast<CastInst>(&i)) {
          auto a = value(c->getOperand(0));
          unsigned from = width(c->getOperand(0)->getType()),
                   to = width(c->getType());
          std::string op = c->getOpcodeName();
          if (op == "ptrtoint" || op == "inttoptr" || op == "addrspacecast" ||
              op == "bitcast")
            op = from == to ? "mov" : from < to ? "zext" : "trunc";
          row = "lift." + op + (op == "mov" ? "" : ".i" + std::to_string(to)) +
                " " + a;
        } else if (isa<FreezeInst>(i))
          row = "lift.mov " + value(i.getOperand(0));
        else
          unimplemented("§16.4 scalar row", 2, &i);
        dest(names[&i], width(i.getType()));
        lines.push_back(names[&i] + " = " + row);
      }
      std::vector<BasicBlock *> sortedEdges(edgeBlocks.begin(),
                                            edgeBlocks.end());
      std::sort(sortedEdges.begin(), sortedEdges.end(), [&](auto *a, auto *b) {
        return blockIndex[a] < blockIndex[b];
      });
      for (auto *b : sortedEdges) {
        lines.push_back(blockName(&bb) + ".e" + std::to_string(blockIndex[b]) +
                        "():");
        moves(&bb, b);
        lines.push_back("qjump " + blockName(b));
      }
    }
    // Canonical first-destination order also renumbers compare-tree rows
    // emitted in creation order. Phi destinations are listed only once.
    std::map<std::string, unsigned> widths;
    for (auto &r : regs) {
      auto at = r.find(":reg[");
      widths[r.substr(0, at)] = std::stoul(r.substr(at + 5));
    }
    std::map<std::string, std::string> renames;
    unsigned cn = 0, tn = 0;
    for (auto &line : lines) {
      if(runtimeNames())break;
      auto eq = line.find(" = ");
      if (eq == std::string::npos)
        continue;
      auto dst = line.substr(0, eq);
      if (dst.size() > 1 && (dst[0] == 'c' || dst[0] == 't') &&
          std::isdigit(dst[1]) && !renames.count(dst))
        renames[dst] = std::string(1, dst[0]) +
                       std::to_string(dst[0] == 'c' ? cn++ : tn++);
    }
    std::vector<std::string> finalRegs;
    std::set<std::string> declared;
    for (auto &line : lines) {
      std::string replaced;
      std::regex token(R"(\b[ct][0-9]+\b)");
      size_t last = 0;
      for (std::sregex_iterator it(line.begin(), line.end(), token), end;
           it != end; ++it) {
        replaced += line.substr(last, it->position() - last);
        replaced += renames.count(it->str()) ? renames[it->str()] : it->str();
        last = it->position() + it->length();
      }
      replaced += line.substr(last);
      line = replaced;
      auto eq = line.find(" = ");
      if (eq != std::string::npos) {
        std::string dst = line.substr(0, eq);
        std::regex loc(R"([A-Za-z_][A-Za-z_0-9]*)");
        for (std::sregex_iterator it(dst.begin(), dst.end(), loc), end;
             it != end; ++it) {
          auto n = it->str();
          if (!declared.insert(n).second)
            continue;
          unsigned w = widths[n];
          for (auto &r : renames)
            if (r.second == n) {
              w = widths[r.first];
              break;
            }
          finalRegs.push_back(n + ":reg[" + std::to_string(w) + "]");
        }
      }
    }
    regs = finalRegs;
    std::vector<std::string> params;
    for (Argument &a : f.args())
      params.push_back(names[&a] + ":reg[" +
                       std::to_string(width(a.getType())) + "]");
    std::string b = "lproc @" + functions.at(&f) + " (" + join(params) + ") (r:reg[" +
                    std::to_string(width(f.getReturnType())) + "]) () () ()\n";
    if (!regs.empty())
      b += "regs { " + join(regs) + " }\n";
    b += join(lines, "\n");
    return b;
  }
};
std::string scalarGlobalKey(const GlobalVariable &g) {
  if(g.hasName())return "name:"+g.getName().str();
  unsigned ordinal=0;for(auto &v:g.getParent()->globals()) {if(&v==&g)break;++ordinal;}
  return "index:"+std::to_string(ordinal);
}
std::string scalarGlobalImage(GlobalVariable &g, const std::map<const GlobalVariable *,uint64_t> &bases) {
  auto &dl=g.getParent()->getDataLayout();
  uint64_t size=dl.getTypeAllocSize(g.getValueType()).getFixedValue();std::vector<uint8_t> bytes(size,0);
  std::function<void(Constant *,uint64_t)> image=[&](Constant *c,uint64_t off) {
    auto *t=c->getType();if(c->isNullValue() || isa<UndefValue>(c) || isa<PoisonValue>(c))return;
    if(auto *st=dyn_cast<StructType>(t)) {auto *sl=dl.getStructLayout(st);for(unsigned k=0;k<st->getNumElements();++k)image(c->getAggregateElement(k),off+sl->getElementOffset(k));return;}
    if(auto *at=dyn_cast<ArrayType>(t)) {for(unsigned k=0;k<at->getNumElements();++k)image(c->getAggregateElement(k),off+k*dl.getTypeAllocSize(at->getElementType()).getFixedValue());return;}
    APInt bits(1,0);
    if(auto *n=dyn_cast<ConstantInt>(c))bits=n->getValue();
    else if(auto *n=dyn_cast<ConstantFP>(c))bits=n->getValueAPF().bitcastToAPInt();
    else if(t->isPointerTy()) {
      auto pw=dl.getPointerSizeInBits(t->getPointerAddressSpace());APInt offset(pw,0);
      auto *root=c->stripAndAccumulateConstantOffsets(dl,offset,true);
      if(auto *target=dyn_cast<GlobalVariable>(root);target && bases.count(target))bits=APInt(pw,bases.at(target))+offset;
      else if(auto *f=dyn_cast<Function>(root);f && f->getMetadata("bennett.address")) bits=cast<ConstantInt>(cast<ConstantAsMetadata>(f->getMetadata("bennett.address")->getOperand(0))->getValue())->getValue().zextOrTrunc(pw)+offset;
      else if(auto *ce=dyn_cast<ConstantExpr>(c);ce && ce->getOpcode()==Instruction::IntToPtr && isa<ConstantInt>(ce->getOperand(0)))bits=cast<ConstantInt>(ce->getOperand(0))->getValue().zextOrTrunc(pw);
      else unimplemented("§19.5 global pointer relocation target",1,c);
    } else unimplemented("§19.5 vector data image",2,c);
    auto n=dl.getTypeStoreSize(t).getFixedValue();bits=bits.zextOrTrunc(n*8);
    for(unsigned k=0;k<n;++k)bytes[off+k]=bits.lshr((dl.isLittleEndian()?k:n-1-k)*8).getLimitedValue()&255;
  };
  if(!g.hasInitializer())unimplemented("§19.5 undefined data image",2,&g);
  image(g.getInitializer(),0);return toHex(ArrayRef<uint8_t>(bytes),true);
}
void lowerScalar(Module &m, Function &f, StringRef desc, StringRef out,
                 unsigned stackCells, uint64_t heapCapacity, int projection, std::map<std::string,std::string> *globalNames, uint64_t sstack) {
  if(auto *md=m.getModuleFlag("bennett.sstack"))sstack=cast<ConstantInt>(cast<ConstantAsMetadata>(md)->getValue())->getZExtValue();
  bool singleFrame=prepareStack(m,f,sstack);
  // Materialise every linked member before computing candidates and read dependencies.
  for (Function &g:m) if(!g.isDeclaration()) normaliseScalar(g);
  Analysis analysis(m); analysis.run();
  std::vector<Function *> closure;
  std::map<Function *,std::string> functions;
  std::function<void(Function *)> collect=[&](Function *g) {
    if(!g || g->isDeclaration() || functions.count(g)) return;
    functions[g]="L"+std::to_string(functions.size()+1);closure.push_back(g);
    for(Instruction &i:instructions(g)) if(auto *c=dyn_cast<CallBase>(&i)) {
      if(auto *target=c->getCalledFunction()) collect(target);
      else if(auto *target=resolve(c->getCalledOperand())) collect(target);
      else {
        auto targets=analysis.candidates(c->getCalledOperand(),c->getFunctionType());
        std::vector<Function *> sorted(targets.begin(),targets.end());
        std::sort(sorted.begin(),sorted.end(),[](auto *a,auto *b) {
          auto address=[](Function *f) {auto *md=f->getMetadata("bennett.address");if(!md) unimplemented("§19.5 comparison function addresses",4,f);return cast<ConstantInt>(cast<ConstantAsMetadata>(md->getOperand(0))->getValue())->getZExtValue();};return address(a)<address(b);
        });for(auto *target:sorted) collect(target);
      }
    }
  };
  auto flag=[&](StringRef name,uint64_t fallback) {auto *md=m.getModuleFlag(name);return md?cast<ConstantInt>(cast<ConstantAsMetadata>(md)->getValue())->getZExtValue():fallback;};
  sstack=flag("bennett.sstack",sstack);
  unsigned snapshot=flag("bennett.entry.snapshot",0);
  bool initialise=flag("bennett.ss.init",0);
  if(snapshot) collect(m.getFunction("__bennett_rt_entry_replay"));
  for(auto &g:m)for(auto &i:instructions(g))if(auto *c=dyn_cast<CallBase>(&i))if(c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_rt_ss_push")initialise=true;
  if(initialise)collect(m.getFunction("__bennett_rt_ss_init"));
  collect(&f);
  Scalar s{m, f}; s.functions=functions;s.analysis=&analysis;
  std::string d = desc.str(), device;
  uint64_t deviceSize = 0, heapLimit = heapCapacity;
  if (StringRef(d).starts_with("dev=")) d=";"+d;
  auto deviceStart = d.find(";dev=");
  if (deviceStart != std::string::npos) {
    auto deviceEnd = d.find(';', deviceStart + 1);
    device = d.substr(deviceStart + 5, deviceEnd - deviceStart - 5);
    d.erase(deviceStart, deviceEnd == std::string::npos ? std::string::npos : deviceEnd - deviceStart);
  }
  std::vector<std::pair<std::string,uint64_t>> devices;
  if (!device.empty()) {
    SmallVector<StringRef> parts; StringRef(device).split(parts,'+');
    for (auto part : parts) {
      std::smatch dev; auto value = part.str();
      if (!std::regex_match(value, dev, std::regex(R"((CLOCK|CLOCK_ARG|BLOCK|CONSOLE|ENTROPY)\(([0-9]+)\))")))
        fail("shape","invalid device binding",&f);
      devices.push_back({dev[1],std::stoull(dev[2])});
    }
  }
  auto hasDevice = [&](StringRef name) { for (auto &d : devices) if (d.first == name) return true; return false; };
  std::set<const GlobalVariable *> used;
  std::set<const Value *> seen;
  std::function<void(const Value *)> visit = [&](const Value *v) {
    if (!seen.insert(v).second) return;
    if (auto *g=dyn_cast<GlobalVariable>(v)) {
      used.insert(g); if(g->hasInitializer())visit(g->getInitializer());return;
    }
    if (isa<Function>(v)) return;
    if(auto *u=dyn_cast<User>(v))for(Value *a:u->operands())visit(a);
  };
  for(auto *g:closure) for(Instruction &i:instructions(g))for(Value *v:i.operands())visit(v);
  bool entropyPositionUsed=used.count(m.getGlobalVariable("__bennett_dev_entropy_pos",true));
  auto deviceGlobal = [&](StringRef suffix) -> GlobalVariable * {
    auto *g = m.getGlobalVariable("__bennett_dev_" + suffix.str(), true);
    if (!g) g = new GlobalVariable(m, Type::getInt64Ty(m.getContext()),false,GlobalValue::InternalLinkage,
      ConstantInt::get(Type::getInt64Ty(m.getContext()),0),"__bennett_dev_"+suffix.str());
    used.insert(g);
    return g;
  };
  for (auto &d : devices) {
    auto &device = d.first; auto deviceSize = d.second;
    if (device == "CLOCK" || device == "CLOCK_ARG") deviceGlobal("clock_c");
    if (device == "ENTROPY") { deviceGlobal("entropy_base"); deviceGlobal("entropy_size"); deviceGlobal("entropy_pos"); }
    if (device == "BLOCK") { deviceGlobal("block_base"); deviceGlobal("block_nsect"); }
    if (device == "CONSOLE") {
      deviceGlobal("console_buf"); deviceGlobal("console_L"); deviceGlobal("console_n");
      heapLimit = std::max(heapLimit, deviceSize);
    }
  }
  // The entry dependency decision precedes private allocation (§16.2). A
  // pointer supplied by OUT or read from this invocation's model buffer does
  // not name caller memory. An arbitrary ARG/loaded pointer still needs replay.
  std::set<const Argument *> privateArguments;
  std::regex bindingPattern(R"((IN|ARG|OUT|MEM_IN)\([^)]*\))");
  unsigned bindingIndex = 0;
  for (std::sregex_iterator it(d.begin(),d.end(),bindingPattern),end;it!=end;++it,++bindingIndex)
    if (((*it)[1] == "OUT" || (*it)[1] == "MEM_IN") && bindingIndex < f.arg_size()) privateArguments.insert(f.getArg(bindingIndex));
  // Track caller pointer parameters through uses and defined calls. Conversion
  // alone needs no bytes; a memory access requires an actual entry snapshot.
  std::set<Value *> pointerUses;
  std::function<bool(Value *)> memoryUse=[&](Value *v) {
    if(!pointerUses.insert(v).second)return false;
    for(User *u:v->users()) {
      if(auto *l=dyn_cast<LoadInst>(u);l && l->getPointerOperand()==v)return true;
      if(auto *st=dyn_cast<StoreInst>(u);st && st->getPointerOperand()==v)return true;
      if(auto *c=dyn_cast<CallBase>(u)) {
        auto *g=c->getCalledFunction();
        if(!g || g->isDeclaration())return true;
        for(unsigned j=0;j<c->arg_size();++j)if(c->getArgOperand(j)==v && memoryUse(g->getArg(j)))return true;
      } else if(isa<Instruction>(u) && !isa<ReturnInst>(u) && memoryUse(u))return true;
    }
    return false;
  };
  if(!snapshot) for(auto &a:f.args())if(a.getType()->isPointerTy() && !privateArguments.count(&a) && memoryUse(&a))
    unimplemented("§8.5 caller pointer snapshot transfer",2,&a);
  // The closure, rather than just its root, owns writes to private globals.
  for(Function &g:m) if(!functions.count(&g) && !g.hasFnAttribute("bennett.stack.internal"))
    for(Instruction &i:instructions(g)) if(auto *st=dyn_cast<StoreInst>(&i))
      if(auto *v=dyn_cast<GlobalVariable>(getUnderlyingObject(st->getPointerOperand()));v && used.count(v))
        unimplemented("§8.5 caller snapshot transfer",2,&i);
  unsigned gn=1;for(GlobalVariable &g:m.globals())if(used.count(&g))s.globals[&g]="G"+std::to_string(gn++);
  if (globalNames) for (auto &g : s.globals) (*globalNames)[g.second] = scalarGlobalKey(*g.first);
  unsigned ret = s.width(f.getReturnType());
  auto semi = d.find(';');
  std::string bindings = d.substr(0, semi);
  std::string target = semi == std::string::npos ? "" : d.substr(semi + 1);
  if (!target.empty() && !std::regex_match(target,std::regex(R"(tgt=(null|[0-9]+))")))
    unimplemented("§8.3 device descriptor bindings",2,&f);
  bool discard = d == "tgt=null" || target == "tgt=null";
  unsigned tgt = ret;
  if (StringRef(target).starts_with("tgt=")) {
    auto v = StringRef(target).drop_front(4);
    if (!discard && v.getAsInteger(10, tgt))
      fail("shape", "invalid target width");
  }
  if (projection < 0 && (tgt == 0 || tgt > 128))
    unimplemented("§8.6 wide outputs", 2, &f);
  std::regex pat(R"((IN|ARG|OUT|MEM_IN)\((\d+)(?:,(zext|sext))?\))");
  std::sregex_iterator it(bindings.begin(), bindings.end(), pat), end;
  std::vector<std::string> ins, args, invoke, insWidths, paramWidths, argTypes,
      wrapperRegs, wrapperRows, mems, memSigs;
  unsigned dn = 0;
  auto prologue = [&](std::string row) {
    auto n = "d" + std::to_string(dn++);
    wrapperRegs.push_back(n + ":reg[64]");
    wrapperRows.push_back(n + " = " + row);
    return n;
  };
  auto devStore = [&](StringRef suffix, std::string value) {
    auto p = prologue("lift.addr @" + s.globals[deviceGlobal(suffix)]);
    wrapperRows.push_back("lift.boundscheck " + p + " 8");
    wrapperRows.push_back("lift.store.i64 " + p + " " + value);
  };
  if(snapshot) {
    mems.push_back("s0:region["+std::to_string(snapshot)+",8] in");
    memSigs.push_back("{\"A\":"+std::to_string(snapshot)+",\"W\":8,\"role\":\"in\"}");
    wrapperRegs.push_back("s:reg[64]");wrapperRows.push_back("s = lift.addr @s0");
    wrapperRegs.push_back("d0:reg[1]");wrapperRows.push_back("d0 = lift.call @"+functions.at(m.getFunction("__bennett_rt_entry_replay"))+" (s)");
  }
  if(initialise) {
    wrapperRegs.push_back("c0:reg[64]");wrapperRows.push_back("c0 = lift.const.i64 "+std::to_string(sstack));
    // The fixed §9.2 linked-input wrapper spells its init result d0.
    // Keep existing object bytes for all other wrappers.
    auto loc=snapshot?"d1":singleFrame?"d0":"t0";wrapperRegs.push_back(std::string(loc)+":reg[1]");
    wrapperRows.push_back(std::string(loc)+" = lift.call @"+functions.at(m.getFunction("__bennett_rt_ss_init"))+" (c0)");
  }
  std::string buffer;
  uint64_t bufferSize = 0;
  std::vector<std::pair<std::string,uint64_t>> outputBuffers;
  std::pair<std::string,uint64_t> consoleBuffer;
  for (auto &d : devices) {
  auto &device = d.first; auto deviceSize = d.second;
  if (device == "CLOCK" || device == "CLOCK_ARG") {
    auto c = device=="CLOCK" ? prologue("lift.const.i64 " + std::to_string(deviceSize)) : prologue("lift.mov clock_initial");
    if(device=="CLOCK_ARG"){args.push_back("clock_initial:i64");argTypes.push_back("\"i64\"");}
    devStore("clock_c", c);
  } else if (device == "ENTROPY") {
    if (deviceSize > 54) fail("shape", "ENTROPY extent exceeds address space");
    mems.push_back("e0:region[" + std::to_string(deviceSize) + ",8] in");
    memSigs.push_back("{\"A\":" + std::to_string(deviceSize) + ",\"W\":8,\"role\":\"in\"}");
    auto p = prologue("lift.addr @e0"); devStore("entropy_base", p);
    auto n = prologue("lift.const.i64 " + std::to_string(uint64_t(1) << deviceSize)); devStore("entropy_size", n);
    // Preserve the already published plugin bytes of an unused model binding.
    // A consuming closure (the §16.8 linked model) starts pos at its data image.
    if(!entropyPositionUsed) {auto z=prologue("lift.const.i64 0");devStore("entropy_pos",z);}

  } else if (device == "BLOCK") {
    if (deviceSize > 54) fail("shape", "BLOCK extent exceeds address space");
    mems.push_back("k0:region[" + std::to_string(deviceSize + 9) + ",8] in");
    memSigs.push_back("{\"A\":" + std::to_string(deviceSize + 9) + ",\"W\":8,\"role\":\"in\"}");
    auto p = prologue("lift.addr @k0"); devStore("block_base", p);
    auto n = prologue("lift.const.i64 " + std::to_string(uint64_t(1) << deviceSize));
    devStore("block_nsect", n);
  } else if (device == "CONSOLE") {
    auto n = prologue("lift.const.i64 " + std::to_string(deviceSize));
    devStore("console_L", n);
    buffer = prologue("lift.alloc " + n); devStore("console_buf", buffer);
    bufferSize = deviceSize; consoleBuffer = {buffer,bufferSize};
    auto z = prologue("lift.const.i64 0"); devStore("console_n", z);
    if (!deviceSize) buffer.clear();
  }
  }
  uint64_t outputBytes = consoleBuffer.second;
  unsigned idx = 0, inCount = 0, argCount = 0;
  std::string reconstructed;
  for (; it != end; ++it) {
    if (!reconstructed.empty())
      reconstructed += ",";
    reconstructed += it->str();
    if (idx >= f.arg_size())
      fail("shape", "too many scalar bindings");
    unsigned w = std::stoul((*it)[2]),
             param = s.width(f.getArg(idx)->getType());
    paramWidths.push_back(std::to_string(param));
    if ((*it)[1] == "IN") {
      if (w > param || !w)
        fail("shape", "invalid IN width");
      std::string n = "x" + std::to_string(inCount++);
      ins.push_back(n + ":wire[" + std::to_string(w) + "] in");
      insWidths.push_back(std::to_string(w));
      if (w < param) {
        auto loc = "w" + std::to_string(idx);
        wrapperRegs.push_back(loc + ":reg[" + std::to_string(param) + "]");
        wrapperRows.push_back(loc + " = lift." +
                              ((*it)[3] == "sext" ? "sext" : "zext") + ".i" +
                              std::to_string(param) + " " + n);
        n = loc;
      }
      invoke.push_back(n);
    } else if ((*it)[1] == "MEM_IN") {
      if (!f.getArg(idx)->getType()->isPointerTy() || !isPowerOf2_64(w))
        fail("shape", "MEM_IN requires a pointer and power-of-two size");
      auto n = "m" + std::to_string(idx), loc = "w" + std::to_string(idx);
      auto a = Log2_64(w);
      mems.push_back(n + ":region[" + std::to_string(a) + ",8] in");
      memSigs.push_back("{\"A\":" + std::to_string(a) + ",\"W\":8,\"role\":\"in\"}");
      wrapperRegs.push_back(loc + ":reg[64]");
      wrapperRows.push_back(loc + " = lift.addr @" + n);
      invoke.push_back(loc);
    } else if ((*it)[1] == "OUT") {
      if (!f.getArg(idx)->getType()->isPointerTy()) fail("shape", "OUT requires a pointer parameter");
      if (!buffer.empty() && projection < 0) unimplemented("§8.6 common multi-output delivery", 2, &f);
      auto c = "c" + std::to_string(idx), loc = "w" + std::to_string(idx);
      wrapperRegs.push_back(c + ":reg[64]");
      wrapperRows.push_back(c + " = lift.const.i64 " + std::to_string(w));
      wrapperRegs.push_back(loc + ":reg[64]");
      wrapperRows.push_back(loc + " = lift.alloc " + c);
      invoke.push_back(loc); buffer = loc; bufferSize = w; outputBuffers.push_back({loc,w});
      if (projection < 0) heapLimit = std::max(heapLimit, uint64_t(w));
      else { outputBytes += w; heapLimit = std::max(heapLimit,outputBytes); }
    } else {
      if (w != param)
        fail("shape", "ARG carrier width mismatch");
      std::string n = "a" + std::to_string(argCount++);
      args.push_back(n + ":i" + std::to_string(w));
      argTypes.push_back("\"i" + std::to_string(w) + "\"");
      invoke.push_back(n);
    }
    ++idx;
  }
  if (idx != f.arg_size() || (!bindings.empty() && reconstructed != bindings &&
                              bindings != "tgt=null"))
    unimplemented("§8 descriptor shape", 2, &f);
  unsigned returnTarget = tgt;
  bool returnDiscard = discard;
  if (discard)
    tgt = 1;
  std::map<std::string,std::string> bodies, signatures;
  std::string lproc;
  for(auto *g:closure) {
    Scalar member{m,*g};member.globals=s.globals;member.functions=functions;member.analysis=&analysis;
    auto name=functions[g];bodies[name]=member.body();
    std::vector<std::string> widths;for(auto &a:g->args())widths.push_back(std::to_string(member.width(a.getType())));
    signatures[name]="{\"abi\":\"0.8\",\"kind\":\"lproc\",\"params\":["+join(widths,",")+"],\"result\":"+std::to_string(member.width(g->getReturnType()))+",\"tier\":\"q\"}";
    if(!lproc.empty())lproc+="\n";lproc+=bodies[name];
  }
  wrapperRegs.push_back("r:reg[" + std::to_string(ret) + "]");
  wrapperRows.push_back("r = lift.call @" + functions.at(&f) + " (" + join(invoke) + ")");
  if (projection >= 0) {
    if (!consoleBuffer.first.empty() && consoleBuffer.second) outputBuffers.push_back(consoleBuffer);
    std::vector<std::pair<std::string,unsigned>> projections;
    if (!returnDiscard) {
      // Return payloads use zero extension; narrowed nonzero dropped bits fault.
      auto n = std::min(returnTarget,128u);
      std::string value = "r";
      if (n != ret) {
        value = "return0"; wrapperRegs.push_back(value + ":reg[" + std::to_string(n) + "]");
        if (n < ret) {
          auto shift = "returnShift", dropped = "returnDropped", zero = "returnZero", bad = "returnBad";
          wrapperRegs.push_back(std::string(shift)+":reg["+std::to_string(ret)+"]"); wrapperRows.push_back(std::string(shift)+" = lift.const.i"+std::to_string(ret)+" "+std::to_string(n));
          wrapperRegs.push_back(std::string(dropped)+":reg["+std::to_string(ret)+"]"); wrapperRows.push_back(std::string(dropped)+" = lift.lshr r "+shift);
          wrapperRegs.push_back(std::string(zero)+":reg["+std::to_string(ret)+"]"); wrapperRows.push_back(std::string(zero)+" = lift.const.i"+std::to_string(ret)+" 0");
          wrapperRegs.push_back(std::string(bad)+":reg[1]"); wrapperRows.push_back(std::string(bad)+" = lift.icmp.ne "+dropped+" "+zero); wrapperRows.push_back(std::string("lift.faultif ")+bad+" 4");
        }
        wrapperRows.push_back(value + (n < ret ? " = lift.trunc.i" : " = lift.zext.i") + std::to_string(n) + " r");
      }
      projections.push_back({value,n});
      for (unsigned lo=128;lo<returnTarget;lo+=128) {
        auto w=std::min(128u,returnTarget-lo); auto p="return"+std::to_string(lo);
        wrapperRegs.push_back(p+":reg["+std::to_string(w)+"]");wrapperRows.push_back(p+" = lift.const.i"+std::to_string(w)+" 0");projections.push_back({p,w});
      }
    }
    for (auto &out : outputBuffers) for (uint64_t lo=0;lo<out.second;lo+=16) {
      auto bytes=std::min(uint64_t(16),out.second-lo), w=bytes*8; auto p="payload"+std::to_string(projections.size()); auto address=out.first;
      if (lo) { auto offset=prologue("lift.const.i64 "+std::to_string(lo)); address=prologue("lift.add "+out.first+" "+offset); }
      wrapperRegs.push_back(p+":reg["+std::to_string(w)+"]");wrapperRows.push_back("lift.boundscheck "+address+" "+std::to_string(bytes));
      wrapperRows.push_back(p+" = lift.load.i"+std::to_string(w)+" "+address);projections.push_back({p,unsigned(w)});
    }
    if (unsigned(projection)>=projections.size()) fail("shape","output projection index",&f);
    tgt=projections[projection].second;wrapperRows.push_back("lift.retval "+projections[projection].first);
  } else if (discard) {
    wrapperRegs.push_back("p0:reg[1]");
    wrapperRows.push_back("p0 = lift.const.i1 0");
    wrapperRows.push_back("lift.retval p0");
  } else if (!buffer.empty()) {
    if (!f.getReturnType()->isVoidTy() || bufferSize * 8 != tgt)
      unimplemented("§8.6 common multi-slice delivery", 2, &f);
    if (tgt % 8) fail("shape", "non-byte buffer delivery");
    wrapperRegs.push_back("t0:reg[" + std::to_string(tgt) + "]");
    wrapperRows.push_back("lift.boundscheck " + buffer + " " + std::to_string(tgt / 8));
    wrapperRows.push_back("t0 = lift.load.i" + std::to_string(tgt) + " " + buffer);
    wrapperRows.push_back("lift.retval t0");
  } else if (tgt != ret) {
    if(tgt<ret) {
      wrapperRegs.push_back("c0:reg["+std::to_string(ret)+"]");wrapperRows.push_back("c0 = lift.const.i"+std::to_string(ret)+" "+std::to_string(tgt));
      wrapperRegs.push_back("t0:reg["+std::to_string(ret)+"]");wrapperRows.push_back("t0 = lift.lshr r c0");
      wrapperRegs.push_back("c1:reg["+std::to_string(ret)+"]");wrapperRows.push_back("c1 = lift.const.i"+std::to_string(ret)+" 0");
      wrapperRegs.push_back("t1:reg[1]");wrapperRows.push_back("t1 = lift.icmp.ne t0 c1");wrapperRows.push_back("lift.faultif t1 4");
    }
    auto n=tgt<ret?"t2":"t0";wrapperRegs.push_back(std::string(n)+":reg["+std::to_string(tgt)+"]");
    wrapperRows.push_back(std::string(n)+" = lift."+(tgt<ret?"trunc":"zext")+".i"+std::to_string(tgt)+" r");wrapperRows.push_back(std::string("lift.retval ")+n);
  }
  else
    wrapperRows.push_back("lift.retval r");
  std::string wrapper = "oracle @ref (" + join(ins) + ") (tgt:wire[" +
                        std::to_string(tgt) + "]) (fault:wire[4]) (" + join(mems) + ") (" +
                        join(args) + ")\nregs { " + join(wrapperRegs) +
                        " }\n^entry():\n" + join(wrapperRows, "\n");
  std::string lsig = "{\"abi\":\"0.8\",\"kind\":\"lproc\",\"params\":[" +
                     join(paramWidths, ",") +
                     "],\"result\":" + std::to_string(ret) + ",\"tier\":\"q\"}";
  std::string osig =
      "{\"abi\":\"0.8\",\"args\":[" + join(argTypes, ",") +
      "],\"fault\":4,\"in\":[" + join(insWidths, ",") +
      "],\"kind\":\"oracle\",\"mem\":[" + join(memSigs, ",") + "],\"tgt\":" + std::to_string(tgt) +
      ",\"tier\":\"q\"}";
  unsigned sc = 0;
  while ((uint64_t(1) << sc) < stackCells)
    ++sc;
  unsigned pw = m.getDataLayout().getPointerSizeInBits();
  std::string prefix = "isa=0.8\nptr_width=" + std::to_string(pw) + "\n";
  // M1 standalone comparison layout: globals in link/module order, data at
  // 4096, heap at the next page, no heap allocations. Driver-supplied layouts M4.
  std::map<std::string,std::string> data, globalLeaves, dataSigs, dataHashes;
  uint64_t nullSize=flag("bennett.null_size",4096);
  uint64_t base=nullSize;std::map<const GlobalVariable *,uint64_t> globalBases;
  for(GlobalVariable &g:m.globals())if(s.globals.count(&g)) {base=alignTo(base,m.getDataLayout().getPreferredAlign(&g));globalBases[&g]=base;base+=m.getDataLayout().getTypeAllocSize(g.getValueType()).getFixedValue();}
  for(GlobalVariable &g:m.globals())if(s.globals.count(&g)) {
    auto size=m.getDataLayout().getTypeAllocSize(g.getValueType()).getFixedValue();
    auto hex=scalarGlobalImage(g,globalBases),name=s.globals[&g];
    data[name]=hex;
    dataSigs[name]="{\"abi\":\"0.8\",\"kind\":\"data\",\"size\":"+std::to_string(size)+",\"tier\":\"-\"}";
    dataHashes[name]=sha(prefix+dataSigs[name]+"\n"+name+" "+hex+"\n");
    globalLeaves[name]="{\"base\":"+std::to_string(globalBases[&g])+",\"image\":\""+name+"\",\"size\":"+std::to_string(size)+"}";
  }
  uint64_t heap=flag("bennett.heap_base",alignTo(base,uint64_t(4096)));unsigned h=0,at=0;
  uint64_t endAddress = flag("bennett.region_base",heap + heapLimit);
  std::string regionLayout, regionHashLeaves;
  for (auto &d : devices) if (d.first == "BLOCK") {
    uint64_t size = uint64_t(1) << (d.second + 9);
    uint64_t regionBase = alignTo(endAddress, size);
    auto leaf = "{\"base\":" + std::to_string(regionBase) + "}";
    regionLayout = "\"k0\":" + leaf;
    regionHashLeaves = "layout interface_regions.ref.k0 " + leaf + "\n";
    endAddress = regionBase + size;
  }
  for (auto &mem : mems) {
    std::smatch parts;
    if (!std::regex_search(mem, parts, std::regex(R"(([mes][0-9]+):region\[([0-9]+),8\])"))) continue;
    uint64_t size = uint64_t(1) << std::stoul(parts[2]);
    auto leaf = "{\"base\":" + std::to_string(alignTo(endAddress, size)) + "}";
    if (!regionLayout.empty()) regionLayout += ",";
    regionLayout += "\"" + parts[1].str() + "\":" + leaf;
    regionHashLeaves += "layout interface_regions.ref." + parts[1].str() + " " + leaf + "\n";
    endAddress = alignTo(endAddress, size) + size;
  }
  while((uint64_t(1)<<h)<endAddress)++h;
  while((uint64_t(1)<<at)<data.size()+mems.size()+heapLimit)++at;
  std::string images,globalLayout,globalHashLeaves,dataSection,refs;
  for(auto &e:data) {
    images+="data "+e.first+" "+e.second+"\n";
    if(!globalLayout.empty())globalLayout+=",";
    globalLayout+="\""+e.first+"\":"+globalLeaves[e.first];
    globalHashLeaves+="layout globals."+e.first+" "+globalLeaves[e.first]+"\n";
    dataSection+=e.first+" "+e.second+"\n";
  }
  // Hash the complete call graph in SCC dependency order (ISA §9.2).
  std::map<std::string,std::string> hashes=dataHashes;
  std::map<std::string,std::set<std::string>> edges;
  std::regex symbolToken(R"(@([LG][0-9]+)\b)");
  for(auto &b:bodies) {
    auto rest=b.second.substr(b.second.find('\n')+1);
    for(std::sregex_iterator it(rest.begin(),rest.end(),symbolToken),end;it!=end;++it)
      if(bodies.count((*it)[1]))edges[b.first].insert((*it)[1]);
  }
  auto reaches=[&](std::string from,std::string to) {
    std::set<std::string> seen;std::function<bool(std::string)> walk=[&](std::string n) {if(n==to)return true;if(!seen.insert(n).second)return false;for(auto &v:edges[n])if(walk(v))return true;return false;};return walk(from);
  };
  std::function<void(std::string)> hashMember=[&](std::string n) {
    if(hashes.count(n))return;
    std::vector<std::string> group;
    for(auto &b:bodies)if(reaches(n,b.first)&&reaches(b.first,n))group.push_back(b.first);
    bool cyclic=group.size()>1 || edges[n].count(n);
    std::set<std::string> members(group.begin(),group.end());
    for(auto &g:group)for(auto &e:edges[g])if(!members.count(e))hashMember(e);
    std::string envelopes;
    for(auto &g:group) {
      auto newline=bodies[g].find('\n');auto rest=bodies[g].substr(newline+1);
      std::string canonical=bodies[g].substr(0,newline+1),refs;size_t last=0;std::set<std::string> referenced;
      for(std::sregex_iterator it(rest.begin(),rest.end(),symbolToken),end;it!=end;++it) {
        auto v=(*it)[1].str();std::string replacement;
        if(cyclic && members.count(v)) replacement="$"+std::to_string(std::find(group.begin(),group.end(),v)-group.begin());
        else {replacement=hashes.at(v);if(referenced.insert(v).second)refs+=replacement+"\n";}
        canonical+=rest.substr(last,it->position()-last)+"@"+replacement;last=it->position()+it->length();
      }
      canonical+=rest.substr(last);std::string images,leaves;
      for(auto &v:data)if(referenced.count(v.first)) {images+="data "+v.first+" "+v.second+"\n";leaves+="layout globals."+v.first+" "+globalLeaves[v.first]+"\n";}
      envelopes+=prefix+signatures[g]+"\n"+canonical+"\n"+images+leaves+refs;
    }
    auto h=sha(envelopes);
    for(unsigned i=0;i<group.size();++i)hashes[group[i]]=cyclic?sha(h+":"+std::to_string(i)):h;
  };
  for(auto &b:bodies)hashMember(b.first);
  std::string canonical, wrapperRefs; size_t last = 0; std::set<std::string> referenced;
  std::regex wrapperToken(R"(@(L[0-9]+|G[0-9]+)\b)");
  for (std::sregex_iterator it(wrapper.begin(),wrapper.end(),wrapperToken),end;it!=end;++it) {
    auto n = it->str().substr(1), hash = hashes.at(n);
    if (referenced.insert(n).second) wrapperRefs += hash + "\n";
    canonical += wrapper.substr(last,it->position()-last) + "@" + hash;
    last = it->position()+it->length();
  }
  canonical += wrapper.substr(last);
  std::string leaves="layout A_tab "+std::to_string(at)+"\nlayout H "+std::to_string(h)+"\nlayout S_cells "+std::to_string(sc)+"\n"+globalHashLeaves+
    "layout heap_base "+std::to_string(heap)+"\nlayout heap_limit_max "+std::to_string(heapLimit)+"\n"+regionHashLeaves+"layout null_size "+std::to_string(nullSize)+"\nlayout ptr_width "+std::to_string(pw)+"\n";
  std::string oh=sha(prefix+osig+"\n"+canonical+"\n"+images+leaves+wrapperRefs);
  std::string symbols="{\"0\":{\"interface_hash\":\""+oh+"\",\"kind\":\"oracle\",\"name\":\"ref\",\"signature\":"+osig+"}";
  unsigned si=1;
  for(auto *g:closure) {auto n=functions[g];symbols+=",\""+std::to_string(si++)+"\":{\"interface_hash\":\""+hashes[n]+"\",\"kind\":\"lproc\",\"name\":\""+n+"\",\"signature\":"+signatures[n]+"}";}
  for(auto &e:data)symbols+=",\""+std::to_string(si++)+"\":{\"interface_hash\":\""+dataHashes[e.first]+"\",\"kind\":\"data\",\"name\":\""+e.first+"\",\"signature\":"+dataSigs[e.first]+"}";
  symbols+="}";
  auto parsedSymbols=json::parse(symbols);if(!parsedSymbols)fail("output",toString(parsedSymbols.takeError()));
  symbols=canonicalJSON(*parsedSymbols);
  std::string layout="{\"A_tab\":"+std::to_string(at)+",\"H\":"+std::to_string(h)+",\"S_cells\":"+std::to_string(sc)+",\"globals\":{"+globalLayout+"},\"heap_base\":"+std::to_string(heap)+",\"heap_limit_max\":"+std::to_string(heapLimit)+",\"interface_regions\":{\"ref\":{"+regionLayout+"}},\"null_size\":"+std::to_string(nullSize)+",\"ptr_width\":"+std::to_string(pw)+"}";
  if (auto ec = sys::fs::create_directories(out))
    fail("output", ec.message());
  SmallString<256> path(out);
  sys::path::append(path, "ref.bennett");
  std::error_code ec;
  raw_fd_ostream o(path, ec);
  if (ec)
    fail("output", ec.message());
  o << "bennett-object isa=0.8 object=0.8 launch=0.8 sched=0.8 cert=0.8 "
       "coverage=0.8 target=0.8 ptr_width="
    << pw << "\n\nsection symbols\n"
    << symbols << "\n\nsection functions\n"
    << wrapper << "\n"
    << lproc << (dataSection.empty() ? "" : "\n\nsection data\n" + StringRef(dataSection).rtrim().str()) << "\n\nsection layout\n"
    << layout << "\n";
  errs() << "bennett: scalar reference object " << path << "\n";
}
} // namespace bennett
