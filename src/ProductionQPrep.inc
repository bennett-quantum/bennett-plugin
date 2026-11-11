  std::map<unsigned,std::pair<std::string,std::string>> preparationTokens;
  std::pair<std::string,std::string> preparationOracle(unsigned width) {
    if(preparationTokens.count(width))return preparationTokens.at(width);
    unsigned id=width;while(snapshotFunctions.count("P"+std::to_string(id)) || m.getFunction("P"+std::to_string(id)))++id;
    auto name="P"+std::to_string(id),w=std::to_string(width);
    auto convert=[&](unsigned from,StringRef value) {
      return width==from?"lift.mov "+value.str():"lift."+std::string(width<from?"trunc":"zext")+".i"+w+" "+value.str();
    };
    auto sig="{\"abi\":\""+producerISA()+"\",\"args\":[\"i8\",\"i64\"],\"fault\":4,\"in\":[],\"kind\":\"oracle\",\"mem\":[],\"tgt\":"+w+",\"tier\":\"q\"}";
    snapshotFunctions[name]={sig,"oracle @"+name+" () (t:wire["+w+"]) (f:wire[4]) () (byte:i8, off:i64)\nregs { b:reg["+w+"], s:reg["+w+"], v:reg["+w+"] }\n^entry():\nb = "+convert(8,"byte")+"\ns = "+convert(64,"off")+"\nv = lift.shl b s\nlift.retval v"};
    auto token="tk"+std::to_string(budgets.size());params.push_back(token+":token");paramTypes.push_back("token");
    budgets.push_back(json::Object{{"token",token},{"region",name},{"steps","4"},{"heap","0"},{"stack","0"},{"depth","0"},{"sstack","0"}});
    return preparationTokens[width]={name,token};
  }
  void prepareQuantumBytes(CallBase &call) {
    generalUsed=true;usesSourceMemory=true;
    withHandle(call.getArgOperand(0),[&](std::string target) {
      auto width=qwidth(a.get(call.getArgOperand(0)),&call);
      auto count=operand(call.getArgOperand(2)),source=operand(call.getArgOperand(1));
      auto valid=emit("i1","icmp.ule "+count+" "+number(width/8));
      auto id=std::to_string(dispatchBlock++),ready="prep"+id,bad=ready+"bad";
      rows.push_back("br "+valid+" ^"+ready+"() ^"+bad+"()");rows.push_back("^"+bad+"():");rows.push_back("trap");rows.push_back("^"+ready+"():");
      // Validate the complete range before changing any wire. Widening keeps
      // the prospective end address from wrapping into another allocation.
      auto base=emit("i64","ptrtoint.i64 "+source),wide=emit("i128","zext.i128 "+base),length=emit("i128","zext.i128 "+count);
      auto end=emit("i128","add "+wide+" "+length);
      auto limit=operand(ConstantInt::get(IntegerType::get(m.getContext(),128),APInt::getOneBitSet(128,m.getDataLayout().getPointerSizeInBits())));
      auto nowrap=emit("i1","icmp.ule "+end+" "+limit);
      auto range="preprange"+id,memoryFault=range+"bad";
      rows.push_back("br "+nowrap+" ^"+range+"() ^"+memoryFault+"()");rows.push_back("^"+memoryFault+"():");
      // ISA §7.2 reserves a nonempty null region on both versions. Its
      // invalid load raises code 7 directly, including on ISA 0.8 CC.
      emit("i8","load.i8 "+emit("ptr","inttoptr "+number(0)));
      rows.push_back("trap");rows.push_back("^"+range+"():");
      byteLoop(count,[&](std::string i) {emit("i8","load.i8 "+addPointer(source,i));});
      auto helper=preparationOracle(width);
      byteLoop(count,[&](std::string i) {
        auto byte=emit("i8","load.i8 "+addPointer(source,i));
        auto offset=emit("i64","mul "+i+" "+number(8));
        auto fault=emit("qreg[4]","qreg.new any 4");
        rows.push_back("oracle_call @"+helper.first+" "+helper.second+" () "+target+" "+fault+" () ("+byte+", "+offset+")");
        rows.push_back("qreg.free "+fault);
      });
    });
  }
