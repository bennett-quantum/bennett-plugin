#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/NoFolder.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/InstIterator.h"
#include <regex>
using namespace llvm;
namespace bennett {
static bool runtimeOp(StringRef op) {
  static const std::set<std::string> names={"bswap","bitreverse","ctpop","ctlz","cttz","fshl","fshr","sshl.sat","ushl.sat","smul.fix","umul.fix","smul.fix.sat","umul.fix.sat","sdiv.fix","udiv.fix","sdiv.fix.sat","udiv.fix.sat","pdep","pext","clmul"};return names.count(op.str());
}
void normaliseInteger(Function &f) {
  SmallVector<IntrinsicInst *> work;for(auto &i:instructions(f))if(auto *c=dyn_cast<IntrinsicInst>(&i))work.push_back(c);
  for(auto *c:work) {
    auto name=Intrinsic::getBaseName(c->getIntrinsicID()).drop_front(5);if(c->arg_empty())continue;
    auto *a=c->getArgOperand(0);if(!a->getType()->isIntegerTy())continue;
    bool extrema=name=="smax"||name=="smin"||name=="umax"||name=="umin",sat=name=="uadd.sat"||name=="usub.sat"||name=="sadd.sat"||name=="ssub.sat";
    bool overflow=name.ends_with(".with.overflow"),mul=overflow && name.contains("mul");
    bool cmp=name=="scmp"||name=="ucmp";
    if(!extrema && !overflow && !sat && !cmp && name!="abs" && !runtimeOp(name))continue;
    IRBuilder<NoFolder> b(c);auto r=c->getName().str();c->setName("");auto *t=cast<IntegerType>(a->getType());unsigned n=t->getBitWidth();auto *zero=ConstantInt::get(t,0);Value *result=nullptr;
    auto *d=c->arg_size()>1?c->getArgOperand(1):nullptr;
    if(extrema) {
      auto predicate=name=="smax"?CmpInst::ICMP_SGT:name=="smin"?CmpInst::ICMP_SLT:name=="umax"?CmpInst::ICMP_UGT:CmpInst::ICMP_ULT;
      auto *cond=b.CreateICmp(predicate,a,d,"nz.c."+r);result=b.CreateSelect(cond,a,d,r);
    } else if(name=="abs") {
      auto *cond=b.CreateICmpSLT(a,zero,"nz.c."+r);auto *neg=b.CreateSub(zero,a,"nz.n."+r);result=b.CreateSelect(cond,neg,a,r);
    } else if(cmp) {
      auto *g=b.CreateICmp(name=="scmp"?CmpInst::ICMP_SGT:CmpInst::ICMP_UGT,a,d,"nz.g."+r);auto *l=b.CreateICmp(name=="scmp"?CmpInst::ICMP_SLT:CmpInst::ICMP_ULT,a,d,"nz.l."+r);
      result=b.CreateOr(b.CreateZExtOrTrunc(g,c->getType(),"nz.z."+r),b.CreateSExtOrTrunc(l,c->getType(),"nz.s."+r),r);
    } else if(overflow || sat) {
      bool sub=name.contains("sub"),sign=name.starts_with("s");Value *sum,*flag;
      if(mul && n>64) {
        std::string op=name.str();std::replace(op.begin(),op.end(),'.','_');
        if(n<=128) {
          auto rt=f.getParent()->getOrInsertFunction("__bennett_rt_"+op+"_i"+std::to_string(n),c->getFunctionType());result=b.CreateCall(rt,{a,d},r);
        } else {
          auto &m=*f.getParent();auto push=m.getOrInsertFunction("__bennett_rt_ss_push",b.getPtrTy(),b.getInt64Ty(),b.getInt64Ty()),pop=m.getOrInsertFunction("__bennett_rt_ss_pop",b.getVoidTy(),b.getPtrTy());
          auto slot=[&](StringRef tag){return b.CreateCall(push,{b.getInt64(8*((n+63)/64)),b.getInt64(8)},"nz."+tag+"."+r);};
          auto *dst=slot("d"),*pa=slot("s0"),*pb=slot("s1");b.CreateStore(a,pa)->setAlignment(Align(8));b.CreateStore(d,pb)->setAlignment(Align(8));
          auto rt=m.getOrInsertFunction("__bennett_rt_i"+std::to_string(n)+"_"+op,b.getInt1Ty(),b.getPtrTy(),b.getPtrTy(),b.getPtrTy());flag=b.CreateCall(rt,{dst,pa,pb});sum=b.CreateLoad(t,dst);
          b.CreateCall(pop,{pb});b.CreateCall(pop,{pa});b.CreateCall(pop,{dst});
          result=b.CreateInsertValue(b.CreateInsertValue(Constant::getNullValue(c->getType()),sum,0),flag,1,r);
        }
      } else {
        if(mul) {
          auto *tw=b.getIntNTy(2*n);auto *x=sign?b.CreateSExt(a,tw):b.CreateZExt(a,tw),*y=sign?b.CreateSExt(d,tw):b.CreateZExt(d,tw);auto *p=b.CreateMul(x,y);sum=b.CreateTrunc(p,t,"nz.s."+r);
          flag=b.CreateICmpNE(p,sign?b.CreateSExt(sum,tw):b.CreateZExt(sum,tw),"nz.c."+r);
        } else {
          sum=sub?b.CreateSub(a,d,"nz.s."+r):b.CreateAdd(a,d,"nz.s."+r);
          if(sign) {auto *x=b.CreateXor(a,sum,"nz.x."+r);auto *y=b.CreateXor(sub?a:d,sub?d:sum,"nz.y."+r);auto *w=b.CreateAnd(x,y,"nz.w."+r);flag=b.CreateICmpSLT(w,zero,"nz.c."+r);}
          else flag=b.CreateICmpULT(sub?a:sum,sub?d:a,"nz.c."+r);
        }
        if(sat) {
          Value *bound=ConstantInt::get(t,sub?APInt::getZero(n):APInt::getAllOnes(n));
          if(sign)bound=b.CreateSelect(b.CreateICmpSLT(a,zero),ConstantInt::get(t,APInt::getSignedMinValue(n)),ConstantInt::get(t,APInt::getSignedMaxValue(n)));
          result=b.CreateSelect(flag,bound,sum,r);
        } else {auto *first=b.CreateInsertValue(Constant::getNullValue(c->getType()),sum,0,"nz.a."+r);result=b.CreateInsertValue(first,flag,1,r);}
      }
    } else {
      std::string op=name.str();std::replace(op.begin(),op.end(),'.','_');auto rt=f.getParent()->getOrInsertFunction("__bennett_rt_"+op+"_i"+std::to_string(n),c->getFunctionType());SmallVector<Value *> args(c->args());result=b.CreateCall(rt,args,r);
    }
    c->replaceAllUsesWith(result);c->eraseFromParent();
  }
}
// Definitions are materialised on closure edges, before hashing or lowering.
// A linked definition always wins, including its own data and callees.
void materialiseIntegerRuntime(Function &f) {
  if(!f.isDeclaration())return;
  std::smatch match;auto name=f.getName().str();bool slot=std::regex_match(name,match,std::regex("__bennett_rt_i([0-9]+)_(.+)"));
  unsigned n;std::string op;
  if(slot) {n=std::stoul(match[1]);op=match[2];}
  else if(std::regex_match(name,match,std::regex("__bennett_rt_(.+)_i([0-9]+)"))) {op=match[1];n=std::stoul(match[2]);}
  else return;
  auto dotted=op;std::replace(dotted.begin(),dotted.end(),'_','.');bool overflow=dotted=="umul.with.overflow"||dotted=="smul.with.overflow";
  if(!runtimeOp(dotted) && !overflow)return;
  auto &m=*f.getParent();auto &ctx=m.getContext();IRBuilder<> b(BasicBlock::Create(ctx,"entry",&f));auto *t=b.getIntNTy(n);unsigned limbs=(n+63)/64;
  unsigned wideArgs=(op=="ctpop"||op=="ctlz"||op=="cttz"||op=="bswap"||op=="bitreverse")?1:(op=="fshl"||op=="fshr")?3:2;
  SmallVector<Value *> args;
  for(unsigned k=0;k<wideArgs;++k) {Value *v=f.getArg(k+(slot?1:0));if(slot) {auto *l=b.CreateLoad(t,v);l->setAlignment(Align(8));v=l;}args.push_back(v);}
  auto *a=args[0];Value *c=args.size()>1?args[1]:nullptr,*result=nullptr,*flag=nullptr;auto *zero=ConstantInt::get(t,0);bool sign=op[0]=='s';
  auto fault=[&](Value *bad) {auto *fail=BasicBlock::Create(ctx,"fault",&f),*ok=BasicBlock::Create(ctx,"ok",&f);b.CreateCondBr(bad,fail,ok);b.SetInsertPoint(fail);b.CreateCall(m.getOrInsertFunction("__bennett_nz_fault",b.getVoidTy(),b.getInt64Ty()),{b.getInt64(5)});b.CreateUnreachable();b.SetInsertPoint(ok);};
  if(op=="ctpop"||op=="ctlz"||op=="cttz"||op=="bswap"||op=="bitreverse"||op=="pdep"||op=="pext"||op=="clmul") {
    // Bit iteration uses native limbs, never a wide dynamic shift or host intrinsic.
    SmallVector<SmallVector<Value *>> words;
    for(auto *v:args) {SmallVector<Value *> w;for(unsigned k=0;k<limbs;++k) {Value *e=v;if(k)e=n22Packing(b.CreateLShr(e,ConstantInt::get(t,64*k)));w.push_back(b.CreateZExtOrTrunc(e,b.getInt64Ty()));}words.push_back(w);}
    auto *pre=b.GetInsertBlock(),*loop=BasicBlock::Create(ctx,"bit",&f),*done=BasicBlock::Create(ctx,"done",&f);b.CreateBr(loop);b.SetInsertPoint(loop);
    auto *index=b.CreatePHI(b.getInt64Ty(),2),*count=b.CreatePHI(b.getInt64Ty(),2);index->addIncoming(b.getInt64(0),pre);count->addIncoming(b.getInt64(op=="ctlz"||op=="cttz"?n:0),pre);
    SmallVector<PHINode *> acc;for(unsigned k=0;k<limbs;++k) {auto *p=b.CreatePHI(b.getInt64Ty(),2);p->addIncoming(b.getInt64(0),pre);acc.push_back(p);}
    auto bit=[&](unsigned arg,Value *i) {auto *word=b.CreateUDiv(i,b.getInt64(64));Value *v=b.getInt64(0);for(unsigned k=0;k<limbs;++k)v=b.CreateSelect(b.CreateICmpEQ(word,b.getInt64(k)),words[arg][k],v);return b.CreateAnd(b.CreateLShr(v,b.CreateAnd(i,b.getInt64(63))),b.getInt64(1));};
    auto *one=bit(0,index);Value *nextCount=count,*target=index,*value=one;
    if(op=="ctpop")nextCount=b.CreateAdd(count,one);
    else if(op=="ctlz")nextCount=b.CreateSelect(b.CreateICmpNE(one,b.getInt64(0)),b.CreateSub(b.getInt64(n-1),index),count);
    else if(op=="cttz")nextCount=b.CreateSelect(b.CreateAnd(b.CreateICmpNE(one,b.getInt64(0)),b.CreateICmpEQ(count,b.getInt64(n))),index,count);
    else if(op=="bitreverse")target=b.CreateSub(b.getInt64(n-1),index);
    else if(op=="bswap")target=b.CreateAdd(b.CreateMul(b.CreateSub(b.getInt64(n/8-1),b.CreateUDiv(index,b.getInt64(8))),b.getInt64(8)),b.CreateAnd(index,b.getInt64(7)));
    else if(op=="pdep"||op=="pext") {auto *mask=bit(1,index);nextCount=b.CreateAdd(count,mask);if(op=="pdep")value=b.CreateAnd(bit(0,count),mask);else {target=count;value=b.CreateAnd(one,mask);}}
    SmallVector<Value *> nextAcc;
    for(unsigned k=0;k<limbs;++k) {
      Value *v;
      if(op=="clmul") {
        // Each set bit of b xors a shifted by the bit index into the accumulator.
        auto *enabled=bit(1,index);Value *shifted=b.getInt64(0);auto *word=b.CreateUDiv(index,b.getInt64(64)),*sh=b.CreateAnd(index,b.getInt64(63));
        for(unsigned j=0;j<limbs;++j) {
          shifted=b.CreateOr(shifted,b.CreateSelect(b.CreateICmpEQ(b.CreateAdd(word,b.getInt64(j)),b.getInt64(k)),b.CreateShl(words[0][j],sh),b.getInt64(0)));
          auto *hi=b.CreateLShr(words[0][j],b.CreateAnd(b.CreateSub(b.getInt64(64),sh),b.getInt64(63)));
          shifted=b.CreateOr(shifted,b.CreateSelect(b.CreateAnd(b.CreateICmpNE(sh,b.getInt64(0)),b.CreateICmpEQ(b.CreateAdd(word,b.getInt64(j+1)),b.getInt64(k))),hi,b.getInt64(0)));
        }
        v=b.CreateXor(acc[k],b.CreateSelect(b.CreateICmpNE(enabled,b.getInt64(0)),shifted,b.getInt64(0)));
      } else v=b.CreateOr(acc[k],b.CreateSelect(b.CreateICmpEQ(b.CreateUDiv(target,b.getInt64(64)),b.getInt64(k)),b.CreateShl(value,b.CreateAnd(target,b.getInt64(63))),b.getInt64(0)));
      nextAcc.push_back(v);acc[k]->addIncoming(v,loop);
    }
    auto *next=b.CreateAdd(index,b.getInt64(1));index->addIncoming(next,loop);count->addIncoming(nextCount,loop);b.CreateCondBr(b.CreateICmpULT(next,b.getInt64(n)),loop,done);b.SetInsertPoint(done);
    if(op=="ctpop"||op=="ctlz"||op=="cttz")result=b.CreateZExtOrTrunc(nextCount,t);
    else {result=zero;for(unsigned k=0;k<limbs;++k) {Value *e=b.CreateZExtOrTrunc(nextAcc[k],t);if(k)e=n22Packing(b.CreateShl(e,ConstantInt::get(t,64*k)));result=b.CreateOr(result,e);}}
  } else if(op=="fshl"||op=="fshr") {
    auto *shift=b.CreateURem(args[2],ConstantInt::get(t,n));auto *rev=b.CreateURem(b.CreateSub(ConstantInt::get(t,n),shift),ConstantInt::get(t,n));
    auto *lo=op=="fshl"?b.CreateShl(a,shift):b.CreateLShr(c,shift);auto *hi=op=="fshl"?b.CreateLShr(c,rev):b.CreateShl(a,rev);
    result=b.CreateOr(lo,b.CreateSelect(b.CreateICmpEQ(shift,zero),zero,hi));
  } else if(op=="sshl_sat"||op=="ushl_sat") {
    // N12 defines overshifts as zero; saturation detects any lost value/sign.
    auto *valid=b.CreateICmpULT(c,ConstantInt::get(t,n));auto *safe=b.CreateSelect(valid,c,zero);auto *v=b.CreateShl(a,safe);
    auto *back=sign?b.CreateAShr(v,safe):b.CreateLShr(v,safe);auto *bad=b.CreateOr(b.CreateICmpNE(back,a),b.CreateAnd(b.CreateNot(valid),b.CreateICmpNE(a,zero)));
    Value *bound=ConstantInt::get(t,APInt::getAllOnes(n));if(sign)bound=b.CreateSelect(b.CreateICmpSLT(a,zero),ConstantInt::get(t,APInt::getSignedMinValue(n)),ConstantInt::get(t,APInt::getSignedMaxValue(n)));
    result=b.CreateSelect(bad,bound,b.CreateSelect(valid,v,zero));
  } else {
    unsigned full=2*n;auto *tw=b.getIntNTy(full);auto ext=[&](Value *v){return sign?b.CreateSExt(v,tw):b.CreateZExt(v,tw);};Value *v;
    if(overflow || op.find("mul_fix")!=std::string::npos) {v=b.CreateMul(ext(a),ext(c));if(!overflow) {auto *scale=b.CreateZExtOrTrunc(f.getArg(wideArgs+(slot?1:0)),tw);v=sign?b.CreateAShr(v,scale):b.CreateLShr(v,scale);}}
    else {fault(b.CreateICmpEQ(c,zero));auto *scale=b.CreateZExtOrTrunc(f.getArg(wideArgs+(slot?1:0)),tw);auto *num=b.CreateShl(ext(a),scale);v=sign?b.CreateSDiv(num,ext(c)):b.CreateUDiv(num,ext(c));}
    result=b.CreateTrunc(v,t);flag=b.CreateICmpNE(v,ext(result));
    if(op.find("_sat")!=std::string::npos) {Value *bound=ConstantInt::get(t,APInt::getAllOnes(n));if(sign)bound=b.CreateSelect(b.CreateICmpSLT(v,ConstantInt::get(tw,0)),ConstantInt::get(t,APInt::getSignedMinValue(n)),ConstantInt::get(t,APInt::getSignedMaxValue(n)));result=b.CreateSelect(flag,bound,result);}
  }
  if(slot) {b.CreateStore(result,f.getArg(0))->setAlignment(Align(8));if(overflow)b.CreateRet(flag);else b.CreateRetVoid();}
  else if(overflow)b.CreateRet(b.CreateInsertValue(b.CreateInsertValue(Constant::getNullValue(f.getReturnType()),result,0),flag,1));
  else b.CreateRet(result);
  if(slot || n<=128)normaliseWideFP(f);
}
}
