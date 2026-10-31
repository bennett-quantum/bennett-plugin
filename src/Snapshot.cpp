#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
using namespace llvm;
namespace bennett {
std::vector<GlobalVariable *> entryGlobals(Module &m) {
  std::vector<GlobalVariable *> globals;
  for(auto &g:m.globals()) if(!g.isConstant() && !g.getMetadata("bennett.snapshot.scratch")) globals.push_back(&g);
  std::map<GlobalVariable *,std::string> order;unsigned ordinal=0;
  for(auto &g:m.globals())if(!g.getMetadata("bennett.snapshot.scratch"))order[&g]="G"+std::to_string(++ordinal);
  std::sort(globals.begin(),globals.end(),[&](auto *a,auto *b){return order.at(a)<order.at(b);});
  return globals;
}
// The stream is k, (size,live)*k, G, Hb. Recompute bases from the complete
// history instead of serialising host pointers or allocating a temporary table.
void prepareEntryReplay(Module &m,unsigned exponent) {
  auto &ctx=m.getContext();IRBuilder<> b(ctx);auto *i64=b.getInt64Ty(),*i8=b.getInt8Ty();auto *ptr=b.getPtrTy();
  m.addModuleFlag(Module::Error,"bennett.entry.snapshot",uint32_t(exponent));
  auto *f=Function::Create(FunctionType::get(b.getVoidTy(),{ptr},false),GlobalValue::InternalLinkage,"__bennett_rt_entry_replay",m);
  f->addFnAttr("bennett.stack.internal");
  auto *s=f->getArg(0);auto *entry=BasicBlock::Create(ctx,"entry",f);b.SetInsertPoint(entry);
  auto load=[&](Type *t,Value *p) {auto *v=b.CreateLoad(t,p);v->setAlignment(Align(1));return v;};
  auto gep=[&](Value *p,Value *n) {return b.CreateGEP(i8,p,n);};
  auto *k=load(i64,s);auto *records=gep(s,b.getInt64(8));
  auto alloc=m.getOrInsertFunction("__bennett_nz_alloc",ptr,i64);
  auto free=m.getOrInsertFunction("__bennett_nz_free",b.getVoidTy(),ptr);
  auto loop=[&](Value *n,const std::function<void(Value *)> &body) {
    auto *pre=b.GetInsertBlock(),*head=BasicBlock::Create(ctx,"loop",f),*step=BasicBlock::Create(ctx,"step",f),*done=BasicBlock::Create(ctx,"done",f);
    b.CreateBr(head);b.SetInsertPoint(head);auto *i=b.CreatePHI(i64,2);i->addIncoming(b.getInt64(0),pre);
    b.CreateCondBr(b.CreateICmpULT(i,n),step,done);b.SetInsertPoint(step);body(i);
    auto *next=b.CreateAdd(i,b.getInt64(1));auto *tail=b.GetInsertBlock();b.CreateBr(head);i->addIncoming(next,tail);b.SetInsertPoint(done);
  };
  auto copyBytes=[&](Value *dst,Value *src,Value *n) {
    auto *chunks=b.CreateUDiv(n,b.getInt64(16));auto *tail=b.CreateMul(chunks,b.getInt64(16));
    loop(chunks,[&](Value *j) {auto *off=b.CreateMul(j,b.getInt64(16));auto *st=b.CreateStore(load(b.getInt128Ty(),gep(src,off)),gep(dst,off));st->setAlignment(Align(1));});
    loop(b.CreateSub(n,tail),[&](Value *j) {auto *off=b.CreateAdd(tail,j);auto *st=b.CreateStore(load(i8,gep(src,off)),gep(dst,off));st->setAlignment(Align(1));});
  };
  uint64_t globalBytes=0;
  auto globals=entryGlobals(m);
  for(auto *g:globals)globalBytes+=m.getDataLayout().getTypeAllocSize(g->getValueType()).getFixedValue();
  auto *globalData=gep(records,b.CreateMul(k,b.getInt64(16)));
  auto *heapData=gep(globalData,b.getInt64(globalBytes));
  auto *pre=b.GetInsertBlock(),*head=BasicBlock::Create(ctx,"history",f),*step=BasicBlock::Create(ctx,"allocation",f),*done=BasicBlock::Create(ctx,"globals",f);
  b.CreateBr(head);b.SetInsertPoint(head);auto *index=b.CreatePHI(i64,2);auto *data=b.CreatePHI(ptr,2);
  index->addIncoming(b.getInt64(0),pre);data->addIncoming(heapData,pre);
  b.CreateCondBr(b.CreateICmpULT(index,k),step,done);b.SetInsertPoint(step);
  auto *r=gep(records,b.CreateMul(index,b.getInt64(16)));auto *size=load(i64,r);auto *live=load(i64,gep(r,b.getInt64(8)));auto *p=b.CreateCall(alloc,{size});
  auto *dead=BasicBlock::Create(ctx,"dead",f),*copy=BasicBlock::Create(ctx,"copy",f),*advance=BasicBlock::Create(ctx,"advance",f);
  b.CreateCondBr(b.CreateICmpEQ(live,b.getInt64(0)),dead,copy);
  b.SetInsertPoint(dead);b.CreateCall(free,{p});b.CreateBr(advance);
  b.SetInsertPoint(copy);
  copyBytes(p,data,size);
  auto *afterCopy=gep(data,size);auto *copyEnd=b.GetInsertBlock();b.CreateBr(advance);
  b.SetInsertPoint(advance);auto *nextData=b.CreatePHI(ptr,2);nextData->addIncoming(data,dead);nextData->addIncoming(afterCopy,copyEnd);
  auto *next=b.CreateAdd(index,b.getInt64(1));b.CreateBr(head);index->addIncoming(next,advance);data->addIncoming(nextData,advance);
  b.SetInsertPoint(done);Value *cursor=globalData;
  for(auto *g:globals) {
    auto n=m.getDataLayout().getTypeAllocSize(g->getValueType()).getFixedValue();
    copyBytes(g,cursor,b.getInt64(n));
    cursor=gep(cursor,b.getInt64(n));
  }
  b.CreateRetVoid();
}
} // namespace bennett
