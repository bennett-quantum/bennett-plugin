static bool requiresArgumentStorage(Function &entry) {
  for(auto &arg:entry.args())if(arg.getArgNo()>0 && !arg.use_empty())return true;
  return false;
}

// The reply contains offsets, never host pointers. The CC launch owns storage.
static void requireArgumentReply(Entry &e, const std::string &condition) {
  auto id=std::to_string(e.dispatchBlock++);
  e.rows.push_back("br "+condition+" ^argv_ok"+id+"() ^argv_bad"+id+"()");
  e.rows.push_back("^argv_bad"+id+"():");e.rows.push_back("trap");
  e.rows.push_back("^argv_ok"+id+"():");
}

static std::string argumentPointer(Entry &e, const std::string &base,
                                   const std::string &offset) {
  return e.emit("ptr","inttoptr "+e.emit("i64","add "+base+" "+offset));
}

static std::string receiveArgumentPayload(Entry &e, const std::string &pointer,
                                          const std::string &length) {
  auto width=std::to_string(e.m.getDataLayout().getPointerSizeInBits());
  auto result=e.emit("i"+width,"hostcall bennett.argv.bytes "+pointer+" "+length);
  return width=="64"?result:e.emit("i64","zext.i64 "+result);
}

static std::vector<std::string> importArgumentBytes(Entry &e, const std::string &header,
                                                   std::string &storage) {
  auto zero=e.number(0),one=e.number(1),headerBytes=e.number(24);
  auto length=receiveArgumentPayload(e,header,headerBytes);
  requireArgumentReply(e,e.emit("i1","icmp.ule "+headerBytes+" "+length));
  storage=e.emit("ptr","alloc "+length);
  auto received=receiveArgumentPayload(e,storage,length);
  requireArgumentReply(e,e.emit("i1","icmp.eq "+received+" "+length));
  auto argc=e.emit("i32","load.i32 "+storage);
  auto envc=e.emit("i64","load.i64 "+e.fieldPointer(storage,8));
  auto declared=e.emit("i64","load.i64 "+e.fieldPointer(storage,16));
  requireArgumentReply(e,e.emit("i1","icmp.eq "+declared+" "+length));
  auto count=e.emit("i64","zext.i64 "+argc),environment=envc;
  auto slots=e.emit("i64","add "+e.emit("i64","add "+count+" "+environment)+" "+e.number(2));
  auto pointerBytes=e.number(e.m.getDataLayout().getPointerSize());
  auto stringStart=e.emit("i64","add "+headerBytes+" "+e.emit("i64","mul "+slots+" "+pointerBytes));
  requireArgumentReply(e,e.emit("i1","icmp.ule "+stringStart+" "+length));
  auto base=e.emit("i64","ptrtoint.i64 "+storage);
  auto argv=argumentPointer(e,base,headerBytes);
  auto envOffset=e.emit("i64","add "+headerBytes+" "+e.emit("i64","mul "+e.emit("i64","add "+count+" "+one)+" "+pointerBytes));
  auto envp=argumentPointer(e,base,envOffset);
  auto last=e.emit("i64","sub "+slots+" "+one);
  auto index=e.fresh("i64"),id=std::to_string(e.dispatchBlock++);
  e.rows.push_back("br ^argv_reloc"+id+"("+zero+")");
  e.rows.push_back("^argv_reloc"+id+"("+index+":i64):");
  auto tableOffset=e.emit("i64","add "+headerBytes+" "+e.emit("i64","mul "+index+" "+pointerBytes));
  auto slot=argumentPointer(e,base,tableOffset);
  auto width=std::to_string(e.m.getDataLayout().getPointerSizeInBits());
  auto offset=e.emit("i"+width,"load.i"+width+" "+slot);
  auto wide=width=="64"?offset:e.emit("i64","zext.i64 "+offset);
  auto isNull=e.emit("i1","icmp.eq "+wide+" "+zero);
  auto sentinel=e.emit("i1","or "+e.emit("i1","icmp.eq "+index+" "+count)+" "+e.emit("i1","icmp.eq "+index+" "+last));
  auto valid=e.emit("i1","and "+e.emit("i1","icmp.ule "+stringStart+" "+wide)+" "+e.emit("i1","icmp.ult "+wide+" "+length));
  requireArgumentReply(e,e.emit("i1","select "+sentinel+" "+isNull+" "+valid));
  auto address=e.emit("i64","add "+base+" "+wide);
  auto relocated=e.emit("i64","select "+isNull+" "+zero+" "+address);
  if(width!="64")relocated=e.emit("i"+width,"trunc.i"+width+" "+relocated);
  e.rows.push_back("store.i"+width+" "+slot+" "+relocated);
  auto next=e.emit("i64","add "+index+" "+one),more=e.emit("i1","icmp.ult "+next+" "+slots);
  e.rows.push_back("br "+more+" ^argv_reloc"+id+"("+next+") ^argv_ready"+id+"()");
  e.rows.push_back("^argv_ready"+id+"():");
  return {argc,argv,envp};
}

static std::string beginLaunchArguments(Entry &e, GlobalVariable &header,
                                        std::vector<std::string> &args,
                                        std::string &storage) {
  auto pointer=e.operand(&header);
  if(e.argvByteStorage)args=importArgumentBytes(e,pointer,storage);
  else e.emit("i64","hostcall bennett.argv "+pointer+" "+e.number(4+2*e.m.getDataLayout().getPointerSize()));
  return pointer;
}

static void finishLaunchArguments(Entry &e, Function &root,
                                  const std::string &pointer,
                                  std::vector<std::string> &args) {
  if(root.arg_size() && root.arg_size()!=2 && root.arg_size()!=3)
    fail("input","§19.2 entry needs main ABI",&root);
  if(e.argvByteStorage) {args.resize(root.arg_size());return;}
  if(root.arg_size()) {
    args.push_back(e.emit("i32","load.i32 "+pointer));
    auto pw=std::to_string(e.m.getDataLayout().getPointerSizeInBits());
    for(unsigned k=1;k<root.arg_size();++k)
      args.push_back(e.emit("ptr","inttoptr "+e.emit("i"+pw,"load.i"+pw+" "+e.fieldPointer(pointer,4+(k-1)*e.m.getDataLayout().getPointerSize()))));
  }
}

static void releaseLaunchArguments(Entry &e, const std::string &storage) {
  if(!storage.empty())e.rows.push_back("free "+storage);
}
