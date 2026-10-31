#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
using namespace llvm;
namespace bennett {
// N26 helpers have ordinary memory operations. The normal L memory machinery
// validates logical addresses, frame lifetimes and model bounds; no host memcpy
// or physical-address shortcut is available in production. Zero length touches
// no pointer. Linked definitions (and their data) retain precedence.
void materialiseMemoryRuntime(Function &f) {
  auto name=f.getName();bool fill=name=="__bennett_rt_memset",copy=name=="__bennett_rt_memmove"||name=="__bennett_rt_memcpy";
  if(!f.isDeclaration() || (!fill && !copy))return;
  auto &ctx=f.getContext();IRBuilder<> b(ctx);auto *expected=FunctionType::get(b.getVoidTy(),{b.getPtrTy(),fill?(Type *)b.getInt8Ty():(Type *)b.getPtrTy(),b.getInt64Ty()},false);
  if(f.getFunctionType()!=expected)fail("input","§12 N26 memory helper signature",&f);
  auto *entry=BasicBlock::Create(ctx,"entry",&f),*direction=BasicBlock::Create(ctx,"direction",&f),*forward=BasicBlock::Create(ctx,"forward",&f),*reverse=copy?BasicBlock::Create(ctx,"reverse",&f):nullptr,*done=BasicBlock::Create(ctx,"done",&f);
  auto *dst=f.getArg(0),*src=f.getArg(1),*length=f.getArg(2);b.SetInsertPoint(entry);b.CreateCondBr(b.CreateICmpEQ(length,b.getInt64(0)),done,direction);b.SetInsertPoint(direction);
  if(copy)b.CreateCondBr(b.CreateICmpUGT(dst,src),reverse,forward);else b.CreateBr(forward);
  b.SetInsertPoint(forward);auto *i=b.CreatePHI(b.getInt64Ty(),2);i->addIncoming(b.getInt64(0),direction);
  Value *value=src;if(copy) {auto *l=b.CreateLoad(b.getInt8Ty(),b.CreateGEP(b.getInt8Ty(),src,i));l->setAlignment(Align(1));value=l;}
  b.CreateStore(value,b.CreateGEP(b.getInt8Ty(),dst,i))->setAlignment(Align(1));auto *next=b.CreateAdd(i,b.getInt64(1));i->addIncoming(next,forward);b.CreateCondBr(b.CreateICmpULT(next,length),forward,done);
  if(copy) {b.SetInsertPoint(reverse);auto *end=b.CreatePHI(b.getInt64Ty(),2);end->addIncoming(length,direction);auto *j=b.CreateSub(end,b.getInt64(1));auto *l=b.CreateLoad(b.getInt8Ty(),b.CreateGEP(b.getInt8Ty(),src,j));l->setAlignment(Align(1));b.CreateStore(l,b.CreateGEP(b.getInt8Ty(),dst,j))->setAlignment(Align(1));end->addIncoming(j,reverse);b.CreateCondBr(b.CreateICmpNE(j,b.getInt64(0)),reverse,done);}
  b.SetInsertPoint(done);b.CreateRetVoid();
}
}
