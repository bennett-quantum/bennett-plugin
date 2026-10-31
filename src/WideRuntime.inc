// Integer-only definitions of the §12.7 slot ABI. A published linked
// definition wins. Inputs are captured before stores, so slot aliasing is safe.
static Function *wideRuntime(Module &m,unsigned n,unsigned code) {
  auto &ctx=m.getContext();IRBuilder<> b(ctx);unsigned l=(n+63)/64,top=n-64*(l-1);
  auto name="__bennett_rt_i"+std::to_string(n)+"_"+Instruction::getOpcodeName(code);
  auto callee=m.getOrInsertFunction(name,b.getVoidTy(),b.getPtrTy(),b.getPtrTy(),b.getPtrTy());auto *f=cast<Function>(callee.getCallee());if(!f->isDeclaration())return f;
  auto *entry=BasicBlock::Create(ctx,"entry",f);b.SetInsertPoint(entry);
  SmallVector<Value *> a,c,result;
  auto pointer=[&](Value *p,unsigned k){return b.CreateGEP(b.getInt64Ty(),p,b.getInt64(k));};
  for(unsigned k=0;k<l;++k) {auto *ty=b.getIntNTy(k+1==l?top:64);a.push_back(b.CreateZExtOrTrunc(b.CreateLoad(ty,pointer(f->getArg(1),k)),b.getInt64Ty()));c.push_back(b.CreateZExtOrTrunc(b.CreateLoad(ty,pointer(f->getArg(2),k)),b.getInt64Ty()));}
  auto neg=[&](SmallVector<Value *> v) {Value *carry=b.getInt64(1);for(unsigned k=0;k<l;++k) {auto *x=b.CreateNot(v[k]);v[k]=b.CreateAdd(x,carry);carry=b.CreateZExt(b.CreateICmpULT(v[k],x),b.getInt64Ty());}if(top<64)v.back()=b.CreateAnd(v.back(),b.getInt64((uint64_t(1)<<top)-1));return v;};
  auto choose=[&](Value *cond,SmallVector<Value *> x,SmallVector<Value *> y) {for(unsigned k=0;k<l;++k)x[k]=b.CreateSelect(cond,x[k],y[k]);return x;};
  if(code==Instruction::Mul) {
    result.assign(l,b.getInt64(0));
    for(unsigned j=0;j<l;++j) {Value *carry=ConstantInt::get(b.getInt128Ty(),0);for(unsigned k=0;k+j<l;++k) {
      auto *product=b.CreateMul(b.CreateZExt(a[j],b.getInt128Ty()),b.CreateZExt(c[k],b.getInt128Ty()));
      auto *sum=b.CreateAdd(b.CreateAdd(product,carry),b.CreateZExt(result[j+k],b.getInt128Ty()));result[j+k]=b.CreateTrunc(sum,b.getInt64Ty());carry=b.CreateLShr(sum,ConstantInt::get(b.getInt128Ty(),64));
    }}
  } else if(code==Instruction::Shl || code==Instruction::LShr || code==Instruction::AShr) {
    Value *valid=b.CreateICmpULT(c[0],b.getInt64(n));for(unsigned k=1;k<l;++k)valid=b.CreateAnd(valid,b.CreateICmpEQ(c[k],b.getInt64(0)));
    auto *words=b.CreateUDiv(c[0],b.getInt64(64)),*bits=b.CreateAnd(c[0],b.getInt64(63));auto *rev=b.CreateAnd(b.CreateSub(b.getInt64(64),bits),b.getInt64(63));auto *zero=b.CreateICmpEQ(bits,b.getInt64(0));
    Value *fill=b.getInt64(0);
    if(code==Instruction::AShr) {a.back()=b.CreateSExtOrTrunc(b.CreateTrunc(a.back(),b.getIntNTy(top)),b.getInt64Ty());fill=b.CreateAShr(a.back(),b.getInt64(63));}
    auto lookup=[&](Value *idx) {Value *v=fill;for(unsigned j=0;j<l;++j)v=b.CreateSelect(b.CreateICmpEQ(idx,b.getInt64(j)),a[j],v);return v;};
    for(unsigned k=0;k<l;++k) {
      bool left=code==Instruction::Shl;auto *idx=left?b.CreateSub(b.getInt64(k),words):b.CreateAdd(b.getInt64(k),words);
      auto *v=lookup(idx),*other=lookup(left?b.CreateSub(idx,b.getInt64(1)):b.CreateAdd(idx,b.getInt64(1)));
      auto *lo=left?b.CreateShl(v,bits):b.CreateLShr(v,bits);auto *hi=left?b.CreateLShr(other,rev):b.CreateShl(other,rev);
      result.push_back(b.CreateSelect(valid,b.CreateOr(lo,b.CreateSelect(zero,b.getInt64(0),hi)),b.getInt64(0)));
    }
  } else {
    bool sign=code==Instruction::SDiv || code==Instruction::SRem,rem=code==Instruction::SRem || code==Instruction::URem;
    Value *zero=b.getTrue();for(auto *v:c)zero=b.CreateAnd(zero,b.CreateICmpEQ(v,b.getInt64(0)));
    auto fault=[&](Value *bad,unsigned value) {auto *fail=BasicBlock::Create(ctx,"fault",f),*ok=BasicBlock::Create(ctx,"ok",f);b.CreateCondBr(bad,fail,ok);b.SetInsertPoint(fail);b.CreateCall(m.getOrInsertFunction("__bennett_nz_fault",b.getVoidTy(),b.getInt64Ty()),{b.getInt64(value)});b.CreateUnreachable();b.SetInsertPoint(ok);};
    fault(zero,5);Value *sa=b.getFalse(),*sc=b.getFalse();
    if(sign) {
      sa=b.CreateICmpNE(b.CreateAnd(a.back(),b.getInt64(uint64_t(1)<<(top-1))),b.getInt64(0));sc=b.CreateICmpNE(b.CreateAnd(c.back(),b.getInt64(uint64_t(1)<<(top-1))),b.getInt64(0));
      Value *min=b.CreateICmpEQ(a.back(),b.getInt64(uint64_t(1)<<(top-1))),*minus=b.getTrue();
      for(unsigned k=0;k<l;++k) {if(k+1<l)min=b.CreateAnd(min,b.CreateICmpEQ(a[k],b.getInt64(0)));minus=b.CreateAnd(minus,b.CreateICmpEQ(c[k],b.getInt64(k+1==l && top<64?(uint64_t(1)<<top)-1:UINT64_MAX)));}
      fault(b.CreateAnd(min,minus),6);a=choose(sa,neg(a),a);c=choose(sc,neg(c),c);
    }
    auto *pre=b.GetInsertBlock(),*loop=BasicBlock::Create(ctx,"bit",f),*done=BasicBlock::Create(ctx,"done",f);b.CreateBr(loop);b.SetInsertPoint(loop);
    auto *index=b.CreatePHI(b.getInt64Ty(),2);index->addIncoming(b.getInt64(n),pre);SmallVector<PHINode *> rs,qs;
    for(unsigned k=0;k<l;++k) {auto *r=b.CreatePHI(b.getInt64Ty(),2),*q=b.CreatePHI(b.getInt64Ty(),2);r->addIncoming(b.getInt64(0),pre);q->addIncoming(b.getInt64(0),pre);rs.push_back(r);qs.push_back(q);}
    auto *next=b.CreateSub(index,b.getInt64(1)),*word=b.CreateUDiv(next,b.getInt64(64)),*bit=b.CreateAnd(next,b.getInt64(63));Value *input=b.getInt64(0);
    for(unsigned k=0;k<l;++k)input=b.CreateSelect(b.CreateICmpEQ(word,b.getInt64(k)),a[k],input);
    Value *carry=b.CreateAnd(b.CreateLShr(input,bit),b.getInt64(1));SmallVector<Value *> shifted,diff;
    for(unsigned k=0;k<l;++k) {shifted.push_back(b.CreateOr(b.CreateShl(rs[k],b.getInt64(1)),carry));carry=b.CreateLShr(rs[k],b.getInt64(63));}
    Value *ge=b.getTrue();for(unsigned k=0;k<l;++k)ge=b.CreateSelect(b.CreateICmpEQ(shifted[k],c[k]),ge,b.CreateICmpUGT(shifted[k],c[k]));ge=b.CreateOr(ge,b.CreateICmpNE(carry,b.getInt64(0)));
    Value *borrow=b.getInt64(0);
    for(unsigned k=0;k<l;++k) {auto *t=b.CreateSub(shifted[k],c[k]);diff.push_back(b.CreateSub(t,borrow));borrow=b.CreateZExt(b.CreateOr(b.CreateICmpULT(shifted[k],c[k]),b.CreateICmpULT(t,borrow)),b.getInt64Ty());}
    SmallVector<Value *> rr,qq;
    for(unsigned k=0;k<l;++k) {auto *r=b.CreateSelect(ge,diff[k],shifted[k]);auto *q=b.CreateOr(qs[k],b.CreateSelect(b.CreateAnd(ge,b.CreateICmpEQ(word,b.getInt64(k))),b.CreateShl(b.getInt64(1),bit),b.getInt64(0)));rs[k]->addIncoming(r,loop);qs[k]->addIncoming(q,loop);rr.push_back(r);qq.push_back(q);}
    b.CreateCondBr(b.CreateICmpNE(next,b.getInt64(0)),loop,done);index->addIncoming(next,loop);b.SetInsertPoint(done);result=rem?rr:qq;if(sign)result=choose(rem?sa:b.CreateXor(sa,sc),neg(result),result);
  }
  for(unsigned k=0;k<l;++k)b.CreateStore(b.CreateTruncOrBitCast(result[k],b.getIntNTy(k+1==l?top:64)),pointer(f->getArg(0),k))->setAlignment(Align(8));b.CreateRetVoid();return f;
}
