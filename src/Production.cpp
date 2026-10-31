#include "Bennett.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Analysis/ValueTracking.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Intrinsics.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/SHA256.h"
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
struct Entry {
  Module &m;
  Analysis &a;
  Function &f;
  std::string out;
  unsigned stack;
  std::vector<uint64_t> defaults;
  std::map<const Value *, std::string> names;
  std::map<const BasicBlock *, std::string> blocks;
  std::set<const Value *> descriptorObjects;
  std::vector<std::string> regs, rows, params, results, paramTypes, resultTypes;
  std::vector<json::Object> budgets;
  std::string reference, shape, refPath;
  std::vector<std::string> references;
  json::Array coverage;
  std::map<std::string, std::pair<std::string, std::string>> actions;
  unsigned next = 0, ordinal = 0;
  unsigned width(Type *t) {
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
    if (auto *c = dyn_cast<ConstantInt>(v)) {
      auto n = fresh("i" + std::to_string(c->getBitWidth()));
      rows.push_back(n + " = const.i" + std::to_string(c->getBitWidth()) + " " +
                     decimal(c->getValue()));
      return n;
    }
    unimplemented("§17.4 CC operand / §6.5 handle environment", 1, v);
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
      auto *c = atom.kind == Atom::Root ? dyn_cast<CallBase>(atom.object) : nullptr;
      if (!c) unimplemented("§6.6 scalar boundary handles", 1, at);
      auto w = integer(a.get(c->getArgOperand(1)), at);
      if (width && width != w) unimplemented("§6.5 mixed-width handle dispatch", 1, at);
      width = w;
    }
    return width;
  }
  std::string type(Value *v) {
    if (v->getType()->isPointerTy() && a.get(v).roots())
      return "qreg[" + std::to_string(qwidth(a.get(v), v)) + "]";
    return "i" + std::to_string(width(v->getType()));
  }
  std::string handle(AV v, const Value *at) {
    auto *r = root(v, at);
    if (!names.count(r))
      unimplemented("§6.5 handle not in live register environment", 1, at);
    return names[r];
  }
  void descriptor(CallBase &c) {
    auto *desc = c.getArgOperand(2);
    auto &ctx = m.getContext();
    auto *u32 = Type::getInt32Ty(ctx), *u64 = Type::getInt64Ty(ctx);
    auto *ptr = PointerType::get(ctx, 0);
    auto *h = StructType::get(ctx, {u32, u32, u32, u32, ptr, ptr});
    auto *b = StructType::get(ctx, {u32, u32, ptr, u64, u64});
    auto &dl = m.getDataLayout();
    auto *hl = dl.getStructLayout(h), *bl = dl.getStructLayout(b);
    auto field = [&](uint64_t off, Type *t) {
      return a.readAt(c, desc, off, t);
    };
    if (integer(field(0, u32), &c) != 2 || integer(field(12, u32), &c) != 0)
      fail("T-IFACE", "§8.1 descriptor header", &c);
    auto ndev = integer(field(8, u32), &c);
    auto candidates = a.candidates(c.getArgOperand(0));
    if (candidates.size() != 1)
      unimplemented("§7.2 production region dispatch", 1, &c);
    auto *callee = *candidates.begin();
    if (integer(field(4, u32), &c) != callee->arg_size())
      fail("T-IFACE", "§8.2 descriptor arity", &c);
    auto target = field(hl->getElementOffset(4), ptr),
         fault = field(hl->getElementOffset(5), ptr);
    if (qwidth(fault, &c) != 4)
      fail("T-SIZE", "§8.2 fault width", &c);
    bool discard = !target.top && target.atoms.size() == 1 &&
                   target.atoms.begin()->kind == Atom::Int &&
                   target.atoms.begin()->integer.isZero();
    std::vector<std::string> ins, args, mems;
    AV output = target;
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
        auto lo = integer(field(off + bl->getElementOffset(3), u64), &c),
             hi = integer(field(off + bl->getElementOffset(4), u64), &c);
        APInt val = APInt(128, lo) | (APInt(128, hi) << 64);
        auto n = fresh("i" + std::to_string(w));
        rows.push_back(n + " = const.i" + std::to_string(w) + " " +
                       decimal(val.zextOrTrunc(w)));
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
          if (!discard || bufferOutput)
            unimplemented("§8.6 multiple output slices", 1, &c);
          output = q; bufferOutput = true;
        }
      } else
        fail("T-IFACE", "§8.2 oracle binding kind", &c);
    }
    std::set<uint64_t> models;
    for (unsigned j = 0; j < ndev; ++j) {
      auto off = hl->getSizeInBytes() + index * bl->getSizeInBytes() + j * 24;
      auto model = integer(field(off, u32), &c);
      if (!models.insert(model).second || integer(field(off + 4, u32), &c))
        fail("T-IFACE", "§8.3 duplicate model or device mode", &c);
      auto q = field(off + 8, ptr);
      auto value = integer(field(off + 16, u64), &c);
      if (ndev != 1) unimplemented("§8.3 combined device models", 1, &c);
      if (model == 3) current += ";dev=CLOCK(" + std::to_string(value) + ")";
      else if (model == 2 || model == 1) {
        auto w = qwidth(q, &c), bytes = w / 8;
        auto unit = model == 2 ? 512 : 1;
        if (w % 8 || bytes < unit || !isPowerOf2_64(bytes / unit))
          fail("T-SIZE", "§8.3 device input extent", &c);
        current += std::string(";dev=") + (model == 2 ? "BLOCK(" : "ENTROPY(") +
                   std::to_string(Log2_64(bytes / unit)) + ")";
        mems.push_back(handle(q, &c));
      } else if (model == 4) {
        if (!discard || bufferOutput)
          unimplemented("§8.6 multiple output slices", 1, &c);
        auto w = qwidth(q, &c);
        if (w % 8) fail("T-SIZE", "§8.3 console width", &c);
        current += ";dev=CONSOLE(" + std::to_string(w / 8) + ")";
        output = q; bufferOutput = true;
      } else fail("T-IFACE", "§8.3 unknown device model", &c);
    }
    discard = discard && !bufferOutput;
    current += ";tgt=" + (discard ? std::string("null")
                                  : std::to_string(qwidth(output, &c)));
    // Null selects the resolved default. Explicit records use the published
    // four i64 fields + fault handle; all-ones means table/default lookup.
    std::vector<uint64_t> budget = defaults;
    if (!isa<ConstantPointerNull>(c.getArgOperand(1))) {
      auto *bp = c.getArgOperand(1);
      for (unsigned i = 0; i < 4; ++i) {
        auto n = integer(a.readAt(c, bp, 8 * i, u64), &c);
        if (n != UINT64_MAX)
          budget[i] = n;
      }
    }
    std::string refName = "ref";
    ValueToValueMapTy vm;
    auto clone = CloneModule(m, vm);
    auto *cf = cast<Function>(vm[callee]);
    normaliseScalar(*cf);
    auto path = out + "/oracle-" + std::to_string(references.size());
    lowerScalar(*clone, *cf, current, path, budget[2], budget[1]);
    auto candidate = read(path + "/ref.bennett");
    auto it = std::find(references.begin(), references.end(), candidate);
    unsigned ri = it - references.begin();
    if (it == references.end()) references.push_back(candidate);
    else sys::fs::remove_directories(path);
    if (ri) refName += std::to_string(ri);
    if (reference.empty()) { reference = candidate; shape = current; refPath = path; }
    // Tokens are minted by the host, positional launch parameters per ISA §10.
    std::string tk = "tk" + std::to_string(budgets.size());
    params.push_back(tk + ":token");
    paramTypes.push_back("token");
    budgets.push_back(json::Object{{"token", tk},
                                   {"steps", std::to_string(budget[0])},
                                   {"heap", std::to_string(budget[1])},
                                   {"stack", std::to_string(budget[2])},
                                   {"depth", std::to_string(budget[3])},
                                   {"sstack", std::to_string(budget[4])}});
    if (refName != "ref") budgets.back()["region"] = refName;
    std::string tgt;
    if (discard) {
      tgt = fresh("qreg[1]");
      rows.push_back(tgt + " = qreg.new any 1");
    } else
      tgt = handle(output, &c);
    rows.push_back("oracle_call @" + refName + " " + tk + " (" + join(ins) + ") " + tgt +
                   " " + handle(fault, &c) + " (" + join(mems) + ") (" + join(args) + ")");
    if (discard)
      rows.push_back("qreg.free " + tgt);
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
    auto n = c.getCalledFunction()->getName();
    bool measurement = n == "__bennett_measure";
    auto q = a.get(c.getArgOperand(measurement ? 0 : 1));
    auto w = qwidth(q, &c);
    auto i = integer(a.get(c.getArgOperand(measurement ? 1 : 2)), &c);
    if (i >= w)
      fail("T-INDEX", "§18.3 gate/measurement index", &c);
    auto src = operand(c.getArgOperand(measurement ? 0 : 1));
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
  void lower() {
    // Descriptor memory has no device representation: its fields are virtual
    // operands. Elide only local storage whose complete use closure is records.
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (c->getCalledFunction() &&
            c->getCalledFunction()->getName() == "__bennett_oracle") {
          descriptorObjects.insert(getUnderlyingObject(c->getArgOperand(2)));
          if (!isa<ConstantPointerNull>(c->getArgOperand(1)))
            descriptorObjects.insert(getUnderlyingObject(c->getArgOperand(1)));
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
              g && (g->getName() == "__bennett_oracle" ||
                    g->getName().starts_with("llvm.lifetime.") ||
                    g->getName().starts_with("llvm.memset.")))
            continue;
        unimplemented("§8.1 escaping descriptor storage", 1, u);
      }
    };
    for (auto *v : descriptorObjects)
      validate(v);
    for (Argument &p : f.args()) {
      auto n = "a" + std::to_string(p.getArgNo()),
           t = "i" + std::to_string(width(p.getType()));
      names[&p] = n;
      params.push_back(n + ":" + t);
      paramTypes.push_back(t);
    }
    if (!f.getReturnType()->isVoidTy()) {
      auto t = "i" + std::to_string(width(f.getReturnType()));
      results.push_back("result:" + t);
      resultTypes.push_back(t);
    }
    unsigned bn = 0;
    for (BasicBlock &bb : f)
      blocks[&bb] = "b" + std::to_string(bn++);
    for (BasicBlock &bb : f)
      for (PHINode &p : bb.phis()) names[&p] = fresh(type(&p));
    auto edge = [&](BasicBlock *to, BasicBlock *from) {
      std::vector<std::string> values;
      for (PHINode &p : to->phis()) values.push_back(operand(p.getIncomingValueForBlock(from)));
      return "^" + blocks[to] + ("(" + join(values) + ")");
    };
    for (BasicBlock &bb : f) {
      std::vector<std::string> bindings;
      for (PHINode &p : bb.phis()) bindings.push_back(names[&p] + ":" + type(&p));
      rows.push_back("^" + blocks[&bb] + "(" + join(bindings) + "):");
      ordinal = 0;
      for (Instruction &i : bb) {
        bool record = false;
        if (auto *g = dyn_cast<GetElementPtrInst>(&i))
          record = descriptorObjects.count(getUnderlyingObject(g));
        if (auto *s = dyn_cast<StoreInst>(&i))
          record = descriptorObjects.count(
              getUnderlyingObject(s->getPointerOperand()));
        if (auto *al = dyn_cast<AllocaInst>(&i))
          record = descriptorObjects.count(al);
        if (record || isa<PHINode>(i))
          continue;
        if (auto *c = dyn_cast<CallBase>(&i)) {
          auto *g = c->getCalledFunction();
          if (!g)
            unimplemented("§17.4 indirect CC call", 1, c);
          auto n = g->getName();
          if (n.starts_with("llvm.lifetime.") ||
              (n.starts_with("llvm.memset.") &&
               descriptorObjects.count(
                   getUnderlyingObject(c->getArgOperand(0)))))
            continue;
          if (n == "__bennett_qalloc" || n == "__bennett_qborrow") {
            auto cls = integer(a.get(c->getArgOperand(0)), c),
                 w = integer(a.get(c->getArgOperand(1)), c);
            if (cls)
              unimplemented("§3.4 configured register class", 1, c);
            auto q = fresh("qreg[" + std::to_string(w) + "]");
            names[c] = q;
            rows.push_back(q + " = qreg.new any " + std::to_string(w));
          } else if (n == "__bennett_qfree")
            rows.push_back("qreg.free " +
                           operand(c->getArgOperand(0)));
          else if (n == "__bennett_oracle")
            descriptor(*c);
          else if (n == "__bennett_gate" || n == "__bennett_measure")
            gate(*c);
          else
            unimplemented("§17.4 CC marker/call lowering", 1, c);
        } else if (auto *r = dyn_cast<ReturnInst>(&i)) {
          auto v = r->getReturnValue() ? operand(r->getReturnValue()) : "";
          rows.push_back("ret" + (v.empty() ? "" : " " + v));
        } else if (auto *br = dyn_cast<BranchInst>(&i)) {
          if (br->isUnconditional())
            rows.push_back("br " + edge(br->getSuccessor(0), &bb));
          else {
            auto p = operand(br->getCondition());
            auto yes = edge(br->getSuccessor(0), &bb), no = edge(br->getSuccessor(1), &bb);
            rows.push_back("br " + p + " " + yes + " " + no);
          }
        } else if (auto *b = dyn_cast<BinaryOperator>(&i)) {
          auto x = operand(b->getOperand(0)), y = operand(b->getOperand(1)),
               d = fresh("i" + std::to_string(width(b->getType())));
          names[b] = d;
          rows.push_back(d + " = " + b->getOpcodeName() + " " + x + " " + y);
        } else if (auto *sel = dyn_cast<SelectInst>(&i)) {
          auto p = operand(sel->getCondition()),
               x = operand(sel->getTrueValue()),
               y = operand(sel->getFalseValue()),
               d = fresh("i" + std::to_string(width(sel->getType())));
          names[sel] = d;
          rows.push_back(d + " = select " + p + " " + x + " " + y);
        } else if (auto *cmp = dyn_cast<ICmpInst>(&i)) {
          auto pred = cmp->getPredicate();
          auto *xv = cmp->getOperand(0), *yv = cmp->getOperand(1);
          if (pred == CmpInst::ICMP_UGT || pred == CmpInst::ICMP_UGE ||
              pred == CmpInst::ICMP_SGT || pred == CmpInst::ICMP_SGE) {
            pred = CmpInst::getSwappedPredicate(pred);
            std::swap(xv, yv);
          }
          auto x = operand(xv), y = operand(yv), d = fresh("i1");
          names[cmp] = d;
          rows.push_back(d + " = icmp." +
                         CmpInst::getPredicateName(pred).str() + " " + x + " " +
                         y);
        } else if (auto *c = dyn_cast<CastInst>(&i);
                   c && (isa<ZExtInst>(c) || isa<SExtInst>(c) ||
                         isa<TruncInst>(c))) {
          auto x = operand(c->getOperand(0)),
               d = fresh("i" + std::to_string(width(c->getType())));
          names[c] = d;
          rows.push_back(d + " = " + c->getOpcodeName() + ".i" +
                         std::to_string(width(c->getType())) + " " + x);
        } else
          unimplemented("§17.4 production CC instruction", 1, &i);
      }
    }
  }
};
// ISA envelopes are derived from generated functions and reference metadata.
// Keep the standalone reference object untouched for byte-exact comparison.
std::string launchObject(Entry &e, json::Object &record,
                         json::Object &certificate) {
  std::map<std::string, std::string> sections;
  std::string ref = e.reference;
  size_t pos = ref.find("\n\nsection ");
  std::string header =
      pos == std::string::npos
          ? "bennett-object isa=0.8 object=0.8 launch=0.8 sched=0.8 cert=0.8 "
            "coverage=0.8 target=0.8 ptr_width=" +
                std::to_string(e.m.getDataLayout().getPointerSizeInBits())
          : ref.substr(0, pos);
  while (pos != std::string::npos) {
    auto start = pos + 10, end = ref.find('\n', start),
         next = ref.find("\n\nsection ", end);
    sections[ref.substr(start, end - start)] =
        StringRef(ref.substr(end + 1,
                             next == std::string::npos ? next : next - end - 1))
            .rtrim()
            .str();
    pos = next;
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
  for (unsigned i = 1; i < e.references.size(); ++i) {
    std::map<std::string, std::string> extra;
    auto text = e.references[i];
    size_t p = text.find("\n\nsection ");
    while (p != std::string::npos) {
      auto start = p + 10, end = text.find('\n', start), next = text.find("\n\nsection ", end);
      extra[text.substr(start, end - start)] = StringRef(text.substr(end + 1, next == std::string::npos ? next : next - end - 1)).rtrim().str();
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
  std::string canonical, refs;
  std::set<std::string> referenced;
  std::regex token(R"(@(ref[0-9]*|M[0-9]+)\b)");
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
  envelope += refs;
  auto ih = hash(envelope);
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
    b["selection_identity"] = oracleHash;
    b["identity"] = oracleHash;
    budgets.push_back(std::move(b));
  }
  record["budgets"] = std::move(budgets);
  record["budget_table_sha256"] = hash(jcs(*record.get("budgets")));
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
                   {ConstantInt::get(size, f.arg_size() + bs->size()), args}));
  auto *av = b.CreateLoad(ptr, args);
  unsigned index = 0;
  for (Argument &arg : f.args()) {
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
void lowerProduction(Module &m, Analysis &a, StringRef out, unsigned stack,
                     StringRef budgetDefault) {
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
  if (auto ec = sys::fs::create_directories(out))
    fail("output", ec.message());
  ValueToValueMapTy vm;
  auto device = CloneModule(m, vm);
  std::vector<Function *> entries;
  for (Function &f : m)
    if (!f.isDeclaration() && a.tiers[&f].count("CC"))
      entries.push_back(&f);
  json::Array launches;
  for (Function *f : entries) {
    std::string dir = out.str() + "/" + f->getName().str();
    if (auto ec = sys::fs::create_directories(dir))
      fail("output", ec.message());
    Entry e{m, a, *f, dir, stack, defaults};
    e.lower();
    json::Object record{{"dialect", "0.2.10"},
                        {"isa", "0.8"},
                        {"llvm_version", LLVM_VERSION_STRING},
                        {"pipeline", "bennett"},
                        {"shape", e.shape}};
    json::Object cert{
        {"versions", json::Object{{"isa", "0.8"}, {"cert", "0.8"}}},
        {"regions", json::Object{}},
        {"composition",
         json::Object{{"multiplicities", json::Object{}},
                      {"epsilon_total", json::Object{{"diamond", 0}}},
                      {"method", "sum_over_multiplicities"}}}};
    auto obj = launchObject(e, record, cert);
    write(dir + "/launch.bennett", obj);
    auto build = jcs(json::Value(std::move(record)));
    hostStub(*f, obj, *parse(build).getAsObject());
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
  for (Function &f : *device)
    if (!f.isDeclaration() && a.tiers[m.getFunction(f.getName())].count("L"))
      normaliseScalar(f);
  std::error_code ec;
  raw_fd_ostream bc(out.str() + "/device.bc", ec);
  if (ec)
    fail("output", ec.message());
  WriteBitcodeToFile(*device, bc);
  raw_fd_ostream host(out.str() + "/host.bc", ec);
  if (ec)
    fail("output", ec.message());
  WriteBitcodeToFile(m, host);
  write(out.str() + "/launches.json",
        jcs(json::Value(std::move(launches))) + "\n");
}
} // namespace bennett
