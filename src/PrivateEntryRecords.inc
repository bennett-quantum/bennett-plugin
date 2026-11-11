  bool withinBudgetRecord(const Value *pointer,const AllocaInst *root,uint64_t extent,uint64_t bytes) {
    int64_t offset=0;
    auto *base=GetPointerBaseWithConstantOffset(pointer,offset,m.getDataLayout());
    return base==root && offset>=0 && uint64_t(offset)<=extent && bytes<=extent-uint64_t(offset);
  }
  bool privateBudgetRecord(Value *pointer) {
    auto *root=dyn_cast<AllocaInst>(getUnderlyingObject(pointer));
    if(!root || root->getFunction()!=&f || !root->isStaticAlloca())return false;
    auto element=m.getDataLayout().getTypeAllocSize(root->getAllocatedType());
    if(element.isScalable() || !element.getFixedValue())return false;
    auto count=cast<ConstantInt>(root->getArraySize())->getValue();
    if(count.getActiveBits()>64 || count.getZExtValue()>UINT64_MAX/element.getFixedValue())return false;
    uint64_t extent=count.getZExtValue()*element.getFixedValue();
    if(!withinBudgetRecord(pointer,root,extent,40))return false;
    std::set<const Value *> seen;
    std::function<bool(const Value *)> confined=[&](const Value *value) {
      if(!seen.insert(value).second)return true;
      for(auto *user:value->users()) {
        if(isa<GetElementPtrInst>(user) || isa<BitCastInst>(user) || isa<AddrSpaceCastInst>(user)) {
          if(!confined(user))return false;
        } else if(auto *store=dyn_cast<StoreInst>(user)) {
          if(store->getPointerOperand()!=value || store->getValueOperand()==value)return false;
          auto size=m.getDataLayout().getTypeStoreSize(store->getValueOperand()->getType());
          if(size.isScalable() || !withinBudgetRecord(value,root,extent,size.getFixedValue()))return false;
        } else if(auto *call=dyn_cast<CallBase>(user)) {
          auto *callee=call->getCalledFunction();if(!callee)return false;
          auto name=callee->getName();
          if(name.starts_with("llvm.lifetime."))continue;
          if(name.starts_with("llvm.memset.") && call->getArgOperand(0)==value) {
            auto *length=dyn_cast<ConstantInt>(call->getArgOperand(2));
            if(!length || length->getValue().getActiveBits()>64 || !withinBudgetRecord(value,root,extent,length->getZExtValue()))return false;
            continue;
          }
          if(name=="__bennett_oracle" && call->getArgOperand(1)==value && call->getArgOperand(2)!=value && call->getArgOperand(0)!=value)continue;
          return false;
        } else return false;
      }
      return true;
    };
    return confined(root);
  }
  std::set<const Value *> oracleRecordObjects() {
    std::set<const Value *> records;
    for(auto &i:instructions(f))if(auto *call=dyn_cast<CallBase>(&i))
      if(auto *callee=call->getCalledFunction();callee && callee->getName()=="__bennett_oracle") {
        records.insert(getUnderlyingObject(call->getArgOperand(2)));
        if(privateBudgetRecord(call->getArgOperand(1)))records.insert(getUnderlyingObject(call->getArgOperand(1)));
      }
    return records;
  }
