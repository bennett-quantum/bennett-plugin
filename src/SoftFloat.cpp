#include "Bennett.h"
#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/NoFolder.h"
#include "llvm/IR/IntrinsicInst.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IRReader/IRReader.h"
#include "llvm/Linker/Linker.h"
#include "llvm/Support/SourceMgr.h"
#include "llvm/Support/MemoryBuffer.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/TargetParser/Triple.h"
#include <cstdlib>
using namespace llvm;
namespace bennett {
static std::string format(Type *t) {
  if(t->isHalfTy())return "f16";
  if(t->isBFloatTy())return "bf16";
  if(t->isFloatTy())return "f32";
  if(t->isDoubleTy())return "f64";
  if(t->isX86_FP80Ty())return "f80";
  if(t->isFP128Ty())return "f128";
  if(t->isPPC_FP128Ty())return "ppcf128";
  fail("input","§13.1 expected scalar floating format");
}
static Type *carrier(Type *t) {return IntegerType::get(t->getContext(),t->getPrimitiveSizeInBits());}
// No numerical implementation lives here. This is the published bitcode edge.
void linkArith(Module &m) {
  auto *path=std::getenv("BENNETT_ARITH_BITCODE");
  if(!path || !*path)return; // Require individual definitions at production closure collection.
  auto bytes=MemoryBuffer::getFile(path);
  if(!bytes)fail("unavailable","§13.1 BENNETT_ARITH_BITCODE could not be read: "+std::string(path));
  auto hash=toHex(SHA256::hash(arrayRefFromStringRef((*bytes)->getBuffer())),true);
  if(auto *prior=m.getModuleFlag("bennett.arith.bitcode.sha256")) {
    if(auto *id=dyn_cast<MDString>(prior);id && id->getString()==hash)return;
    fail("input","§13.1 BENNETT_ARITH_BITCODE changed across comparison links");
  }
  SMDiagnostic error;auto lib=parseIRFile(path,error,m.getContext());
  if(!lib) {error.print("BENNETT_ARITH_BITCODE",errs());fail("unavailable","§13.1 BENNETT_ARITH_BITCODE could not be read");}
  if(!lib->getDataLayoutStr().empty() && !m.getDataLayoutStr().empty() && lib->getDataLayout()!=m.getDataLayout())
    fail("input","§13.1 BENNETT_ARITH_BITCODE DataLayout mismatch");
  if(Linker::linkModules(m,std::move(lib)))fail("input","§13.1 BENNETT_ARITH_BITCODE link failed");
  m.addModuleFlag(Module::Error,"bennett.arith.bitcode.sha256",MDString::get(m.getContext(),hash));
}
void requireSoftFloat(Function &f) {
  if(f.isDeclaration() && f.getName().starts_with("__bennett_sf_"))
    fail("unavailable", "§13.1 missing entry point "+f.getName().str()+"; The entry points are defined by bennett-arith and are part of its bitcode the driver links; supply BENNETT_ARITH_BITCODE", &f);
}
void normaliseFP(Function &f) {
  auto &m=*f.getParent();auto &ctx=f.getContext();
  // N16 is unfused, before N32. No target-dependent contract intrinsic remains.
  SmallVector<Instruction *> work;
  for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work)if(auto *c=dyn_cast<IntrinsicInst>(i))
    if(Intrinsic::getBaseName(c->getIntrinsicID())=="llvm.fmuladd" || Intrinsic::getBaseName(c->getIntrinsicID())=="llvm.experimental.constrained.fmuladd") {
      IRBuilder<NoFolder> b(c);auto r=c->getName().str();c->setName("");
      Value *mul,*add;
      if(c->arg_size()==5) {
        SmallVector<Type *> types={c->getType(),c->getType(),c->getArgOperand(3)->getType(),c->getArgOperand(4)->getType()};
        auto *sig=FunctionType::get(c->getType(),types,false);auto name=c->getCalledFunction()->getName().str();
        auto position=name.find("fmuladd");auto mn=name;mn.replace(position,7,"fmul");name.replace(position,7,"fadd");
        mul=b.CreateCall(m.getOrInsertFunction(mn,sig),{c->getArgOperand(0),c->getArgOperand(1),c->getArgOperand(3),c->getArgOperand(4)},"nz.m."+r);
        add=b.CreateCall(m.getOrInsertFunction(name,sig),{mul,c->getArgOperand(2),c->getArgOperand(3),c->getArgOperand(4)},r);
      } else {mul=b.CreateFMul(c->getArgOperand(0),c->getArgOperand(1),"nz.m."+r);add=b.CreateFAdd(mul,c->getArgOperand(2),r);}
      c->replaceAllUsesWith(add);c->eraseFromParent();
    }
  work.clear();for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work)if(auto *c=dyn_cast<IntrinsicInst>(i)) {
    auto op=Intrinsic::getBaseName(c->getIntrinsicID());
    bool env=op.ends_with(".fpenv"),mode=op.ends_with(".fpmode"),round=op.ends_with(".rounding");
    if(!env && !mode && !round)continue;
    bool read=op.starts_with("llvm.get."),reset=op.starts_with("llvm.reset.");
    if(!read && !reset && !op.starts_with("llvm.set."))continue;
    IRBuilder<NoFolder> b(c);auto r=c->getName().str();c->setName("");
    auto *ty=StructType::get(ctx,{b.getInt32Ty(),b.getInt32Ty()});auto *state=m.getGlobalVariable("__bennett_rt_fenv");
    if(!state)state=new GlobalVariable(m,ty,false,GlobalValue::ExternalLinkage,nullptr,"__bennett_rt_fenv");
    auto *rp=b.CreateStructGEP(ty,state,0);auto *fp=b.CreateStructGEP(ty,state,1);
    if(read) {
      Value *value=b.CreateLoad(b.getInt32Ty(),rp,"nz.round."+r);
      if(env) {value=b.CreateZExt(value,b.getInt64Ty());auto *flags=b.CreateZExt(b.CreateLoad(b.getInt32Ty(),fp),b.getInt64Ty());value=b.CreateOr(value,b.CreateShl(flags,b.getInt64(32)));}
      value=b.CreateZExtOrTrunc(value,c->getType(),r);c->replaceAllUsesWith(value);
    } else {
      Value *value=reset?static_cast<Value *>(b.getInt64(0)):c->getArgOperand(0);
      b.CreateStore(b.CreateZExtOrTrunc(value,b.getInt32Ty()),rp);
      if(env) {value=b.CreateZExtOrTrunc(value,b.getInt64Ty());value=b.CreateLShr(value,b.getInt64(32));b.CreateStore(b.CreateTrunc(value,b.getInt32Ty()),fp);}
    }
    c->eraseFromParent();
  }
  auto native=[&](Type *t) {Triple triple(m.getTargetTriple());return t->isDoubleTy() || t->isFloatTy() || (triple.getArch()==Triple::x86_64?t->isX86_FP80Ty():t->isFP128Ty());};
  // N33 runs module-wide before N32, including declaration order.
  work.clear();for(auto &i:instructions(f))work.push_back(&i);
  const std::set<std::string> libm={"sin","cos","tan","asin","acos","atan","atan2","sinh","cosh","tanh","exp","exp2","exp10","log","log2","log10","pow","powi","sincos","sincospi","modf"};
  auto rewrite=[&](Instruction *i,std::string op,SmallVector<Value *> inputs,bool transcendental,bool constrained=false,int rounding=0,bool ignoreExceptions=false) {
    IRBuilder<NoFolder> b(i);std::string r=i->getName().str();i->setName("");
    Type *out=i->getType(),*fp=nullptr;
    for(auto *v:inputs)if(v->getType()->isFloatingPointTy()) {fp=v->getType();break;}
    if(!fp && out->isFloatingPointTy())fp=out;
    if(!fp)fail("input","§13 soft-float operand format",i);
    bool pair=out->isStructTy();
    bool fromInt=op=="sitofp"||op=="uitofp";
    bool toInt=op=="fptosi"||op=="fptoui"||op=="lround"||op=="llround"||op=="lrint"||op=="llrint";
    bool conversion=op=="fpext"||op=="fptrunc";
    std::string name="__bennett_sf_"+op+"_"+format(fp);
    if(conversion) name+="_"+format(out);
    if(transcendental && op=="powi")name+="_i"+std::to_string(inputs[1]->getType()->getIntegerBitWidth());
    bool wide=(fromInt && inputs[0]->getType()->getIntegerBitWidth()>128) || (toInt && out->getIntegerBitWidth()>128);
    if(wide)name+="_wide";
    if(constrained)name+="_rm";
    SmallVector<Value *> args;
    for(unsigned k=0;k<inputs.size();++k) {
      auto *v=inputs[k];if(v->getType()->isFloatingPointTy())v=b.CreateBitCast(v,carrier(v->getType()),"nz."+std::to_string(k)+"."+r);
      args.push_back(v);
    }
    Value *slot=nullptr;
    unsigned bits=toInt?out->getIntegerBitWidth():fromInt?inputs[0]->getType()->getIntegerBitWidth():0;
    if(fromInt && !wide && bits<128)args[0]=op=="sitofp"?b.CreateSExt(args[0],b.getInt128Ty(),"nz.x."+r):b.CreateZExt(args[0],b.getInt128Ty(),"nz.x."+r);
    if(wide) {
      auto push=m.getOrInsertFunction("__bennett_rt_ss_push",b.getPtrTy(),b.getInt64Ty(),b.getInt64Ty());
      slot=b.CreateCall(push,{b.getInt64(8*((bits+63)/64)),b.getInt64(8)},toInt?"nz.d."+r:"nz.s."+r);
      if(fromInt) {
        for(unsigned k=0;k<(bits+63)/64;++k) {
          auto *p=b.CreateGEP(b.getInt64Ty(),slot,b.getInt64(k),"nz.s"+std::to_string(k)+"."+r);
          Value *v=inputs[0];if(k)v=b.CreateLShr(v,ConstantInt::get(v->getType(),64*k));
          v=b.CreateTrunc(v,IntegerType::get(ctx,std::min(64u,bits-64*k)));
          b.CreateStore(v,p)->setAlignment(Align(8));
        }
        args={slot,b.getInt32(bits)};
      } else {args.insert(args.begin(),slot);args.push_back(b.getInt32(bits));}
    } else if(toInt)args.push_back(b.getInt32(bits));
    Value *round=nullptr;
    if(constrained) {
      if(rounding>=0)round=b.getInt32(rounding);
      else {
        auto *ty=StructType::get(ctx,{b.getInt32Ty(),b.getInt32Ty()});
        auto *env=m.getGlobalVariable("__bennett_rt_fenv");
        if(!env)env=new GlobalVariable(m,ty,false,GlobalValue::ExternalLinkage,nullptr,"__bennett_rt_fenv");
        round=b.CreateLoad(b.getInt32Ty(),b.CreateStructGEP(ty,env,0),"nz.round."+r);
      }
      args.push_back(round);
    }
    Type *ret=toInt?(wide?b.getVoidTy():b.getInt128Ty()):out->isFloatingPointTy()?carrier(out):out;
    if(pair) {SmallVector<Type *> fields;for(Type *t:cast<StructType>(out)->elements())fields.push_back(t->isFloatingPointTy()?carrier(t):t);ret=StructType::get(ctx,fields);}
    SmallVector<Type *> types;for(auto *v:args)types.push_back(v->getType());
    auto *signature=FunctionType::get(ret,types,false);
    if(auto *existing=m.getFunction(name);existing && existing->getFunctionType()!=signature)
      fail("input","§13.1 incompatible linked entry point "+name,existing);
    auto target=m.getOrInsertFunction(name,signature);
    Value *savedFlags=nullptr,*flagAddress=nullptr;
    if(constrained && ignoreExceptions) {
      auto *ty=StructType::get(ctx,{b.getInt32Ty(),b.getInt32Ty()});auto *env=m.getGlobalVariable("__bennett_rt_fenv");
      if(!env)env=new GlobalVariable(m,ty,false,GlobalValue::ExternalLinkage,nullptr,"__bennett_rt_fenv");
      flagAddress=b.CreateStructGEP(ty,env,1);savedFlags=b.CreateLoad(b.getInt32Ty(),flagAddress,"nz.flags."+r);
    }
    auto *call=b.CreateCall(target,args,ret->isVoidTy()?"":out==ret?r:"nz.i."+r);Value *value=call;
    if(savedFlags)b.CreateStore(savedFlags,flagAddress);
    if(wide && toInt) {
      value=Constant::getNullValue(out);
      for(unsigned k=0;k<(bits+63)/64;++k) {
        auto *p=b.CreateGEP(b.getInt64Ty(),slot,b.getInt64(k),"nz.rp"+std::to_string(k)+"."+r);
        auto *v=b.CreateLoad(IntegerType::get(ctx,std::min(64u,bits-64*k)),p,"nz.rm"+std::to_string(k)+"."+r);v->setAlignment(Align(8));
        Value *part=b.CreateZExt(v,out);if(k)part=b.CreateShl(part,ConstantInt::get(out,64*k));value=b.CreateOr(value,part);
      }
    }
    if(wide) {auto pop=m.getOrInsertFunction("__bennett_rt_ss_pop",b.getVoidTy(),b.getPtrTy());b.CreateCall(pop,{slot});}
    if(toInt && !wide && bits<128)value=b.CreateTrunc(call,out,r);
    else if(out->isFloatingPointTy())value=b.CreateBitCast(call,out,r);
    else if(pair) {
      Value *aggregate=Constant::getNullValue(out);
      for(unsigned j=0;j<cast<StructType>(out)->getNumElements();++j) {
        auto n=std::to_string(j);Value *part=b.CreateExtractValue(call,j,"nz.outbits"+n+"."+r);
        auto *t=cast<StructType>(out)->getElementType(j);
        if(t->isFloatingPointTy())part=b.CreateBitCast(part,t,"nz.outfp"+n+"."+r);
        aggregate=b.CreateInsertValue(aggregate,part,j,j+1==cast<StructType>(out)->getNumElements()?r:"nz.out"+n+"."+r);
      }
      value=aggregate;
    }
    i->replaceAllUsesWith(value);i->eraseFromParent();
  };
  for(auto *i:work)if(auto *c=dyn_cast<IntrinsicInst>(i)) {
    auto op=Intrinsic::getBaseName(c->getIntrinsicID()).drop_front(5).str();if(!libm.count(op))continue;
    SmallVector<Value *> args(c->args());auto *t=args[0]->getType();
    if(!t->isFloatingPointTy())continue;
    bool special=op=="powi"||op=="sincos"||op=="sincospi"||op=="modf";
    if(native(t) && !special) {
      auto name=op+(t->isDoubleTy()?"":t->isFloatTy()?"f":"l");auto target=m.getOrInsertFunction(name,c->getFunctionType());IRBuilder<NoFolder> b(c);
      auto *v=b.CreateCall(target,args);v->takeName(c);c->replaceAllUsesWith(v);c->eraseFromParent();
    } else rewrite(c,op,args,true);
  }
  work.clear();for(auto &i:instructions(f))work.push_back(&i);
  const std::set<std::string> sf={"sqrt","floor","ceil","trunc","round","roundeven","rint","nearbyint","canonicalize","minnum","maxnum","minimum","maximum","minimumnum","maximumnum","fma","is.fpclass","ldexp","frexp","lround","llround","lrint","llrint","fptosi.sat","fptoui.sat","fptrunc.round"};
  for(auto *i:work) {
    std::string op;SmallVector<Value *> args;
    if(auto *cmp=dyn_cast<FCmpInst>(i)) {args={cmp->getOperand(0),cmp->getOperand(1),ConstantInt::get(Type::getInt32Ty(ctx),cmp->getPredicate())};op="cmp";}
    else if(auto *c=dyn_cast<IntrinsicInst>(i)) {
      auto base=Intrinsic::getBaseName(c->getIntrinsicID()).drop_front(5);bool constrained=base.consume_front("experimental.constrained.");
      if(base=="convert.to.arbitrary.fp" || base=="convert.from.arbitrary.fp") {
        bool to=base=="convert.to.arbitrary.fp";std::string fmt;SmallVector<Value *> values;
        for(auto &arg:c->args())if(auto *meta=dyn_cast<MetadataAsValue>(arg.get())) {
          if(auto *name=dyn_cast<MDString>(meta->getMetadata());name && fmt.empty())fmt=name->getString().str();
        } else values.push_back(arg.get());
        if(fmt.empty())unimplemented("§13.1 arbitrary FP metadata format naming (requires the published arith entry-point schema)",2,c);
        rewrite(c,std::string(to?"convert_to_":"convert_from_")+fmt,values,false);continue;
      }
      if(base=="convert.to.fp16" || base=="convert.from.fp16") {
        IRBuilder<NoFolder> b(c);auto r=c->getName().str();c->setName("");bool to=base=="convert.to.fp16";
        auto *src=c->getArgOperand(0);Type *fp=to?src->getType():c->getType();
        Value *arg=to?b.CreateBitCast(src,carrier(fp),"nz.0."+r):src;
        auto name=to?"__bennett_sf_fptrunc_"+format(fp)+"_f16":"__bennett_sf_fpext_f16_"+format(fp);
        auto *ret=to?c->getType():carrier(fp);auto target=m.getOrInsertFunction(name,ret,arg->getType());
        auto *call=b.CreateCall(target,{arg},to?r:"nz.i."+r);Value *value=to?static_cast<Value *>(call):b.CreateBitCast(call,fp,r);
        c->replaceAllUsesWith(value);c->eraseFromParent();continue;
      }
      if(!constrained && !sf.count(base.str()))continue;
      args=SmallVector<Value *>(c->args());int rounding=0;bool ignore=false;
      if(constrained || base=="fptrunc.round") {
        SmallVector<Value *> values;
        for(auto *v:args)if(auto *meta=dyn_cast<MetadataAsValue>(v)) {
          if(auto *s=dyn_cast<MDString>(meta->getMetadata())) {
            auto mode=s->getString();ignore|=mode=="fpexcept.ignore";if(mode.starts_with("round."))rounding=mode=="round.downward"?1:mode=="round.upward"?2:mode=="round.towardzero"?3:mode=="round.tonearestaway"?4:mode=="round.dynamic"?-1:0;
            if((base=="fcmp"||base=="fcmps") && mode!="fpexcept.ignore") {
              auto pred=StringSwitch<int>(mode).Case("false",0).Case("oeq",1).Case("ogt",2).Case("oge",3).Case("olt",4).Case("ole",5).Case("one",6).Case("ord",7).Case("uno",8).Case("ueq",9).Case("ugt",10).Case("uge",11).Case("ult",12).Case("ule",13).Case("une",14).Case("true",15).Default(-1);
              if(pred>=0)values.push_back(ConstantInt::get(Type::getInt32Ty(ctx),pred));
            }
          }
        } else values.push_back(v);
        args=values;
      }
      op=base.str();if(op=="fcmp"||op=="fcmps")op="cmp";
      if(op=="fptosi.sat")op="fptosi";if(op=="fptoui.sat")op="fptoui";
      if(op=="is.fpclass")op="isfpclass";
      if(op=="fptrunc.round") {op="fptrunc";constrained=true;}
      if(op.size()>1 && op[0]=='f' && (op=="fadd"||op=="fsub"||op=="fmul"||op=="fdiv"||op=="frem"))op.erase(0,1);
      rewrite(i,op,args,false,constrained,rounding,ignore);continue;
    } else {
      switch(i->getOpcode()) {
      case Instruction::FAdd:op="add";break;case Instruction::FSub:op="sub";break;case Instruction::FMul:op="mul";break;case Instruction::FDiv:op="div";break;case Instruction::FRem:op="rem";break;
      case Instruction::SIToFP:op="sitofp";break;case Instruction::UIToFP:op="uitofp";break;case Instruction::FPToSI:op="fptosi";break;case Instruction::FPToUI:op="fptoui";break;case Instruction::FPExt:op="fpext";break;case Instruction::FPTrunc:op="fptrunc";break;default:continue;
      }
      for(auto &v:i->operands())args.push_back(v);
    }
    if(i->getType()->isVectorTy() || args[0]->getType()->isVectorTy())continue;
    rewrite(i,op,args,false);
  }
}
} // namespace bennett

namespace bennett {
// N22 rerun for the limb loads/stores exposed by §13.1 wide conversions.
// Decompose only transport/packing here; general wide arithmetic is N22's owner.
void normaliseWideFP(Function &f) {
  std::map<Value *,SmallVector<Value *>> parts;
  SmallVector<Instruction *> dead,work;
  for(auto &i:instructions(f))work.push_back(&i);
  auto wide=[](Type *t){return t->isIntegerTy() && t->getIntegerBitWidth()>128;};
  for(auto *i:work)if(auto *l=dyn_cast<LoadInst>(i);l && wide(l->getType())) {
    IRBuilder<NoFolder> b(l);auto r=l->getName().str();unsigned bits=l->getType()->getIntegerBitWidth();
    for(unsigned k=0;k<(bits+63)/64;++k) {
      auto *p=b.CreateGEP(b.getInt64Ty(),l->getPointerOperand(),b.getInt64(k),"nz.p"+std::to_string(k)+"."+r);
      auto *v=b.CreateLoad(IntegerType::get(f.getContext(),std::min(64u,bits-64*k)),p,"nz.m"+std::to_string(k)+"."+r);v->setAlignment(commonAlignment(l->getAlign(),8*k));parts[l].push_back(v);
    }
    dead.push_back(l);
  }
  // The canonical packing graph created above is temporary, never an ISA-wide operation.
  std::function<Value *(Value *,unsigned,IRBuilder<> &)> limb=[&](Value *v,unsigned k,IRBuilder<> &b)->Value * {
    unsigned bits=v->getType()->getIntegerBitWidth(),w=std::min(64u,bits-64*k);auto *ty=IntegerType::get(f.getContext(),w);
    if(parts.count(v))return parts[v][k];
    if(auto *c=dyn_cast<ConstantInt>(v))return ConstantInt::get(ty,c->getValue().lshr(64*k).trunc(w));
    if(auto *z=dyn_cast<ZExtInst>(v)) {
      auto *in=z->getOperand(0);auto n=in->getType()->getIntegerBitWidth();
      if(64*k>=n)return ConstantInt::get(ty,0);
      auto *value=n>128?limb(in,k,b):in;
      if(n<=128 && k)value=b.CreateLShr(value,ConstantInt::get(value->getType(),64*k));
      return b.CreateZExtOrTrunc(value,ty);
    }
    if(auto *op=dyn_cast<BinaryOperator>(v)) {
      if(op->getOpcode()==Instruction::Or) {
        auto *x=limb(op->getOperand(0),k,b),*y=limb(op->getOperand(1),k,b);
        if(auto *c=dyn_cast<ConstantInt>(x);c && c->isZero())return y;
        if(auto *c=dyn_cast<ConstantInt>(y);c && c->isZero())return x;
        return b.CreateOr(x,y);
      }
      if((op->getOpcode()==Instruction::Shl || op->getOpcode()==Instruction::LShr) && isa<ConstantInt>(op->getOperand(1))) {
        unsigned shift=cast<ConstantInt>(op->getOperand(1))->getLimitedValue();
        if(shift%64==0) {
          int index=op->getOpcode()==Instruction::Shl?int(k)-int(shift/64):int(k)+int(shift/64);
          if(index<0 || unsigned(index)*64>=bits)return ConstantInt::get(ty,0);
          return b.CreateZExtOrTrunc(limb(op->getOperand(0),index,b),ty);
        }
      }
    }
    unimplemented("§12 N22 general wide limb operation",2,dyn_cast<Instruction>(v));
  };
  for(auto *i:work)if(auto *t=dyn_cast<TruncInst>(i);t && wide(t->getOperand(0)->getType()) && t->getType()->getIntegerBitWidth()<=64) {
    IRBuilder<> b(t);auto *v=limb(t->getOperand(0),0,b);v=b.CreateTruncOrBitCast(v,t->getType());t->replaceAllUsesWith(v);dead.push_back(t);
  }
  unsigned ordinal=0;
  for(auto *i:work)if(auto *s=dyn_cast<StoreInst>(i);s && wide(s->getValueOperand()->getType())) {
    IRBuilder<> b(s);auto r=f.getName().str()+"."+std::to_string(ordinal++);auto *v=s->getValueOperand();unsigned bits=v->getType()->getIntegerBitWidth();
    for(unsigned k=0;k<(bits+63)/64;++k) {
      auto *value=limb(v,k,b);auto *p=b.CreateGEP(b.getInt64Ty(),s->getPointerOperand(),b.getInt64(k),"nz.q"+std::to_string(k)+"."+r);
      b.CreateStore(value,p)->setAlignment(commonAlignment(s->getAlign(),8*k));
    }
    s->eraseFromParent();
  }
  // Remove the now-unused wide reconstruction, including its narrow extensions.
  bool more=true;while(more) {more=false;SmallVector<Instruction *> erase;
    for(auto &i:instructions(f))if(i.use_empty() && !i.isTerminator() && (isa<CastInst>(i)||isa<BinaryOperator>(i)|| (isa<LoadInst>(i) && parts.count(&i))))erase.push_back(&i);
    // Only temporary wide packing and its own input casts; leave unrelated dead source rows alone.
    for(auto *i:erase)if(wide(i->getType()) || (isa<TruncInst>(i) && wide(i->getOperand(0)->getType()))) {i->eraseFromParent();more=true;}
  }
}
}

namespace bennett {
// §16 lowering of the bit-exact operations N32 explicitly retains. This is
// carrier manipulation, not arithmetic or a runtime numerical definition.
void materialiseFPBits(Function &f) {
  SmallVector<Instruction *> work;for(auto &i:instructions(f))work.push_back(&i);
  for(auto *i:work) {
    std::string op;
    if(i->getOpcode()==Instruction::FNeg)op="neg";
    if(auto *c=dyn_cast<IntrinsicInst>(i)) {
      auto name=Intrinsic::getBaseName(c->getIntrinsicID());
      if(name=="llvm.fabs")op="abs";if(name=="llvm.copysign")op="copysign";
    }
    if(op.empty() || !i->getType()->isFloatingPointTy())continue;
    IRBuilder<> b(i);auto *ty=cast<IntegerType>(carrier(i->getType()));unsigned bits=ty->getBitWidth();
    // PPCDoubleDouble's high double is in low 64 bits of the APFloat carrier.
    unsigned sign=i->getType()->isPPC_FP128Ty()?63:bits-1;
    auto mask=APInt::getOneBitSet(bits,sign);
    auto toggle=mask;if(i->getType()->isPPC_FP128Ty())toggle.setBit(127);auto r=i->getName().str();i->setName("");
    Value *input=isa<IntrinsicInst>(i)?cast<CallBase>(i)->getArgOperand(0):i->getOperand(0);
    auto *value=b.CreateBitCast(input,ty);Value *out;
    if(op=="neg")out=b.CreateXor(value,ConstantInt::get(ty,toggle));
    else {
      if(i->getType()->isPPC_FP128Ty()) {
        auto *negative=b.CreateICmpNE(b.CreateAnd(value,ConstantInt::get(ty,mask)),ConstantInt::get(ty,0));
        out=b.CreateSelect(negative,b.CreateXor(value,ConstantInt::get(ty,toggle)),value);
      } else out=b.CreateAnd(value,ConstantInt::get(ty,~mask));
      if(op=="copysign") {
        auto *other=b.CreateBitCast(cast<CallBase>(i)->getArgOperand(1),ty);
        if(i->getType()->isPPC_FP128Ty()) {
          auto *negative=b.CreateICmpNE(b.CreateAnd(other,ConstantInt::get(ty,mask)),ConstantInt::get(ty,0));
          out=b.CreateSelect(negative,b.CreateXor(out,ConstantInt::get(ty,toggle)),out);
        } else out=b.CreateOr(out,b.CreateAnd(other,ConstantInt::get(ty,mask)));
      }
    }
    out=b.CreateBitCast(out,i->getType(),r);i->replaceAllUsesWith(out);i->eraseFromParent();
  }
}
}
