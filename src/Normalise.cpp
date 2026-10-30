#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/Config/llvm-config.h"
using namespace llvm;
namespace bennett {
// M1 scalar materialisation slice. Other rules remain explicit M2 obligations;
// this function is not a full §12 validator or a production conformance verdict.
void normaliseScalar(Function &f) {
  auto removeAttrs = [&](AttributeList attrs) {
    static const std::set<std::string> erased = {
      "noundef","nonnull","range","align","dereferenceable","dereferenceable_or_null",
      "nofpclass","noalias","nocapture","captures","readnone","readonly","writeonly",
      "returned","writable","dead_on_unwind","initializes","allocalign","allocptr",
      "memory","argmemonly","inaccessiblememonly","inaccessiblemem_or_argmemonly",
      "willreturn","mustprogress","nosync","nofree","norecurse","speculatable"};
    for (unsigned idx : attrs.indexes()) {
      bool abiAlign = attrs.hasAttributeAtIndex(idx,Attribute::ByVal) || attrs.hasAttributeAtIndex(idx,Attribute::ByRef) || attrs.hasAttributeAtIndex(idx,Attribute::StructRet) || attrs.hasAttributeAtIndex(idx,Attribute::InAlloca) || attrs.hasAttributeAtIndex(idx,Attribute::Preallocated);
      auto old = attrs.getAttributes(idx);
      for (Attribute a : old)
        if (a.isEnumAttribute() || a.isIntAttribute() || a.isTypeAttribute()) {
          auto name = Attribute::getNameFromAttrKind(a.getKindAsEnum());
          if (erased.count(name.str()) && !(name=="align" && abiAlign))
            attrs = attrs.removeAttributeAtIndex(f.getContext(),idx,a.getKindAsEnum());
        }
    }
    return attrs;
  };
  // N1–N4, in separate sweeps to preserve table ordering.
  for (Instruction &i : instructions(f)) i.dropPoisonGeneratingFlags();
  for (Instruction &i : instructions(f))
    if (isa<FPMathOperator>(i)) i.setFastMathFlags(FastMathFlags());
  for (Instruction &i : instructions(f)) {
    SmallVector<std::pair<unsigned,MDNode *>> md; i.getAllMetadataOtherThanDebugLoc(md);
    for (auto &m : md) i.setMetadata(m.first,nullptr);
  }
  f.setAttributes(removeAttrs(f.getAttributes()));
  for (Instruction &i : instructions(f))
    if (auto *c = dyn_cast<CallBase>(&i)) c->setAttributes(removeAttrs(c->getAttributes()));
  SmallVector<Instruction *> work;
  for (Instruction &i : instructions(f)) work.push_back(&i);
  // N5/N6.
  for (Instruction *&i : work)
    if (auto *c = dyn_cast<IntrinsicInst>(i)) {
      StringRef name=c->getCalledFunction()->getName();
      bool erase=name.starts_with("llvm.assume") || name.starts_with("llvm.lifetime.") || name.starts_with("llvm.dbg.") || name=="llvm.sideeffect" || name=="llvm.donothing";
      if (erase) { if (!c->use_empty()) unimplemented("§12 scalar intrinsic result",2,c); c->eraseFromParent(); i=nullptr; }
    }
  // N7 recursive constant replacement (including constant aggregate fields).
  std::function<Constant *(Constant *)> zero = [&](Constant *c)->Constant * {
    if (isa<UndefValue>(c) || isa<PoisonValue>(c)) return Constant::getNullValue(c->getType());
    if (isa<ConstantAggregate>(c) || isa<ConstantVector>(c)) {
      SmallVector<Constant *> fields; bool changed=false;
      for (Value *v : c->operands()) { auto *old=cast<Constant>(v), *n=zero(old);fields.push_back(n);changed|=old!=n; }
      if (!changed) return c;
      if (auto *t=dyn_cast<StructType>(c->getType())) return ConstantStruct::get(t,fields);
      if (auto *t=dyn_cast<ArrayType>(c->getType())) return ConstantArray::get(t,fields);
      return ConstantVector::get(fields);
    }
    return c;
  };
  for (Instruction *i : work) if (i)
    for (Use &u : i->operands()) if (auto *c=dyn_cast<Constant>(u.get())) u.set(zero(c));
  // N8.
  for (Instruction *&i : work) if (auto *z=dyn_cast_or_null<FreezeInst>(i)) {z->replaceAllUsesWith(z->getOperand(0));z->eraseFromParent();i=nullptr;}
  // N9, scalar atomics. LLVM's single-thread lowering is represented explicitly.
  for (Instruction *&i : work) if (i) {
    if (auto *l=dyn_cast<LoadInst>(i)) {l->setAtomic(AtomicOrdering::NotAtomic);l->setVolatile(false);}
    if (auto *s=dyn_cast<StoreInst>(i)) {s->setAtomic(AtomicOrdering::NotAtomic);s->setVolatile(false);}
    if (isa<FenceInst>(i)) {i->eraseFromParent();i=nullptr;continue;}
    if (auto *a=dyn_cast<AtomicRMWInst>(i)) {
      IRBuilder<> b(a); std::string r=a->getName().str();
      auto *old=b.CreateLoad(a->getType(),a->getPointerOperand(),"nz.l."+r); old->setAlignment(a->getAlign());
      Value *v=a->getValOperand(), *n=nullptr;
      switch(a->getOperation()) {
      case AtomicRMWInst::Xchg:n=v;break;
      case AtomicRMWInst::Add:n=b.CreateAdd(old,v,"nz.v."+r);break;
      case AtomicRMWInst::Sub:n=b.CreateSub(old,v,"nz.v."+r);break;
      case AtomicRMWInst::And:n=b.CreateAnd(old,v,"nz.v."+r);break;
      case AtomicRMWInst::Or:n=b.CreateOr(old,v,"nz.v."+r);break;
      case AtomicRMWInst::Xor:n=b.CreateXor(old,v,"nz.v."+r);break;
      case AtomicRMWInst::Nand: {auto *t=b.CreateAnd(old,v,"nz.a."+r);n=b.CreateXor(t,Constant::getAllOnesValue(v->getType()),"nz.v."+r);break;}
      default:unimplemented("§12 N9 remaining atomic operations",2,a);
      }
      auto *s=b.CreateStore(n,a->getPointerOperand());s->setAlignment(a->getAlign());a->replaceAllUsesWith(old);a->eraseFromParent();i=nullptr;
    }
  }
  // N10.
  for (Instruction *&i : work) if (auto *c=dyn_cast_or_null<IntrinsicInst>(i)) {
    StringRef n=c->getCalledFunction()->getName();Constant *v=nullptr;
    if (n.starts_with("llvm.is.constant.")) v=ConstantInt::getFalse(f.getContext());
    if (n.starts_with("llvm.objectsize.")) v=cast<ConstantInt>(c->getArgOperand(1))->isZero()?Constant::getAllOnesValue(c->getType()):Constant::getNullValue(c->getType());
    if(v) {c->replaceAllUsesWith(v);c->eraseFromParent();i=nullptr;}
  }
  // N14. Preserve the unsafe shift only behind the defined zero-select.
  for (Instruction *&i : work) if (auto *op=dyn_cast_or_null<BinaryOperator>(i))
    if(op->isShift() && op->getType()->isIntegerTy()) {
      unsigned width=op->getType()->getIntegerBitWidth();auto *amount=op->getOperand(1);
      if(auto *c=dyn_cast<ConstantInt>(amount)) {
        if(c->getValue().uge(width)) {op->replaceAllUsesWith(Constant::getNullValue(op->getType()));op->eraseFromParent();i=nullptr;}
      } else {
        IRBuilder<> b(op);auto r=op->getName().str();auto *cmp=b.CreateICmpUGE(amount,ConstantInt::get(op->getType(),width),"nz.c."+r);
        op->setName("nz.s."+r);b.SetInsertPoint(op->getNextNode());
        auto *select=cast<Instruction>(b.CreateSelect(cmp,Constant::getNullValue(op->getType()),op,r));
        op->replaceUsesWithIf(select,[&](Use &u) {return u.getUser()!=select;});
      }
    }
}
} // namespace bennett
