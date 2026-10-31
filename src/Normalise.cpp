#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/Operator.h"
#include "llvm/Transforms/Utils/Local.h"
#include "llvm/Transforms/Scalar/LowerWidenableCondition.h"
#include "llvm/Config/llvm-config.h"
using namespace llvm;
namespace bennett {
// M1 scalar materialisation slice. Other rules remain explicit M2 obligations;
// this function is not a full §12 validator or a production conformance verdict.
void normaliseScalar(Function &f) {
  // N0's last lowering, invoked only when this intrinsic occurs.
  bool widenable=false;
  for(Instruction &i:instructions(f)) if(auto *c=dyn_cast<IntrinsicInst>(&i))
    widenable|=c->getIntrinsicID()==Intrinsic::experimental_widenable_condition;
  if(widenable) {FunctionAnalysisManager analyses;LowerWidenableConditionPass().run(f,analyses);}
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
    for (auto &m : md)
      if(m.first!=f.getContext().getMDKindID("bennett.rstep")) i.setMetadata(m.first,nullptr);
  }
  f.setAttributes(removeAttrs(f.getAttributes()));
  for (Instruction &i : instructions(f))
    if (auto *c = dyn_cast<CallBase>(&i)) c->setAttributes(removeAttrs(c->getAttributes()));
  SmallVector<Instruction *> work;
  for (Instruction &i : instructions(f)) work.push_back(&i);
  // N5/N6. Identity calls are replaced before deleting the effect-free calls;
  // reverse order removes token consumers before their producers.
  auto family=[](StringRef name,StringRef prefix) {return name==prefix || (name.starts_with(prefix) && name.drop_front(prefix.size()).starts_with("."));};
  for(Instruction *&i:work) if(auto *c=dyn_cast<IntrinsicInst>(i)) {
    StringRef name=c->getCalledFunction()->getName();
    bool identity=false;
    for(StringRef prefix:{"llvm.expect","llvm.annotation","llvm.ptr.annotation","llvm.launder.invariant.group","llvm.strip.invariant.group","llvm.ssa.copy","llvm.arithmetic.fence","llvm.threadlocal.address","llvm.protected.field.ptr","llvm.ptrauth.sign","llvm.ptrauth.auth","llvm.ptrauth.resign","llvm.ptrauth.auth.with.pc.and.resign","llvm.ptrauth.strip"}) identity|=family(name,prefix);
    if(identity) {c->replaceAllUsesWith(c->getArgOperand(0));c->eraseFromParent();i=nullptr;}
  }
  for(auto it=work.rbegin();it!=work.rend();++it) if(auto *c=dyn_cast_or_null<IntrinsicInst>(*it)) {
    StringRef name=c->getCalledFunction()->getName();bool erase=false;
    for(StringRef prefix:{"llvm.assume","llvm.sideeffect","llvm.donothing","llvm.pseudoprobe","llvm.fake.use","llvm.dbg","llvm.experimental.noalias.scope.decl","llvm.codeview.annotation","llvm.var.annotation","llvm.reloc.none","llvm.prefetch","llvm.pcmarker","llvm.clear_cache","llvm.experimental.convergence","llvm.seh","llvm.xray","llvm.experimental.stackmap","llvm.eh.unwind.init","llvm.asan.check.memaccess","llvm.hwasan.check.memaccess","llvm.lifetime","llvm.invariant.start","llvm.invariant.end"}) erase|=family(name,prefix);
    if(erase) {if(!c->use_empty()) unimplemented("§12 N5/N6 live intrinsic result",2,c);c->eraseFromParent();*it=nullptr;}
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
  std::set<GlobalVariable *> globals; std::set<Value *> seen;
  std::function<void(Value *)> data=[&](Value *v) {
    if(!seen.insert(v).second)return;
    if(auto *g=dyn_cast<GlobalVariable>(v)) {globals.insert(g);if(g->hasInitializer())data(g->getInitializer());return;}
    if(isa<Function>(v))return;
    if(auto *u=dyn_cast<User>(v))for(Value *x:u->operands())data(x);
  };
  for(Instruction *i:work)if(i)for(Value *v:i->operands())data(v);
  for(auto *g:globals)if(g->hasInitializer())g->setInitializer(zero(g->getInitializer()));
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
      case AtomicRMWInst::Min:
      case AtomicRMWInst::Max:
      case AtomicRMWInst::UMin:
      case AtomicRMWInst::UMax: {
        auto op=a->getOperation();
        auto pred=op==AtomicRMWInst::Min?CmpInst::ICMP_SLT:
                  op==AtomicRMWInst::Max?CmpInst::ICMP_SGT:
                  op==AtomicRMWInst::UMin?CmpInst::ICMP_ULT:CmpInst::ICMP_UGT;
        auto *k=b.CreateICmp(pred,old,v,"nz.k."+r);
        n=b.CreateSelect(k,old,v,"nz.v."+r);break;
      }
      case AtomicRMWInst::UIncWrap: {
        auto *k=b.CreateICmpUGE(old,v,"nz.k."+r);
        auto *inc=b.CreateAdd(old,ConstantInt::get(v->getType(),1),"nz.i."+r);
        n=b.CreateSelect(k,Constant::getNullValue(v->getType()),inc,"nz.v."+r);break;
      }
      case AtomicRMWInst::UDecWrap: {
        auto *k=b.CreateICmpEQ(old,Constant::getNullValue(v->getType()),"nz.k."+r);
        auto *g=b.CreateICmpUGT(old,v,"nz.g."+r);
        auto *w=b.CreateOr(k,g,"nz.w."+r);
        auto *d=b.CreateSub(old,ConstantInt::get(v->getType(),1),"nz.d."+r);
        n=b.CreateSelect(w,v,d,"nz.v."+r);break;
      }
#if LLVM_VERSION_MAJOR >= 23
      case AtomicRMWInst::USubCond:
      case AtomicRMWInst::USubSat: {
        auto *k=b.CreateICmpUGE(old,v,"nz.k."+r);
        auto *s=b.CreateSub(old,v,"nz.s."+r);
        Value *fallback=a->getOperation()==AtomicRMWInst::USubCond?static_cast<Value *>(old):Constant::getNullValue(v->getType());
        n=b.CreateSelect(k,s,fallback,"nz.v."+r);break;
      }
#endif
      default:unimplemented("§12 N9 remaining atomic operations",2,a);
      }
      auto *s=b.CreateStore(n,a->getPointerOperand());s->setAlignment(a->getAlign());a->replaceAllUsesWith(old);a->eraseFromParent();i=nullptr;
    }
    if (auto *c=dyn_cast_or_null<AtomicCmpXchgInst>(i)) {
      IRBuilder<> b(c);auto r=c->getName().str();
      auto *old=b.CreateLoad(c->getCompareOperand()->getType(),c->getPointerOperand(),"nz.l."+r);old->setAlignment(c->getAlign());
      auto *eq=b.CreateICmpEQ(old,c->getCompareOperand(),"nz.e."+r);
      auto *value=b.CreateSelect(eq,c->getNewValOperand(),old,"nz.s."+r);
      b.CreateStore(value,c->getPointerOperand())->setAlignment(c->getAlign());
      auto *agg=b.CreateInsertValue(Constant::getNullValue(c->getType()),old,{0},"nz.a."+r);
      c->setName("");auto *result=b.CreateInsertValue(agg,eq,{1},r);
      c->replaceAllUsesWith(result);c->eraseFromParent();i=nullptr;
    }
  }
  // N11: F(4), including deletion of the original successor suffix.
  for (Instruction *i : work) if(auto *c=dyn_cast_or_null<IntrinsicInst>(i)) {
    auto n=c->getCalledFunction()->getName();
    if(n=="llvm.trap" || n=="llvm.debugtrap" || n=="llvm.ubsantrap" || n=="llvm.looptrap") {
      IRBuilder<> b(c);auto *ty=Type::getInt64Ty(f.getContext());
      auto fault=f.getParent()->getOrInsertFunction("__bennett_nz_fault",Type::getVoidTy(f.getContext()),ty);
      b.CreateCall(fault,{ConstantInt::get(ty,4)});
      // Later work entries can point into the erased suffix. Clear them first.
      for(auto *&entry:work) if(entry && entry->getParent()==c->getParent() &&
          (entry==c || c->comesBefore(entry))) entry=nullptr;
      changeToUnreachable(c,false);
    }
  }
  // N10.
  for (Instruction *&i : work) if (auto *c=dyn_cast_or_null<IntrinsicInst>(i)) {
    StringRef n=c->getCalledFunction()->getName();Constant *v=nullptr;
    if (n.starts_with("llvm.is.constant.")) v=ConstantInt::getFalse(f.getContext());
    if (n.starts_with("llvm.objectsize.")) v=cast<ConstantInt>(c->getArgOperand(1))->isZero()?Constant::getAllOnesValue(c->getType()):Constant::getNullValue(c->getType());
    if(n=="llvm.allow.runtime.check" || n=="llvm.allow.ubsan.check") v=ConstantInt::getTrue(f.getContext());
    if(n.starts_with("llvm.allow.sanitize.")) v=ConstantInt::getFalse(f.getContext());
    if(n.starts_with("llvm.get.dynamic.area.offset")) v=Constant::getNullValue(c->getType());
    if(n.starts_with("llvm.vscale.")) v=ConstantInt::get(c->getType(),1);
    if(v) {c->replaceAllUsesWith(v);c->eraseFromParent();i=nullptr;}
  }
  // N12. N27 supplies the corresponding integer helper rewrite below.
  for(Instruction *i:work) if(auto *c=dyn_cast_or_null<IntrinsicInst>(i)) {
    auto n=c->getCalledFunction()->getName();
    if(n.starts_with("llvm.abs.") || n.starts_with("llvm.ctlz.") || n.starts_with("llvm.cttz.")) c->setArgOperand(1,ConstantInt::getFalse(f.getContext()));
  }
  // N14. Preserve the unsafe shift only behind the defined zero-select.
  for (Instruction *&i : work) if (auto *op=dyn_cast_or_null<BinaryOperator>(i))
    if(op->isShift() && op->getType()->isIntegerTy()) {
      unsigned width=op->getType()->getIntegerBitWidth();auto *amount=op->getOperand(1);
      // V7 explicitly admits the already materialised N14 pattern. A key
      // printer visiting that closure again must not wrap its shift twice.
      if(op->hasOneUse()) if(auto *s=dyn_cast<SelectInst>(*op->user_begin()))
        if(s->getFalseValue()==op && isa<Constant>(s->getTrueValue()) &&
           cast<Constant>(s->getTrueValue())->isNullValue())
          if(auto *cmp=dyn_cast<ICmpInst>(s->getCondition());
             cmp && cmp->getPredicate()==CmpInst::ICMP_UGE && cmp->getOperand(0)==amount)
            if(auto *c=dyn_cast<ConstantInt>(cmp->getOperand(1));c && c->getValue()==width) continue;
      if(auto *c=dyn_cast<ConstantInt>(amount)) {
        if(c->getValue().uge(width)) {op->replaceAllUsesWith(Constant::getNullValue(op->getType()));op->eraseFromParent();i=nullptr;}
      } else {
        IRBuilder<> b(op);auto r=op->getName().str();auto *cmp=b.CreateICmpUGE(amount,ConstantInt::get(op->getType(),width),"nz.c."+r);
        op->setName("nz.s."+r);b.SetInsertPoint(op->getNextNode());
        auto *select=cast<Instruction>(b.CreateSelect(cmp,Constant::getNullValue(op->getType()),op,r));
        op->replaceUsesWithIf(select,[&](Use &u) {return u.getUser()!=select;});
      }
    }
  // N15/N21 lane renaming. Preserve the unsigned index width before building
  // exact L and lane constants (an i1 index into four lanes must not alias 2/3).
  std::map<Value *,SmallVector<Value *>> laneValues;
  auto lanesOf=[&](Value *v)->SmallVector<Value *> {
    if(laneValues.count(v)) return laneValues[v];
    SmallVector<Value *> result;
    if(auto *c=dyn_cast<Constant>(v))
      for(unsigned k=0;k<cast<VectorType>(v->getType())->getElementCount().getKnownMinValue();++k) {
        auto *e=c->getAggregateElement(k);if(!e) return {};result.push_back(e);
      }
    return result;
  };
  SmallVector<Instruction *> laneWork, deadVectors;
  for(Instruction &i:instructions(f)) laneWork.push_back(&i);
  for(Instruction *i:laneWork) {
    auto *extract=dyn_cast<ExtractElementInst>(i);
    auto *insert=dyn_cast<InsertElementInst>(i);
    if(!extract && !insert) continue;
    auto *vector=i->getOperand(0);auto *index=i->getOperand(extract?1:2);
    unsigned count=cast<VectorType>(vector->getType())->getElementCount().getKnownMinValue();
    auto *constant=dyn_cast<ConstantInt>(index);
    if(constant && constant->getValue().uge(count)) {
      i->replaceAllUsesWith(extract?Constant::getNullValue(i->getType()):vector);i->eraseFromParent();continue;
    }
    auto values=lanesOf(vector);if(values.empty()) continue;
    IRBuilder<> b(i);auto r=i->getName().str();
    Value *wide=index;
    if(!constant) {
      unsigned width=std::max(index->getType()->getIntegerBitWidth(),Log2_64(count)+1);
      wide=b.CreateZExtOrTrunc(index,IntegerType::get(f.getContext(),width),"nz.i."+r);
    }
    if(insert) {
      if(constant) values[constant->getZExtValue()]=insert->getOperand(1);
      else for(unsigned k=0;k<count;++k) {
        auto *cmp=b.CreateICmpEQ(wide,ConstantInt::get(wide->getType(),k),"nz.k"+std::to_string(k)+"."+r);
        values[k]=b.CreateSelect(cmp,insert->getOperand(1),values[k],"nz.l"+std::to_string(k)+"."+r);
      }
      laneValues[i]=values;deadVectors.push_back(i);
    } else {
      Value *replacement=nullptr;
      if(constant) replacement=values[constant->getZExtValue()];
      else {
        auto *outside=b.CreateICmpUGE(wide,ConstantInt::get(wide->getType(),count),"nz.c."+r);
        Value *value=Constant::getNullValue(i->getType());
        for(unsigned k=0;k<count;++k) {
          auto *cmp=b.CreateICmpEQ(wide,ConstantInt::get(wide->getType(),k),"nz.k"+std::to_string(k)+"."+r);
          value=b.CreateSelect(cmp,values[k],value,k+1==count?"nz.e."+r:"nz.l"+std::to_string(k)+"."+r);
        }
        i->setName("");replacement=b.CreateSelect(outside,Constant::getNullValue(i->getType()),value,r);
      }
      i->replaceAllUsesWith(replacement);i->eraseFromParent();
    }
  }
  // A vector may still have a genuine vector user; never erase that producer.
  for(auto it=deadVectors.rbegin();it!=deadVectors.rend();++it)
    if((*it)->use_empty()) (*it)->eraseFromParent();

  // N26. The helpers are ordinary linked device functions; this rewrite does
  // not supply their implementation or make an unknown call a passing object.
  unsigned memoryOrdinal=0;
  SmallVector<MemIntrinsic *> memory;
  for(Instruction &i:instructions(f)) if(auto *m=dyn_cast<MemIntrinsic>(&i)) memory.push_back(m);
  for(auto *m:memory) {
    IRBuilder<> b(m);std::string r=m->hasName()?m->getName().str():f.getName().str()+"."+std::to_string(memoryOrdinal++);
    auto *length=m->getLength();auto *i64=Type::getInt64Ty(f.getContext());
    Value *n=length;
    if(length->getType()!=i64) n=b.CreateZExtOrTrunc(length,i64,"nz.n."+r);
    auto *ptr=PointerType::get(f.getContext(),0);auto *voidTy=Type::getVoidTy(f.getContext());
    if(auto *copy=dyn_cast<MemTransferInst>(m)) {
      if(copy->getDestAddressSpace()!=0 || copy->getSourceAddressSpace()!=0) unimplemented("§12 N26 address-space helper ABI",2,copy);
      auto helper=f.getParent()->getOrInsertFunction("__bennett_rt_memmove",voidTy,ptr,ptr,i64);
      b.CreateCall(helper,{copy->getDest(),copy->getSource(),n});
    } else if(auto *fill=dyn_cast<MemSetInst>(m)) {
      if(fill->getDestAddressSpace()!=0) unimplemented("§12 N26 address-space helper ABI",2,fill);
      auto helper=f.getParent()->getOrInsertFunction("__bennett_rt_memset",voidTy,ptr,Type::getInt8Ty(f.getContext()),i64);
      b.CreateCall(helper,{fill->getDest(),fill->getValue(),n});
    } else unimplemented("§12 N26 memory intrinsic family",2,m);
    m->eraseFromParent();
  }
  // N27 scalar count helpers (wide limb-slot ABI remains a separate rule).
  SmallVector<IntrinsicInst *> counts;
  for(Instruction &i:instructions(f)) if(auto *c=dyn_cast<IntrinsicInst>(&i)) {
    auto n=c->getCalledFunction()->getName();
    if((n.starts_with("llvm.ctlz.") || n.starts_with("llvm.cttz.")) && c->getType()->isIntegerTy() && c->getType()->getIntegerBitWidth()<=128) counts.push_back(c);
  }
  for(auto *c:counts) {
    auto n=c->getCalledFunction()->getName();auto op=n.starts_with("llvm.ctlz.")?"ctlz":"cttz";
    auto helper=f.getParent()->getOrInsertFunction("__bennett_rt_"+std::string(op)+"_i"+std::to_string(c->getType()->getIntegerBitWidth()),c->getFunctionType());
    IRBuilder<> b(c);SmallVector<Value *> args(c->args());auto *replacement=b.CreateCall(helper,args);replacement->takeName(c);c->replaceAllUsesWith(replacement);c->eraseFromParent();
  }

}
} // namespace bennett

// N24 and the independent, materialised runtime. A linked runtime definition
// wins: its exact rows are contract/link input (e.g. the budget-stage fixture).
#include <regex>
#include "llvm/AsmParser/Parser.h"
#include "llvm/Linker/Linker.h"
#include "llvm/Support/SourceMgr.h"
namespace bennett {
void normaliseStack(Function &f) {
  // Stack save/restore are calls into the same logical lifetime machinery.
  SmallVector<CallInst *> intrinsics;
  for(auto &i:instructions(f))if(auto *c=dyn_cast<CallInst>(&i))if(auto *g=c->getCalledFunction())
    if(g->getName().starts_with("llvm.stacksave") || g->getName().starts_with("llvm.stackrestore"))intrinsics.push_back(c);
  for(auto *c:intrinsics) {
    bool save=c->getCalledFunction()->getName().starts_with("llvm.stacksave");
    auto target=f.getParent()->getOrInsertFunction(save?"__bennett_rt_ss_save":"__bennett_rt_ss_restore",c->getFunctionType());
    IRBuilder<> b(c);SmallVector<Value *> args(c->args());auto *r=b.CreateCall(target,args);r->takeName(c);c->replaceAllUsesWith(r);c->eraseFromParent();
  }
  SmallVector<AllocaInst *> allocas;
  for(auto &i:instructions(f))if(auto *a=dyn_cast<AllocaInst>(&i))allocas.push_back(a);
  if(allocas.empty())return;
  auto &m=*f.getParent();auto &ctx=f.getContext();auto *i64=Type::getInt64Ty(ctx);auto *ptr=PointerType::getUnqual(ctx);
  uint64_t size=0,alignment=1;std::map<AllocaInst *,uint64_t> offsets;
  for(auto *a:allocas)if(a->getParent()==&f.getEntryBlock())if(auto *n=dyn_cast<ConstantInt>(a->getArraySize())) {
    auto align=a->getAlign().value();alignment=std::max(alignment,align);size=alignTo(size,align);offsets[a]=size;
    auto bytes=m.getDataLayout().getTypeAllocSize(a->getAllocatedType()).getFixedValue();
    if(n->getValue().ugt(UINT64_MAX/std::max(uint64_t(1),bytes)) || UINT64_MAX-size<n->getZExtValue()*bytes)fail("input","§17.3 frame extent overflow",a);
    size+=n->getZExtValue()*bytes;
  }
  if(size>UINT64_MAX-(alignment-1))fail("input","§17.3 aligned frame extent overflow",&f);
  size=alignTo(size,alignment);
  IRBuilder<> b(&*f.getEntryBlock().getFirstInsertionPt());
  auto push=m.getOrInsertFunction("__bennett_rt_ss_push",ptr,i64,i64);
  auto *fp=b.CreateCall(push,{b.getInt64(size),b.getInt64(alignment)},"nz.fp."+f.getName());
  auto dynamic=m.getOrInsertFunction("__bennett_rt_ss_alloca",ptr,i64,i64);
  for(auto *a:allocas) {
    b.SetInsertPoint(a);Value *p;
    if(offsets.count(a))p=b.CreateGEP(b.getInt8Ty(),fp,b.getInt64(offsets[a]));
    else {
      auto *count=b.CreateZExtOrTrunc(a->getArraySize(),i64);
      auto bytes=m.getDataLayout().getTypeAllocSize(a->getAllocatedType()).getFixedValue();
      // Nonwrapping allocation size is part of the faulting N24 semantics.
      auto *bad=b.CreateICmpUGT(count,b.getInt64(UINT64_MAX/std::max(uint64_t(1),bytes)));
      auto check=m.getOrInsertFunction("__bennett_ss_size_check",b.getVoidTy(),b.getInt1Ty());b.CreateCall(check,{bad});
      p=b.CreateCall(dynamic,{b.CreateMul(count,b.getInt64(bytes)),b.getInt64(a->getAlign().value())});
    }
    if(p->getType()!=a->getType())p=b.CreateAddrSpaceCast(p,a->getType());
    p->takeName(a);a->replaceAllUsesWith(p);a->eraseFromParent();
  }
  auto pop=m.getOrInsertFunction("__bennett_rt_ss_pop",b.getVoidTy(),ptr);
  for(auto &i:instructions(f))if(isa<ReturnInst>(i)) {b.SetInsertPoint(&i);b.CreateCall(pop,{fp});}
}
void prepareStack(Module &m,Function &root,uint64_t capacity) {
  std::set<Function *> closure;std::function<void(Function *)> visit=[&](Function *f) {
    if(!f || f->isDeclaration() || !closure.insert(f).second)return;
    for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))visit(c->getCalledFunction());
  };visit(&root);
  for(auto *f:closure)normaliseStack(*f);
  bool needed=false;
  for(auto *f:closure)for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(auto *g=c->getCalledFunction())needed|=g->getName()=="__bennett_rt_ss_push";
  if(!needed)return;
  auto *init=m.getFunction("__bennett_rt_ss_init");
  if(!init || init->isDeclaration()) {
    std::string source=
#include "runtime/ShadowStack.inc"
    ;
    source=std::regex_replace(source,std::regex("CAP"),std::to_string(capacity+1));
    SMDiagnostic error;auto runtime=parseAssemblyString(source,error,m.getContext());
    if(!runtime) {error.print("bennett shadow runtime",errs());fail("output","invalid internal shadow runtime");}
    runtime->setDataLayout(m.getDataLayout());
    for(auto &f:*runtime)if(!f.isDeclaration())f.addFnAttr("bennett.stack.internal");
    if(Linker::linkModules(m,std::move(runtime)))fail("output","shadow runtime link failed");
  }
  // Prove only a constant subrange of a fresh frame in the same block, before
  // any possibly invalidating call. Everything else uses the logical table.
  for(auto *f:closure)if(!f->hasFnAttribute("bennett.stack.internal")) {
    SmallVector<Instruction *> accesses;
    for(auto &i:instructions(f))if(isa<LoadInst>(i)||isa<StoreInst>(i))accesses.push_back(&i);
    for(auto *i:accesses) {
      Value *p;Type *type;
      if(auto *l=dyn_cast<LoadInst>(i)){p=l->getPointerOperand();type=l->getType();}
      else {auto *s=cast<StoreInst>(i);p=s->getPointerOperand();type=s->getValueOperand()->getType();}
      APInt offset(m.getDataLayout().getPointerTypeSizeInBits(p->getType()),0);
      auto *base=p->stripAndAccumulateConstantOffsets(m.getDataLayout(),offset,true);
      if(isa<GlobalVariable>(base))continue;
      bool proven=false;
      if(auto *c=dyn_cast<CallBase>(base);c && c->getParent()==i->getParent() && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_rt_ss_push") {
        auto bytes=m.getDataLayout().getTypeStoreSize(type).getFixedValue();
        if(auto *n=dyn_cast<ConstantInt>(c->getArgOperand(0));n && !offset.isNegative() && offset.getLimitedValue()<=n->getZExtValue() && bytes<=n->getZExtValue()-offset.getLimitedValue()) {
          proven=true;for(auto it=std::next(c->getIterator());&*it!=i;++it)if(isa<CallBase>(*it)){proven=false;break;}
        }
      }
      if(proven)continue;
      // A linked runtime must expose its logical checker or carry an explicit
      // internal-path proof. Runtime-looking source names never exempt access.
      if(!m.getFunction("__bennett_rt_ss_check"))
        unimplemented("§17.3 linked runtime logical-frame validation",2,i);
      IRBuilder<> b(i);auto check=m.getOrInsertFunction("__bennett_rt_ss_check",b.getVoidTy(),b.getPtrTy(),b.getInt64Ty());
      if(p->getType()!=b.getPtrTy())p=b.CreateAddrSpaceCast(p,b.getPtrTy());
      b.CreateCall(check,{p,b.getInt64(m.getDataLayout().getTypeStoreSize(type).getFixedValue())});
    }
  }
}
} // namespace bennett
