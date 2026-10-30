#include "Bennett.h"
#include "llvm/Config/llvm-config.h"
#include "llvm/IR/InstIterator.h"
#include "llvm/IR/Operator.h"
#include "llvm/Support/FileSystem.h"
#include "llvm/Support/Path.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include <regex>
using namespace llvm;
namespace bennett {
static std::string sha(StringRef s){return toHex(SHA256::hash(arrayRefFromStringRef(s)),true);}
static std::string number(const APInt &n){SmallString<48> s;n.toString(s,10,false);return s.str().str();}
static std::string join(const std::vector<std::string> &v,StringRef sep=", "){
 std::string s;for(auto &x:v){if(!s.empty())s+=sep;s+=x;}return s;
}
struct Scalar {
 Module &m;Function &f;
 std::map<const Value *,std::string> names;
 std::vector<std::string> regs,lines;
 unsigned constants=0,temps=0;
 unsigned width(Type *t){
  if(t->isIntegerTy()&&t->getIntegerBitWidth()<=128)return t->getIntegerBitWidth();
  if(t->isPointerTy())return m.getDataLayout().getPointerTypeSizeInBits(t);
  if(t->isVoidTy())return 1;
  if(t->isFloatingPointTy())unimplemented("§13 soft-float",2,&f);
  unimplemented("§12.6/§12.7 vector/aggregate/wide scalar",2,&f);
 }
 void dest(std::string n,unsigned w){regs.push_back(n+":reg["+std::to_string(w)+"]");}
 std::string constant(APInt n){std::string s="c"+std::to_string(constants++);dest(s,n.getBitWidth());lines.push_back(s+" = lift.const.i"+std::to_string(n.getBitWidth())+" "+number(n));return s;}
 std::string temp(unsigned w,std::string row){std::string s="t"+std::to_string(temps++);dest(s,w);lines.push_back(s+" = "+row);return s;}
 std::string value(Value *v){
  if(isa<UndefValue>(v)||isa<PoisonValue>(v)||isa<ConstantPointerNull>(v))return constant(APInt(width(v->getType()),0));
  if(auto *c=dyn_cast<ConstantInt>(v))return constant(c->getValue());
  if(auto *c=dyn_cast<ConstantExpr>(v)) {
   if(c->getOpcode()==Instruction::GetElementPtr)return gep(cast<GEPOperator>(c),"");
   unimplemented("§16.4 constant expression",2,v);
  }
  if(names.count(v))return names[v];
  unimplemented("§16.4 non-scalar operand",2,v);
 }
 std::string gep(GEPOperator *g,std::string output) {
  unsigned p=width(g->getType()),i=m.getDataLayout().getIndexTypeSizeInBits(g->getType());
  if(i>128||p>128)unimplemented("§12.7 wide pointer limbs",2,&f);
  std::string base=value(g->getPointerOperand()),acc=base;
  if(i<p)acc=temp(i,"lift.trunc.i"+std::to_string(i)+" "+base);
  // collectOffset preserves insertion order of dynamic indices.
  #if LLVM_VERSION_MAJOR >= 23
  SmallMapVector<Value *,APInt,4> vars;
#else
  MapVector<Value *,APInt> vars;
#endif
APInt off(i,0);
  if(!g->collectOffset(m.getDataLayout(),i,vars,off))unimplemented("§16.4 GEP",2,&f);
  std::vector<std::pair<Value *,APInt>> dynamic;
  for(auto &e:vars)dynamic.push_back(e);
  for(unsigned k=0;k<dynamic.size();++k){auto &e=dynamic[k];std::string idx=value(e.first);unsigned w=width(e.first->getType());
   if(w!=i)idx=temp(i,std::string(w<i?"lift.sext.i":"lift.trunc.i")+std::to_string(i)+" "+idx);
   if(e.second!=1){auto c=constant(e.second);idx=temp(i,"lift.mul "+idx+" "+c);}
   bool last=k+1==dynamic.size()&&off.isZero()&&i==p;
   if(last&&!output.empty()){dest(output,p);lines.push_back(output+" = lift.add "+acc+" "+idx);acc=output;}
   else acc=temp(i,"lift.add "+acc+" "+idx);
  }
  if(!off.isZero()){auto c=constant(off);if(i==p&&!output.empty()){dest(output,p);lines.push_back(output+" = lift.add "+acc+" "+c);acc=output;}else acc=temp(i,"lift.add "+acc+" "+c);}
  if(i<p){auto lo=temp(p,"lift.zext.i"+std::to_string(p)+" "+acc);auto c=constant(APInt::getHighBitsSet(p,p-i));auto hi=temp(p,"lift.and "+base+" "+c);
   if(output.empty())return temp(p,"lift.or "+hi+" "+lo);
   dest(output,p);lines.push_back(output+" = lift.or "+hi+" "+lo);return output;
  }
  if(acc==base&&!output.empty()){dest(output,p);lines.push_back(output+" = lift.mov "+base);return output;}
  return acc;
 }
 std::string body(){
  unsigned k=0;for(Argument &a:f.args())names[&a]="a"+std::to_string(k++);
  k=0;for(Instruction &i:instructions(f))if(!i.getType()->isVoidTy())names[&i]="v"+std::to_string(k++);
  if(f.size()!=1)unimplemented("§16.4 branches/phi/switch",2,&f);
  for(Instruction &i:instructions(f)) {
   if(auto *g=dyn_cast<GetElementPtrInst>(&i)){gep(cast<GEPOperator>(g),names[&i]);continue;}
   if(auto *r=dyn_cast<ReturnInst>(&i)){auto v=r->getReturnValue()?value(r->getReturnValue()):"r";lines.push_back("lift.ret "+v);continue;}
   if(isa<UnreachableInst>(i)){lines.push_back("fault 4");continue;}
   if(auto *call=dyn_cast<CallBase>(&i)) {
    if(auto *g=call->getCalledFunction();g&&g->getName()=="__bennett_nz_fault") {
     auto *c=dyn_cast<ConstantInt>(call->getArgOperand(0));if(!c)unimplemented("§12.3 nonliteral fault",2,call);
     lines.push_back("fault "+number(c->getValue()));break;
    }
    unimplemented("§14 calls",2,call);
   }
   if(isa<LoadInst>(i)||isa<StoreInst>(i)||isa<AllocaInst>(i))unimplemented("§17.1/§17.3 memory",2,&i);
   if(i.getType()->isFPOrFPVectorTy())unimplemented("§13 soft-float",2,&i);
   std::string row;
   if(auto *c=dyn_cast<ICmpInst>(&i)) {
    auto a=value(c->getOperand(0)),b=value(c->getOperand(1));auto pred=c->getPredicate();
    if(pred==CmpInst::ICMP_UGT||pred==CmpInst::ICMP_UGE||pred==CmpInst::ICMP_SGT||pred==CmpInst::ICMP_SGE){pred=CmpInst::getSwappedPredicate(pred);std::swap(a,b);}
    row="lift.icmp."+CmpInst::getPredicateName(pred).str()+" "+a+" "+b;
   }else if(auto *b=dyn_cast<BinaryOperator>(&i)) {
    auto a=value(b->getOperand(0)),c=value(b->getOperand(1));
    // ISA shifts define >=W as zero; the materialised scalar semantics agrees.
    row="lift."+std::string(b->getOpcodeName())+" "+a+" "+c;
   }else if(auto *s=dyn_cast<SelectInst>(&i)) {
    auto c=value(s->getCondition()),a=value(s->getTrueValue()),b=value(s->getFalseValue());row="lift.select "+c+" "+a+" "+b;
   }else if(auto *c=dyn_cast<CastInst>(&i)) {
    auto a=value(c->getOperand(0));unsigned from=width(c->getOperand(0)->getType()),to=width(c->getType());
    std::string op=c->getOpcodeName();
    if(op=="ptrtoint"||op=="inttoptr"||op=="addrspacecast"||op=="bitcast")op=from==to?"mov":from<to?"zext":"trunc";
    row="lift."+op+(op=="mov"?"":".i"+std::to_string(to))+" "+a;
   }else if(isa<FreezeInst>(i))row="lift.mov "+value(i.getOperand(0));
   else unimplemented("§16.4 scalar row",2,&i);
   dest(names[&i],width(i.getType()));lines.push_back(names[&i]+" = "+row);
  }
  std::vector<std::string> params;for(Argument &a:f.args())params.push_back(names[&a]+":reg["+std::to_string(width(a.getType()))+"]");
  std::string b="lproc @L1 ("+join(params)+") (r:reg["+std::to_string(width(f.getReturnType()))+"]) () () ()\n";
  if(!regs.empty())b+="regs { "+join(regs)+" }\n";
  b+="^b0():\n"+join(lines,"\n");return b;
 }
};
void lowerScalar(Module &m,Function &f,StringRef desc,StringRef out,unsigned stackCells) {
 Scalar s{m,f};unsigned ret=s.width(f.getReturnType());
 std::string d=desc.str();auto semi=d.find(';');std::string bindings=d.substr(0,semi);
 std::string target=semi==std::string::npos?"":d.substr(semi+1);
 bool discard=d=="tgt=null"||target=="tgt=null";unsigned tgt=ret;
 if(StringRef(target).starts_with("tgt=")) {auto v=StringRef(target).drop_front(4);if(!discard&&v.getAsInteger(10,tgt))fail("shape","invalid target width");}
 if(tgt==0||tgt>128)unimplemented("§8.6 wide outputs",2,&f);
 std::regex pat(R"((IN|ARG)\((\d+)(?:,(zext|sext))?\))");std::sregex_iterator it(bindings.begin(),bindings.end(),pat),end;
 std::vector<std::string> ins,args,invoke,insWidths,paramWidths,argTypes,wrapperRegs,wrapperRows;
 unsigned idx=0,inCount=0,argCount=0;
 std::string reconstructed;
 for(;it!=end;++it){if(!reconstructed.empty())reconstructed+=",";reconstructed+=it->str();
  if(idx>=f.arg_size())fail("shape","too many scalar bindings");
  unsigned w=std::stoul((*it)[2]),param=s.width(f.getArg(idx)->getType());paramWidths.push_back(std::to_string(param));
  if((*it)[1]=="IN") {
   if(w>param||!w)fail("shape","invalid IN width");std::string n="x"+std::to_string(inCount++);
   ins.push_back(n+":wire["+std::to_string(w)+"] in");insWidths.push_back(std::to_string(w));
   if(w<param){auto loc="w"+std::to_string(idx);wrapperRegs.push_back(loc+":reg["+std::to_string(param)+"]");wrapperRows.push_back(loc+" = lift."+((*it)[3]=="sext"?"sext":"zext")+".i"+std::to_string(param)+" "+n);n=loc;}
   invoke.push_back(n);
  }else {if(w!=param)fail("shape","ARG carrier width mismatch");std::string n="a"+std::to_string(argCount++);args.push_back(n+":i"+std::to_string(w));argTypes.push_back("\"i"+std::to_string(w)+"\"");invoke.push_back(n);}
  ++idx;
 }
 if(idx!=f.arg_size()||(!bindings.empty()&&reconstructed!=bindings&&bindings!="tgt=null"))unimplemented("§8 descriptor shape",2,&f);
 if(discard)tgt=1;
 std::string lproc=s.body();
 wrapperRegs.push_back("r:reg["+std::to_string(ret)+"]");wrapperRows.push_back("r = lift.call @L1 ("+join(invoke)+")");
 if(discard){wrapperRegs.push_back("p0:reg[1]");wrapperRows.push_back("p0 = lift.const.i1 0");wrapperRows.push_back("lift.retval p0");}
 else if(tgt!=ret)unimplemented("§8.2 target extension/truncation",2,&f);
 else wrapperRows.push_back("lift.retval r");
 std::string wrapper="oracle @ref ("+join(ins)+") (tgt:wire["+std::to_string(tgt)+"]) (fault:wire[4]) () ("+join(args)+")\nregs { "+join(wrapperRegs)+" }\n^entry():\n"+join(wrapperRows,"\n");
 std::string lsig="{\"abi\":\"0.8\",\"kind\":\"lproc\",\"params\":["+join(paramWidths,",")+"],\"result\":"+std::to_string(ret)+",\"tier\":\"q\"}";
 std::string osig="{\"abi\":\"0.8\",\"args\":["+join(argTypes,",")+"],\"fault\":4,\"in\":["+join(insWidths,",")+"],\"kind\":\"oracle\",\"mem\":[],\"tgt\":"+std::to_string(tgt)+",\"tier\":\"q\"}";
 unsigned sc=0;while((uint64_t(1)<<sc)<stackCells)++sc;
 unsigned pw=m.getDataLayout().getPointerSizeInBits();std::string prefix="isa=0.8\nptr_width="+std::to_string(pw)+"\n";
 std::string lh=sha(prefix+lsig+"\n"+lproc+"\n");
 std::string canonical=wrapper;auto pos=canonical.find("@L1",canonical.find('\n'));canonical.replace(pos,3,"@"+lh);
 std::string leaves="layout A_tab 0\nlayout H 12\nlayout S_cells "+std::to_string(sc)+"\nlayout heap_base 4096\nlayout heap_limit_max 0\nlayout null_size 4096\nlayout ptr_width "+std::to_string(pw)+"\n";
 std::string oh=sha(prefix+osig+"\n"+canonical+"\n"+leaves+lh+"\n");
 std::string symbols="{\"0\":{\"interface_hash\":\""+oh+"\",\"kind\":\"oracle\",\"name\":\"ref\",\"signature\":"+osig+"},\"1\":{\"interface_hash\":\""+lh+"\",\"kind\":\"lproc\",\"name\":\"L1\",\"signature\":"+lsig+"}}";
 std::string layout="{\"A_tab\":0,\"H\":12,\"S_cells\":"+std::to_string(sc)+",\"globals\":{},\"heap_base\":4096,\"heap_limit_max\":0,\"interface_regions\":{\"ref\":{}},\"null_size\":4096,\"ptr_width\":"+std::to_string(pw)+"}";
 if(auto ec=sys::fs::create_directories(out))fail("output",ec.message());
 SmallString<256> path(out);sys::path::append(path,"ref.bennett");std::error_code ec;raw_fd_ostream o(path,ec);if(ec)fail("output",ec.message());
 o<<"bennett-object isa=0.8 object=0.8 launch=0.8 sched=0.8 cert=0.8 coverage=0.8 target=0.8 ptr_width="<<pw<<"\n\nsection symbols\n"<<symbols<<"\n\nsection functions\n"<<wrapper<<"\n"<<lproc<<"\n\nsection layout\n"<<layout<<"\n";
 errs()<<"bennett: scalar reference object "<<path<<"\n";
}
}
