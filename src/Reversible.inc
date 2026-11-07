void prepareVarargsStack(Module &m,Function *&root,uint64_t capacity);
// §15.2 rows without an IR replacement trap only when reached.
static void normaliseRAsm(Function &f, json::Array &coverage) {
  SmallVector<CallInst *> sites;
  for(auto &i:instructions(f))if(auto *c=dyn_cast<CallInst>(&i);c && c->isInlineAsm())sites.push_back(c);
  for(auto *c:sites) {
    auto *assembly=cast<InlineAsm>(c->getCalledOperand());
    auto text=std::regex_replace(StringRef(assembly->getAsmString()).str(),std::regex("[;\\s]+")," ");text=StringRef(text).trim().str();
    bool erased=c->getType()->isVoidTy() && (text.empty() || text=="pause" || text=="nop");
    coverage.push_back(json::Object{{"function",f.getName()},{"asm",text},{"constraints",assembly->getConstraintString()},
      {"source","dialect-0.2.13:N31"},{"classification",erased?"lowered":"trapped"},{"reason",erased?"§15.2 barrier/no-op":"§15.2 unlisted asm row: F(8)"}});
    if(!erased) {
      IRBuilder<> b(c);auto fault=f.getParent()->getOrInsertFunction("__bennett_nz_fault",b.getVoidTy(),b.getInt64Ty());
      auto *trap=b.CreateCall(fault,{b.getInt64(8)});
      trap->setMetadata("bennett.asm",MDNode::get(f.getContext(),MDString::get(f.getContext(),"§15.2 asm "+text+" constraints "+StringRef(assembly->getConstraintString()).str())));
      if(!c->getType()->isVoidTy())c->replaceAllUsesWith(Constant::getNullValue(c->getType()));
    }
    c->eraseFromParent();
  }
}
// §19.2 whole-program mode uses the same scalar ABI and memory linker as CC.
// R bodies differ in effects, history, mandatory counters and exit propagation.
void lowerReversible(Module &source, Analysis &sourceAnalysis, Function &sourceEntry,
                     StringRef out, unsigned stack, StringRef budgetDefault,
                     StringRef budgetFile, StringRef disk) {
  sourceAnalysis.releaseTransferGraphs();
  auto device=CloneModule(source);auto &m=*device;
  auto entryName=sourceEntry.getName().str();auto *root=m.getFunction(entryName);
  for(auto &arg:root->args())if(arg.getArgNo()>0 && !arg.use_empty())
    unimplemented("§19.2 argv/envp byte storage in R launch",4,&arg);
  SmallVector<StringRef> components;budgetDefault.split(components,',');
  std::vector<uint64_t> defaults;
  for(auto c:components) {uint64_t n;if(c.getAsInteger(10,n))fail("input","§9.2 budget default");defaults.push_back(n);}
  if(defaults.size()!=5)fail("input","§9.2 budget default needs five components");
  BudgetTable table(defaults,budgetFile);auto limits=table.baseline(*root);
  // Each R instruction reads and consumes the shared source-step counter.
  auto *steps=new GlobalVariable(m,Type::getInt64Ty(m.getContext()),false,
      GlobalValue::InternalLinkage,ConstantInt::get(Type::getInt64Ty(m.getContext()),0),"__bennett_rt_rsteps");
  root->setName(entryName+".R");
  auto *launch=Function::Create(FunctionType::get(Type::getInt32Ty(m.getContext()),false),
      GlobalValue::ExternalLinkage,entryName,m);
  IRBuilder<> builder(BasicBlock::Create(m.getContext(),"launch",launch));builder.CreateRet(builder.getInt32(0));
  // The published runtime supplies logical frames; no native allocator is used.
  prepareVarargsStack(m,root,table.capacities[4]);
  materialiseStackRuntime(m,table.capacities[4]);
  auto *init=m.getFunction("__bennett_rt_ss_init");
  json::Array asmCoverage;
  std::vector<Function *> closure{root,init};std::set<Function *> seen;
  std::set<Value *> addresses;
  std::function<void(Value *)> address=[&](Value *v) {
    if(!addresses.insert(v).second)return;
    if(auto *f=resolve(v);f && !f->isDeclaration()) {if(!seen.count(f))closure.push_back(f);return;}
    if(auto *g=dyn_cast<GlobalVariable>(v)) {if(g->hasInitializer())address(g->getInitializer());return;}
    if(auto *constant=dyn_cast<Constant>(v))for(auto &operand:constant->operands())address(operand);
  };
  for(unsigned k=0;k<closure.size();++k) {
    auto *f=closure[k];if(!f || !seen.insert(f).second)continue;
    normaliseScalar(*f);materialiseFPBits(*f);normaliseRAsm(*f,asmCoverage);
    for(auto &i:instructions(*f))if(auto *call=dyn_cast<IntrinsicInst>(&i);call && call->getType()->isVectorTy())
      unimplemented("§12 N21/N27 vector intrinsic lane materialisation",2,call);
    for(auto &i:instructions(*f))for(auto &v:i.operands())address(v);
    for(auto &i:instructions(*f))if(auto *c=dyn_cast<CallBase>(&i)) {
      auto *g=resolve(c->getCalledOperand());
      if(g) {materialiseIntegerRuntime(*g);materialiseMemoryRuntime(*g);if(!g->isDeclaration() && !markers().count(g->getName().str()) && !seen.count(g))closure.push_back(g);}
    }
  }
  closure.assign(seen.begin(),seen.end());
  // Stable source order, independent of heap addresses and LLVM major.
  closure.clear();for(auto &f:m)if(seen.count(&f))closure.push_back(&f);
  Analysis a(m,root,true);a.run();a.checkHandles();a.checkRegions();
  std::error_code ec;if((ec=sys::fs::create_directories(out)))fail("output",ec.message());
  std::string dir=out.str()+"/"+entryName;if((ec=sys::fs::create_directories(dir)))fail("output",ec.message());
  Entry e{m,a,*launch,dir,stack,table};e.argvService=true;e.usesCCCalls=true;e.ccHeapBytes=table.capacities[1];
  if(!disk.empty()) {
    e.diskImage=read(disk);auto *image=ConstantDataArray::getString(m.getContext(),e.diskImage,false);
    auto *global=new GlobalVariable(m,image->getType(),true,GlobalValue::InternalLinkage,image,"__bennett_rt_disk_image");
    e.diskDataKey=scalarGlobalKey(*global);e.ccGlobals.insert(e.diskDataKey);
  }
  std::map<Function *,std::string> names;unsigned ordinal=0;
  for(auto *f:closure)names[f]="R"+std::to_string(ordinal++);
  e.ccNames=&names;
  auto *argv=new GlobalVariable(m,ArrayType::get(builder.getInt8Ty(),4+2*m.getDataLayout().getPointerSize()),false,
      GlobalValue::InternalLinkage,ConstantAggregateZero::get(ArrayType::get(builder.getInt8Ty(),4+2*m.getDataLayout().getPointerSize())),"__bennett_rt_argv");
  auto *eh=m.getGlobalVariable("__bennett_rt_eh",true);
  for(auto *f:closure) {
    Entry callee{m,a,*f,dir,stack,table};callee.ccNames=&names;callee.rTier=f!=init;
    callee.rSteps=steps;callee.rEH=eh;callee.lower();
    e.ccGlobals.insert(callee.ccGlobals.begin(),callee.ccGlobals.end());
    for(auto &point:callee.asmPoints)e.asmPoints.push_back(std::move(point));
    e.effectModels.insert(callee.effectModels.begin(),callee.effectModels.end());
    e.ccHeapBytes=std::max(e.ccHeapBytes,callee.ccHeapBytes);
    json::Array pt,rt;for(auto &t:callee.paramTypes)pt.push_back(t);for(auto &t:callee.resultTypes)rt.push_back(t);
    auto tier=callee.rTier?"r":"cc";
    auto sig=jcs(json::Value(json::Object{{"abi","0.8"},{"kind",tier},{"tier",tier},{"params",std::move(pt)},{"results",std::move(rt)}}));
    e.ccFunctions[names.at(f)]={sig,"fn "+std::string(tier)+" @"+names.at(f)+" ("+join(callee.params)+") ("+join(callee.results)+") () () ()\n"+join(callee.rows,"\n")};
  }
  e.rows={"^entry():"};
  // argv service reply: little-endian (argc:i32, argv:P, envp:P), packed.
  // The host populates the pointed-to argument storage in device memory.
  auto argp=e.operand(argv),length=e.number(4+2*m.getDataLayout().getPointerSize());
  e.emit("i64","hostcall bennett.argv "+argp+" "+length);
  e.rows.push_back("call @"+names.at(init)+" "+e.number(table.capacities[4]));
  auto stepP=e.operand(steps),limit=e.number(limits[0]);e.rows.push_back("store.i64 "+stepP+" "+limit);
  std::vector<std::string> args;
  if(root->arg_size()) {
    if(root->arg_size()!=2 && root->arg_size()!=3)fail("input","§19.2 entry needs main ABI",root);
    args.push_back(e.emit("i32","load.i32 "+argp));
    auto pw=std::to_string(m.getDataLayout().getPointerSizeInBits());
    for(unsigned k=1;k<root->arg_size();++k)args.push_back(e.emit("ptr","inttoptr "+e.emit("i"+pw,"load.i"+pw+" "+e.fieldPointer(argp,4+(k-1)*m.getDataLayout().getPointerSize()))));
  }
  if(!root->getReturnType()->isIntegerTy(32))fail("input","§19.2 entry status must be i32",root);
  auto status=e.emit("i32","call @"+names.at(root)+(args.empty()?"":" "+join(args," ")));
  if(eh) {
    auto p=e.operand(eh),active=e.emit("i32","load.i32 "+p),four=e.operand(builder.getInt32(4));
    auto exiting=e.emit("i1","icmp.eq "+active+" "+four);
    auto selector=e.emit("i32","load.i32 "+e.fieldPointer(p,4));status=e.emit("i32","select "+exiting+" "+selector+" "+status);
  }
  e.rows.push_back("ret "+status);e.resultTypes={"i32"};e.results={"status:i32"};
  json::Object record{{"dialect","0.2.13"},{"isa","0.8"},{"llvm_version",LLVM_VERSION_STRING},{"pipeline","bennett"},
    {"mode","reversible"},{"verdict","blocked:BD-B-ISA7"},{"source_step_limit",std::to_string(limits[0])},{"asm_rows",std::move(asmCoverage)}};
  record["entry_initialisation"] = json::Object{{"shadow_stack_bytes",std::to_string(table.capacities[4])}};
  json::Object cert{{"versions",json::Object{{"isa","0.8"},{"cert","0.8"}}},{"regions",json::Object{}},
    {"composition",json::Object{{"multiplicities",json::Object{}},{"epsilon_total",json::Object{{"diamond",0}}},{"method","sum_over_multiplicities"}}}};
  auto object=launchObject(e,record,cert);write(dir+"/launch.bennett",object);
  auto build=jcs(json::Value(std::move(record)));write(dir+"/build.json",build+"\n");
  cert["producer"]=json::Object{{"name","bennett-plugin"},{"version","0.2.13+build."+hash(build)},
    {"materialisation",json::Object{{"llvm_version",LLVM_VERSION_STRING},{"pipeline","bennett"},{"normaliser_version","0.2.8"}}}};
  write(dir+"/certificate.json",jcs(json::Value(std::move(cert)))+"\n");
  auto report=completeCoverage(object);auto sections=objectSections(object);auto symbols=parse(sections.at("symbols"));
  for(auto &point:e.asmPoints) {
    auto *p=point.getAsObject();StringRef identity;
    for(auto &symbol:*symbols.getAsObject())if(symbol.second.getAsObject()->getString("name")==p->getString("symbol"))identity=*symbol.second.getAsObject()->getString("interface_hash");
    for(auto &entry:*report.getArray("entries")) {
      auto *entryObject=entry.getAsObject();auto *at=entryObject->getArray("point");
      if((*at)[0].getAsString()==identity && (*at)[1].getAsString()==p->getString("block") && (*at)[2].getAsInteger()==p->getInteger("ordinal")) {
        (*entryObject)["source"]="dialect-0.2.13:N31";(*entryObject)["classification"]="trapped";(*entryObject)["reason"]=*p->getString("reason");
      }
    }
  }
  auto coverage=jcs(json::Value(std::move(report)))+"\n";write(dir+"/coverage.json",coverage);write(dir+"/all-coverage.json",coverage);
  write(dir+"/blockers.json",jcs(json::Value(json::Array{json::Object{{"code","BD-B-ISA7"},{"entry",entryName},
    {"section","11.5/17.6/25.1"},{"reason","R entry: mandatory pre-instruction typed fault 1 requires ISA-7; generic trap only on exhausted counter; no later source effect; prefix history retained"}}}))+"\n");
  // Device bitcode retains materialised bodies; host main gets the launch ABI.
  launch->eraseFromParent();root->setName(entryName);
  checkComparisonMaterialisation(m);
  raw_fd_ostream bc(out.str()+"/device.bc",ec);if(ec)fail("output",ec.message());WriteBitcodeToFile(m,bc);bc.close();
  auto buildRecord=parse(build);hostStub(sourceEntry,object,*buildRecord.getAsObject(),sharesGlobalState(sourceEntry, sourceAnalysis));
  raw_fd_ostream host(out.str()+"/host.bc",ec);if(ec)fail("output",ec.message());WriteBitcodeToFile(source,host);host.close();
  write(out.str()+"/launches.json",jcs(json::Value(json::Array{json::Object{{"entry",entryName},{"object",entryName+"/launch.bennett"},{"build_sha256",hash(build)},{"verdict","blocked:BD-B-ISA7"}}}))+"\n");
  json::Object artifacts;
  for(auto file:{"host.bc","device.bc","launches.json"}) {auto bytes=read(out.str()+"/"+file);artifacts[file]=json::Object{{"bytes",int64_t(bytes.size())},{"sha256",hash(bytes)}};}
  for(auto file:{"launch.bennett","build.json","certificate.json","coverage.json","all-coverage.json","blockers.json"}) {auto path=entryName+"/"+file;auto bytes=read(out.str()+"/"+path);artifacts[path]=json::Object{{"bytes",int64_t(bytes.size())},{"sha256",hash(bytes)}};}
  write(dir+"/launch-record.json",jcs(json::Value(json::Object{{"schema","bennett-plugin-launch-record-1"},{"entry",entryName},{"artifacts",std::move(artifacts)}}))+"\n");
}
