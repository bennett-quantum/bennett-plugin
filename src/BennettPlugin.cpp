#include "Bennett.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/Passes/PassBuilder.h"
#if LLVM_VERSION_MAJOR >= 23
#include "llvm/Plugins/PassPlugin.h"
#else
#include "llvm/Passes/PassPlugin.h"
#endif
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Transforms/Utils/Local.h"
#include "llvm/Bitcode/BitcodeWriter.h"
#include "llvm/Transforms/Utils/Cloning.h"
#include <cstdlib>
using namespace llvm;
namespace {
cl::opt<std::string> Dialect("bennett-dialect",
                             cl::desc("Required exact dialect version"));
cl::opt<std::string> ISA("bennett-isa", cl::init("0.8"));
cl::opt<std::string> Output("bennett-out");
cl::opt<std::string> BudgetTableFile("bennett-budgets",cl::init(""));
cl::opt<std::string> BudgetDefault("bennett-budget-default",cl::init("1048576,1048576,65536,256,65536"));
cl::opt<std::string> Report("bennett-report");
cl::opt<bool> DescriptorReference("bennett-descriptor-reference", cl::desc("Non-production reference objects from statically resolved marker descriptors"));
cl::opt<bool> NormaliseOnly("bennett-normalise-only", cl::desc("Test-only M1 scalar N-rule materialisation; no conformance verdict"));
cl::opt<bool> AnalysisOnly(
    "bennett-analysis-only",
    cl::desc("Non-production S1-S5 report; emits no device object"));
cl::opt<bool> LegalityAudit(
    "bennett-legality-audit",
    cl::desc("Test-only §21.1 legacy spike ABI; requires analysis-only"));
cl::opt<bool> Prelink("bennett-pre-link",
                      cl::desc("Explicit pre-link phase: do nothing"));
cl::opt<bool> Closed("bennett-closed-unit");
cl::opt<std::string> Oracle("bennett-oracle");
cl::opt<std::string>
    Shape("bennett-scalar-shape",
          cl::desc("Scalar test shape, e.g. IN(8,zext),IN(8,zext);tgt=9"));
cl::opt<unsigned> StackCells("bennett-scalar-stack", cl::init(32));
} // namespace
namespace bennett {
[[noreturn]] void fail(StringRef code, StringRef section, const Value *v) {
  errs() << "bennett: " << code << ": " << section;
  if (v) {
    errs() << " at ";
    v->print(errs());
  }
  errs() << "\n";
  std::exit(1);
}
[[noreturn]] void unimplemented(StringRef sec, unsigned n, const Value *v) {
  fail("unimplemented", (sec + " (milestone " + Twine(n) + ")").str(), v);
}
bool auditLegality() { return LegalityAudit; }
const std::map<std::string, std::string> &markers() {
  // Compact types: v=void, p=ptr AS0, b=i1, w=i32, n=i64, d=double.
  static std::map<std::string, std::string> names = {
      {"__bennett_qalloc", "pnn"},
      {"__bennett_qborrow", "pnn"},
      {"__bennett_qfree", "vp"},
      {"__bennett_gate", "vwpn"},
      {"__bennett_gate2", "vwpnpn"},
      {"__bennett_gate3", "vwpnpnpn"},
      {"__bennett_rot", "vwpnd"},
      {"__bennett_measure", "bpn"},
      {"__bennett_qload", "vppp"},
      {"__bennett_qstore", "vppp"},
      {"__bennett_qprep", "vppn"},
      {"__bennett_observe", "vpn"},
      {"__bennett_ctrl", "vpnppp"},
      {"__bennett_adj", "vppp"},
      {"__bennett_compute", "vpppp"},
      {"__bennett_reversible", "vppp"},
      {"__bennett_oracle", "vppp"},
      {"__bennett_inplace", "vpppp"},
      {"__bennett_effect_console_write", "vpn"},
      {"__bennett_effect_clock_read", "vp"},
      {"__bennett_effect_entropy_read", "vpn"},
      {"__bennett_effect_block_read", "vnp"},
      {"__bennett_effect_block_write", "vnp"}};
  if (LegalityAudit)
    names["__bennett_ctrl_v"] = "vnpnn";
  return names;
}
std::vector<unsigned> regionOperands(StringRef n) {
  if (n == "__bennett_ctrl" || n == "__bennett_ctrl_v")
    return {2};
  if (n == "__bennett_compute" || n == "__bennett_inplace")
    return {0, 1};
  if (n == "__bennett_adj" || n == "__bennett_reversible" ||
      n == "__bennett_oracle")
    return {0};
  return {};
}
std::vector<unsigned> handleOperands(StringRef n) {
  if (n == "__bennett_qfree" || n == "__bennett_measure" ||
      n == "__bennett_qprep" || n == "__bennett_ctrl" ||
      n == "__bennett_ctrl_v")
    return {0};
  if (n == "__bennett_gate" || n == "__bennett_rot")
    return {1};
  if (n == "__bennett_gate2")
    return {1, 3};
  if (n == "__bennett_gate3")
    return {1, 3, 5};
  if (n == "__bennett_qload" || n == "__bennett_qstore")
    return {0, 1, 2};
  return {};
}
static Type *type(LLVMContext &c, char t) {
  switch (t) {
  case 'v':
    return Type::getVoidTy(c);
  case 'p':
    return PointerType::get(c, 0);
  case 'b':
    return Type::getInt1Ty(c);
  case 'w':
    return Type::getInt32Ty(c);
  case 'n':
    return Type::getInt64Ty(c);
  case 'd':
    return Type::getDoubleTy(c);
  }
  llvm_unreachable("invalid marker table");
}
static FunctionType *signature(LLVMContext &c, const std::string &s,
                               bool var = false) {
  SmallVector<Type *> args;
  for (unsigned i = 1; i < s.size(); ++i)
    args.push_back(type(c, s[i]));
  return FunctionType::get(type(c, s[0]), args, var);
}
static void attributes(AttributeList attrs, const Value *v) {
  for (unsigned idx : attrs.indexes())
    for (Attribute a : attrs.getAttributes(idx)) {
      if (a.isStringAttribute())
        continue;
      StringRef n = Attribute::getNameFromAttrKind(a.getKindAsEnum());
      bool fn = idx == AttributeList::FunctionIndex;
      static const std::set<std::string> functionAttrs = {
          "nounwind",  "nonlazybind", "uwtable",  "strictfp",   "cold",
          "hot",       "nomerge",     "noinline", "convergent", "builtin",
          "nobuiltin", "optsize",     "minsize",  "optnone"};
      static const std::set<std::string> valueAttrs = {
          "noundef", "nonnull", "range", "zeroext", "signext"};
      bool good = (fn ? functionAttrs : valueAttrs).count(n.str());
      if (!good)
        fail("BD-E-MARKER-ATTRIBUTE", "§3.6 " + n.str(), v);
    }
}
static bool runtimeName(StringRef n) {
  return n.starts_with("__bennett_nz_") || n.starts_with("__bennett_sf_") ||
         n.starts_with("__bennett_rt_") || n.starts_with("__bennett_dev_");
}
static void recognise(Module &m) {
  // §4.1 S1: reserved-name rules precede recognition, in module order.
  for (Function &f : m)
    if (markers().count(f.getName().str()) || runtimeName(f.getName()))
      if (!f.isDeclaration() && (Closed || !runtimeName(f.getName())))
        fail("BD-E-MARKER-DEFINED", "§3.1", &f);
  for (GlobalValue &v : m.global_values())
    if (v.getName().starts_with("__bennett_") &&
        !markers().count(v.getName().str()) &&
        (!runtimeName(v.getName()) || Closed))
      fail("BD-E-MARKER-UNKNOWN", "§3.1", &v);
  for (Function &f : m)
    if (markers().count(f.getName().str()))
      for (User *u : f.users()) {
        auto *cb = dyn_cast<CallBase>(u);
        if (!cb || cb->getCalledOperand() != &f)
          fail("BD-E-MARKER-ADDRESS", "§3.1", u);
        // Callee use is permitted, but the same instruction may also pass its
        // address.
        for (Value *a : cb->args())
          if (a == &f)
            fail("BD-E-MARKER-ADDRESS", "§3.1", cb);
      }
  for (Function &f : m)
    if (auto it = markers().find(f.getName().str()); it != markers().end()) {
      auto *expected = signature(m.getContext(), it->second);
      bool variadicProbe = LegalityAudit && f.getName() == "__bennett_ctrl_v";
      if (LegalityAudit) {
        static const std::map<std::string, std::string> legacy = {
            {"__bennett_ctrl", "vnpnn"},   {"__bennett_adj", "vpp"},
            {"__bennett_compute", "vppp"}, {"__bennett_reversible", "vpnp"},
            {"__bennett_inplace", "vppp"}, {"__bennett_ctrl_v", "vnpnn"}};
        auto it = legacy.find(f.getName().str());
        if (it != legacy.end()) {
          // The spike control begins with ptr, i64, ptr, i64.
          auto sig = it->second;
          if (f.getName() == "__bennett_ctrl")
            sig = "vpnpnp";
          if (variadicProbe)
            sig = "vpnpn";
          auto *old = signature(m.getContext(), sig, variadicProbe);
          if (f.getFunctionType() == old)
            expected = old;
        }
      }
      bool kr = f.isVarArg() && f.arg_empty() &&
                f.getReturnType() == expected->getReturnType();
      for (User *u : f.users())
        if (auto *cb = dyn_cast<CallBase>(u)) {
          if ((f.getFunctionType() != expected && !kr) ||
              (cb->getFunctionType() != expected &&
               !(kr && cb->getFunctionType() ==
                           signature(m.getContext(), it->second, true))) ||
              (!variadicProbe && cb->arg_size() != expected->getNumParams()) ||
              (variadicProbe && cb->arg_size() < expected->getNumParams()) ||
              cb->getCallingConv() != CallingConv::C ||
              f.getCallingConv() != CallingConv::C || cb->hasOperandBundles())
            fail("BD-E-MARKER-SIGNATURE", "§3.5", cb);
          for (unsigned i = 0; i < expected->getNumParams(); ++i)
            if (cb->getArgOperand(i)->getType() != expected->getParamType(i))
              fail("BD-E-MARKER-SIGNATURE", "§3.5 argument type", cb);
        }
    }
  for (Function &f : m)
    if (markers().count(f.getName().str())) {
      if (f.hasExternalWeakLinkage())
        fail("BD-E-MARKER-ATTRIBUTE", "§3.6 extern_weak", &f);
      attributes(f.getAttributes(), &f);
      for (User *u : f.users())
        if (auto *cb = dyn_cast<CallBase>(u)) {
          attributes(cb->getAttributes(), cb);
          if (auto *ci = dyn_cast<CallInst>(cb); ci && ci->isMustTailCall())
            fail("BD-E-MARKER-ATTRIBUTE", "§3.6 musttail", ci);
        }
    }
  for (GlobalVariable &g : m.globals()) {
    auto n = g.getName();
    if ((n.starts_with("jlplt___bennett_") && n.ends_with("_got")) ||
        (g.getAttributes().hasAttribute("julia.fname") &&
         g.getAttributes()
             .getAttribute("julia.fname")
             .getValueAsString()
             .starts_with("__bennett_")))
      fail("BD-E-JULIA-CCALL", "§3.8", &g);
  }
  SmallVector<InvokeInst *> invokes;
  for (Function &f : m)
    for (Instruction &i : instructions(f))
      if (auto *iv = dyn_cast<InvokeInst>(&i))
        if (auto *callee = iv->getCalledFunction();
            callee && markers().count(callee->getName().str()))
          invokes.push_back(iv);
  for (InvokeInst *iv : invokes)
    changeToCall(iv);
  for (Function &f : m)
    if (!f.isDeclaration())
      removeUnreachableBlocks(f);
  // Effect lies use the full S2 call graph later, including region edges.
}
static void checkVersion(Module &m) {
  if (Dialect != "0.2.10" || ISA != "0.8")
    fail("BD-E-VERSION", "§19.9 expected dialect 0.2.10 / ISA 0.8");
  if (auto *md = m.getModuleFlag("bennett.dialect")) {
    auto *s = dyn_cast<MDString>(md);
    if (!s || s->getString() != "0.2.10")
      fail("BD-E-VERSION", "§19.9 module flag");
  }
}
static void checkOperands(Module &m) {
  unsigned classes = 0;
  if (auto *md = dyn_cast_or_null<MDNode>(m.getModuleFlag("bennett.classes")))
    classes = md->getNumOperands();
  for (Function &f : m)
    for (Instruction &i : instructions(f))
      if (auto *c = dyn_cast<CallBase>(&i))
        if (auto *g = c->getCalledFunction()) {
          auto n = g->getName();
          unsigned max = 0;
          if (n == "__bennett_gate")
            max = 8;
          else if (n == "__bennett_gate2" || n == "__bennett_rot")
            max = 3;
          else if (n == "__bennett_gate3")
            max = 1;
          if (max)
            if (auto *op = dyn_cast<ConstantInt>(c->getArgOperand(0));
                op && (op->isZero() || op->getValue().ugt(max)))
              fail("BD-E-OPERAND", "§3.4 operation code", c);
          if (n == "__bennett_qalloc" || n == "__bennett_qborrow") {
            if (auto *cls = dyn_cast<ConstantInt>(c->getArgOperand(0));
                cls && cls->getValue().ugt(classes))
              fail("BD-E-OPERAND", "§3.4 class", c);
            if (auto *width = dyn_cast<ConstantInt>(c->getArgOperand(1));
                width && width->isZero())
              fail("BD-E-OPERAND", "§3.4 width zero", c);
          }
        }
}
struct BennettPass : PassInfoMixin<BennettPass> {
  PreservedAnalyses run(Module &m, ModuleAnalysisManager &) {
    if (Prelink)
      return PreservedAnalyses::all();
    if (LegalityAudit && !AnalysisOnly)
      fail("test mode",
           "legality-audit requires analysis-only; never production");
    recognise(m);
    checkVersion(m);
    if (NormaliseOnly) {
      for (Function &f : m) if (!f.isDeclaration()) normaliseScalar(f);
      errs() << "bennett: scalar normalisation test mode; full N0-N35/V1-V16 pending M2\n";
      return PreservedAnalyses::none();
    }
    Analysis a(m);
    a.run();
    a.checkHandles();
    a.checkRegions();
    if (!Report.empty()) {
      std::error_code ec;
      raw_fd_ostream o(Report, ec);
      if (ec)
        fail("output", ec.message());
      o << formatv("{0:2}\n", json::Value(a.report()));
    }
    if (AnalysisOnly) {
      errs()
          << "bennett: analysis-only: S1-S5 complete; no production artefact\n";
      return PreservedAnalyses::none();
    }
    checkOperands(m);
    if (Output.empty())
      fail("output", "§19.9 -bennett-out is required");
    if (!Oracle.empty()) {
      auto *f = m.getFunction(Oracle);
      if (!f || f->isDeclaration())
        fail("input", "oracle function missing");
      ValueToValueMapTy map;
      auto materialised = CloneModule(m, map);
      auto *mf = cast<Function>(map[f]);
      normaliseScalar(*mf);
      lowerScalar(*materialised, *mf, Shape, Output, StackCells);
      std::error_code ec;
      raw_fd_ostream bc(Output + "/materialised.bc", ec);
      if (ec) fail("output", ec.message());
      WriteBitcodeToFile(*materialised, bc);
      return PreservedAnalyses::none();
    }
    if (DescriptorReference) {
      unsigned objects=0;
      for(Function &caller:m)for(Instruction &i:instructions(caller))
        if(auto *c=dyn_cast<CallBase>(&i))
          if(auto *marker=c->getCalledFunction();marker && marker->getName()=="__bennett_oracle") {
            Value *desc=c->getArgOperand(2);
            auto integer=[&](AV v)->uint64_t {
              if(v.top || v.atoms.size()!=1 || v.atoms.begin()->kind!=Atom::Int)
                unimplemented("§8.4 non-singleton descriptor shape",2,c);
              return v.atoms.begin()->integer.getLimitedValue();
            };
            auto u32=Type::getInt32Ty(m.getContext());auto ptr=PointerType::get(m.getContext(),0);
            auto *h=StructType::get(m.getContext(),{u32,u32,u32,u32,ptr,ptr});
            auto *b=StructType::get(m.getContext(),{u32,u32,ptr,Type::getInt64Ty(m.getContext()),Type::getInt64Ty(m.getContext())});
            auto *hl=m.getDataLayout().getStructLayout(h),*bl=m.getDataLayout().getStructLayout(b);
            auto field=[&](uint64_t off,Type *t) {return a.readAt(*c,desc,off,t);};
            if(integer(field(0,u32))!=2 || integer(field(12,u32))!=0 || integer(field(8,u32))!=0)
              unimplemented("§8.1/§8.3 descriptor header/device dispatch",2,c);
            unsigned params=integer(field(4,u32));
            auto qwidth=[&](AV q)->unsigned {
              if(q.top || q.atoms.size()!=1 || q.atoms.begin()->kind!=Atom::Root)
                unimplemented("§6.5 descriptor register dispatch",3,c);
              auto *alloc=dyn_cast<CallBase>(q.atoms.begin()->object);
              if(!alloc)unimplemented("§6.6 boundary descriptor register",3,c);
              return integer(a.get(alloc->getArgOperand(1)));
            };
            auto target=field(hl->getElementOffset(4),ptr), fault=field(hl->getElementOffset(5),ptr);
            if(qwidth(fault)!=4)unimplemented("§8.2 T-SIZE fault dispatch",3,c);
            bool discard=!target.top && target.atoms.size()==1 && target.atoms.begin()->kind==Atom::Int && target.atoms.begin()->integer.isZero();
            unsigned tgt=discard?0:qwidth(target);
            auto candidates=a.candidates(c->getArgOperand(0));
            for(Function *f:candidates) {
              if(params!=f->arg_size())unimplemented("§8.2 flattened descriptor arity",2,c);
              std::string shape;unsigned j=0;
              for(Argument &param:f->args()) {
                uint64_t off=hl->getSizeInBytes()+j*bl->getSizeInBytes();
                unsigned kind=integer(field(off,u32)),mode=integer(field(off+bl->getElementOffset(1),u32));
                if(j++)shape+=",";
                if(kind==1 && mode<=1)shape+="IN("+std::to_string(qwidth(field(off+bl->getElementOffset(2),ptr)))+","+(mode?"sext":"zext")+")";
                else if(kind==2) {
                  unsigned w=param.getType()->isPointerTy()?m.getDataLayout().getPointerTypeSizeInBits(param.getType()):param.getType()->getPrimitiveSizeInBits().getFixedValue();
                  shape+="ARG("+std::to_string(w)+")";
                } else unimplemented("§8.4 MEM_IN/OUT/INOUT descriptor dispatch",2,c);
              }
              shape+=";tgt="+(discard?std::string("null"):std::to_string(tgt));
              ValueToValueMapTy map;auto clone=CloneModule(m,map);auto *mf=cast<Function>(map[f]);normaliseScalar(*mf);
              lowerScalar(*clone,*mf,shape,Output+"/oracle-"+std::to_string(objects++),StackCells);
            }
          }
      if(!objects)fail("input","descriptor-reference found no oracle shape");
      errs()<<"bennett: descriptor reference objects only; CC launches remain unimplemented: §17.4 (milestone 3)\n";
      return PreservedAnalyses::none();
    }
    for (Function &f : m)
      if (a.tiers[&f].count("R"))
        fail("unimplemented", "§25.1 BLK-5 (blocked: bp-is0)", &f);
    for (Function &f : m)
      for (Instruction &i : instructions(f))
        if (auto *c = dyn_cast<CallBase>(&i))
          if (auto *g = c->getCalledFunction();
              g && (g->getName() == "__bennett_qalloc" ||
                    g->getName() == "__bennett_qborrow")) {
            auto width = a.get(c->getArgOperand(1));
            if (width.top)
              fail("unimplemented", "§25.1 BLK-1 (blocked: bp-2tw)", c);
          }
    lowerProduction(m, a, Output, StackCells, BudgetDefault, BudgetTableFile);
    return PreservedAnalyses::none();
  }
  static bool isRequired() { return true; }
};
} // namespace bennett
extern "C" LLVM_ATTRIBUTE_WEAK PassPluginLibraryInfo llvmGetPassPluginInfo() {
  return {LLVM_PLUGIN_API_VERSION, "bennett", "dialect-0.2.10;isa-0.8",
          [](PassBuilder &pb) {
            pb.registerPipelineParsingCallback(
                [](StringRef n, ModulePassManager &pm,
                   ArrayRef<PassBuilder::PipelineElement>) {
                  if (n != "bennett")
                    return false;
                  pm.addPass(bennett::BennettPass());
                  return true;
                });
          }};
}
