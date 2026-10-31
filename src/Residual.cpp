#include "Bennett.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Operator.h"
using namespace llvm;
namespace bennett {
// A reader of materialised IR, deliberately separate from the producer. Neither
// annotations from the producer nor runtime-looking names exempt an instruction.
void validateResidual(Module &m, bool classical) {
  auto reject=[](StringRef rule,const Value *v) {fail("BD-E-RESIDUAL",("§12.4 "+rule).str(),v);};
  const std::set<std::string> attrs={
    "noundef","nonnull","range","align","dereferenceable","dereferenceable_or_null",
    "nofpclass","noalias","nocapture","captures","readnone","readonly","writeonly",
    "returned","writable","dead_on_unwind","initializes","allocalign","allocptr",
    "memory","argmemonly","inaccessiblememonly","inaccessiblemem_or_argmemonly",
    "willreturn","mustprogress","nosync","nofree","norecurse","speculatable"};
  auto checkAttrs=[&](AttributeList list,const Value *v) {
    for(unsigned index:list.indexes()) {
      bool abi=list.hasAttributeAtIndex(index,Attribute::ByVal) || list.hasAttributeAtIndex(index,Attribute::ByRef) || list.hasAttributeAtIndex(index,Attribute::StructRet) || list.hasAttributeAtIndex(index,Attribute::InAlloca) || list.hasAttributeAtIndex(index,Attribute::Preallocated);
      for(Attribute a:list.getAttributes(index)) if(!a.isStringAttribute()) {
        auto name=Attribute::getNameFromAttrKind(a.getKindAsEnum());
        if(attrs.count(name.str()) && !(name=="align" && abi))reject("V3",v);
      }
    }
  };
  std::function<void(Type *,const Value *)> checkType=[&](Type *t,const Value *v) {
    if(t->isVectorTy())reject("V13",v);
    if(t->isIntegerTy() && t->getIntegerBitWidth()>128)reject("V14",v);
    if(auto *s=dyn_cast<StructType>(t))for(Type *e:s->elements())checkType(e,v);
    if(auto *a=dyn_cast<ArrayType>(t))checkType(a->getElementType(),v);
  };
  std::set<const Value *> seen;
  std::function<void(const Value *,const Value *)> constants=[&](const Value *v,const Value *at) {
    if(!seen.insert(v).second)return;
    if(isa<UndefValue>(v)||isa<PoisonValue>(v))reject("V5",at);
    if(auto *g=dyn_cast<GlobalVariable>(v)) {if(g->hasInitializer())constants(g->getInitializer(),at);return;}
    if(isa<GlobalValue>(v))return;
    if(auto *c=dyn_cast<Constant>(v))for(const Value *e:c->operands())constants(e,at);
  };
  const std::set<std::string> removed={
#include "ResidualIntrinsics.inc"
  };
  auto hasFP=[](Type *t) {return t->isFPOrFPVectorTy();};
  for(Function &f:m)if(!f.isDeclaration()) {
    checkAttrs(f.getAttributes(),&f);if(f.hasPersonalityFn())reject("V3",&f);checkType(f.getReturnType(),&f);
    for(Argument &a:f.args())checkType(a.getType(),&a);
    for(Instruction &i:instructions(f)) {
      if(auto *o=dyn_cast<OverflowingBinaryOperator>(&i);o && (o->hasNoUnsignedWrap()||o->hasNoSignedWrap()))reject("V1",&i);
      if(auto *o=dyn_cast<PossiblyExactOperator>(&i);o && o->isExact())reject("V1",&i);
      if(auto *o=dyn_cast<GetElementPtrInst>(&i);o && o->isInBounds())reject("V1",&i);
      // dropPoisonGeneratingFlags is used only on a private instruction copy
      // to detect new major-specific flags (disjoint, nneg, samesign, GEP nusw).
      auto *copy=i.clone();copy->dropPoisonGeneratingFlags();
      bool flags=copy->getRawSubclassOptionalData()!=i.getRawSubclassOptionalData();copy->deleteValue();
      if(flags)reject("V1",&i);
      if(auto *o=dyn_cast<FPMathOperator>(&i);o && o->getFastMathFlags().any())reject("V1",&i);
      SmallVector<std::pair<unsigned,MDNode *>> md;i.getAllMetadataOtherThanDebugLoc(md);
      for(auto &e:md)if(e.first!=m.getContext().getMDKindID("bennett.rstep"))reject("V2",&i);
      auto *call=dyn_cast<CallBase>(&i);
      if(call)checkAttrs(call->getAttributes(),&i);
      if(auto *intr=dyn_cast<IntrinsicInst>(&i)) {
        auto name=Intrinsic::getBaseName(intr->getIntrinsicID());
        if(removed.count(name.str()))reject("V4",&i);
      }
      for(Value *v:i.operands())constants(v,&i);
      bool atomic=isa<FreezeInst>(i)||isa<FenceInst>(i)||isa<AtomicRMWInst>(i)||isa<AtomicCmpXchgInst>(i);
      if(auto *l=dyn_cast<LoadInst>(&i))atomic|=l->isAtomic()||l->isVolatile();
      if(auto *s=dyn_cast<StoreInst>(&i))atomic|=s->isAtomic()||s->isVolatile();
      if(atomic)reject("V6",&i);
      if(auto *b=dyn_cast<BinaryOperator>(&i);b && b->isShift() && b->getType()->isIntegerTy()) {
        unsigned width=b->getType()->getIntegerBitWidth();auto *amount=b->getOperand(1);bool guarded=false;
        if(auto *c=dyn_cast<ConstantInt>(amount))guarded=c->getValue().ult(width);
        if(b->hasOneUse())if(auto *s=dyn_cast<SelectInst>(*b->user_begin()))
          if(s->getFalseValue()==b && isa<Constant>(s->getTrueValue()) && cast<Constant>(s->getTrueValue())->isNullValue())
            if(auto *c=dyn_cast<ICmpInst>(s->getCondition());c && c->getPredicate()==CmpInst::ICMP_UGE && c->getOperand(0)==amount)
              if(auto *w=dyn_cast<ConstantInt>(c->getOperand(1)))guarded|=w->getValue()==width;
        if(!guarded)reject("V7",&i);
      }
      if((isa<ExtractElementInst>(i)||isa<InsertElementInst>(i)) && !isa<ConstantInt>(i.getOperand(isa<ExtractElementInst>(i)?1:2)))reject("V8",&i);
      bool fp=hasFP(i.getType());for(Value *v:i.operands())fp|=hasFP(v->getType());
      bool transport=isa<BitCastInst>(i)||isa<LoadInst>(i)||isa<StoreInst>(i)||isa<SelectInst>(i)||isa<PHINode>(i)||isa<ReturnInst>(i)||isa<InsertValueInst>(i)||isa<ExtractValueInst>(i)||call;
      bool bitexact=i.getOpcode()==Instruction::FNeg;
      bool fpIntrinsic=false;
      if(auto *intr=dyn_cast<IntrinsicInst>(&i)) {auto n=Intrinsic::getBaseName(intr->getIntrinsicID());bitexact|=n=="llvm.fabs"||n=="llvm.copysign";fpIntrinsic=true;}
      if(fp && ((!transport && !bitexact)||(fpIntrinsic && !bitexact)))reject("V9 V10",&i);
      if(isa<AllocaInst>(i))reject("V11",&i);
      if(call && !classical)if(auto *g=resolve(call->getCalledOperand());g && g->isDeclaration() && !g->isIntrinsic() && g->getName()!="__bennett_nz_fault" && g->getName()!="__bennett_nz_alloc" && g->getName()!="__bennett_nz_free")reject("V12",&i);
      checkType(i.getType(),&i);for(Value *v:i.operands())checkType(v->getType(),&i);
      bool eh=isa<VAArgInst>(i)||isa<InvokeInst>(i)||isa<LandingPadInst>(i)||isa<ResumeInst>(i)||isa<FuncletPadInst>(i)||isa<CatchSwitchInst>(i)||isa<CleanupReturnInst>(i)||isa<CatchReturnInst>(i);
      if(call)if(auto *g=call->getCalledFunction()) {
        auto n=g->getName();eh|=n=="setjmp"||n=="_setjmp"||n=="sigsetjmp"||n=="__sigsetjmp"||n.starts_with("llvm.va_start")||n.starts_with("llvm.va_end")||n.starts_with("llvm.va_copy");
      }
      if(eh)reject("V15",&i);
      if(call && call->isInlineAsm())reject("V16",&i);
      if(auto *intr=dyn_cast<IntrinsicInst>(&i))if(intr->getCalledFunction()->getName().starts_with("llvm.")) {
        auto n=intr->getCalledFunction()->getName().drop_front(5).split('.').first;
        for(StringRef target:{"aarch64","amdgcn","arm","bpf","dx","hexagon","loongarch","mips","nvvm","ppc","r600","riscv","s390","spv","ve","wasm","x86","xcore"})if(n==target)reject("V16",&i);
      }
    }
  }
}
} // namespace bennett
