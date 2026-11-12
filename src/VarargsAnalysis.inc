// The published rows cover System V, AAPCS64 and RISC-V LP64, rather than
// every ABI sharing those instruction sets. Preserve explicit System V CC.
static bool unsupportedVaABI(Module &m,const Value *at) {
  Triple triple(m.getTargetTriple());
  auto *function=dyn_cast<Function>(at);
  auto cc=function?function->getCallingConv():CallingConv::C;
  return cc==CallingConv::Win64 ||
      (triple.isOSWindows() && cc!=CallingConv::X86_64_SysV) ||
      (triple.isOSDarwin() && triple.getArch()==Triple::aarch64);
}
// The materialiser and S2 use this same spill graph (§5.2, §14.3).
static Value *spillVaArguments(IRBuilder<> &b,CallBase *c,const std::string &r) {
  if(!isa<CallInst>(c))unimplemented("§14.3 N23 invoke of a variadic function",2,c);
  auto &dl=c->getModule()->getDataLayout();
  auto *caller=b.GetInsertBlock()->getParent();
  unsigned fixed=c->getFunctionType()->getNumParams();
  uint64_t size=0,alignment=8;
  SmallVector<uint64_t> offsets;
  for(unsigned k=fixed;k<c->arg_size();++k) {
    if(c->paramHasAttr(k,Attribute::ByVal))unimplemented("§14.3 N23 byval variadic argument",2,c);
    auto *t=c->getArgOperand(k)->getType();
    if(!t->isSized() || dl.getTypeStoreSize(t).isScalable())
      unimplemented("§5.2 / §14.3 N23 variadic slot has no fixed ABI size",2,c);
    uint64_t align=std::max<uint64_t>(8,dl.getABITypeAlign(t).value());
    size=alignTo(size,align);offsets.push_back(size);
    size+=alignTo(dl.getTypeStoreSize(t).getFixedValue(),8);
    alignment=std::max(alignment,align);
  }
  Value *block=ConstantPointerNull::get(b.getPtrTy());
  if(size) {
    IRBuilder<> entry(&caller->getEntryBlock(),caller->getEntryBlock().begin());
    auto *slot=entry.CreateAlloca(ArrayType::get(b.getInt8Ty(),size),nullptr,"nz.vb."+r);
    slot->setAlignment(Align(alignment));block=slot;
    for(unsigned k=fixed;k<c->arg_size();++k) {
      unsigned j=k-fixed;
      Value *address=j?b.CreateGEP(b.getInt8Ty(),block,b.getInt64(offsets[j]),"nz.vb"+std::to_string(j)+"."+r):block;
      b.CreateStore(c->getArgOperand(k),address)->setAlignment(Align(std::max<uint64_t>(8,dl.getABITypeAlign(c->getArgOperand(k)->getType()).value())));
    }
  }
  return block;
}

// Private S2 instructions retain source operands and live for the analysis run.
// A spill's alloca is one object per call site, as in the materialised caller.
Function *varargsTransfer(Instruction &i,bool spill) {
  auto &m=*i.getModule();auto &ctx=m.getContext();
  auto *call=dyn_cast<IntrinsicInst>(&i);
  bool start=call && call->getIntrinsicID()==Intrinsic::vastart;
  if(start && !i.getFunction()->isVarArg())
    unimplemented("§5.2 / §14.3 N23 va_start outside a variadic definition",2,&i);
  SmallVector<Type *> params;
  if(start)params.push_back(PointerType::get(ctx,0));
  auto *result=spill?PointerType::get(ctx,0):i.getType();
  auto *f=Function::Create(FunctionType::get(result,params,false),GlobalValue::InternalLinkage,"",m);
  f->setCallingConv(i.getFunction()->getCallingConv());
  auto *bb=BasicBlock::Create(ctx,"",f);IRBuilder<> b(bb);
  if(spill) b.CreateRet(spillVaArguments(b,cast<CallBase>(&i),"s2"));
  else {
    auto *copy=i.clone();copy->insertInto(bb,bb->end());
    b.SetInsertPoint(bb);
    b.CreateRet(i.getType()->isVoidTy()?nullptr:copy);
    lowerVaOperations(*f,start?&*f->arg_begin():nullptr);
  }
  f->removeFromParent();return f;
}
