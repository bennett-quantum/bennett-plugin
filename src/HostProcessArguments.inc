static void declareArgumentService(json::Object &services, bool bytes) {
  auto name=bytes?"bennett.argv.bytes":"bennett.argv";
  services[name]=json::Object{{"version",bytes?"1":"0.2.10"}};
}

// Host-side serialization for the versioned CC argv-byte import service.
static void checkHostArguments(IRBuilder<> &b, Value *condition) {
  auto *function=b.GetInsertBlock()->getParent();auto &context=function->getContext();
  auto *good=BasicBlock::Create(context,"argv.valid",function);
  auto *bad=BasicBlock::Create(context,"argv.invalid",function);
  b.CreateCondBr(condition,good,bad);b.SetInsertPoint(bad);
  b.CreateCall(function->getParent()->getOrInsertFunction("llvm.trap",b.getVoidTy()));
  b.CreateUnreachable();b.SetInsertPoint(good);
}

static std::pair<Value *,Value *> hostArgumentVectorSize(IRBuilder<> &b, Value *vector) {
  auto *function=b.GetInsertBlock()->getParent();auto &module=*function->getParent();
  auto &context=module.getContext();auto *size=module.getDataLayout().getIntPtrType(context);
  auto *ptr=PointerType::get(context,0);auto *count=b.CreateAlloca(size),*bytes=b.CreateAlloca(size);
  b.CreateStore(ConstantInt::get(size,0),count);b.CreateStore(ConstantInt::get(size,0),bytes);
  auto *head=BasicBlock::Create(context,"argv.measure",function);
  auto *body=BasicBlock::Create(context,"argv.measure.string",function);
  auto *done=BasicBlock::Create(context,"argv.measured",function);
  b.CreateCondBr(b.CreateIsNull(vector),done,head);b.SetInsertPoint(head);
  auto *index=b.CreateLoad(size,count);
  auto *string=b.CreateLoad(ptr,b.CreateGEP(ptr,vector,index));
  b.CreateCondBr(b.CreateIsNull(string),done,body);b.SetInsertPoint(body);
  auto length=module.getOrInsertFunction("strlen",size,ptr);
  auto *n=b.CreateAdd(b.CreateCall(length,{string}),ConstantInt::get(size,1));
  b.CreateStore(b.CreateAdd(b.CreateLoad(size,bytes),n),bytes);
  b.CreateStore(b.CreateAdd(index,ConstantInt::get(size,1)),count);b.CreateBr(head);
  b.SetInsertPoint(done);return {b.CreateLoad(size,count),b.CreateLoad(size,bytes)};
}

static void storeArgumentField(IRBuilder<> &b, Value *value, Value *destination) {
  auto &module=*b.GetInsertBlock()->getModule();
  if(!module.getDataLayout().isLittleEndian()) {
    auto *integer=cast<IntegerType>(value->getType());
    auto swap=module.getOrInsertFunction("llvm.bswap.i"+std::to_string(integer->getBitWidth()),integer,integer);
    value=b.CreateCall(swap,{value});
  }
  b.CreateAlignedStore(value,destination,Align(1));
}

static void packHostArgumentVector(IRBuilder<> &b, Value *vector, Value *count,
                                    Value *table, Value *buffer, Value *cursor) {
  auto *function=b.GetInsertBlock()->getParent();auto &context=function->getContext();
  auto &module=*function->getParent();auto *size=module.getDataLayout().getIntPtrType(context);
  auto *ptr=PointerType::get(context,0);auto *indexSlot=b.CreateAlloca(size);
  b.CreateStore(ConstantInt::get(size,0),indexSlot);
  auto *head=BasicBlock::Create(context,"argv.pack",function);
  auto *body=BasicBlock::Create(context,"argv.pack.string",function);
  auto *done=BasicBlock::Create(context,"argv.packed",function);
  b.CreateBr(head);b.SetInsertPoint(head);auto *index=b.CreateLoad(size,indexSlot);
  b.CreateCondBr(b.CreateICmpULT(index,count),body,done);b.SetInsertPoint(body);
  auto *string=b.CreateLoad(ptr,b.CreateGEP(ptr,vector,index));
  auto *offset=b.CreateLoad(size,cursor);
  storeArgumentField(b,offset,b.CreateGEP(size,table,index));
  auto *length=b.CreateAdd(b.CreateCall(module.getOrInsertFunction("strlen",size,ptr),{string}),ConstantInt::get(size,1));
  b.CreateMemCpy(b.CreateGEP(b.getInt8Ty(),buffer,offset),Align(1),string,Align(1),length);
  b.CreateStore(b.CreateAdd(offset,length),cursor);
  b.CreateStore(b.CreateAdd(index,ConstantInt::get(size,1)),indexSlot);b.CreateBr(head);
  b.SetInsertPoint(done);storeArgumentField(b,ConstantInt::get(size,0),b.CreateGEP(size,table,count));
}

static std::pair<Value *,Value *> packHostArguments(IRBuilder<> &b, Function &entry) {
  auto &module=*entry.getParent();auto *size=module.getDataLayout().getIntPtrType(entry.getContext());
  auto *ptr=PointerType::get(entry.getContext(),0);
  auto *argc=entry.getArg(0),*argv=entry.getArg(1);
  Value *envp;
  if(entry.arg_size()==3)envp=entry.getArg(2);
  else envp=b.CreateLoad(ptr,module.getOrInsertGlobal("environ",ptr));
  auto [argCount,argBytes]=hostArgumentVectorSize(b,argv);
  auto [envCount,envBytes]=hostArgumentVectorSize(b,envp);
  checkHostArguments(b,b.CreateICmpEQ(argCount,b.CreateZExtOrTrunc(argc,size)));
  auto *pointerBytes=ConstantInt::get(size,module.getDataLayout().getPointerSize());
  auto *headerBytes=ConstantInt::get(size,24);
  auto *envOffset=b.CreateAdd(headerBytes,b.CreateMul(b.CreateAdd(argCount,ConstantInt::get(size,1)),pointerBytes));
  auto *stringsOffset=b.CreateAdd(envOffset,b.CreateMul(b.CreateAdd(envCount,ConstantInt::get(size,1)),pointerBytes));
  auto *length=b.CreateAdd(stringsOffset,b.CreateAdd(argBytes,envBytes));
  auto *buffer=b.CreateCall(module.getOrInsertFunction("malloc",ptr,size),{length});
  checkHostArguments(b,b.CreateIsNotNull(buffer));
  storeArgumentField(b,argc,buffer);
  storeArgumentField(b,b.getInt32(0),b.CreateGEP(b.getInt8Ty(),buffer,b.getInt64(4)));
  storeArgumentField(b,b.CreateZExtOrTrunc(envCount,b.getInt64Ty()),b.CreateGEP(b.getInt8Ty(),buffer,b.getInt64(8)));
  storeArgumentField(b,b.CreateZExtOrTrunc(length,b.getInt64Ty()),b.CreateGEP(b.getInt8Ty(),buffer,b.getInt64(16)));
  auto *cursor=b.CreateAlloca(size);b.CreateStore(stringsOffset,cursor);
  packHostArgumentVector(b,argv,argCount,b.CreateGEP(b.getInt8Ty(),buffer,headerBytes),buffer,cursor);
  packHostArgumentVector(b,envp,envCount,b.CreateGEP(b.getInt8Ty(),buffer,envOffset),buffer,cursor);
  return {buffer,length};
}

static void replyHostArguments(IRBuilder<> &b, Function &entry, const json::Object &record,
                                Value *program, Value *run, Value *request, Value *result) {
  auto &module=*entry.getParent();auto *ptr=PointerType::get(entry.getContext(),0);
  auto *size=module.getDataLayout().getIntPtrType(entry.getContext());auto *i32=b.getInt32Ty();
  auto api=[&](StringRef name, Type *ret, ArrayRef<Type *> types) {
    return module.getOrInsertFunction(name,FunctionType::get(ret,types,false));
  };
  auto status=[&](Value *value) {checkHostArguments(b,b.CreateICmpEQ(value,b.getInt32(0)));};
  auto *initialisation=record.getObject("entry_initialisation");
  bool bytes=initialisation && initialisation->getString("arguments")=="bennett-argv-bytes-1";
  auto *serviceName=b.CreateGlobalString(bytes?"bennett.argv.bytes":"bennett.argv");
  auto obtain=[&]() {
    auto *req=b.CreateLoad(ptr,request);checkHostArguments(b,b.CreateIsNotNull(req));
    auto *service=b.CreateCall(api("bennett_request_service",ptr,{ptr}),{req});
    status(b.CreateCall(api("strcmp",i32,{ptr,ptr}),{service,serviceName}));return req;
  };
  auto answer=[&](Value *req, Value *reply, Value *length) {
    status(b.CreateCall(api("bennett_reply",i32,{ptr,b.getInt64Ty(),ptr,size}),{program,run,reply,length}));
    b.CreateCall(api("bennett_request_free",b.getVoidTy(),{ptr}),{req});
    status(b.CreateCall(api("bennett_wait",i32,{ptr,b.getInt64Ty(),ptr,ptr}),{program,run,result,request}));
  };
  auto *req=obtain();
  if(bytes) {
    auto [reply,length]=packHostArguments(b,entry);answer(req,reply,length);
    req=obtain();answer(req,reply,length);
    b.CreateCall(api("free",b.getVoidTy(),{ptr}),{reply});
  } else {
    auto *type=ArrayType::get(b.getInt8Ty(),4+2*module.getDataLayout().getPointerSize());
    auto *reply=b.CreateAlloca(type);b.CreateStore(ConstantAggregateZero::get(type),reply);
    Value *argc=entry.arg_empty()?(Value *)b.getInt32(0):entry.getArg(0);
    storeArgumentField(b,argc,reply);answer(req,reply,ConstantInt::get(size,type->getNumElements()));
  }
}
