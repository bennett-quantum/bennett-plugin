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
struct Scalar {
  Module &m;
  Function &f;
  std::map<const Value *, std::string> names;
  std::vector<std::string> regs, lines;
  unsigned constants = 0, temps = 0, expressions = 0;
  std::map<const GlobalVariable *, std::string> globals;
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
    std::string s = "c" + std::to_string(constants++);
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
      std::string n = "c" + std::to_string(constants++);
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
        names[&i] = "v" + std::to_string(k++);
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
        if (auto *br = dyn_cast<BranchInst>(&i)) {
          if (br->isUnconditional() ||
              br->getSuccessor(0) == br->getSuccessor(1)) {
            moves(&bb, br->getSuccessor(0));
            lines.push_back("qjump " + blockName(br->getSuccessor(0)));
          } else {
            auto cond = value(br->getCondition());
            auto yes = target(br->getSuccessor(0)),
                 no = target(br->getSuccessor(1));
            lines.push_back("qbranch " + cond + " " + yes + " " + no);
          }
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
          unimplemented("§14 calls", 2, call);
        }
        if (auto *l = dyn_cast<LoadInst>(&i)) {
          unsigned w = width(l->getType());
          if (w % 8) unimplemented("§12 N22 nonbyte load",2,l);
          auto p = value(l->getPointerOperand());lines.push_back("lift.boundscheck "+p+" "+std::to_string(w/8));
          dest(names[l],w);lines.push_back(names[l]+" = lift.load.i"+std::to_string(w)+" "+p);continue;
        }
        if (auto *st = dyn_cast<StoreInst>(&i)) {
          auto p=value(st->getPointerOperand()),v=value(st->getValueOperand());
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
        std::regex loc(R"([A-Za-z]+[0-9]+)");
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
    std::string b = "lproc @L1 (" + join(params) + ") (r:reg[" +
                    std::to_string(width(f.getReturnType())) + "]) () () ()\n";
    if (!regs.empty())
      b += "regs { " + join(regs) + " }\n";
    b += join(lines, "\n");
    return b;
  }
};
void lowerScalar(Module &m, Function &f, StringRef desc, StringRef out,
                 unsigned stackCells) {
  Scalar s{m, f};
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
  for(Instruction &i:instructions(f))for(Value *v:i.operands())visit(v);
  for(Instruction &i:instructions(f)) {
    Value *p=nullptr;
    if(auto *l=dyn_cast<LoadInst>(&i))p=l->getPointerOperand();
    if(auto *st=dyn_cast<StoreInst>(&i))p=st->getPointerOperand();
    if(p && !isa<GlobalVariable>(getUnderlyingObject(p)))
      unimplemented("§8.5 entry-state replay / §17.3 shadow-stack memory",2,&i);
  }
  // A mutable global written outside this closure needs caller-entry replay.
  // Until M2 that dependency must fail, rather than silently reset its bytes.
  for(Function &g:m)if(&g!=&f)
    for(Instruction &i:instructions(g)) {
      if(auto *st=dyn_cast<StoreInst>(&i))
        if(auto *v=dyn_cast<GlobalVariable>(getUnderlyingObject(st->getPointerOperand()));v && used.count(v))
          unimplemented("§8.5 mutable global entry-state replay",2,&i);
    }
  unsigned gn=1;for(GlobalVariable &g:m.globals())if(used.count(&g))s.globals[&g]="G"+std::to_string(gn++);
  unsigned ret = s.width(f.getReturnType());
  std::string d = desc.str();
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
  if (tgt == 0 || tgt > 128)
    unimplemented("§8.6 wide outputs", 2, &f);
  std::regex pat(R"((IN|ARG)\((\d+)(?:,(zext|sext))?\))");
  std::sregex_iterator it(bindings.begin(), bindings.end(), pat), end;
  std::vector<std::string> ins, args, invoke, insWidths, paramWidths, argTypes,
      wrapperRegs, wrapperRows;
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
  if (discard)
    tgt = 1;
  std::string lproc = s.body();
  wrapperRegs.push_back("r:reg[" + std::to_string(ret) + "]");
  wrapperRows.push_back("r = lift.call @L1 (" + join(invoke) + ")");
  if (discard) {
    wrapperRegs.push_back("p0:reg[1]");
    wrapperRows.push_back("p0 = lift.const.i1 0");
    wrapperRows.push_back("lift.retval p0");
  } else if (tgt != ret)
    unimplemented("§8.2 target extension/truncation", 2, &f);
  else
    wrapperRows.push_back("lift.retval r");
  std::string wrapper = "oracle @ref (" + join(ins) + ") (tgt:wire[" +
                        std::to_string(tgt) + "]) (fault:wire[4]) () (" +
                        join(args) + ")\nregs { " + join(wrapperRegs) +
                        " }\n^entry():\n" + join(wrapperRows, "\n");
  std::string lsig = "{\"abi\":\"0.8\",\"kind\":\"lproc\",\"params\":[" +
                     join(paramWidths, ",") +
                     "],\"result\":" + std::to_string(ret) + ",\"tier\":\"q\"}";
  std::string osig =
      "{\"abi\":\"0.8\",\"args\":[" + join(argTypes, ",") +
      "],\"fault\":4,\"in\":[" + join(insWidths, ",") +
      "],\"kind\":\"oracle\",\"mem\":[],\"tgt\":" + std::to_string(tgt) +
      ",\"tier\":\"q\"}";
  unsigned sc = 0;
  while ((uint64_t(1) << sc) < stackCells)
    ++sc;
  unsigned pw = m.getDataLayout().getPointerSizeInBits();
  std::string prefix = "isa=0.8\nptr_width=" + std::to_string(pw) + "\n";
  // M1 standalone comparison layout: globals in link/module order, data at
  // 4096, heap at the next page, no heap allocations. Driver-supplied layouts M4.
  std::map<std::string,std::string> data, globalLeaves, dataSigs, dataHashes;
  uint64_t base=4096;
  for(GlobalVariable &g:m.globals())if(s.globals.count(&g)) {
    if(!g.hasInitializer())unimplemented("§19.5 undefined data image",2,&g);
    auto &dl=m.getDataLayout();uint64_t size=dl.getTypeAllocSize(g.getValueType()).getFixedValue();
    base=alignTo(base,dl.getPreferredAlign(&g));
    std::vector<uint8_t> bytes(size,0);
    std::function<void(Constant *,uint64_t)> image=[&](Constant *c,uint64_t off) {
      Type *t=c->getType();
      if(c->isNullValue())return;
      if(isa<UndefValue>(c)||isa<PoisonValue>(c))return;
      if(auto *st=dyn_cast<StructType>(t)) {auto *sl=dl.getStructLayout(st);for(unsigned k=0;k<st->getNumElements();++k)image(c->getAggregateElement(k),off+sl->getElementOffset(k));return;}
      if(auto *at=dyn_cast<ArrayType>(t)) {for(unsigned k=0;k<at->getNumElements();++k)image(c->getAggregateElement(k),off+k*dl.getTypeAllocSize(at->getElementType()).getFixedValue());return;}
      APInt bits(1,0);
      if(auto *n=dyn_cast<ConstantInt>(c))bits=n->getValue();
      else if(auto *n=dyn_cast<ConstantFP>(c))bits=n->getValueAPF().bitcastToAPInt();
      else unimplemented("§19.5 pointer/vector data relocation",2,c);
      unsigned n=dl.getTypeStoreSize(t).getFixedValue();bits=bits.zextOrTrunc(n*8);
      for(unsigned k=0;k<n;++k)bytes[off+k]=bits.lshr((dl.isLittleEndian()?k:n-1-k)*8).getLimitedValue()&255;
    };
    image(g.getInitializer(),0);std::string hex=toHex(ArrayRef<uint8_t>(bytes),true),name=s.globals[&g];
    data[name]=hex;
    dataSigs[name]="{\"abi\":\"0.8\",\"kind\":\"data\",\"size\":"+std::to_string(size)+",\"tier\":\"-\"}";
    dataHashes[name]=sha(prefix+dataSigs[name]+"\n"+name+" "+hex+"\n");
    globalLeaves[name]="{\"base\":"+std::to_string(base)+",\"image\":\""+name+"\",\"size\":"+std::to_string(size)+"}";
    base+=size;
  }
  uint64_t heap=alignTo(base,uint64_t(4096));unsigned h=0,at=0;
  while((uint64_t(1)<<h)<heap)++h;
  while((uint64_t(1)<<at)<data.size())++at;
  std::string images,globalLayout,globalHashLeaves,dataSection,refs;
  for(auto &e:data) {
    images+="data "+e.first+" "+e.second+"\n";
    if(!globalLayout.empty())globalLayout+=",";
    globalLayout+="\""+e.first+"\":"+globalLeaves[e.first];
    globalHashLeaves+="layout globals."+e.first+" "+globalLeaves[e.first]+"\n";
    dataSection+=e.first+" "+e.second+"\n";
  }
  // Symbol references contribute hashes in first-reference order, independently
  // of lexicographic data/layout leaf order.
  std::string canonicalL;std::set<std::string> referenced;
  std::regex token(R"(@G[0-9]+\b)");size_t last=0;
  for(std::sregex_iterator it(lproc.begin(),lproc.end(),token),end;it!=end;++it) {
    std::string n=it->str().substr(1);if(referenced.insert(n).second)refs+=dataHashes[n]+"\n";
    canonicalL+=lproc.substr(last,it->position()-last)+"@"+dataHashes[n];last=it->position()+it->length();
  }
  canonicalL+=lproc.substr(last);
  std::string lh=sha(prefix+lsig+"\n"+canonicalL+"\n"+images+globalHashLeaves+refs);
  std::string canonical=wrapper;auto pos=canonical.find("@L1",canonical.find('\n'));canonical.replace(pos,3,"@"+lh);
  std::string leaves="layout A_tab "+std::to_string(at)+"\nlayout H "+std::to_string(h)+"\nlayout S_cells "+std::to_string(sc)+"\n"+globalHashLeaves+
    "layout heap_base "+std::to_string(heap)+"\nlayout heap_limit_max 0\nlayout null_size 4096\nlayout ptr_width "+std::to_string(pw)+"\n";
  std::string oh=sha(prefix+osig+"\n"+canonical+"\n"+images+leaves+lh+"\n");
  std::string symbols="{\"0\":{\"interface_hash\":\""+oh+"\",\"kind\":\"oracle\",\"name\":\"ref\",\"signature\":"+osig+"},\"1\":{\"interface_hash\":\""+lh+"\",\"kind\":\"lproc\",\"name\":\"L1\",\"signature\":"+lsig+"}";
  unsigned si=2;for(auto &e:data)symbols+=",\""+std::to_string(si++)+"\":{\"interface_hash\":\""+dataHashes[e.first]+"\",\"kind\":\"data\",\"name\":\""+e.first+"\",\"signature\":"+dataSigs[e.first]+"}";
  symbols+="}";
  std::string layout="{\"A_tab\":"+std::to_string(at)+",\"H\":"+std::to_string(h)+",\"S_cells\":"+std::to_string(sc)+",\"globals\":{"+globalLayout+"},\"heap_base\":"+std::to_string(heap)+",\"heap_limit_max\":0,\"interface_regions\":{\"ref\":{}},\"null_size\":4096,\"ptr_width\":"+std::to_string(pw)+"}";
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
