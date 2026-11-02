// N23 (§14.3). A variadic definition takes a va block in place of its variadic arguments, every call
// of it spills them into one, and va_start builds the target's va_list so that the front end's
// inline va_arg takes its memory path. An external variadic without bitcode keeps its call (§4.5).
namespace {
enum class VaTarget {X86_64,AArch64,RISCV64};
VaTarget vaTarget(Module &m,const Value *at) {
  Triple triple(m.getTargetTriple());
  // A module with no triple is the System V layout of every published example.
  if(triple.getArch()==Triple::UnknownArch || triple.getArch()==Triple::x86_64)return VaTarget::X86_64;
  if(triple.getArch()==Triple::aarch64)return VaTarget::AArch64;
  if(triple.getArch()==Triple::riscv64)return VaTarget::RISCV64;
  unimplemented("§14.3 N23 va_list row for this target ABI",2,at);
}
uint64_t vaListBytes(VaTarget t) {return t==VaTarget::X86_64?24:t==VaTarget::AArch64?32:8;}
void writeVaList(IRBuilder<> &b,Value *ap,Value *block,VaTarget target,const std::string &r) {
  auto field=[&](uint64_t offset,const char *tag)->Value * {
    return offset?b.CreateGEP(b.getInt8Ty(),ap,b.getInt64(offset),std::string("nz.")+tag+"."+r):ap;
  };
  auto *null=ConstantPointerNull::get(b.getPtrTy());
  auto put=[&](Value *value,Value *address,unsigned align) {b.CreateStore(value,address)->setAlignment(Align(align));};
  if(target==VaTarget::X86_64) {
    put(b.getInt32(48),ap,4);
    put(b.getInt32(176),field(4,"vfo"),4);
    put(block,field(8,"vov"),8);
    put(null,field(16,"vrs"),8);
  } else if(target==VaTarget::AArch64) {
    put(block,field(0,"vs"),8);
    put(null,field(8,"vgt"),8);
    put(null,field(16,"vvt"),8);
    put(b.getInt32(0),field(24,"vgo"),4);
    put(b.getInt32(0),field(28,"vvo"),4);
  } else put(block,field(0,"vs"),8);
}
}
void normaliseVarargs(Module &m,Function *&root) {
  auto &ctx=m.getContext();
  auto spared=[&](Function *f) {return f->isIntrinsic() || markers().count(f->getName().str());};
  SmallVector<CallBase *> calls;bool any=false;
  for(Function &f:m) {
    any|=f.isVarArg() && !f.isDeclaration() && !spared(&f);
    for(Instruction &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i))if(c->getFunctionType()->isVarArg()) {
      auto *direct=resolve(c->getCalledOperand());
      if(direct && (direct->isDeclaration() || spared(direct)))continue;
      calls.push_back(c);
    }
  }
  if(!any)return;
  auto &dl=m.getDataLayout();
  std::map<Function *,unsigned> resultless;
  for(auto *c:calls) {
    if(!isa<CallInst>(c))unimplemented("§14.3 N23 invoke of a variadic function",2,c);
    Function *caller=c->getFunction();auto *oldType=c->getFunctionType();
    unsigned fixed=oldType->getNumParams();
    std::string r=c->hasName()?c->getName().str():caller->getName().str()+"."+std::to_string(resultless[caller]++);
    uint64_t size=0,alignment=8;
    SmallVector<uint64_t> offsets;
    for(unsigned k=fixed;k<c->arg_size();++k) {
      if(c->paramHasAttr(k,Attribute::ByVal))unimplemented("§14.3 N23 byval variadic argument",2,c);
      auto *t=c->getArgOperand(k)->getType();
      uint64_t align=std::max<uint64_t>(8,dl.getABITypeAlign(t).value());
      size=alignTo(size,align);offsets.push_back(size);
      size+=alignTo(dl.getTypeStoreSize(t).getFixedValue(),8);
      alignment=std::max(alignment,align);
    }
    IRBuilder<> b(ctx);
    Value *block=ConstantPointerNull::get(b.getPtrTy());
    if(size) {
      b.SetInsertPoint(&*caller->getEntryBlock().getFirstInsertionPt());
      auto *slot=b.CreateAlloca(ArrayType::get(b.getInt8Ty(),size),nullptr,"nz.vb."+r);
      slot->setAlignment(Align(alignment));block=slot;
      b.SetInsertPoint(c);
      for(unsigned k=fixed;k<c->arg_size();++k) {
        unsigned j=k-fixed;
        Value *address=j?b.CreateGEP(b.getInt8Ty(),block,b.getInt64(offsets[j]),"nz.vb"+std::to_string(j)+"."+r):block;
        b.CreateStore(c->getArgOperand(k),address)->setAlignment(Align(std::max<uint64_t>(8,dl.getABITypeAlign(c->getArgOperand(k)->getType()).value())));
      }
    }
    SmallVector<Type *> params(oldType->param_begin(),oldType->param_end());params.push_back(PointerType::get(ctx,0));
    auto *newType=FunctionType::get(oldType->getReturnType(),params,false);
    SmallVector<Value *> args(c->arg_begin(),c->arg_begin()+fixed);args.push_back(block);
    SmallVector<OperandBundleDef> bundles;c->getOperandBundlesAsDefs(bundles);
    b.SetInsertPoint(c);
    auto *replacement=b.CreateCall(newType,c->getCalledOperand(),args,bundles);
    replacement->setCallingConv(c->getCallingConv());
    SmallVector<AttributeSet> paramAttrs;
    for(unsigned k=0;k<fixed;++k)paramAttrs.push_back(c->getAttributes().getParamAttrs(k));
    paramAttrs.push_back(AttributeSet());
    replacement->setAttributes(AttributeList::get(ctx,c->getAttributes().getFnAttrs(),c->getAttributes().getRetAttrs(),paramAttrs));
    // A new call instruction: the callee reads the caller's frame, so it can be no tail call.
    replacement->setDebugLoc(c->getDebugLoc());
    if(c->hasName()) {auto name=c->getName().str();c->setName("");replacement->setName(name);}
    c->replaceAllUsesWith(replacement);c->eraseFromParent();
  }
  SmallVector<Function *> variadic;
  for(Function &f:m)if(f.isVarArg() && !f.isDeclaration() && !spared(&f))variadic.push_back(&f);
  for(Function *f:variadic) {
    auto *oldType=f->getFunctionType();
    SmallVector<Type *> params(oldType->param_begin(),oldType->param_end());params.push_back(PointerType::get(ctx,0));
    auto *nf=Function::Create(FunctionType::get(oldType->getReturnType(),params,false),f->getLinkage(),f->getAddressSpace(),"",&m);
    nf->copyAttributesFrom(f);nf->copyMetadata(f,0);
    m.getFunctionList().remove(nf);m.getFunctionList().insertAfter(f->getIterator(),nf);
    nf->splice(nf->begin(),f);
    auto to=nf->arg_begin();
    for(Argument &a:f->args()) {to->setName(a.getName());a.replaceAllUsesWith(&*to);++to;}
    Argument *block=&*to;block->setName("nz.va");
    SmallVector<IntrinsicInst *> intrinsics;
    SmallVector<VAArgInst *> reads;
    for(Instruction &i:instructions(nf)) {
      if(auto *c=dyn_cast<IntrinsicInst>(&i)) {auto id=c->getIntrinsicID();if(id==Intrinsic::vastart || id==Intrinsic::vaend || id==Intrinsic::vacopy)intrinsics.push_back(c);}
      if(auto *v=dyn_cast<VAArgInst>(&i))reads.push_back(v);
    }
    auto target=vaTarget(m,nf);unsigned started=0,arguments=0;
    for(auto *c:intrinsics) {
      IRBuilder<> b(c);
      if(c->getIntrinsicID()==Intrinsic::vastart)writeVaList(b,c->getArgOperand(0),block,target,nf->getName().str().empty()?f->getName().str()+"."+std::to_string(started++):nf->getName().str()+"."+std::to_string(started++));
      else if(c->getIntrinsicID()==Intrinsic::vacopy)b.CreateMemCpy(c->getArgOperand(0),Align(1),c->getArgOperand(1),Align(1),vaListBytes(target));
      c->eraseFromParent();
    }
    for(auto *v:reads) {
      // IR va_arg by the same memory layout: load the cursor, read, advance by the slot.
      IRBuilder<> b(v);auto r=v->hasName()?v->getName().str():std::to_string(arguments++);
      Value *cursorAddress=target==VaTarget::X86_64?b.CreateGEP(b.getInt8Ty(),v->getPointerOperand(),b.getInt64(8),"nz.vov."+r):v->getPointerOperand();
      auto *cursor=b.CreateLoad(b.getPtrTy(),cursorAddress,"nz.vc."+r);cursor->setAlignment(Align(8));
      auto *t=v->getType();
      uint64_t align=std::max<uint64_t>(8,dl.getABITypeAlign(t).value());
      Value *at=cursor;
      if(align>8) {
        auto *bits=b.CreatePtrToInt(cursor,b.getInt64Ty());
        auto *rounded=b.CreateAnd(b.CreateAdd(bits,b.getInt64(align-1)),b.getInt64(~(align-1)));
        at=b.CreateGEP(b.getInt8Ty(),cursor,b.CreateSub(rounded,bits),"nz.vcr."+r);
      }
      auto *value=b.CreateLoad(t,at);value->setAlignment(Align(1));
      auto *next=b.CreateGEP(b.getInt8Ty(),at,b.getInt64(alignTo(dl.getTypeStoreSize(t).getFixedValue(),8)),"nz.vn."+r);
      b.CreateStore(next,cursorAddress)->setAlignment(Align(8));
      if(v->hasName()) {auto name=v->getName().str();v->setName("");value->setName(name);}
      v->replaceAllUsesWith(value);v->eraseFromParent();
    }
    auto name=f->getName().str();
    f->replaceAllUsesWith(nf);
    if(root==f)root=nf;
    f->eraseFromParent();
    nf->setName(name);
  }
  // N23 removes these calls, so their declarations are no longer part of the module.
  SmallVector<Function *> unused;
  for(Function &f:m)if(f.use_empty() && (f.getIntrinsicID()==Intrinsic::vastart || f.getIntrinsicID()==Intrinsic::vaend || f.getIntrinsicID()==Intrinsic::vacopy))unused.push_back(&f);
  for(auto *f:unused)f->eraseFromParent();
}
