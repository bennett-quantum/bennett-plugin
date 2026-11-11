#include "../PrivateEntryRecords.inc"
  // Private CC bookkeeping is not part of G: it mirrors the ISA allocator,
  // never consumes heap entries itself, and is rebuilt per launch.
  bool automaticSnapshot = false;
  unsigned snapshotExponent = 0, snapshotTableExponent = 0;
  GlobalVariable *snapshotBytes=nullptr,*historyCount=nullptr,*historyEntries=nullptr;
  std::vector<GlobalVariable *> snapshotGlobals;
  std::map<std::string,std::pair<std::string,std::string>> snapshotFunctions;
  std::string snapshotToken;
  std::string number(uint64_t n) {return operand(ConstantInt::get(Type::getInt64Ty(m.getContext()),n));}
  std::string emit(std::string t,std::string row) {auto n=fresh(t);rows.push_back(n+" = "+row);return n;}
  std::string addPointer(std::string p,std::string n) {auto bits=emit("i64","ptrtoint.i64 "+p);auto sum=emit("i64","add "+bits+" "+n);return emit("ptr","inttoptr "+sum);}
  void byteLoop(std::string count,const std::function<void(std::string)> &body) {
    auto id=std::to_string(dispatchBlock++),head="snapshot"+id,step=head+"step",done=head+"done";
    auto i=fresh("i64");auto zero=number(0);rows.push_back("br ^"+head+"("+zero+")");rows.push_back("^"+head+"("+i+":i64):");
    auto test=emit("i1","icmp.ult "+i+" "+count);rows.push_back("br "+test+" ^"+step+"() ^"+done+"()");rows.push_back("^"+step+"():");body(i);
    auto one=number(1);auto next=emit("i64","add "+i+" "+one);rows.push_back("br ^"+head+"("+next+")");rows.push_back("^"+done+"():");
  }
  void copyBytes(std::string dst,std::string src,std::string n) {
    auto chunks=emit("i64","lshr "+n+" "+number(4));auto tail=emit("i64","mul "+chunks+" "+number(16));
    byteLoop(chunks,[&](std::string i){auto off=emit("i64","mul "+i+" "+number(16));auto p=addPointer(src,off);auto v=emit("i128","load.i128 "+p);auto d=addPointer(dst,off);rows.push_back("store.i128 "+d+" "+v);});
    auto remaining=emit("i64","sub "+n+" "+tail);
    byteLoop(remaining,[&](std::string i) {auto off=emit("i64","add "+tail+" "+i);auto p=addPointer(src,off);auto v=emit("i8","load.i8 "+p);auto d=addPointer(dst,off);rows.push_back("store.i8 "+d+" "+v);});
  }
  uint64_t snapshotBindingOffset(unsigned index) {
    auto &ctx=m.getContext();auto *i32=Type::getInt32Ty(ctx),*i64=Type::getInt64Ty(ctx);auto *ptr=PointerType::get(ctx,0);
    auto *header=StructType::get(ctx,{i32,i32,i32,i32,ptr,ptr});auto *binding=StructType::get(ctx,{i32,i32,ptr,i64,i64});
    return m.getDataLayout().getTypeAllocSize(header).getFixedValue()+index*m.getDataLayout().getTypeAllocSize(binding).getFixedValue();
  }
  bool wantsSnapshot() {
    if(m.getModuleFlag("bennett.entry.snapshot"))return false; // accepted linked replay inputs
    bool callerState=false,dependency=false,uncertainWrites=false;
    std::set<const GlobalVariable *> callerWrites;
    std::set<const Value *> privateInputs;
    auto descriptors=oracleRecordObjects();
    std::set<Function *> region;
    std::function<void(Function *)> regionVisit=[&](Function *fn) {
      if(!fn || fn->isDeclaration() || !region.insert(fn).second)return;
      for(auto &i:instructions(fn))if(auto *c=dyn_cast<CallBase>(&i)) {
        if(auto *target=c->getCalledFunction())regionVisit(target);
        else for(auto *target:a.candidates(c->getCalledOperand(),c->getFunctionType()))regionVisit(target);
      }
    };
    for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_oracle")for(auto *target:a.candidates(c->getArgOperand(0)))regionVisit(target);
    bool regionStack=false;
    for(auto *fn:region)for(auto &i:instructions(fn)) {
      regionStack|=isa<AllocaInst>(i);
      if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction()) {auto name=c->getCalledFunction()->getName();regionStack|=name.starts_with("__bennett_rt_ss_") || name.starts_with("llvm.stacksave") || name.starts_with("llvm.stackrestore");}
    }
    // Include the implicit N24 materialisation, even before allocas have
    // become calls. These helpers' private writes do not constitute a caller
    // entry-state dependency when the caller has no stack state of its own.
    if(regionStack)for(auto &fn:m)if(fn.getName().starts_with("__bennett_rt_ss_"))regionVisit(&fn);
    // ss_init is an implicit wrapper-prologue member of the L closure.
    regionVisit(m.getFunction("__bennett_rt_ss_init"));
    for(auto &fn:m)if(!region.count(&fn))for(auto &i:instructions(fn))if(auto *st=dyn_cast<StoreInst>(&i))
      if(auto *g=dyn_cast<GlobalVariable>(getUnderlyingObject(st->getPointerOperand()))) {callerWrites.insert(g);callerState=true;}
    std::set<Function *> callerSeen;
    std::function<void(Function *)> caller=[&](Function *fn) {
      if(!fn || fn->isDeclaration() || !callerSeen.insert(fn).second)return;
      for(auto &i:instructions(fn)) {
        if(auto *al=dyn_cast<AllocaInst>(&i))callerState|=!descriptors.count(al);
        if(auto *st=dyn_cast<StoreInst>(&i)) {
          auto *base=getUnderlyingObject(st->getPointerOperand());callerState|=!descriptors.count(base);
          if(auto *g=dyn_cast<GlobalVariable>(base))callerWrites.insert(g);
          else if(!isa<AllocaInst>(base))uncertainWrites=true;
        }
        if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction()) {
          auto *target=c->getCalledFunction();auto name=target->getName();
          callerState|=name=="__bennett_nz_alloc" || name=="__bennett_nz_free" || name.starts_with("__bennett_rt_ss_");
          if(!markers().count(name.str()))caller(target);
        }
      }
    };caller(&f);
    std::set<Function *> seen;std::function<void(Function *)> visit=[&](Function *g) {
      if(!g || g->isDeclaration() || !seen.insert(g).second)return;
      for(auto &i:instructions(g)) {
        dependency|=isa<AllocaInst>(i) || isa<PtrToIntInst>(i);
        Value *p=nullptr;if(auto *l=dyn_cast<LoadInst>(&i))p=l->getPointerOperand();if(auto *st=dyn_cast<StoreInst>(&i))p=st->getPointerOperand();
        if(p) {auto *base=getUnderlyingObject(p);if(auto *global=dyn_cast<GlobalVariable>(base))dependency|=!global->isConstant() && (uncertainWrites || callerWrites.count(global));else dependency|=!privateInputs.count(base);}

        if(auto *c=dyn_cast<CallBase>(&i)) {
          if(auto *t=c->getCalledFunction())dependency|=t->getName()=="__bennett_nz_alloc" || t->getName()=="__bennett_nz_free" || t->getName().starts_with("__bennett_rt_ss_");
          if(auto *target=c->getCalledFunction())visit(target);
          else for(auto *target:a.candidates(c->getCalledOperand(),c->getFunctionType()))visit(target);
        }
      }
    };
    for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_oracle")for(auto *g:a.candidates(c->getArgOperand(0))) {
      privateInputs.clear();seen.clear();
      for(auto &arg:g->args()) {auto kind=descriptorField(*c,snapshotBindingOffset(arg.getArgNo()),Type::getInt32Ty(m.getContext()));if(!kind.top && kind.atoms.size()==1 && kind.atoms.begin()->kind==Atom::Int && (kind.atoms.begin()->integer==3 || kind.atoms.begin()->integer==4))privateInputs.insert(&arg);}
      visit(g);
    }
    return callerState && dependency;
  }
  void setupSnapshot() {
    if(!wantsSnapshot())return;
    automaticSnapshot=true;generalUsed=true;
    snapshotGlobals=entryGlobals(m);
    for(auto &g:m.globals())if(!g.getMetadata("bennett.snapshot.scratch"))ccGlobals.insert(scalarGlobalKey(g));
    uint64_t total=0;for(auto *g:snapshotGlobals) {total+=m.getDataLayout().getTypeAllocSize(g->getValueType()).getFixedValue();ccGlobals.insert(scalarGlobalKey(*g));}
    // At most heap_limit_max successful allocations (zero-sized ones bump by
    // one). Include the pre-entry headroom in the static table capacity.
    uint64_t interfaceCount=0,modelGlobals=0;
    for(auto &i:instructions(f))if(auto *c=dyn_cast<CallBase>(&i);c && c->getCalledFunction() && c->getCalledFunction()->getName()=="__bennett_oracle") {
      uint64_t slots=1;auto nd=descriptorField(*c,8,Type::getInt32Ty(m.getContext()));
      if(singletonInt(nd)){slots+=integer(nd,c);if(integer(nd,c))modelGlobals=12;}else {slots+=5;modelGlobals=12;}
      for(auto *callee:a.candidates(c->getArgOperand(0)))for(auto &arg:callee->args()) {
        auto kind=descriptorField(*c,snapshotBindingOffset(arg.getArgNo()),Type::getInt32Ty(m.getContext()));
        if(!singletonInt(kind) || integer(kind,c)==3)++slots;
      }
      interfaceCount=std::max(interfaceCount,slots);
    }
    uint64_t capacity=PowerOf2Ceil(table.capacities[1]+m.global_size()+3+interfaceCount+modelGlobals);
    snapshotTableExponent=Log2_64(capacity);
    uint64_t bytes=8+16*capacity+total+table.capacities[1];snapshotExponent=4;while((uint64_t(1)<<snapshotExponent)<bytes)++snapshotExponent;
    auto scratch=[&](Type *t) {auto *g=new GlobalVariable(m,t,false,GlobalValue::InternalLinkage,Constant::getNullValue(t),"");g->setMetadata("bennett.snapshot.scratch",MDNode::get(m.getContext(),{}));ccGlobals.insert(scalarGlobalKey(*g));return g;};
    historyCount=scratch(Type::getInt64Ty(m.getContext()));historyEntries=scratch(ArrayType::get(Type::getInt64Ty(m.getContext()),capacity*3));snapshotBytes=scratch(ArrayType::get(Type::getInt8Ty(m.getContext()),uint64_t(1)<<snapshotExponent));
  }
  void recordAllocation(std::string p,std::string size) {
    if(!automaticSnapshot)return;
    auto count=operand(historyCount),table=operand(historyEntries);auto k=emit("i64","load.i64 "+count);auto off=emit("i64","mul "+k+" "+number(24));auto slot=addPointer(table,off);
    auto bits=emit("i64","ptrtoint.i64 "+p);rows.push_back("store.i64 "+slot+" "+bits);auto sz=addPointer(slot,number(8));rows.push_back("store.i64 "+sz+" "+size);auto live=addPointer(slot,number(16));rows.push_back("store.i64 "+live+" "+number(1));auto next=emit("i64","add "+k+" "+number(1));rows.push_back("store.i64 "+count+" "+next);
  }
  void recordFree(std::string p) {
    if(!automaticSnapshot)return;
    auto table=operand(historyEntries),count=operand(historyCount);auto k=emit("i64","load.i64 "+count),bits=emit("i64","ptrtoint.i64 "+p);
    byteLoop(k,[&](std::string i) {auto off=emit("i64","mul "+i+" "+number(24));auto slot=addPointer(table,off);auto base=emit("i64","load.i64 "+slot);auto eq=emit("i1","icmp.eq "+bits+" "+base);auto livep=addPointer(slot,number(16));auto live=emit("i64","load.i64 "+livep);auto value=emit("i64","select "+eq+" "+number(0)+" "+live);rows.push_back("store.i64 "+livep+" "+value);});
  }
  std::string buildSnapshot() {
    auto dst=operand(snapshotBytes),table=operand(historyEntries),count=operand(historyCount);auto k=emit("i64","load.i64 "+count);
    byteLoop(number(uint64_t(1)<<(snapshotExponent-4)),[&](std::string i) {auto p=addPointer(dst,emit("i64","mul "+i+" "+number(16)));rows.push_back("store.i128 "+p+" "+operand(ConstantInt::get(IntegerType::get(m.getContext(),128),0)));});
    rows.push_back("store.i64 "+dst+" "+k);
    auto records=addPointer(dst,number(8));
    byteLoop(k,[&](std::string i) {auto src=addPointer(table,emit("i64","mul "+i+" "+number(24)));auto d=addPointer(records,emit("i64","mul "+i+" "+number(16)));auto sz=emit("i64","load.i64 "+addPointer(src,number(8)));rows.push_back("store.i64 "+d+" "+sz);auto live=emit("i64","load.i64 "+addPointer(src,number(16)));rows.push_back("store.i64 "+addPointer(d,number(8))+" "+live);});
    auto cursor=addPointer(records,emit("i64","mul "+k+" "+number(16)));
    for(auto *g:snapshotGlobals) {auto n=m.getDataLayout().getTypeAllocSize(g->getValueType()).getFixedValue();copyBytes(cursor,operand(g),number(n));cursor=addPointer(cursor,number(n));}
    auto id=std::to_string(dispatchBlock++),head="heapcopy"+id,step=head+"step",copy=head+"live",advance=head+"advance",done=head+"done";auto i=fresh("i64"),data=fresh("ptr");rows.push_back("br ^"+head+"("+number(0)+", "+cursor+")");rows.push_back("^"+head+"("+i+":i64, "+data+":ptr):");auto test=emit("i1","icmp.ult "+i+" "+k);rows.push_back("br "+test+" ^"+step+"() ^"+done+"()");rows.push_back("^"+step+"():");auto slot=addPointer(table,emit("i64","mul "+i+" "+number(24)));auto base=emit("i64","load.i64 "+slot);auto sz=emit("i64","load.i64 "+addPointer(slot,number(8)));auto live=emit("i64","load.i64 "+addPointer(slot,number(16)));auto yes=emit("i1","icmp.ne "+live+" "+number(0));rows.push_back("br "+yes+" ^"+copy+"() ^"+advance+"("+data+")");rows.push_back("^"+copy+"():");copyBytes(data,emit("ptr","inttoptr "+base),sz);auto nextData=addPointer(data,sz);rows.push_back("br ^"+advance+"("+nextData+")");auto dp=fresh("ptr");rows.push_back("^"+advance+"("+dp+":ptr):");auto next=emit("i64","add "+i+" "+number(1));rows.push_back("br ^"+head+"("+next+", "+dp+")");rows.push_back("^"+done+"():");
    return dst;
  }
  void snapshotRuntime() {
    if(!snapshotFunctions.empty())return;
    snapshotFunctions["xor128"]={"{\"abi\":\""+producerISA()+"\",\"args\":[\"i64\",\"i64\"],\"fault\":4,\"in\":[],\"kind\":\"oracle\",\"mem\":[],\"tgt\":128,\"tier\":\"q\"}",
      "oracle @xor128 () (t:wire[128]) (f:wire[4]) () (lo:i64, hi:i64)\nregs { a:reg[128], b:reg[128], s:reg[128], h:reg[128], v:reg[128] }\n^entry():\na = lift.zext.i128 lo\nb = lift.zext.i128 hi\ns = lift.const.i128 64\nh = lift.shl b s\nv = lift.or h a\nlift.retval v"};
    for(unsigned j=4;j<=snapshotExponent;++j) {
      auto name="B"+std::to_string(j);auto w=std::to_string(uint64_t(8)<<j);
      auto sig="{\"abi\":\""+producerISA()+"\",\"kind\":\"cc\",\"params\":[\"ptr\",\"token\"],\"results\":[\"qreg["+w+"]\"],\"tier\":\"cc\"}";
      auto body="fn cc @"+name+" (p:ptr, tk:token) (q:qreg["+w+"]) () () ()\n^entry():\n";
      if(j==4)body+="q = qreg.new any 128\nf = qreg.new any 4\nlo = load.i64 p\nn = const.i64 8\na = ptrtoint.i64 p\nb = add a n\np1 = inttoptr b\nhi = load.i64 p1\noracle_call @xor128 tk () q f () (lo, hi)\nqreg.free f\nret q";
      else {auto previous="B"+std::to_string(j-1);body+="l = call @"+previous+" p tk\nn = const.i64 "+std::to_string(uint64_t(1)<<(j-1))+"\na = ptrtoint.i64 p\nb = add a n\np1 = inttoptr b\nr = call @"+previous+" p1 tk\nq = qreg.concat l r\nret q";}
      snapshotFunctions[name]={sig,body};
    }
    snapshotToken="tk"+std::to_string(budgets.size());params.push_back(snapshotToken+":token");paramTypes.push_back("token");
    budgets.push_back(json::Object{{"token",snapshotToken},{"region","xor128"},{"steps","6"},{"heap","0"},{"stack","0"},{"depth","0"},{"sstack","0"}});
  }
  std::string prepareSnapshot(std::string bytes) {
    snapshotRuntime();return emit("qreg["+std::to_string(uint64_t(8)<<snapshotExponent)+"]","call @B"+std::to_string(snapshotExponent)+" "+bytes+" "+snapshotToken);
  }
  void releaseSnapshot(std::string q,std::string bytes) {
    for(uint64_t off=0;off<(uint64_t(1)<<snapshotExponent);off+=16) {
      auto p=addPointer(bytes,number(off));auto lo=emit("i64","load.i64 "+p),hi=emit("i64","load.i64 "+addPointer(p,number(8)));
      auto view=emit("qreg[128]","qreg.slice "+q+" "+std::to_string(off*8)+" 128"),fr=emit("qreg[4]","qreg.new any 4");rows.push_back("oracle_call @xor128 "+snapshotToken+" () "+view+" "+fr+" () ("+lo+", "+hi+")");rows.push_back("qreg.free "+fr);
    }
    rows.push_back("qreg.free "+q);
  }
