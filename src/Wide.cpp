#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/NoFolder.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/TargetParser/Triple.h"
using namespace llvm;
namespace bennett {
Value *n22Packing(Value *v) {
  if(auto *i=dyn_cast<Instruction>(v);i && i->getType()->isIntegerTy() && i->getType()->getIntegerBitWidth()>128)i->setMetadata("bennett.n22.pack",MDNode::get(i->getContext(),{}));
  return v;
}
static bool wide(Type *t) {return t->isIntegerTy() && t->getIntegerBitWidth()>128;}
// Resolve full nested paths through N22/N25 adapter aggregates, without
// folding source arithmetic or losing the true width of a partial limb.
static Value *aggregateProjection(Value *v,ArrayRef<unsigned> path) {
  if(path.empty())return v;
  if(auto *c=dyn_cast<Constant>(v)) {
    for(unsigned n:path) {c=c->getAggregateElement(n);if(!c)return nullptr;}
    return c;
  }
  if(auto *e=dyn_cast<ExtractValueInst>(v)) {
    SmallVector<unsigned> combined(e->getIndices());combined.append(path.begin(),path.end());
    return aggregateProjection(e->getAggregateOperand(),combined);
  }
  if(auto *in=dyn_cast<InsertValueInst>(v)) {
    auto indices=in->getIndices();unsigned common=std::min(path.size(),indices.size());
    if(std::equal(path.begin(),path.begin()+common,indices.begin())) {
      if(indices.size()<=path.size())return aggregateProjection(in->getInsertedValueOperand(),path.drop_front(indices.size()));
      return nullptr; // The selected subtree itself contains a changed field.
    }
    return aggregateProjection(in->getAggregateOperand(),path);
  }
  return nullptr;
}
#include "WideRuntime.inc"
// N22 values are SSA tuples, never a reconstructed wide scalar. Recursive
// lookup permits forward block order; phi shells break loop-carried cycles.
void normaliseWideFP(Function &f) {
  auto &m=*f.getParent();auto &ctx=f.getContext();
  std::map<Value *,SmallVector<Value *>> parts;
  SmallVector<Instruction *> dead,work;
  std::function<bool(Type *)> hasWide=[&](Type *t) {if(wide(t))return true;if(auto *s=dyn_cast<StructType>(t)) {for(auto *e:s->elements())if(hasWide(e))return true;}if(auto *a=dyn_cast<ArrayType>(t))return hasWide(a->getElementType());return false;};
  bool aggregateMemory=false;
  // Wide fields cross aggregate control-flow nodes as independent scalar
  // fields before N22 splits those scalars into limbs. The shells preserve
  // loop-carried phis; full paths retain nested arrays and true top widths.
  for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work)if(i->getType()->isAggregateType() && hasWide(i->getType()) &&
      (isa<PHINode>(i)||isa<SelectInst>(i)||isa<FreezeInst>(i))) {
    std::vector<std::pair<Type *,SmallVector<unsigned>>> fields;
    std::function<void(Type *,SmallVector<unsigned>)> visit=[&](Type *t,SmallVector<unsigned> path) {
      if(t->isAggregateType()) {
        unsigned n=t->isStructTy()?cast<StructType>(t)->getNumElements():cast<ArrayType>(t)->getNumElements();
        for(unsigned k=0;k<n;++k) {auto next=path;next.push_back(k);visit(t->isStructTy()?cast<StructType>(t)->getElementType(k):t->getArrayElementType(),next);}
      } else fields.push_back({t,path});
    };visit(i->getType(),{});
    auto *phi=dyn_cast<PHINode>(i);IRBuilder<NoFolder> b(phi?&*i->getParent()->getFirstInsertionPt():i);
    Value *aggregate=Constant::getNullValue(i->getType());unsigned n=0;
    for(auto &field:fields) {
      auto name="nz.f"+std::to_string(n++)+"."+i->getName().str();Value *value;
      if(phi) {
        auto *part=PHINode::Create(field.first,phi->getNumIncomingValues(),name,phi);
        for(unsigned k=0;k<phi->getNumIncomingValues();++k) {
          auto *block=phi->getIncomingBlock(k);IRBuilder<> edge(block->getTerminator());
          part->addIncoming(edge.CreateExtractValue(phi->getIncomingValue(k),field.second),block);
        }
        value=part;
      } else if(auto *select=dyn_cast<SelectInst>(i)) {
        auto *left=b.CreateExtractValue(select->getTrueValue(),field.second);
        auto *right=b.CreateExtractValue(select->getFalseValue(),field.second);
        value=b.CreateSelect(select->getCondition(),left,right,name);
      } else value=b.CreateFreeze(b.CreateExtractValue(i->getOperand(0),field.second),name);
      aggregate=b.CreateInsertValue(aggregate,value,field.second);
    }
    i->replaceAllUsesWith(aggregate);i->eraseFromParent();
  }
  work.clear();
  // Aggregate transport follows DataLayout offsets, including nested arrays.
  for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work) {
    auto *l=dyn_cast<LoadInst>(i);auto *s=dyn_cast<StoreInst>(i);
    Type *t=l?l->getType():s?s->getValueOperand()->getType():nullptr;
    if(!t || !t->isAggregateType())continue;
    aggregateMemory=true;
    IRBuilder<NoFolder> b(i);unsigned ordinal=0;std::string r=i->hasName()?i->getName().str():f.getName().str()+".agg";i->setName("");
    std::function<Value *(Type *,Value *,Value *,uint64_t)> access=[&](Type *ty,Value *base,Value *v,uint64_t off)->Value * {
      if(ty->isAggregateType()) {
        unsigned n=ty->isStructTy()?cast<StructType>(ty)->getNumElements():cast<ArrayType>(ty)->getNumElements();
        Value *out=Constant::getNullValue(ty);
        for(unsigned k=0;k<n;++k) {
          Type *et=ty->isStructTy()?cast<StructType>(ty)->getElementType(k):cast<ArrayType>(ty)->getElementType();
          uint64_t delta=ty->isStructTy()?m.getDataLayout().getStructLayout(cast<StructType>(ty))->getElementOffset(k):k*m.getDataLayout().getTypeAllocSize(et).getFixedValue();
          auto *e=access(et,base,v?(isa<Constant>(v)?cast<Constant>(v)->getAggregateElement(k):b.CreateExtractValue(v,{k})):nullptr,off+delta);
          if(!v)out=b.CreateInsertValue(out,e,{k});
        }
        return out;
      }
      auto *p=b.CreateGEP(b.getInt8Ty(),base,b.getInt64(off),"nz.e"+std::to_string(ordinal++)+"."+r);
      if(v) {b.CreateStore(v,p)->setAlignment(commonAlignment(s->getAlign(),off));return v;}
      auto *e=b.CreateLoad(ty,p);e->setAlignment(commonAlignment(l->getAlign(),off));return e;
    };
    auto *v=access(t,l?l->getPointerOperand():s->getPointerOperand(),s?s->getValueOperand():nullptr,0);
    if(l)l->replaceAllUsesWith(v);i->eraseFromParent();
  }

  bool wideAggregate=false;
  // Resolve projections of freshly scalarised aggregate loads and N27 limb tuples.
  for(auto &i:instructions(f))if(auto *e=dyn_cast<ExtractValueInst>(&i)) {
    if(!aggregateMemory && !hasWide(e->getAggregateOperand()->getType()))continue;
    wideAggregate=true;
    if(auto *value=aggregateProjection(e->getAggregateOperand(),e->getIndices()))e->replaceAllUsesWith(value);
  }
  bool cleanup=aggregateMemory||wideAggregate;while(cleanup) {SmallVector<Instruction *> erase;for(auto &i:instructions(f))if(i.use_empty() && (isa<ExtractValueInst>(i)||isa<InsertValueInst>(i)))erase.push_back(&i);for(auto *i:erase)i->eraseFromParent();cleanup=!erase.empty();}
  // Byte-rounded accesses also include the slots introduced below.
  auto byteMemory=[&]() {
  SmallVector<Instruction *> accesses;for(auto &i:instructions(f))accesses.push_back(&i);
  for(auto *i:accesses) {
    auto *l=dyn_cast<LoadInst>(i);auto *s=dyn_cast<StoreInst>(i);Type *t=l?l->getType():s?s->getValueOperand()->getType():nullptr;
    if(!t || !t->isIntegerTy() || !(t->getIntegerBitWidth()%8))continue;
    IRBuilder<NoFolder> b(i);auto *bt=b.getIntNTy(8*((t->getIntegerBitWidth()+7)/8));
    if(l) {auto r=l->getName().str();l->setName("");auto *v=b.CreateLoad(bt,l->getPointerOperand(),"nz.l."+r);v->setAlignment(l->getAlign());l->replaceAllUsesWith(b.CreateTrunc(v,t,r));}
    else {auto *v=b.CreateZExt(s->getValueOperand(),bt);b.CreateStore(v,s->getPointerOperand())->setAlignment(s->getAlign());}
    i->eraseFromParent();
  }
  };
  byteMemory();
  work.clear();for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work)if(auto *p=dyn_cast<PHINode>(i);p && wide(p->getType())) {
    auto n=p->getType()->getIntegerBitWidth();
    for(unsigned k=0;k<(n+63)/64;++k)parts[p].push_back(PHINode::Create(IntegerType::get(ctx,std::min(64u,n-64*k)),p->getNumIncomingValues(),"nz.m"+std::to_string(k)+"."+p->getName(),p));
    dead.push_back(p);
  }
  std::function<SmallVector<Value *>(Value *)> split;
  // Extract a bit interval, used by casts and N21's temporary packing graph.
  auto slice=[&](Value *v,unsigned offset,unsigned width,IRBuilder<> &b)->Value * {
    unsigned n=v->getType()->getIntegerBitWidth();auto *ty=b.getIntNTy(width);
    if(offset>=n)return ConstantInt::get(ty,0);
    if(!wide(v->getType())) {if(offset)v=b.CreateLShr(v,ConstantInt::get(v->getType(),offset));return b.CreateZExtOrTrunc(v,ty);}
    auto a=split(v);unsigned k=offset/64,sh=offset%64;
    Value *lo=b.CreateZExtOrTrunc(a[k],b.getInt64Ty());if(sh)lo=b.CreateLShr(lo,b.getInt64(sh));
    if(sh && k+1<a.size() && width>64-sh)lo=b.CreateOr(lo,b.CreateShl(b.CreateZExtOrTrunc(a[k+1],b.getInt64Ty()),b.getInt64(64-sh)));
    return b.CreateZExtOrTrunc(lo,ty);
  };
  split=[&](Value *v)->SmallVector<Value *> {
    if(parts.count(v))return parts[v];
    unsigned n=v->getType()->getIntegerBitWidth(),count=(n+63)/64;SmallVector<Value *> out;
    if(auto *c=dyn_cast<ConstantInt>(v)) {for(unsigned k=0;k<count;++k)out.push_back(ConstantInt::get(ctx,c->getValue().lshr(64*k).trunc(std::min(64u,n-64*k))));return out;}
    auto *i=dyn_cast<Instruction>(v);if(!i)unimplemented("§12.7 N22 wide parameter ABI",2,v);
    IRBuilder<NoFolder> b(i);IRBuilder<> fold(i);auto r=i->getName().str();
    auto name=[&](StringRef prefix,unsigned k){return "nz."+prefix.str()+std::to_string(k)+"."+r;};
    if(auto *l=dyn_cast<LoadInst>(i)) {
      for(unsigned k=0;k<count;++k) {auto *p=b.CreateGEP(b.getInt64Ty(),l->getPointerOperand(),b.getInt64(k),name("p",k));auto *e=b.CreateLoad(b.getIntNTy(std::min(64u,n-64*k)),p,name("m",k));e->setAlignment(commonAlignment(l->getAlign(),8*k));out.push_back(e);}
    } else if(auto *s=dyn_cast<SelectInst>(i)) {
      auto a=split(s->getTrueValue()),c=split(s->getFalseValue());
      for(unsigned k=0;k<count;++k)out.push_back(b.CreateSelect(s->getCondition(),a[k],c[k],name("m",k)));
    } else if(isa<FreezeInst>(i)) {
      auto a=split(i->getOperand(0));for(unsigned k=0;k<count;++k)out.push_back(b.CreateFreeze(a[k],name("m",k)));
    } else if(auto *p=dyn_cast<PtrToIntInst>(i)) {
      auto pw=m.getDataLayout().getPointerTypeSizeInBits(p->getOperand(0)->getType());
      auto *value=fold.CreatePtrToInt(p->getOperand(0),b.getIntNTy(pw));
      for(unsigned k=0;k<count;++k)out.push_back(slice(value,64*k,std::min(64u,n-64*k),fold));
    } else if(auto *e=dyn_cast<ExtractValueInst>(i)) {
      if(auto *value=aggregateProjection(e->getAggregateOperand(),e->getIndices()))out=split(value);
      if(out.empty())unimplemented("§12.7 N22 aggregate projection",2,i);
    } else if(isa<ZExtInst>(i)||isa<SExtInst>(i)||isa<TruncInst>(i)) {
      auto *src=i->getOperand(0);unsigned sw=src->getType()->getIntegerBitWidth();
      for(unsigned k=0;k<count;++k) {
        unsigned w=std::min(64u,n-64*k);Value *e;
        if(isa<SExtInst>(i) && 64*k+w>sw) {
          if(64*k<sw) {e=slice(src,64*k,std::min(w,sw-64*k),fold);e=fold.CreateSExtOrTrunc(e,b.getIntNTy(w));}
          else {auto *top=slice(src,sw-1,1,fold);e=fold.CreateSExt(top,b.getIntNTy(w));}
        } else e=slice(src,64*k,w,fold);
        out.push_back(e);
      }
    } else if(auto *op=dyn_cast<BinaryOperator>(i)) {
      auto code=op->getOpcode();auto a=split(op->getOperand(0)),c=split(op->getOperand(1));
      if(code==Instruction::Add || code==Instruction::Sub) {
        bool sub=code==Instruction::Sub;Value *carry=nullptr;
        for(unsigned k=0;k<count;++k) {
          auto *t=b.CreateBinOp((Instruction::BinaryOps)code,a[k],c[k],name(k?"t":"m",k));Value *e=t,*z=nullptr;
          if(k) {z=b.CreateZExtOrTrunc(carry,t->getType(),name("z",k));e=b.CreateBinOp((Instruction::BinaryOps)code,t,z,name("m",k));}
          out.push_back(e);
          if(k+1<count) {
            if(!k)carry=b.CreateICmpULT(sub?a[k]:e,sub?c[k]:a[k],name("c",k));
            else {auto *u=b.CreateICmpULT(sub?a[k]:t,sub?c[k]:a[k],name("u",k));auto *v=b.CreateICmpULT(sub?t:e,sub?z:t,name("v",k));carry=b.CreateOr(u,v,name("c",k));}
          }
        }
      } else if(code==Instruction::And || code==Instruction::Or || code==Instruction::Xor) {
        for(unsigned k=0;k<count;++k) {
          if(code==Instruction::Or && isa<ConstantInt>(a[k]) && cast<ConstantInt>(a[k])->isZero())out.push_back(c[k]);
          else if(code==Instruction::Or && isa<ConstantInt>(c[k]) && cast<ConstantInt>(c[k])->isZero())out.push_back(a[k]);
          else out.push_back(fold.CreateBinOp((Instruction::BinaryOps)code,a[k],c[k],name("m",k)));
        }
      } else if(op->isShift() && op->getMetadata("bennett.n22.pack") && isa<ConstantInt>(op->getOperand(1)) && cast<ConstantInt>(op->getOperand(1))->getValue().urem(64)==0) {
        auto shift=cast<ConstantInt>(op->getOperand(1))->getLimitedValue(n);unsigned words=shift/64;
        for(unsigned k=0;k<count;++k) {
          int index=code==Instruction::Shl?int(k)-int(words):int(k)+int(words);auto *ty=b.getIntNTy(std::min(64u,n-64*k));
          Value *e=index>=0 && unsigned(index)<count?fold.CreateZExtOrTrunc(a[index],ty):ConstantInt::get(ty,0);
          if(code==Instruction::AShr) { /* nontrivial signed shifts use the runtime below */ out.clear();break; }
          out.push_back(e);
        }
      }
      if(out.empty()) {
        auto push=m.getOrInsertFunction("__bennett_rt_ss_push",b.getPtrTy(),b.getInt64Ty(),b.getInt64Ty());auto pop=m.getOrInsertFunction("__bennett_rt_ss_pop",b.getVoidTy(),b.getPtrTy());
        auto slot=[&](StringRef suffix) {return b.CreateCall(push,{b.getInt64(8*count),b.getInt64(8)},"nz."+suffix+"."+r);};
        auto *dst=slot("d"),*pa=slot("a"),*pb=slot("b");
        for(unsigned k=0;k<count;++k) {b.CreateStore(a[k],b.CreateGEP(b.getInt64Ty(),pa,b.getInt64(k)))->setAlignment(Align(8));b.CreateStore(c[k],b.CreateGEP(b.getInt64Ty(),pb,b.getInt64(k)))->setAlignment(Align(8));}
        auto *rt=wideRuntime(m,n,code);b.CreateCall(rt,{dst,pa,pb});
        for(unsigned k=0;k<count;++k)out.push_back(b.CreateLoad(b.getIntNTy(std::min(64u,n-64*k)),b.CreateGEP(b.getInt64Ty(),dst,b.getInt64(k))));
        b.CreateCall(pop,{pb});b.CreateCall(pop,{pa});b.CreateCall(pop,{dst});
      }
    } else if(auto *c=dyn_cast<CallBase>(i);c && c->getCalledFunction() && c->getCalledFunction()->getName().starts_with("__bennett_rt_")) {
      auto rtname=c->getCalledFunction()->getName().str();auto suffix="_i"+std::to_string(n);
      if(rtname.size()<=suffix.size() || rtname.substr(rtname.size()-suffix.size())!=suffix)unimplemented("§12.8 slot runtime name",2,i);
      auto op=rtname.substr(13,rtname.size()-13-suffix.size());
      auto push=m.getOrInsertFunction("__bennett_rt_ss_push",b.getPtrTy(),b.getInt64Ty(),b.getInt64Ty());auto pop=m.getOrInsertFunction("__bennett_rt_ss_pop",b.getVoidTy(),b.getPtrTy());
      auto slot=[&](StringRef suffix) {return b.CreateCall(push,{b.getInt64(8*count),b.getInt64(8)},"nz."+suffix+"."+r);};
      auto *dst=slot("d");SmallVector<Value *> args{dst},slots;SmallVector<Type *> types;
      unsigned index=0;
      for(auto &u:c->args()) {
        if(wide(u->getType())) {
          auto a=split(u);auto label="s"+std::to_string(index++);auto *p=slot(label);slots.push_back(p);args.push_back(p);
          for(unsigned k=0;k<a.size();++k)b.CreateStore(a[k],b.CreateGEP(b.getInt64Ty(),p,b.getInt64(k),"nz."+label+std::to_string(k)+"."+r))->setAlignment(Align(8));
        } else args.push_back(u);
      }
      for(auto *v:args)types.push_back(v->getType());
      b.CreateCall(m.getOrInsertFunction("__bennett_rt_i"+std::to_string(n)+"_"+op,FunctionType::get(b.getVoidTy(),types,false)),args);
      for(unsigned k=0;k<count;++k) {auto *v=b.CreateLoad(b.getIntNTy(std::min(64u,n-64*k)),b.CreateGEP(b.getInt64Ty(),dst,b.getInt64(k),"nz.rp"+std::to_string(k)+"."+r),"nz.rm"+std::to_string(k)+"."+r);v->setAlignment(Align(8));out.push_back(v);}
      for(auto it=slots.rbegin();it!=slots.rend();++it)b.CreateCall(pop,{*it});b.CreateCall(pop,{dst});
    } else unimplemented("§12 N22 general wide limb operation",2,i);
    parts[v]=out;dead.push_back(i);return out;
  };
  unsigned ordinal=0;
  for(auto *i:work) {
    if(auto *p=dyn_cast<PHINode>(i);p && wide(p->getType())) {
      for(unsigned j=0;j<p->getNumIncomingValues();++j) {auto a=split(p->getIncomingValue(j));for(unsigned k=0;k<a.size();++k)cast<PHINode>(parts[p][k])->addIncoming(a[k],p->getIncomingBlock(j));}
    } else if(auto *s=dyn_cast<StoreInst>(i);s && wide(s->getValueOperand()->getType())) {
      auto a=split(s->getValueOperand());IRBuilder<NoFolder> b(s);auto r=f.getName().str()+"."+std::to_string(ordinal++);
      for(unsigned k=0;k<a.size();++k) {auto *p=b.CreateGEP(b.getInt64Ty(),s->getPointerOperand(),b.getInt64(k),"nz.q"+std::to_string(k)+"."+r);b.CreateStore(a[k],p)->setAlignment(commonAlignment(s->getAlign(),8*k));}dead.push_back(s);
    } else if(auto *p=dyn_cast<IntToPtrInst>(i);p && wide(p->getOperand(0)->getType())) {
      IRBuilder<> b(p);auto *value=slice(p->getOperand(0),0,m.getDataLayout().getPointerTypeSizeInBits(p->getType()),b);
      p->replaceAllUsesWith(b.CreateIntToPtr(value,p->getType()));dead.push_back(p);
    } else if(auto *t=dyn_cast<TruncInst>(i);t && wide(t->getOperand(0)->getType()) && !wide(t->getType())) {
      IRBuilder<> b(t);auto a=split(t->getOperand(0));Value *v=b.CreateZExtOrTrunc(a[0],t->getType());
      if(t->getType()->getIntegerBitWidth()>64)v=b.CreateOr(v,b.CreateShl(b.CreateZExt(a[1],t->getType()),ConstantInt::get(t->getType(),64)));
      t->replaceAllUsesWith(v);dead.push_back(t);
    } else if(auto *cmp=dyn_cast<ICmpInst>(i);cmp && wide(cmp->getOperand(0)->getType())) {
      auto a=split(cmp->getOperand(0)),c=split(cmp->getOperand(1));IRBuilder<NoFolder> b(cmp);auto r=cmp->getName().str();cmp->setName("");auto pred=cmp->getPredicate();
      Value *value=ConstantInt::get(b.getInt1Ty(),CmpInst::isTrueWhenEqual(pred));
      for(unsigned k=0;k<a.size();++k) {auto suffix=std::to_string(k)+"."+r;auto *eq=b.CreateICmpEQ(a[k],c[k],"nz.eq"+suffix);auto p=k+1==a.size()?pred:ICmpInst::getUnsignedPredicate(pred);auto *v=b.CreateICmp(p,a[k],c[k],"nz.cmp"+suffix);value=b.CreateSelect(eq,value,v,k+1==a.size()?r:"nz.c"+suffix);}
      cmp->replaceAllUsesWith(value);dead.push_back(cmp);
    }
  }
  // Resolve even unused wide producers so identity is independent of liveness.
  for(auto *i:work)if(wide(i->getType()) && !isa<PHINode>(i))split(i);
  std::set<Instruction *> unique(dead.begin(),dead.end());
  for(auto *i:unique)for(auto *u:i->users())if(!unique.count(dyn_cast<Instruction>(u)))unimplemented("§12.7 N22 wide consumer ABI",2,i);
  for(auto *i:unique)i->dropAllReferences();for(auto *i:unique)i->eraseFromParent();
  byteMemory();
}
}

namespace bennett {
#include "Varargs.inc"
Function *normaliseWideABI(Module &m,Function *root) {
  auto &ctx=m.getContext();
  // N23 precedes N22's signature work; a variadic signature has no carrier to widen.
  normaliseVarargs(m,root);
  std::function<Type *(Type *)> shape=[&](Type *t)->Type * {
    if(wide(t)) {SmallVector<Type *> fields;unsigned n=t->getIntegerBitWidth();for(unsigned k=0;k<(n+63)/64;++k)fields.push_back(IntegerType::get(ctx,std::min(64u,n-64*k)));return StructType::get(ctx,fields);}
    if(auto *s=dyn_cast<StructType>(t);s && !s->isOpaque()) {SmallVector<Type *> fields;bool change=false;for(auto *e:s->elements()){auto *v=shape(e);change|=v!=e;fields.push_back(v);}if(change)return StructType::get(ctx,fields,s->isPacked());}
    if(auto *a=dyn_cast<ArrayType>(t)) {auto *e=shape(a->getElementType());if(e!=a->getElementType())return ArrayType::get(e,a->getNumElements());}
    return t;
  };
  std::function<uint64_t(Type *)> payload=[&](Type *t)->uint64_t {
    if(auto *st=dyn_cast<StructType>(t)) {uint64_t n=0;for(auto *e:st->elements())n+=payload(e);return n;}
    if(auto *at=dyn_cast<ArrayType>(t))return at->getNumElements()*payload(at->getElementType());
    return t->isVoidTy()?0:m.getDataLayout().getTypeSizeInBits(t).getKnownMinValue();
  };
  auto demoted=[&](Type *t) {return shape(t)->isAggregateType() && payload(shape(t))>128;};
  // Temporary adapter expressions are consumed by N22, not left at the ABI.
  std::function<Value *(IRBuilder<> &,Value *,Type *,bool)> adapt=[&](IRBuilder<> &b,Value *v,Type *old,bool unpack)->Value * {
    Type *to=unpack?old:shape(old);if(shape(old)==old)return v;
    if(wide(old)) {
      unsigned n=old->getIntegerBitWidth();Value *out=Constant::getNullValue(to);
      for(unsigned k=0;k<(n+63)/64;++k) {
        if(unpack) {Value *e=b.CreateZExt(b.CreateExtractValue(v,{k}),old);if(k)e=n22Packing(b.CreateShl(e,ConstantInt::get(old,64*k)));out=b.CreateOr(out,e);}
        else {Value *e=v;if(k)e=n22Packing(b.CreateLShr(e,ConstantInt::get(old,64*k)));e=b.CreateTrunc(e,b.getIntNTy(std::min(64u,n-64*k)));out=b.CreateInsertValue(out,e,{k});}
      }
      return out;
    }
    unsigned n=old->isStructTy()?cast<StructType>(old)->getNumElements():cast<ArrayType>(old)->getNumElements();Value *out=Constant::getNullValue(to);
    for(unsigned k=0;k<n;++k) {auto *et=old->isStructTy()?cast<StructType>(old)->getElementType(k):cast<ArrayType>(old)->getElementType();out=b.CreateInsertValue(out,adapt(b,b.CreateExtractValue(v,{k}),et,unpack),{k});}return out;
  };
  SmallVector<Function *> work;for(auto &f:m)if(!f.isIntrinsic())work.push_back(&f);
  std::map<Function *,Function *> changed;
  for(auto *f:work) {
    SmallVector<Type *> params;bool hidden=demoted(f->getReturnType());bool change=hidden || shape(f->getReturnType())!=f->getReturnType();
    if(hidden)params.push_back(PointerType::get(ctx,0));
    for(auto &a:f->args()) {auto *t=a.getType();change|=shape(t)!=t;if(wide(t))for(auto *e:cast<StructType>(shape(t))->elements())params.push_back(e);else params.push_back(shape(t));}
    if(!change)continue;
    auto *nf=Function::Create(FunctionType::get(hidden?Type::getVoidTy(ctx):shape(f->getReturnType()),params,f->isVarArg()),f->getLinkage(),f->getAddressSpace(),"",&m);nf->takeName(f);f->setName(nf->getName()+".n22.old");nf->setCallingConv(f->getCallingConv());
    nf->copyAttributesFrom(f);nf->copyMetadata(f,0);
    SmallVector<AttributeSet> attrs;
    if(hidden)attrs.push_back(AttributeSet());
    for(auto &a:f->args()) {
      if(wide(a.getType()))attrs.append((a.getType()->getIntegerBitWidth()+63)/64,AttributeSet());
      else attrs.push_back(shape(a.getType())==a.getType()?f->getAttributes().getParamAttrs(a.getArgNo()):AttributeSet());
    }
    nf->setAttributes(AttributeList::get(ctx,f->getAttributes().getFnAttrs(),!hidden && shape(f->getReturnType())==f->getReturnType()?f->getAttributes().getRetAttrs():AttributeSet(),attrs));changed[f]=nf;
  }
  if(changed.empty())return root;
  std::set<Function *> touched;
  for(auto [f,nf]:changed)if(!f->isDeclaration()) {
    touched.insert(nf);
    nf->splice(nf->end(),f);IRBuilder<> b(&*nf->getEntryBlock().getFirstInsertionPt());bool hidden=demoted(f->getReturnType());unsigned index=hidden?1:0;
    if(hidden)nf->getArg(0)->setName("nz.ret");
    for(auto &a:f->args()) {
      Value *v;
      if(wide(a.getType())) {Value *tuple=Constant::getNullValue(shape(a.getType()));unsigned n=(a.getType()->getIntegerBitWidth()+63)/64;for(unsigned k=0;k<n;++k){auto *e=nf->getArg(index++);e->setName("nz.m"+std::to_string(k)+"."+a.getName());tuple=b.CreateInsertValue(tuple,e,{k});}v=adapt(b,tuple,a.getType(),true);}
      else {auto *e=nf->getArg(index++);e->setName(a.getName());v=adapt(b,e,a.getType(),true);}
      a.replaceAllUsesWith(v);
    }
    SmallVector<ReturnInst *> returns;for(auto &i:instructions(nf))if(auto *r=dyn_cast<ReturnInst>(&i);r && r->getReturnValue())returns.push_back(r);
    for(auto *r:returns) {
      b.SetInsertPoint(r);auto *value=adapt(b,r->getReturnValue(),f->getReturnType(),false);
      if(hidden) {b.CreateStore(value,nf->getArg(0));b.CreateRetVoid();}else b.CreateRet(value);
      r->eraseFromParent();
    }
  }
  // Calls use their original FunctionType even for aliases/indirect pointers.
  SmallVector<CallInst *> calls;for(auto &f:m)for(auto &i:instructions(f))if(auto *c=dyn_cast<CallInst>(&i))calls.push_back(c);
  for(auto *c:calls) {
    auto *ft=c->getFunctionType();bool hidden=demoted(ft->getReturnType());bool change=hidden || shape(ft->getReturnType())!=ft->getReturnType();for(auto *t:ft->params())change|=shape(t)!=t;if(!change || (c->getCalledFunction() && c->getCalledFunction()->isIntrinsic()))continue;
    touched.insert(c->getFunction());
    IRBuilder<> b(c);SmallVector<Value *> args;SmallVector<Type *> types;
    AllocaInst *returnSlot=nullptr;
    if(hidden) {
      IRBuilder<> entry(&*c->getFunction()->getEntryBlock().getFirstInsertionPt());
      returnSlot=entry.CreateAlloca(shape(ft->getReturnType()),nullptr,"nz.ret."+c->getName());
      args.push_back(returnSlot);
    }
    for(auto &u:c->args()) {auto *v=u.get();auto *t=v->getType();auto *e=adapt(b,v,t,false);if(wide(t))for(unsigned k=0;k<(t->getIntegerBitWidth()+63)/64;++k)args.push_back(b.CreateExtractValue(e,{k}));else args.push_back(e);}
    for(auto *v:args)types.push_back(v->getType());auto *callee=c->getCalledOperand();if(auto *g=dyn_cast<Function>(callee);changed.count(g))callee=changed[g];
    auto *nc=b.CreateCall(FunctionType::get(hidden?Type::getVoidTy(ctx):shape(ft->getReturnType()),types,ft->isVarArg()),callee,args);nc->setCallingConv(c->getCallingConv());nc->copyMetadata(*c);
    SmallVector<AttributeSet> attrs;
    if(hidden)attrs.push_back(AttributeSet());
    for(unsigned j=0;j<c->arg_size();++j) {
      auto *t=c->getArgOperand(j)->getType();
      if(wide(t))attrs.append((t->getIntegerBitWidth()+63)/64,AttributeSet());
      else attrs.push_back(shape(t)==t?c->getAttributes().getParamAttrs(j):AttributeSet());
    }
    nc->setAttributes(AttributeList::get(ctx,c->getAttributes().getFnAttrs(),!hidden && shape(c->getType())==c->getType()?c->getAttributes().getRetAttrs():AttributeSet(),attrs));
    if(!c->getType()->isVoidTy()) {auto *result=hidden?b.CreateLoad(shape(c->getType()),returnSlot):static_cast<Value *>(nc);auto *v=adapt(b,result,c->getType(),true);v->takeName(c);c->replaceAllUsesWith(v);}c->eraseFromParent();
  }
  for(auto [f,nf]:changed) {if(root==f)root=nf;f->replaceAllUsesWith(nf);f->eraseFromParent();}
  // Fold adapter insert/extract chains without optimising source arithmetic.
  for(auto &f:m)if(touched.count(&f) && !f.isDeclaration()) {
    SmallVector<ExtractValueInst *> extracts;for(auto &i:instructions(f))if(auto *e=dyn_cast<ExtractValueInst>(&i))extracts.push_back(e);
    for(auto *e:extracts) {
      if(auto *value=aggregateProjection(e->getAggregateOperand(),e->getIndices()))e->replaceAllUsesWith(value);
    }
    bool more=true;while(more) {more=false;SmallVector<Instruction *> dead;for(auto &i:instructions(f))if(i.use_empty() && (isa<ExtractValueInst>(i)||isa<InsertValueInst>(i)))dead.push_back(&i);for(auto *i:dead)i->eraseFromParent();more=!dead.empty();}
  }
  return root;
}
}
