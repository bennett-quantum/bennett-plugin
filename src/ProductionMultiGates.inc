  bool multiWireHandleUse(Instruction &value) {
    for(auto *user:value.users())if(auto *call=dyn_cast<CallBase>(user))
      if(auto *callee=call->getCalledFunction())
        if(callee->getName()=="__bennett_gate2" || callee->getName()=="__bennett_gate3")return true;
    return false;
  }
  // Resolve source handles before assigning action slots: distinct wire roles
  // can refer to the same register, but a register occurs only once in mut.
  bool multiGateLeaf(const std::vector<std::string> &handles,
                     const std::vector<unsigned> &widths,
                     const std::vector<uint64_t> &indices, uint64_t opcode) {
    std::vector<std::string> registers, declarations, sizes, wires;
    for(unsigned i=0;i<handles.size();++i) {
      auto found=std::find(registers.begin(),registers.end(),handles[i]);
      auto slot=std::distance(registers.begin(),found);
      if(found==registers.end()) {
        registers.push_back(handles[i]);
        sizes.push_back(std::to_string(widths[i]));
        declarations.push_back("s"+std::to_string(slot)+":wire["+sizes.back()+"] mut");
      }
      for(unsigned j=0;j<i;++j)if(handles[i]==handles[j] && indices[i]==indices[j]) {
        rows.push_back("trap");return false;
      }
      wires.push_back("s"+std::to_string(slot)+"["+std::to_string(indices[i])+"]");
    }
    auto op=handles.size()==3?"ccx":opcode==1?"cx":opcode==2?"cz":"swap";
    auto name=action(join(declarations),"",join(sizes,","),"",op+std::string(" ")+join(wires," "));
    rows.push_back("action_call @"+name+" ("+join(registers)+") () () ()");
    return true;
  }
  void multiGateOn(CallBase &call, const std::vector<std::string> &handles,
                   const std::vector<unsigned> &widths) {
    auto id=std::to_string(dispatchBlock++),done="multi"+id+"done",bad="multi"+id+"bad";
    std::vector<uint64_t> indices(handles.size());
    auto choose=[&](Value *value,std::vector<uint64_t> keys,const std::function<void(uint64_t)> &body) {
      auto domain=a.get(value);
      if(!domain.top) {
        std::vector<uint64_t> finite;
        for(auto key:keys)if(domain.atoms.count(*intValue(key,widthOf(value)).atoms.begin()))finite.push_back(key);
        keys=std::move(finite);
      }
      if(keys.empty())rows.push_back("br ^"+bad+"()");
      else if(singletonInt(domain))body(keys[0]);
      else compareTree(operand(value),widthOf(value),keys,body,bad);
    };
    std::function<void(unsigned)> selectIndex=[&](unsigned i) {
      if(i==handles.size()) {
        choose(call.getArgOperand(0),handles.size()==3?std::vector<uint64_t>{1}:std::vector<uint64_t>{1,2,3},[&](uint64_t op) {
          if(multiGateLeaf(handles,widths,indices,op))rows.push_back("br ^"+done+"()");
        });return;
      }
      std::vector<uint64_t> keys;
      for(uint64_t k=0;k<widths[i];++k)keys.push_back(k);
      choose(call.getArgOperand(2+2*i),keys,[&](uint64_t k) {indices[i]=k;selectIndex(i+1);});
    };
    selectIndex(0);
    rows.push_back("^"+bad+"():");rows.push_back("trap");rows.push_back("^"+done+"():");
  }
  void multiGate(CallBase &call) {
    unsigned arity=call.getCalledFunction()->getName()=="__bennett_gate3"?3:2;
    std::vector<std::string> handles(arity);
    std::vector<unsigned> widths(arity);
    std::function<void(unsigned)> resolve=[&](unsigned i) {
      if(i==arity) {multiGateOn(call,handles,widths);return;}
      auto *value=call.getArgOperand(1+2*i);
      withHandle(value,[&](std::string q) {
        handles[i]=q;widths[i]=qwidth(a.get(value),&call);resolve(i+1);
      });
    };
    resolve(0);
  }
  bool lowerQuantumMarker(CallBase &call, StringRef n) {
    auto *c=&call;
    if (n == "__bennett_qalloc" || n == "__bennett_qborrow") {
      auto w = integer(a.get(c->getArgOperand(1)), c);
      auto q = files.count(c) ? files.at(c).q : fresh("qreg[" + std::to_string(w) + "]");
      if (files.count(c)) {
        // No site is executed twice in this acyclic entry-local file.
        // Distinct nonzero identities are stable across stores and loads;
        // free retires the live tag before any later use can match it.
        auto tag = fresh("i" + std::to_string(m.getDataLayout().getPointerSizeInBits()));
        rows.push_back(tag + " = const.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + std::to_string(files.at(c).identity));
        names[c] = tag;
        rows.push_back("store.i" + std::to_string(m.getDataLayout().getPointerSizeInBits()) + " " + files.at(c).tag + " " + tag);
      } else names[c] = q;
      allocateRegister(*c, q, w);
    } else if (n == "__bennett_qfree")
      withHandle(c->getArgOperand(0), [&](std::string q) { rows.push_back("qreg.free " + q); }, true);
    else if (n == "__bennett_oracle")
      descriptor(*c);
    else if (n == "__bennett_inplace")
      inplace(*c);
    else if(n=="__bennett_ctrl" && controlledIdentity(*c)) {}
    else if (n == "__bennett_gate2" || n == "__bennett_gate3")
      multiGate(*c);
    else if (n == "__bennett_gate" || n == "__bennett_measure")
      gate(*c);
    else return false;
    return true;
  }
